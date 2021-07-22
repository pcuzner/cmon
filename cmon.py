#!usr/bin/python3
# change to platform-python
import sys
import logging

try:
    import urwid  # type: ignore
except ImportError:
    urwid = None

try:
    import humanize  # type: ignore
except ImportError:
    humanize = None

from argparse import ArgumentParser
from requests.api import get
from typing import Optional, Tuple, List

from cmon.http_api import endpoint_available
from cmon.app import CmonApp
from cmon.mgr_prometheus import Metrics
from cmon.config import Config


LOG_FILENAME = 'cmon.log'
logger = logging.getLogger()
# console = logging.StreamHandler(sys.stdout)
logfile = logging.FileHandler(LOG_FILENAME, mode='w')
logger.setLevel(logging.INFO)
logger.addHandler(logfile)

log_levels = {
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'error': logging.ERROR
}


def get_parser():

    parser = ArgumentParser()
    parser.add_argument(
        '--log-level',
        type=str,
        choices=['info', 'debug', 'error'],
        default='info',
        help="logging mode for diagnostics"
    )
    parser.add_argument(
        '--log-file',
        type=str,
        default='cmon.log',
        help="filename for logging"
    )
    parser.add_argument(
        '--ceph-url',
        type=str,
        help="URL(s) of the ceph endpoints (e.g. http://<hostname>:<port>/metrics)"
    )
    parser.add_argument(
        '--prometheus-url',
        type=str,
        help="URL of the Prometheus server endpoint (hostname:port)"
    )
    parser.add_argument(
        '--alertmanager-url',
        type=str,
        help="URL of an alertmanager endpoint (hostname:port)"
    )
    parser.add_argument(
        '--refresh-interval',
        type=int,
        choices=[5,10,15],
        default=Config.defaults['refresh_interval'],
        help="Should be the same as the mgr/prometheus module's scrape_interval setting"
    )
    parser.add_argument(
        '--config-file',
        type=str,
        default=Config.defaults['config_file'],
        help="config file in yaml format for for default "
    )
    parser.add_argument(
        '-i', '--ioload',
        dest='ioload',
        action='store_true',
        default=Config.defaults['panel_ioload'],
        help="show I/O load panel "
    )
    parser.add_argument(
        '-a', '--alerts',
        dest='alerts',
        action='store_true',
        default=Config.defaults['panel_alerts'],
        help="show Prometheus Alerts"
    )
    parser.add_argument(
        '-p', '--pools',
        dest='pools',
        action='store_true',
        default=Config.defaults['panel_pools'],
        help="show Pool information"
    )
    parser.add_argument(
        '-r', '--rbds',
        dest='rbds',
        action='store_true',
        default=Config.defaults['panel_rbds'],
        help="show RBD performance information (if pool enabled in prometheus)"
    )
    parser.add_argument(
        '-g', '--rgws',
        dest='rgws',
        action='store_true',
        default=Config.defaults['panel_rgws'],
        help="show RGW performance information"
    )

    return parser


def check_ready(config: Config) -> List[str]:

    problems = []
    if not urwid:
        problems.append("python3-urwid is unavailable, unable to start")
    if not humanize:
        problems.append("python3-humanize is unavailable, unable to start")

    if config.prometheus_url:
        if not endpoint_available(f"{config.prometheus_url}/api/v1/status/config"):
            logger.warning(f"Unable to access prometheus endpoint at {config.prometheus_url}")

    if not config.ceph_url:
        problems.append("you must supply a ceph_url parameter for the mgr/prometheus connection")

    return problems


def main():
    config = Config(args)

    problems = check_ready(config)
    if problems:
        print("Unable to start cmon:")
        for p in problems:
            print(p)
        sys.exit(1)

    # keep mypy happy on the instantiate of the Metrics instance
    target_url = getattr(config, 'ceph_url')
    scrape_interval = getattr(config, 'refresh_interval')

    metrics = Metrics(
        target_url=target_url,
        scrape_interval=scrape_interval
    )

    metrics_usable = metrics.build()

    if metrics_usable:

        app = CmonApp(config, metrics)
        app.run()

    else:
        print("Unable to build the metrics from mgr/prometheus. Check your ceph-url setting is correct, or look at cmon.log")


if __name__ == "__main__":

    parser = get_parser()
    args = parser.parse_args()
    logfile = logging.FileHandler(args.log_file, mode='w')
    logger.addHandler(logfile)
    if args.log_level:
        logger.setLevel(log_levels[args.log_level])

    main()
