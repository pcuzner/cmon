import humanize  # type: ignore
import logging

from typing import Dict, List, Any

from .utils import relabel, merge_dict_lists_by_key
from .mgr_prometheus import Metrics, sum_metrics

logger = logging.getLogger(__name__)

HEALTH_MAP = {
    0.0: 'OK',
    1.0: 'WARNING',
    2.0: 'ERROR'
}

PG_STATE_MAP = {
    "error": [
        "ceph_pg_stale",
        "ceph_pg_down",
        "ceph_pg_failed_repair"
    ],
    "unknown": [
        "ceph_pg_unknown"
    ],
}


class CategoryTotal:

    def __init__(self, total: float, pct: float = 0):
        self.total = total
        self.pct = pct

    def __repr__(self):
        return f"({self.total}, {self.pct})"


def get_pool_summary(metrics: Metrics) -> List[Dict[str, str]]:

    pool_data = fetch_metric_list(metrics, 'ceph_pool_metadata')
    updates = []
    updates.extend([relabel(fetch_metric_list(metrics, 'ceph_pool_rd'), 'delta', 'pool_rd')])
    updates.extend([relabel(fetch_metric_list(metrics, 'ceph_pool_wr'), 'delta', 'pool_wr')])
    updates.extend(
        [relabel(fetch_metric_list(metrics, 'ceph_pool_rd_bytes'), 'delta', 'pool_rd_bytes')])
    updates.extend(
        [relabel(fetch_metric_list(metrics, 'ceph_pool_wr_bytes'), 'delta', 'pool_wr_bytes')])
    updates.extend(
        [relabel(fetch_metric_list(metrics, 'ceph_pool_percent_used'), 'value', 'percent_used')])
    updates.extend([relabel(fetch_metric_list(
        metrics, 'ceph_pool_compress_under_bytes'), 'value', 'compress_under_bytes')])
    updates.extend([relabel(fetch_metric_list(
        metrics, 'ceph_pool_compress_bytes_used'), 'value', 'compress_bytes_used')])
    updates.extend([relabel(fetch_metric_list(metrics, 'ceph_pg_total'), 'value', 'pg_count')])
    updates.extend([relabel(fetch_metric_list(metrics, 'ceph_pg_active'), 'value', 'pg_active')])
    updates.extend([relabel(fetch_metric_list(metrics, 'ceph_pool_stored'), 'value', 'stored_bytes')])
    updates.extend([relabel(fetch_metric_list(
        metrics, 'ceph_pool_recovering_objects_per_sec'), 'value', 'recovery_rate')])
    updates.extend(
        [relabel(fetch_metric_list(metrics, 'ceph_pool_max_avail'), 'value', 'max_avail_bytes')])
    # TODO add more pool info here
    merge_dict_lists_by_key(pool_data, updates, ['pool_id'])
    for pool in pool_data:
        if 'compression_mode' in pool:
            # Pacific and above
            if pool['compression_mode'] == 'none':
                pool['compression'] = 'OFF'
            else:
                pool['compression'] = 'ON'
        else:
            # Older release
            pool['compression'] = 'N/A'
        pool['throughput'] = f"{humanize.naturalsize(pool['pool_rd_bytes'] + pool['pool_wr_bytes'])}/s"
        pool['IOPS'] = str(int(pool['pool_wr'] + pool['pool_rd']))
        pool['stored'] = humanize.naturalsize(pool['stored_bytes'], binary=True)
        pool['avail'] = humanize.naturalsize(pool['max_avail_bytes'], binary=True)
        pool['PGs'] = str(int(pool['pg_count']))
        pool['savings'] = humanize.naturalsize(
            float(pool['compress_under_bytes']) - float(pool['compress_bytes_used']), binary=True)
        pool['health'] = 'OK' if pool['recovery_rate'] == 0 else 'RECOVERING'
        if 'percent_used' in pool:
            # Pacific
            pool['used %'] = f"{pool['percent_used']:.1f}"
        else:
            # older
            pool['used %'] = 'N/A'

    return pool_data


def create_osd_summary(metrics: Metrics) -> Dict[str, Any]:
    osds = fetch_metric_list(metrics, 'ceph_osd_metadata')
    updates = []
    updates.extend([relabel(fetch_metric_list(metrics, 'ceph_osd_up'), 'value', 'up')])
    updates.extend([relabel(fetch_metric_list(metrics, 'ceph_osd_in'), 'value', 'in')])
    updates.extend(
        [relabel(fetch_metric_list(metrics, 'ceph_osd_stat_bytes'), 'value', 'size_bytes')])
    updates.extend(
        [relabel(fetch_metric_list(metrics, 'ceph_osd_stat_bytes_used'), 'value', 'bytes_used')])
    return merge_dict_lists_by_key(osds, updates, ['ceph_daemon'])


def fetch_metric_list(metrics: Metrics, metric_name: str) -> List[Dict[str, str]]:
    if metric_name in metrics.data:
        return metrics.data[metric_name].dump_to_list()
    else:
        return []


def get_inventory(metrics: Metrics) -> Dict[str, Any]:

    def _summarize(data):
        summary = {
            "up": 0,
            "down": 0
        }
        for d in data:
            if d['value'] == 1:
                summary['up'] += 1
            else:
                summary['down'] += 1
        return summary

    def _summarize_versions(metadata: List[Dict[str, Any]]) -> Dict[str, Any]:
        daemon_lookup: Dict[str, Any] = {
            "_all_": set(),
        }
        for daemon in metadata:
            daemon_type = daemon.get('ceph_daemon', 'unknown.daemon').split('.')[0]
            if daemon_type not in daemon_lookup:
                daemon_lookup[daemon_type] = {}
            version_text = daemon.get('ceph_version', '')
            if version_text:
                # core daemons report version like this - 
                #       ceph_version="ceph version 16.1.0-752-g98cc35e1 (98cc35e129ac9d1966d4063b83706ac954f3a6ed) pacific (rc)"
                # ceph-exporter reports version like this - 
                #       ceph_version="18.2.0-1252-g6a0590bd"
                vers = version_text.replace('ceph version ', '')
                vers_id = vers.split('.')[0]  # 16
                d = daemon_lookup[daemon_type]
                if vers_id in d:
                    d[vers_id] = d[vers_id] + 1
                else:
                    d[vers_id] = 1

                daemon_lookup['_all_'].add(vers_id)
        for d_type in daemon_lookup:
            if d_type == '_all_':
                continue
            if not daemon_lookup[d_type]:
                logger.warning(f"metadata for daemon {d_type} is missing ceph_version information")

        return daemon_lookup

    states: Dict[str, Any] = {}
    mon_data = fetch_metric_list(metrics, 'ceph_mon_metadata')
    mgr_data = fetch_metric_list(metrics, 'ceph_mgr_metadata')
    osd_data = fetch_metric_list(metrics, 'ceph_osd_up')
    mds_data = fetch_metric_list(metrics, 'ceph_mds_metadata')
    rgw_data = fetch_metric_list(metrics, 'ceph_rgw_metadata')
    rbd_mirror_data = fetch_metric_list(metrics, 'ceph_rbd_mirror_metadata')
    cephfs_mirror_data = fetch_metric_list(metrics, 'ceph_cephfs_mirror_metadata')
    iscsi_data = fetch_metric_list(metrics, 'ceph_iscsi_metadata')

    daemon_metadata = mon_data + mgr_data + osd_data + \
        mds_data + rgw_data + rbd_mirror_data + cephfs_mirror_data
    states['versions'] = _summarize_versions(daemon_metadata)
    states['mon'] = _summarize(mon_data)
    states['mgr'] = _summarize(mgr_data)
    states['osd'] = _summarize(osd_data)
    states['mds'] = _summarize(mds_data)
    states['rbd-mirror'] = _summarize(rbd_mirror_data)
    states['cephfs-mirror'] = _summarize(cephfs_mirror_data)
    states['rgw'] = _summarize(rgw_data)
    states['iscsi'] = _summarize(iscsi_data)

    metadata = [metric_name for metric_name in metrics.data if metric_name.endswith('metadata')]
    hosts = set()
    for metric_name in metadata:
        metric_dump = fetch_metric_list(metrics, metric_name)
        for m in metric_dump:
            if 'hostname' in m:
                hosts.add(m.get('hostname', ''))
            else:
                # skipping metadata metric since it doesn't include a hostname label
                break
    states['hosts'] = len(hosts)
    states['hostnames'] = list(hosts)

    return states


def get_capacity_info(metrics: Metrics) -> Dict[str, float]:
    total_data = fetch_metric_list(metrics, 'ceph_cluster_total_bytes')
    total: float = 0
    if total_data:
        total = float(total_data[0].get('value', 0))

    used: float = 0
    used_data = fetch_metric_list(metrics, 'ceph_cluster_total_used_bytes')
    if used_data:
        used = float(used_data[0].get('value', 0))

    disks = fetch_metric_list(metrics, 'ceph_disk_occupation')
    total_disks = 0
    hostdisk = set()

    for d in disks:
        osd_disks = d.get('device_ids', '')
        if osd_disks:
            # Octopus / Pacific onwards
            for dev_name in osd_disks.split(','):
                _, name = dev_name.split('=')
                hostdisk.add(f"{d['instance']}-{name}")
        else:
            # Nautilus just count the primary devices for now
            hostdisk.add(f"{d['instance']}-{d['device']}")
    total_disks = len(hostdisk)

    compressed_pools_count = 0
    compress_under_bytes = 0
    compress_used_bytes = 0

    pool_metadata = fetch_metric_list(metrics, 'ceph_pool_metadata')
    updates = []
    updates.extend([relabel(fetch_metric_list(
        metrics, 'ceph_pool_compress_under_bytes'), 'value', 'compress_under_bytes')])
    updates.extend([relabel(fetch_metric_list(
        metrics, 'ceph_pool_compress_bytes_used'), 'value', 'compress_used_bytes')])

    pool_data = merge_dict_lists_by_key(pool_metadata, updates, ['pool_id'])

    for p in pool_data:
        comp_mode = p.get('compression_mode', None)
        if comp_mode:
            if comp_mode != 'none':
                compressed_pools_count += 1
        compress_under_bytes += p.get('compress_under_bytes', 0)
        compress_used_bytes += p.get('compress_used_bytes', 0)

    compression_savings = compress_under_bytes - compress_used_bytes

    return {
        "total_bytes": total,
        "used_bytes": used,
        "disks_total": total_disks,
        "compressed_pools_count": compressed_pools_count,
        "compression_savings_bytes": compression_savings
    }


def get_health(metrics: Metrics) -> str:
    health = fetch_metric_list(metrics, 'ceph_health_status')[0]
    logger.debug(f"health status : {health}")
    return HEALTH_MAP[float(health['value'])]


def get_total_iops(metrics: Metrics) -> float:
    iops = sum_metrics(metrics.data['ceph_pool_rd'], sum_by_variable="delta")
    iops += sum_metrics(metrics.data['ceph_pool_wr'], sum_by_variable="delta")
    logger.debug(f"total IOPS : {iops}")
    return iops


def get_total_throughput(metrics: Metrics) -> float:
    throughput = sum_metrics(metrics.data['ceph_pool_rd_bytes'], sum_by_variable="delta")
    throughput += sum_metrics(metrics.data['ceph_pool_wr_bytes'], sum_by_variable="delta")
    logger.debug(f"total throughput : {throughput}")
    return throughput


def get_pg_summary(metrics: Metrics) -> Dict[str, CategoryTotal]:

    pg_overview = {}

    def _fetch_pg_state_total(pg_metric_name: str) -> float:
        if pg_metric_name in metrics.data:
            return sum_metrics(metrics.data[pg_metric_name], sum_by_variable='value')
        else:
            return 0

    pg_total = _fetch_pg_state_total('ceph_pg_total')
    pg_ok = _fetch_pg_state_total('ceph_pg_active') and \
        _fetch_pg_state_total('ceph_pg_clean')

    pg_overview['OK'] = CategoryTotal(pg_ok, (pg_ok / pg_total) * 100)

    for category in PG_STATE_MAP:
        pg_states = PG_STATE_MAP[category]
        category_total: float = 0
        for pg_name in pg_states:
            category_total += _fetch_pg_state_total(pg_name)
        if category_total > 0:
            pg_overview[category] = CategoryTotal(
                category_total, ((category_total / pg_total) * 100))

    # pg's can be in a multiple states, so we just look at the discrete settings and lump
    # everything else into the warning category
    all_categories: float = 0
    for category in pg_overview:
        all_categories += pg_overview[category].total
    diff = pg_total - all_categories
    if diff > 0:
        pg_overview['warning'] = CategoryTotal(diff, ((diff / pg_total) * 100))

    pg_overview['total'] = CategoryTotal(pg_total)

    logger.debug(f"PG category breakdown: {pg_overview}")

    return pg_overview


def get_rbd_performance(metrics: Metrics) -> List[Dict[str, Any]]:
    # NB. rbd data coule be 000's of images that need to be processed
    rbd_performance_metric_names = [
        'ceph_rbd_read_bytes',
        'ceph_rbd_write_ops',
        'ceph_rbd_write_bytes',
        'ceph_rbd_read_latency_sum',
        'ceph_rbd_read_latency_count',
        'ceph_rbd_write_latency_sum',
        'ceph_rbd_write_latency_count',
    ]

    def _build_key(data: Dict[str, Any]) -> str:
        return f"{data['pool']}|{data['namespace']}|{data['image']}"

    lookup = {}
    base_list = relabel(fetch_metric_list(metrics, 'ceph_rbd_read_ops'), 'delta', 'read_ops')
    if base_list:
        for item in base_list:
            key = _build_key(item)
            lookup[key] = item

        for m in rbd_performance_metric_names:
            m_data = fetch_metric_list(metrics, m)
            for item in m_data:
                key = _build_key(item)
                if key in lookup:
                    new_property = m.replace('ceph_rbd_', '')
                    lookup[key].update({new_property: item['delta']})
                else:
                    # every rbd should have an entry so this is weird, and indicates a problem in the
                    # ceph exporter (mgr/prometheus)
                    raise ValueError(
                        f"processing metric {m}, encountered a mismatch for entry {key}")

        # now calculate the read and write latencies, and handle formatting
        for key in lookup:
            item = lookup[key]

            total_ops = int(item['read_ops'] + item['write_ops'])
            rlat = item['read_latency_count'] / \
                item['read_latency_sum'] if item['read_latency_count'] > 0 else 0
            read_latency = f"{rlat*1000000:>7.2f}"
            wlat = item['write_latency_count'] / \
                item['write_latency_sum'] if item['write_latency_count'] > 0 else 0
            write_latency = f"{wlat*1000000:>7.2f}"
            item.update({
                "total_ops": total_ops,
                "read_ops": int(item['read_ops']),
                "write_ops": int(item['write_ops']),
                "read_latency": read_latency,
                "read_bytes": humanize.naturalsize(item['read_bytes'], binary=False),
                "write_bytes": humanize.naturalsize(item['write_bytes'], binary=False),
                "write_latency": write_latency,
            })

    return [lookup[k] for k in lookup]


def get_rgw_performance(metrics: Metrics) -> List[Dict[str, Any]]:
    """Return RGW performance data extracted from the mgr/prometheus metrics
    
    Note that in environments that have ceph-exporter the rgw performance data is no
    longer returned by mgr/prometheus and must be queried from the Prometheus server.
    """

    base_list = fetch_metric_list(metrics, 'ceph_rgw_metadata')
    updates = []
    updates.extend([relabel(fetch_metric_list(metrics, 'ceph_rgw_get'), "delta", "gets")])
    updates.extend([relabel(fetch_metric_list(metrics, 'ceph_rgw_put'), "delta", "puts")])

    updates.extend([relabel(fetch_metric_list(metrics, 'ceph_rgw_get_b'), "delta", "get_b")])
    updates.extend([relabel(fetch_metric_list(metrics, 'ceph_rgw_put_b'), "delta", "put_b")])

    rgw_data = merge_dict_lists_by_key(
        base_list=base_list, updates=updates, key_names=['ceph_daemon'])
    for gw in rgw_data:
        gw.update({
            "get_throughput": humanize.naturalsize(gw.get('get_b', 0)),
            "put_throughput": humanize.naturalsize(gw.get('put_b', 0)),
            "gets": str(int(gw.get('gets', 0))),
            "puts": str(int(gw.get('puts', 0))),
        })

    return rgw_data
