import os
import sys
import time

parent_dir = os.getcwd()
sys.path.append(os.path.join(os.path.dirname(parent_dir)))

from cmon.http_api import get_prometheus_alerts, get_prometheus_data


prometheus_url = 'http://192.168.122.92:9095'

alerts = get_prometheus_alerts(prometheus_url)
print(alerts.text)
start = time.time()

iops_query = {
    "query": "sum(rate(ceph_pool_rd[30s])) + sum(rate(ceph_pool_wr[30s]))",
    # "query": "sum(rate(ceph_pool_rd[30s]) + rate(ceph_pool_wr[30s]))",
    "step": "15s",
    "start": f"{start-885}",
    "end": f"{start}",
}

data = get_prometheus_data(prometheus_url, params=iops_query)
print(data.text)