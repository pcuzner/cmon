import sys
import time
import hashlib
import logging

from typing import Dict, List, Optional, Union, Set, Tuple

from .utils import Filter, timeit, valid_url
from .http_api import get_mgr_data

logger = logging.getLogger(__name__)

# TODO
# use the count of missing samples in the divisor when calculating the delta


def extract_labels(raw_str: str) -> Optional[str]:
    a_start = raw_str.find('{')
    a_end = raw_str.rfind('}')
    if '{' not in raw_str:
        return None
    return raw_str[a_start + 1:a_end]


class MetricInstance:

    def __init__(self, metric_type: str, raw_str: str, tstamp: int):

        self._metric_type = metric_type
        self.value = float(raw_str.split(' ')[-1])
        self.delta: float = 0
        self.tstamp = tstamp
        labels = extract_labels(raw_str)
        if labels:
            labels_to_read = True
            while labels_to_read:
                q1 = labels.find('"')
                q2 = labels.find('"', q1 + 1) + 1
                kv_pair = labels[0:q2]

                k, v = kv_pair.split('=', 1)
                if len(v) == 2:
                    # len=2 is just a "" value
                    v = ''
                else:
                    # prometheus exporter provides label values as quoted text
                    # so we remove the quotes before storing
                    v = v[1:-1]
                setattr(self, k, v)
                if q2 == len(labels):
                    labels_to_read = False
                else:
                    labels = labels[q2 + 1:]

    def update(self, raw_str: str, tstamp: int, scrape_interval: int) -> None:
        new_value = float(raw_str.split(' ')[-1])
        self.delta = (new_value - self.value) / scrape_interval
        self.value = new_value
        self.tstamp = tstamp

    def dump_to_json(self, attr_name: Optional[str] = None) -> Optional[Dict[str, str]]:
        data = {}
        if attr_name:
            if hasattr(self, attr_name):
                return {
                    attr_name: getattr(self, attr_name)
                }
            else:
                return None

        attrs = [k for k in self.__dict__ if not k.startswith('_')]
        for k in attrs:
            data[k] = getattr(self, k)
        return data if data else None

    def __str__(self) -> str:
        s = ""
        attrs = [k for k in self.__dict__ if not k.startswith(('_', 'value'))]
        for k in attrs:
            s += f'{k}="{getattr(self, k)}",'
        s = s.rstrip(',')
        s += f" {self.value}"
        return s


class Metric:
    hash_size = 12

    def __init__(self, metric_name: str, metric_type: str):
        self.name: str = metric_name
        # type is not being set correctly or consistently
        # so we're setting it, but not relying on it to set instance delta
        self.type: str = metric_type
        self.values: Dict[str, MetricInstance] = {}
        self.instances_to_remove: List[str] = []
        self.tstamp: Optional[int] = None
        logger.debug(f"created metric {self.name}, type is {self.type}")

    def _get_hash(self, raw_str: str) -> str:
        labels = extract_labels(raw_str)
        if not labels:
            logger.debug(f"creating singleton for {self.name}")
            return "singleton"
        return hashlib.sha1(labels.encode('utf-8')).hexdigest()[0:self.hash_size]

    def add(self, raw: str, tstamp: int) -> str:
        key = self._get_hash(raw)
        self.tstamp = tstamp
        self.values[key] = MetricInstance(self.type, raw, self.tstamp)
        return key

    # def prepare_update(self):
    #     self.instances_to_remove = self.values.keys()

    def update(self, raw: str, tstamp: int, scrape_interval: int) -> str:
        key = self._get_hash(raw)
        # if raw.startswith('ceph_pool_rd'):
        #     print(f"{key} from raw value {raw}")
        self.tstamp = tstamp
        if key in self.values:
            self.values[key].update(raw, self.tstamp, scrape_interval)
            # self.instances_to_remove.remove(key)
        else:
            self.values[key] = MetricInstance(self.type, raw, self.tstamp)
        return key

    @property
    def value(self):
        if len(self.values) != 1:
            return None

        return self.values["singleton"].value

    def dump_to_list(self, attr_name: Optional[str] = None) -> Union[List[Dict[str, str]], List]:
        data = []
        for k in self.values:
            i = self.values[k]
            data.append(i.dump_to_json(attr_name))
        return data

    def __str__(self) -> str:
        hdr = f"{self.name} ({self.type})\n"
        items = ""
        for instance in self.values:
            items += f"{str(self.values[instance])}\n"
        return hdr + items


# class MetricHistory:
#     def __init__(self, desc:str, size: int = 5) -> None:
#         self.description: str = desc
#         self.size: int = size
#         self.history: List[Metric] = []

#     def add(self, metric: Optional[Metric]) -> None:
#         logger.debug(f"adding {metric.name} to history")
#         self.history.append(metric)
#         if len(self.history) > self.size:
#             logger.debug(f"removing the oldest metric for {metric.name} from the history")
#             self.history.pop(0)

class Metrics:

    def __init__(self, target_url: str, max_failures: int = 6, scrape_interval: int = 10):
        self.data: Dict[str, Metric] = {}
        self.mgr_endpoint = target_url
        self.consecutive_scrape_failures = 0
        self.max_failures = max_failures
        self.tstamp: int
        self.scrape_interval = scrape_interval

    @property
    def scraped(self):
        return self.consecutive_scrape_failures == 0

    # def update_history(self, with_data: bool = True):
    #     for history_metric in self.history:
    #         if history_metric in self.data:
    #             if with_data:
    #                 self.history[history_metric].add(self.data[history_metric])
    #             else:
    #                 self.history[history_metric].add(None)

    @timeit
    def build(self) -> bool:
        url_ok, err = valid_url(self.mgr_endpoint)
        if not url_ok:
            logger.error(f"URL '{self.mgr_endpoint}' is unusable: {err}")
            return False

        self.tstamp, raw_data = self.fetch()
        if raw_data:
            # sync_flag = self._gen_sync_flag()
            for d in raw_data.split('\n'):
                if d.startswith("# TYPE"):
                    f = d.split(' ')
                    # metric_type_name = f[2]
                    metric_type = f[-1]
                    # if metric_name not in self.data:
                    # not seen it, so create a new entry
                    # self.data[metric_name] = Metric(metric_name, metric_type)
                elif d.startswith("ceph_"):
                    if '{' in d:
                        metric_name = d.split('{')[0]
                    else:
                        metric_name = d.split(' ')[0]
                    if metric_name in self.data:
                        self.data[metric_name].add(d, self.tstamp)
                    else:
                        self.data[metric_name] = Metric(metric_name, metric_type)
                        self.data[metric_name].add(d, self.tstamp)
            logger.info("metrics built successfully")
            # logger.info("seeding the metric history, with the first observations")
            # self.update_history()
            return True
        else:
            # no data returned, unable to continue
            logger.error(
                f"Unable to get latest data from mgr/prometheus endpoint at {self.mgr_endpoint}")
            return False
            # print("unable to build the initial metrics set. http request failed, check the log for the specific error message")
            # sys.exit(1)

    @timeit
    def update(self) -> None:
        all_metrics: Set[str] = set(self.data.keys())
        seen_metrics: Set[str] = set()
        seen_instances: Dict[str, Set[str]] = {}

        self.tstamp, raw_data = self.fetch()

        if raw_data:
            logger.debug("received data from mgr endpoint, processing start")
            # lets update the metrics map
            self.consecutive_scrape_failures = 0
            for d in raw_data.split('\n'):
                if d.startswith("# TYPE"):
                    f = d.split(' ')
                    # metric_type_name = f[2]
                    metric_type = f[-1]
                elif d.startswith('ceph_'):
                    if '{' in d:
                        metric_name = d.split('{')[0]
                    else:
                        metric_name = d.split(' ')[0]
                    if metric_name in self.data:
                        instance_key = self.data[metric_name].update(
                            d, self.tstamp, self.scrape_interval)
                        if metric_name not in seen_instances:
                            logger.debug(f"creating seen metric for {metric_name}")
                            seen_instances[metric_name] = {instance_key}
                        else:
                            logger.debug(
                                f"updating seen metric set for {metric_name} with instance id {instance_key}")
                            seen_instances[metric_name].add(instance_key)

                        seen_metrics.add(metric_name)
                    else:
                        logger.debug(f"new metric{metric_name} has appeared, and will be added")
                        # new metric has appeared
                        self.data[metric_name] = Metric(metric_name, metric_type)
                        instance_key = self.data[metric_name].add(d, self.tstamp)
                        seen_instances[metric_name] = {instance_key}

            # self.update_history()
            logger.info("metrics update complete")
            self.prune_metrics(all_metrics.difference(seen_metrics))
            self.prune_instances(seen_instances)
        else:
            logger.error(
                f"Unable to get latest data from mgr/prometheus endpoint at {self.mgr_endpoint}")
            # self.update_history(with_data=False)
            self.consecutive_scrape_failures += 1
            if self.consecutive_scrape_failures >= self.max_failures:
                print(
                    f"Terminating. {self.max_failures} scrapes from the mgr have failed. Unable to continue.")
                logger.critical(
                    f"Scrapes from {self.mgr_endpoint} have failed {self.max_failures} times. Terminating")
                sys.exit(1)

    @timeit
    def fetch(self) -> Tuple[int, Optional[str]]:
        tstamp = int(time.time())
        r = get_mgr_data(self.mgr_endpoint)

        if r.status_code == 200:
            # success
            logger.debug(f"http request to {self.mgr_endpoint} successful")
            return tstamp, r.text
        else:
            if r.status_code == 500:
                logger.error(f"Unable to reach/contact {self.mgr_endpoint}")
            else:
                logger.error(
                    f"HTTP request to {self.mgr_endpoint} failed with status: {r.status_code}")
            return tstamp, None

    @timeit
    def prune_instances(self, seen_instances):
        count_pruned_instances = 0
        count_metrics_changed = 0
        for k in self.data:
            m = self.data[k]
            all_instances = set(m.values.keys())
            deleted_instances = all_instances.difference(seen_instances[k])
            if deleted_instances:
                logger.debug(f"{len(deleted_instances)} instance pruned from metric {k}")
                count_metrics_changed += 1
                count_pruned_instances += len(deleted_instances)
                for d in deleted_instances:
                    del m.values[d]
        logger.info(
            f"instance pruning removed {count_pruned_instances} metric instances across {count_metrics_changed} metrics")

    @timeit
    def prune_metrics(self, expired_metrics: Set[str]) -> None:
        for k in expired_metrics:
            logger.debug(f"removing metric {k}")
            del self.data[k]
        logger.info(f"{len(expired_metrics)} metrics removed: {expired_metrics}")


def label_match(metric_instance: Union[MetricInstance, Dict[str, str]], filter: Filter) -> bool:
    for k in filter.__dict__.keys():
        if k == "value":
            continue

        if isinstance(metric_instance, MetricInstance):
            if not hasattr(metric_instance, k):
                logger.debug("filter had a label, that the metric doesn't have")
                return False
            if getattr(metric_instance, k) != getattr(filter, k):
                return False
        else:
            if k not in metric_instance:
                logger.debug("filter had a label that the metric list didn't have")
                return False
            if metric_instance[k] != getattr(filter, k):
                return False
    return True


def count(metric: Union[Metric, List[Dict[str, str]]], filter: Optional[Filter] = None) -> Optional[int]:

    def _count_metrics() -> int:
        metric: Metric
        if not filter:
            return len(metric.values)

        matches = 0
        for k in metric.values:
            i = metric.values[k]
            if filter.value:
                logger.debug("checking value match")
                if abs(float(i.value) - filter.value) > 0.00001:
                    continue
            filter_keys = [k for k in filter.__dict__ if k != "value"]
            if filter_keys:
                logger.debug("checking labels")
                if not label_match(i, filter):
                    continue
            matches += 1
        return matches

    def _count_lists() -> int:
        metric: List[Dict[str, str]]
        matches = 0
        if not filter:
            return len(metric)
        for i in metric:
            if filter.value:
                logger.debug("checking value match")
                if abs(float(i['value']) - filter.value) > 0.00001:
                    continue
            filter_keys = [k for k in filter.__dict__ if k != "value"]
            if filter_keys:
                logger.debug("checking labels")
                if not label_match(i, filter):
                    continue
            matches += 1

        return matches

    if isinstance(metric, Metric):
        return _count_metrics()
    elif isinstance(metric, List):
        return _count_lists()
    return None


def sum_metrics(metric: Metric, sum_by_variable: str = "delta") -> float:

    # FIXME could ad a filter to only sum by a specific criteria

    total = 0
    for k in metric.values:
        i = metric.values[k]
        inc = getattr(i, sum_by_variable)
        total += inc
    return total
