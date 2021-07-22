
import time
import urwid  # type: ignore
import logging
import humanize  # type: ignore

from typing import Dict, List, Any

from .common import (
    CmonComponent,
    CmonTable,
    DataTable,
    Icon,
    SingleStat,
    MyListBox,
    BarChart,
    HStackBar,
)

from ..ceph import (
    get_inventory,
    get_capacity_info,
    get_health,
    get_rbd_performance,
    get_pg_summary,
    get_pool_summary,
    get_rgw_performance,
    get_total_throughput,
    get_total_iops,
    CategoryTotal
)

from ..http_api import (
    get_prometheus_data,
    get_prometheus_alerts,
)

from ..utils import (
    age,
    GraphScale
)

logger = logging.getLogger(__name__)


class Inventory(CmonComponent):
    single_daemon_warning = ['mon', 'mgr', 'osd', 'mds']

    def _format_service(self, svc_type: str, svc_data: Dict[str, int]) -> urwid.Text:
        svc_width = 6
        up_width = 4
        down_width = 2
        if 'mirror' in svc_type:
            svc_width = 13
            up_width = 2
            down_width = 2
        svc = []
        svc.extend([('normal', f"{svc_type:<{svc_width}}"), " "])
        if svc_data['up'] + svc_data['down'] == 0:
            svc.append(f"{'-':>{up_width}}")
        else:
            up_attr = 'normal'
            if svc_type in Inventory.single_daemon_warning and svc_data['up'] == 1:
                up_attr = 'warning'
            svc.extend([(up_attr, f"{svc_data['up']:>{up_width}}"), ('ok', Icon.up)])
            if svc_data['down'] > 0:
                svc.extend(["  ", f"{svc_data['down']:>{down_width}}", " ", ('error', Icon.down)])
        return urwid.Text(svc)

    def _build_widget(self):
        # singleton for mon, mgr, mds, iscsi, osd should change attr for the daemon type to warning
        inventory = get_inventory(self.metrics)
        logger.debug(inventory)
        version_str = "unknown"
        versions = " + ".join(inventory['versions']['_all_'])
        if len(inventory['versions']['_all_']) == 1:
            version_str = versions
        else:
            version_str = f"Mixed ({versions})"

        return urwid.Padding(
            urwid.LineBox(
                urwid.Padding(
                    urwid.Pile([
                        urwid.Divider(),
                        urwid.Text(f"Ceph Version: {version_str}"),
                        urwid.Divider(),
                        self._format_service('mon', inventory['mon']),
                        urwid.Divider(),
                        self._format_service('mgr', inventory['mgr']),
                        urwid.Divider(),
                        self._format_service('osd', inventory['osd']),
                        urwid.Divider(),
                        self._format_service('mds', inventory['mds']),
                        urwid.Divider(),
                        self._format_service('rgw', inventory['rgw']),
                        urwid.Divider(),
                        self._format_service('iscsi', inventory['iscsi']),
                        urwid.Divider('_'),
                        urwid.Divider(),
                        self._format_service('rbd-mirror', inventory['rbd-mirror']),
                        urwid.Divider(),
                        self._format_service('cephfs-mirror', inventory['cephfs-mirror']),
                        urwid.Divider('_'),
                        urwid.Divider(),
                        urwid.Text(f"Hosts  {inventory['hosts']:>4}"),
                        urwid.Divider(),
                    ]),
                    left=2, right=2,
                ),
                title='Inventory'
            ),
            align='left',
            width=32
        )


class Capacity(CmonComponent):
    def _build_widget(self):

        capacity_info = get_capacity_info(self.metrics)
        percent_used = int((capacity_info['used_bytes'] / capacity_info['total_bytes']) * 100)
        free = capacity_info['total_bytes'] - capacity_info['used_bytes']
        sfx = ''
        if percent_used > 90:
            sfx = ' error'
        elif percent_used > 80:
            sfx = ' warning'

        complete = f"pg complete{sfx}"
        smooth = f"pg smooth{sfx}"

        return urwid.Padding(
            urwid.LineBox(
                urwid.Padding(
                    urwid.Pile([
                        urwid.Divider(),
                        urwid.Text(
                            f"Raw Capacity ({humanize.naturalsize(capacity_info['used_bytes'],binary=True).replace(' ','')} used/"
                            f"{humanize.naturalsize(free, binary=True)} free)"
                        ),
                        urwid.Columns([
                            (33, urwid.ProgressBar('pg normal', complete, percent_used, 100, smooth)),
                            urwid.Padding(
                                # urwid.Text(f"{humanize.naturalsize(capacity_info['total_bytes'], binary=True).replace(' ', '')}", align='right'),
                                urwid.Text(
                                    f"{humanize.naturalsize(capacity_info['total_bytes'], binary=True)}", align='right'),
                                left=1, right=1
                            ),
                        ]),
                        urwid.Divider(),
                        urwid.Text('Physical Devices'),
                        urwid.Text(f"{capacity_info['disks_total']}"),
                        urwid.Divider(),
                        urwid.Text('Compression Active'),
                        urwid.Text(f"{capacity_info['compressed_pools_count']} pool(s)"),
                        urwid.Divider(),
                        urwid.Text('Total Savings'),
                        urwid.Text(
                            f"{humanize.naturalsize(capacity_info['compression_savings_bytes'], binary=True)}"),
                        urwid.Divider()
                    ]),
                    left=1),
                title="Cluster Capacity",
            ),
            align='left'
        )


class Health(SingleStat):

    title = 'Health'

    def _format(self):
        health = get_health(self.metrics)
        if health == 'OK':
            self.colour = 'normal'
        else:
            self.colour = health.lower()
        return health


class IOPS(SingleStat):

    title = 'IOPS'

    def _format(self):
        total_iops = get_total_iops(self.metrics)
        return str(int(total_iops))


class Throughput(SingleStat):

    title = 'Throughput'

    def _format(self):
        total_throughput = get_total_throughput(self.metrics)
        if total_throughput < 0:
            # sometimes the stats generate a negative throughput value, so we bounce them back to positives
            total_throughput *= -1
        return f"{humanize.naturalsize(total_throughput, binary=False)}/s"


class PrometheusAlerts(CmonComponent):

    title = "Prometheus Alerts"

    # example output from prometheus query
    # {"status":"success",
    #   "data":{"alerts":[
    #       {"labels":{"alertname":"low monitor quorum count",
    #                   "oid":"1.3.6.1.4.1.50495.15.1.2.3.1",
    #                   "severity":"critical",
    #                   "type":"ceph_default"},
    #       "annotations":{"description":"Monitor count in quorum is below three.\n\nOnly 1 of 1 monitors are active.\n\nThe following monitors are down:\n"},"state":"firing","activeAt":"2021-06-30T21:04:45.710572658Z","value":"1e+00"},{"labels":{"alertname":"network packets dropped","device":"eth0","instance":"rh8ceph1","job":"node","oid":"1.3.6.1.4.1.50495.15.1.2.8.2","severity":"warning","type":"ceph_default"},"annotations":{"description":"Node rh8ceph1 experiences packet drop \u003e 0.01% or \u003e 10 packets/s on interface eth0.\n"},
    #       "state":"firing",
    #       "activeAt":"2021-06-30T21:04:45.896136035Z",
    #       "value":"4.7619047619047616e-02"}
    #       ]}}
    def __init__(self, parent):

        self.parent = parent
        self.visible = parent.config.panel_alerts
        self.column_spacing = 2
        self.highlights = {
            "warning": "warning reversed",
            "critical": "error reversed",
            "page": "error reversed",
        }
        self.column_names = {
            "severity": 12,
            "state": 8,
            "age": 14,
            "alertname": 24,
            "description": 0,
        }
        [('severity', 12), ('state', 10), ("age", 15), ("alertname", 24), ('description', 0)]
        self.table_height = 4
        self.prometheus_url = parent.prometheus_url
        self.t_head = self._headings()
        self.t_body: MyListBox
        self.t_footer: urwid.Text
        self.row = 1
        self.table: urwid.Pile
        self.alert_data = []
        # self.widget = self._build_widget()
        super().__init__(visible=parent.config.panel_alerts)
        self.focus_support = True

    def _headings(self):
        cols = []
        for name in self.column_names:
            if self.column_names[name]:
                cols.append((self.column_names[name], urwid.Text(name.capitalize())))
            else:
                cols.append(urwid.Text(name.capitalize()))
        return urwid.Columns(cols, dividechars=self.column_spacing)

    def _update_footer(self, row_num: int):
        logger.debug("in alerts panel footer update call")
        if row_num + 1 != self.row:
            self.row = row_num + 1
            self.t_footer.set_text(f"{self.row}/{len(self.alert_data)} alerts")

    def _build_rows(self, data):
        rows = []
        sorted_alerts = sorted(data, key=lambda k: (
            k['labels']['severity'], k['labels']['alertname']))

        for alert in sorted_alerts:
            alert_age = 'unknown'
            description = ''
            # row = []
            labels = alert.get('labels', {})
            annotations = alert.get('annotations', {})
            if annotations:
                description = annotations.get('description', '')
                description = description.replace('\n', ' ')
            if labels:
                alertname = labels.get('alertname', '?')
                severity = labels.get('severity', '?')
            state = alert.get('state', 'Unknown')
            active_at = alert.get('activeAt', '')
            if active_at:
                alert_age = age(active_at)

            rows.append(
                urwid.AttrMap(
                    urwid.Columns([
                        (self.column_names['severity'], urwid.Text(
                            (self.highlights[severity], f"{severity:^10} "))),
                        (self.column_names['state'], urwid.Text(state)),
                        (self.column_names['age'], urwid.Text(alert_age)),
                        (self.column_names['alertname'], urwid.Text(alertname)),
                        urwid.Text(description),
                    ], dividechars=self.column_spacing
                    ),
                    None,
                    focus_map='reversed')
            )

        return rows

    def _build_body(self):  # , alert_data: List[Dict[str, Any]]):
        return MyListBox(urwid.SimpleListWalker(self._build_rows(self.alert_data)))

    def _build_widget(self):
        if self.visible:
            logger.info("alerts table is visible")
            if self.prometheus_url:
                return self._alerts_table()
            else:
                return self._alerts_unavailable()
        else:
            return

    def _alerts_table(self):
        logger.info("fetching alert state")
        self.t_footer = urwid.Text("No alerts")
        self.t_body = MyListBox(urwid.SimpleListWalker([]))

        self.alert_data = []
        r = get_prometheus_alerts(self.prometheus_url)
        if r.status_code == 200:
            js = r.json()
            self.alert_data = js['data'].get('alerts', [])
            if self.alert_data:
                self.t_body = self._build_body()
                self.t_footer = urwid.Text(f"{self.row}/{len(self.alert_data)} alerts")
        elif r.status_code == 500:
            self.t_footer = urwid.Text(
                ('error', f'Unable to retrieve alerts from {self.prometheus_url}'))

        table_layout = [self.t_head]
        if self.t_body.contents:
            table_layout.append(
                urwid.BoxAdapter(self.t_body, height=self.table_height)
            )
        # table_layout.append(self.t_footer)
        self.table = urwid.Pile(table_layout)
        return urwid.Padding(
            urwid.LineBox(
                urwid.Padding(
                    urwid.Pile([
                        self.table,
                        self.t_footer,
                    ]),
                    left=1,
                    right=1
                ),
                title=self.title),
            align='left',
            width='pack'
        )

    def _alerts_unavailable(self):
        return \
            urwid.LineBox(
                urwid.Padding(
                    urwid.Text(("warning", "\nPrometheus url is needed to show alerts\n\n")),
                    align='left', left=1
                ),
                title=self.title
            )

    def _move(self, direction: str):
        if direction == 'up':
            self.t_body.focus_previous()
            self._update_footer(self.table.get_focus_path()[1])
        elif direction == 'down':
            self.t_body.focus_next()
            self._update_footer(self.table.get_focus_path()[1])

    def keypress(self, size, key):
        logger.debug("processing keypress in alerts table")
        if self.t_body:

            if key == 'up':
                self._move('up')
            if key == 'down':
                self._move('down')

        self.parent.keypress(key)

    def mouse_event(self, size, event, button, col, row, wrow):
        # print(event) # "mouse press"
        # print(button) # button no. 1-5, 1=left, 2=middle, 3=right, 4-wheel-up, 5 wheel-down
        if event == 'mouse press':

            if button == 4:
                # up
                self._move('up')
            elif button == 5:
                # down
                self._move('down')

    def update(self):
        logger.debug("in alerts update method")
        current_focus = self.table.get_focus_path()
        self.original_widget = self._build_widget()
        self.table.set_focus_path(current_focus)
        self._update_footer(current_focus[1])


class PoolInfo(CmonTable):
    title = 'Pool Details'
    column_list = ['name', 'description', 'stored', 'used %', 'avail',
                   'PGs', 'compression', 'savings', 'IOPS', 'throughput', 'health']

    def __init__(self, parent):
        self.parent = parent
        self.table = None
        super().__init__(metrics=parent.metrics, visible=parent.config.panel_pools)
        self.focus_support = True

    def _build_table(self):
        pool_data = get_pool_summary(self.parent.metrics)
        msg = None
        if not pool_data:
            msg = "no pools found"

        self.table = DataTable(
            self.parent,
            column_list=PoolInfo.column_list,
            data=pool_data,
            msg=msg,
            description='pools')


class PGStatus(CmonComponent):
    title = "Placement Group Health"
    hbar_width = 33
    hbar_order = ['OK', 'warning', 'error', 'unknown']

    def _get_pg_summary(self):
        return get_pg_summary(self.metrics)

    def _build_hbar(self, pg_overview: Dict[str, CategoryTotal]) -> HStackBar:

        items = []
        for k in self.hbar_order:
            if k in pg_overview:
                items.append((k, pg_overview[k].pct))
        return HStackBar(items, self.hbar_width)

    def _build_legend(self, pg_overview: Dict[str, CategoryTotal]):
        legend = []
        for k in self.hbar_order:
            if k in pg_overview:
                col = f"pgs {k}"
                k_txt = k if k == 'OK' else k.capitalize()
                legend.extend([(col, k_txt), " ", (col, f"{int(pg_overview[k].pct)}% ")])
        return urwid.Text(legend)

    def _build_widget(self):
        pg_overview = self._get_pg_summary()
        hbar = self._build_hbar(pg_overview)
        legend = self._build_legend(pg_overview)
        return urwid.Padding(
            urwid.LineBox(
                urwid.Padding(
                    urwid.Pile([
                        urwid.Divider(" "),
                        urwid.Columns([
                            (self.hbar_width, hbar),
                            urwid.Text(f"{int(pg_overview['total'].total):>7} PGs")
                        ]),
                        legend,
                    ]),
                    left=1, right=1),
                title=self.title)
        )


class RBDPerformance(CmonTable):

    title = "RBD Performance (TOP 10)"
    column_list = ['image', 'pool', 'namespace', 'read_ops', 'read_bytes',
                   'read_latency', 'write_ops', 'write_bytes', 'write_latency']

    def __init__(self, parent):
        self.parent = parent
        self.table = None
        super().__init__(metrics=parent.metrics, visible=parent.config.panel_rbds)
        self.focus_support = True

    def _build_table(self):

        rbd_data = get_rbd_performance(self.metrics)
        sorted_rbd_data = []
        msg = None
        if not rbd_data:
            # no rbds are being tracked
            msg = "no rbd performance information available"
        else:
            active_rbds = [r for r in rbd_data if (r['read_ops'] or r['write_ops']) > 0]
            if active_rbds:
                sorted_rbd_data = sorted(active_rbds, key=lambda k: k['total_ops'], reverse=True)
                if len(sorted_rbd_data) > self.parent.top_rbd_count:
                    sorted_rbd_data = sorted_rbd_data[:self.parent.top_rbd_count]
            else:
                msg = "rbd data present, waiting for rbd I/O activity"
        logger.info(f"{len(sorted_rbd_data)} rbd images extracted")

        self.table = DataTable(
            self.parent,
            column_list=RBDPerformance.column_list,
            data=sorted_rbd_data,
            msg=msg,
            description='rbd image(s)')


class IOGraphs(CmonComponent):

    title = 'I/O Load Overview (last 15 mins)'

    def __init__(self, parent):
        self.parent = parent
        self.prometheus_available = True
        self.prometheus_url = parent.prometheus_url
        self.chart_height = 10
        self.iops_query = {
            "query": "sum(rate(ceph_pool_rd[30s])) + sum(rate(ceph_pool_wr[30s]))",
            # "query": "sum(rate(ceph_pool_rd[30s]) + rate(ceph_pool_wr[30s]))",
            "step": f"{self.parent.refresh_interval}s",
            "start": "",
            "end": "",
        }
        self.throughput_query = {
            "query": "sum(rate(ceph_pool_rd_bytes[30s])) + sum(rate(ceph_pool_wr_bytes[30s]))",
            # "query": "sum(rate(ceph_pool_rd_bytes[30s]) + rate(ceph_pool_wr_bytes[30s]))",
            "step": f"{self.parent.refresh_interval}s",
            "start": "",
            "end": "",
        }
        super().__init__(visible=parent.config.panel_ioload)

    def bar_graph(self, scheme: str, smooth: bool = True):
        return BarChart(scheme)

    def _build_widget(self):
        if self.visible:
            if self.prometheus_url:
                return self._graphs()
            else:
                return self._graphs_unavailable()
        else:
            return

    def _build_chart_data(self, raw_values) -> List[List[int]]:
        max_value = 0
        values = []
        colour_switch = False
        for item in raw_values:
            value = int(float(item))
            if value > max_value:
                max_value = value

            colour_switch = not colour_switch

            value_pair = [value, 0] if colour_switch else [0, value]

            values.append(value_pair)

        return values

    def _fetch_prometheus_data(self, query: Dict[str, Any], window_start: float, window_end: float) -> List[float]:
        raw_values = []

        query['start'] = window_start
        query['end'] = window_end

        r = get_prometheus_data(self.prometheus_url, params=query)

        if r.status_code == 200:
            self.prometheus_available = True
            js = r.json()
            results = js['data']['result']
            if results:
                # iops query is a summary, so only 1 list element
                raw_data = js['data']['result'][0]['values']
                # raw_values is a list of timestamp, value pairs, so extract just the value
                raw_values = [float(i[1]) for i in raw_data]
                # data_values, max_value = self._build_chart_data(raw_values)
        elif r.status_code == 500:
            self.prometheus_available = False
        else:
            # FIXME prometheus returned a strange code, what should be done?
            pass

        return raw_values

    def _graphs(self):
        window_end: float = time.time()
        # FIXME - what if cmon is started before there are 10mins of data, what is returned from prometheus?
        window_start: float = window_end - 885  # 870  # 15 mins - 15s for the current interval

        iops_data = self._fetch_prometheus_data(self.iops_query, window_start, window_end)
        # print(iops_data)

        if self.prometheus_available:
            if iops_data:
                iops_data_fmtd = self._build_chart_data(iops_data)
                iops_graph = self.bar_graph('blue')
                y_axis = GraphScale(0, max(iops_data) or 1, unit='short')
                iops_graph.set_data(iops_data_fmtd, y_axis.max)
                iops_labels = urwid.GraphVScale(y_axis.labels, y_axis.max)

                throughput_data = self._fetch_prometheus_data(
                    self.throughput_query, window_start, window_end)
                throughput_data_fmtd = self._build_chart_data(throughput_data)
                throughput_graph = self.bar_graph(scheme='magenta')
                y_axis = GraphScale(0, max(throughput_data) or 1, unit='dec-bytes')
                throughput_graph.set_data(throughput_data_fmtd, y_axis.max)

                graph_labels = y_axis.labels
                throughput_labels = urwid.GraphVScale(graph_labels, y_axis.max)
                if ' ' in graph_labels[0][1]:
                    throughput_unit = f"{graph_labels[0][1].split(' ')[1]}/s"
                else:
                    throughput_unit = "B/s"

                return urwid.Padding(
                    urwid.LineBox(
                        urwid.Pile([
                            urwid.Text('IOPS'),
                            urwid.Columns([
                                (8, urwid.BoxAdapter(iops_labels, height=self.chart_height)),
                                urwid.BoxAdapter(iops_graph, height=self.chart_height),
                            ]),
                            urwid.Divider(),
                            urwid.Text(f"Throughput ({throughput_unit})"),
                            urwid.Columns([
                                (8, urwid.BoxAdapter(throughput_labels, height=self.chart_height)),
                                urwid.BoxAdapter(throughput_graph, height=self.chart_height),
                            ]),
                        ]),
                        title=self.title),
                )
            else:
                return \
                    urwid.LineBox(
                        urwid.Padding(
                            urwid.Text(
                                ('warning', "\nQuery to prometheus resulted in no data. Unable to show IO load Activity\n\n\n\n")),
                            align='left', left=1
                        ),
                        title=self.title
                    )
        else:
            # prometheus endpoint is not reachable
            return \
                urwid.LineBox(
                    urwid.Padding(
                        urwid.Text(
                            ('error', f"\nPrometheus endpoint @ {self.prometheus_url} is not responding\n")),
                        align='left', left=1
                    ),
                    title=self.title
                )

    def _graphs_unavailable(self):
        return \
            urwid.LineBox(
                urwid.Padding(
                    urwid.Text(
                        ('warning', "\nPrometheus url is needed to show IO load Activity\n\n\n\n")),
                    align='left', left=1
                ),
                title=self.title
            )


class RGWPerformance(CmonTable):
    title = 'RGW Performance'
    column_list = ['ceph_daemon', 'hostname', 'gets', 'get_throughput', 'puts', 'put_throughput']

    def __init__(self, parent):
        self.parent = parent
        self.table = None
        super().__init__(metrics=parent.metrics, visible=parent.config.panel_rgws)
        self.focus_support = True

    def _build_table(self):
        rgw_data = get_rgw_performance(self.parent.metrics)
        msg = None
        if not rgw_data:
            msg = "no rgw daemons found"

        self.table = DataTable(
            self.parent,
            column_list=RGWPerformance.column_list,
            data=rgw_data,
            msg=msg,
            description='RGW instance(s)',
            col_spacing=3
        )
