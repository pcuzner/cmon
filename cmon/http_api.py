import requests
import urllib3.exceptions  # type: ignore
import logging

from typing import Dict, Any

from .utils import timeit

logger = logging.getLogger(__name__)


@timeit
def get_mgr_data(url: str) -> requests.Response:
    try:
        r = requests.get(f"{url}")
    except (requests.exceptions.ConnectionError, urllib3.exceptions.NewConnectionError, urllib3.exceptions.MaxRetryError):
        r = requests.Response()
        r.status_code = 500
    logger.debug(
        f"GET request to {url} completed with status code:{r.status_code}, {len(r.text)} bytes returned")
    return r


def get_prometheus_data(url: str, params: Dict[str, Any]) -> requests.Response:
    # example of params for a range - use time.time() for the window_start/end
    # "query": "rate(ceph_pool_rd[15m])",
    # "step": "10s",
    # "start": f"{window_start}",
    # "end": f"{window_end}"

    query_type = 'query'
    if 'start' in params:
        query_type = 'query_range'
    try:
        r = requests.get(f'{url}/api/v1/{query_type}',
                         params=params)
    except (requests.exceptions.ConnectionError, urllib3.exceptions.NewConnectionError, urllib3.exceptions.MaxRetryError):
        r = requests.Response()
        r.status_code = 500
    logger.debug(
        f"GET request to {url} completed with status code:{r.status_code}, {len(r.text)} bytes returned")
    return r


def get_prometheus_alerts(url: str) -> requests.Response:

    try:
        r = requests.get(f'{url}/api/v1/alerts')
    except (requests.exceptions.ConnectionError, urllib3.exceptions.NewConnectionError, urllib3.exceptions.MaxRetryError):
        r = requests.Response()
        r.status_code = 500
    logger.debug(
        f"GET request to {url} completed with status code:{r.status_code}, {len(r.text)} bytes returned")
    return r


def endpoint_available(url: str) -> bool:
    try:
        requests.get(f'{url}')
    except (requests.exceptions.ConnectionError, urllib3.exceptions.NewConnectionError, urllib3.exceptions.MaxRetryError):
        return False
    return True
