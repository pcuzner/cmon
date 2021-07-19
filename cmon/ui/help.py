import urwid
import logging

from .common import CmonComponent, Icon

logger = logging.getLogger(__name__)


class HelpInformation(CmonComponent):
    title = "Help"

    def _build_widget(self):

        return \
            urwid.LineBox(
                urwid.Filler(
                    urwid.Padding(
                        urwid.Pile([
                            urwid.Divider(),
                            urwid.Text(
                                [("pgm name", "cmon"), " is a command line status monitor for Ceph. It gathers status information for a cluster "
                                 "directly from the mgr/prometheus HTTP endpoint, and can also show I/O load and current alert "
                                 "state by optionally integrating with the Ceph cluster's Prometheus server."]),
                            urwid.Divider(),
                            urwid.Text(
                                "cmon's core panels show inventory, health, iops, throughput, PG health and capacity. Note that "
                                "since thera are so many variations of PG state, the PG health panel simplifies state into discrete "
                                "'buckets' of OK, warning, error and unknown."
                            ),
                            urwid.Divider(),
                            urwid.Text(
                                "Additional panels may be toggled on/off as follows"
                            ),
                            urwid.Divider(),
                            urwid.Columns([
                                (15, urwid.Text("Key")),
                                urwid.Text("Description")
                            ]),
                            urwid.Columns([
                                (15, urwid.Text("a or A")),
                                urwid.Text(
                                    "Show a list of currently active alerts from Prometheus"
                                )
                            ]),
                            urwid.Columns([
                                (15, urwid.Text("i or I")),
                                urwid.Text(
                                    "Show the IO load from the last 10 minutes of the cluster in terms of "
                                    "IOPS and throughput, using data sourced from Promethues")
                            ]),
                            urwid.Columns([
                                (15, urwid.Text("p or P")),
                                urwid.Text(
                                    "Show a breakdown of the pools defined, include current Pool I/O load"
                                )
                            ]),
                            urwid.Columns([
                                (15, urwid.Text("r or R")),
                                urwid.Text(
                                    "Show the performance data for top 10 rbd's (IOPS/throughput and latency)"
                                )
                            ]),
                            urwid.Columns([
                                (15, urwid.Text("g or G")),
                                urwid.Text(
                                    "Show the performance data RGW instances"
                                )
                            ]),
                            urwid.Divider(),
                            urwid.Divider('_'),
                            urwid.Divider(),
                            urwid.Text(
                                "In addition to the monitoring, the tool also performs some rudimentary checks."),
                            urwid.Text(
                                " - if the number of daemons defined are too few, the count will be rendered in yellow"
                            ),
                            urwid.Text(
                                " - if the cluster health is not in an OK state, it's panel will be coloured accordingly"
                            ),
                            urwid.Text([
                                ("normal", " - the colour of the capacity bar changes based on utilisation;"),
                                ("ok", " 0-80 "),
                                ("normal", Icon.arrow_right),
                                ("warning", " 80-90 "),
                                ("normal", Icon.arrow_right),
                                ("error", " > 90")
                            ]),
                            urwid.Divider(),
                            urwid.Text([
                                ('bold', "TIP"), ": A countdown timer is shown in the bottom right corner to indicate when the next metrics "
                                "refresh will take place."
                            ])

                        ]),
                        left=1,
                        right=1
                    ),
                    'top'),
                title="Help"
            )
