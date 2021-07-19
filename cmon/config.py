from argparse import ArgumentParser
import os
import sys
import logging
import yaml

logger = logging.getLogger(__name__)


class Config:
    defaults = {
        "ceph_url": "http://localhost:9283/metrics",
        "prometheus_url": "",
        "alertmanager_url": "",
        "refresh_interval": 15,
        "config_file": os.path.join(os.path.expanduser('~'), 'cmon.yaml'),
        "panel_ioload": False,
        "panel_alerts": False,
        "panel_pools": False,
        "panel_rbds": False,
        "panel_rgws": False,
    }

    def __init__(self, args: ArgumentParser):
        self.args = args
        self.ceph_url = Config.defaults['ceph_url']
        self.prometheus_url = Config.defaults['prometheus_url']
        self.refresh_interval = Config.defaults['refresh_interval']
        self.panel_ioload = Config.defaults['panel_ioload']
        self.panel_alerts = Config.defaults['panel_alerts']
        self.panel_pools = Config.defaults['panel_pools']
        self.panel_rbds = Config.defaults['panel_rbds']
        self.panel_rgws = Config.defaults['panel_rgws']

        self._load_cfg_file()

        self._apply_env()

        self._apply_args()

        self._validate()

        self.show_config()

    def _load_cfg_file(self) -> None:
        # load defaults from local file if present
        if os.path.exists(self.args.config_file):
            try:
                with open(self.args.config_file, 'r') as f:
                    cfg = yaml.safe_load(f)
            except yaml.YAMLError:
                print(f"Invalid yaml in {self.args.config_file}")
                sys.exit(1)
            except OSError:
                print(f"Unable to open/access the config file at {self.args.config_file}")
                sys.exit(1)
            for k in cfg:
                if k in Config.defaults:
                    logger.info(f"setting {k} from config file")
                    setattr(self, k, cfg[k])
                else:
                    logger.warning(f"config file load skipped bogus setting: {k}")

        else:
            logger.info(f"local config file ({self.args.config_file})not found, using defaults")

    def _apply_env(self):
        for name in Config.defaults.keys():
            env_value = os.environ.get(name.upper(), None)
            if env_value:
                logger.info(f"applying environment variable setting for {name}")
                setattr(self, name, env_value)

    def _apply_args(self) -> None:
        if self.args.ceph_url:
            logger.info("applying runtime override for ceph_url")
            self.ceph_url = self.args.ceph_url

        if self.args.prometheus_url:
            logger.info("applying runtime override for prometheus_url")
            self.prometheus_url = self.args.prometheus_url

        if self.args.refresh_interval and self.args.refresh_interval != Config.defaults['refresh_interval']:
            logger.info("applying runtime override for refresh_interval")
            self.refresh_interval = self.args.refresh_interval

        if self.args.alerts != Config.defaults['panel_alerts']:
            self.panel_alerts = self.args.alerts
        if self.args.ioload != Config.defaults['panel_ioload']:
            self.panel_ioload = self.args.ioload
        if self.args.pools != Config.defaults['panel_pools']:
            self.panel_pools = self.args.pools
        if self.args.rbds != Config.defaults['panel_rbds']:
            self.panel_rbds = self.args.rbds
        if self.args.rgws != Config.defaults['panel_rgws']:
            self.panel_rgws = self.args.rgws

    def _validate(self):
        # TODO validate the settings we have, url's valid etc
        pass

    def show_config(self) -> None:
        logger.info("cmon parameters configured:")
        logger.info(f"ceph url: {self.ceph_url}")
        logger.info(f"prometheus url: {self.prometheus_url}")
        logger.info(f"refresh interval: {self.refresh_interval}")

        logger.info(f"alerts: {self.panel_alerts}")
        logger.info(f"ioload: {self.panel_ioload}")
        logger.info(f"pools: {self.panel_pools}")
        logger.info(f"rbds: {self.panel_rbds}")
        logger.info(f"rgws: {self.panel_rgws}")
