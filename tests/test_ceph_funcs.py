import sys
import os
import time
parent_dir = os.getcwd()
sys.path.append(os.path.join(os.path.dirname(parent_dir)))

from cmon.mgr_prometheus import Metrics
from cmon.ceph import get_inventory, get_capacity_info, get_pool_summary, get_pg_summary, get_rbd_performance, get_rgw_performance

# m = Metrics(target_url='http://192.168.122.92:9283/metrics')
m = Metrics(target_url='http://localhost:8000/with_rgw')
m.build()

s = time.time()
print(get_inventory(m))

print(get_capacity_info(m))

print(get_pool_summary(m))

print(get_pg_summary(m))

print(get_rbd_performance(m))

print(get_rgw_performance(m))
print(f"elapsed : { time.time() - s}s")
sys.exit(0)
