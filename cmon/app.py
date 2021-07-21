from cmon.ui.panels import RGWPerformance
import urwid
import sys
import time
import logging

from urllib.parse import urlparse

from cmon import __version__ as cmon_version
from .ui import (
    Inventory,
    Health,
    Capacity,
    IOPS,
    Throughput,
    HelpInformation,
    PrometheusAlerts,
    IOGraphs,
    PoolInfo,
    PGStatus,
    RBDPerformance,
    RefreshTimer
)

from .utils import timeit

logger = logging.getLogger(__name__)

# when background is set to '', it inherits from the terminal
# the pallete needs to define the transitions using fcolor:bcolor notation for the hStackBar widget
# we should start off with defining an initial color set and then automatically
# fill inth transition colors
palette = [
    ('pg normal', 'white', 'dark gray'),
    ('pg complete', 'white', 'dark green'),
    ('pg complete warning', 'white', 'yellow'),
    ('pg complete error', 'white', 'dark red'),
    ('pg smooth', 'dark green', 'dark gray'),
    ('pg smooth warning', 'yellow', 'dark gray'),
    ('pg smooth error', 'dark red', 'dark gray'),
    ('bg background', 'light gray', ''),
    ('bg 1', 'black', 'dark blue', 'standout'),
    ('bg 1 smooth', 'dark blue', ''),
    ('bg 2', 'black', 'light blue', 'standout'),
    ('bg 2 smooth', 'light blue', ''),
    ('bg 3', 'black', 'dark magenta', 'standout'),
    ('bg 3 smooth', 'dark magenta', ''),
    ('bg 4', 'black', 'light magenta', 'standout'),
    ('bg 4 smooth', 'light magenta', ''),
    ('title', 'white', 'dark blue'),
    ('pgm name', 'white,bold,underline', ''),
    ('normal', '', ''),
    ('bold', 'white,bold', ''),
    ('message', 'black', 'light gray'),
    ('ok', 'dark green', ''),
    ('warning', 'yellow', ''),
    ('warning reversed', 'black', 'yellow'),
    ('error', 'light red', ''),
    ('error reversed', 'white', 'dark red'),
    ('reversed', 'white', 'dark gray'),
    ('pgs OK', 'dark green', ''),
    ("pgs warning", 'yellow', ''),
    ("pgs error", 'dark red', ''),
    ('pgs unknown', 'dark magenta', ''),
    ("pgs OK:pgs OK", "dark green", "dark green"),
    ("pgs OK:pgs warning", "dark green", "yellow"),
    ("pgs OK:pgs error", "dark green", "dark red"),
    ("pgs OK:pgs unknown", "dark green", "dark magenta"),
    ("pgs warning:pgs warning", "yellow", "yellow"),
    ("pgs warning:pgs error", "yellow", "dark red"),
    ("pgs warning:pgs unknown", "yellow", "dark magenta"),
    ("pgs error:pgs error", "dark red", "dark red"),
    ("pgs error:pgs unknown", "dark red", "dark magenta"),
    ("pgs unknown:pgs unknown", "dark magenta", "dark magenta"),
]


class CmonApp:

    def __init__(self, config, metrics):
        self.config = config
        self.top_rbd_count = 10
        self.refresh_interval = self.config.refresh_interval
        self.refresh_countdown = self.refresh_interval
        self.loop = None
        self.mgr_ip = self.config.ceph_url
        self.prometheus_url = self.config.prometheus_url or None
        self.metrics = metrics   # add the metrics object here!

        self.panels = [
            'inventory',
            'capacity',
            'health',
            'iops',
            'throughput',
            'alerts',
            'pool_info',
            'rbd_performance',
            'io_load_graphs',
            'pg_status',
            'rgw_performance',
        ]

        self.inventory = Inventory(metrics=self.metrics)
        self.capacity = Capacity(metrics=self.metrics)
        self.health = Health(metrics=self.metrics)
        self.iops = IOPS(metrics=self.metrics)
        self.throughput = Throughput(metrics=self.metrics)
        self.alerts = PrometheusAlerts(self)
        self.io_load_graphs = IOGraphs(self)
        self.pg_status = PGStatus(metrics=self.metrics)

        self.pool_info = PoolInfo(self)
        self.rbd_performance = RBDPerformance(self)
        self.rgw_performance = RGWPerformance(self)

        self.help = HelpInformation()
        self.help.visible = False

        self.refresh_timer = RefreshTimer(self.refresh_interval)

        self.toggled_panels = urwid.Pile([
            self.alerts,
            self.pool_info,
            self.rbd_performance,
            self.rgw_performance,
        ])

        self.ptr = 0

    def _build_ui(self):

        header = urwid.Columns([
            urwid.Text(('title', f" cmon  [mgr @ {urlparse(self.mgr_ip).netloc}]"), align='left'),
            urwid.Text(('title', f"v{cmon_version} "), align='right')
        ])
        title = urwid.AttrMap(header, 'title')
        footer = urwid.AttrMap(
            urwid.Columns([
                urwid.Text(('message', " Use 'h' for help, or 'q' to Quit."), align='left'),
                self.refresh_timer
            ]),
            'message')

        # the iographs are not sized. if the are it creates more of a UX problem if the user
        # resizes the terminal window
        self.body = urwid.Filler(
            urwid.Pile([
                urwid.Divider(),
                urwid.Columns([
                    (32, urwid.Pile([self.inventory])),
                    (48, urwid.Pile([
                        urwid.Columns([self.health, self.iops, self.throughput], dividechars=0),
                        self.pg_status,
                        self.capacity])),
                    self.io_load_graphs
                ], dividechars=0),
                self.toggled_panels,
                # self.alerts,
                # self.pool_info,
                # self.rbd_performance,
                # self.rgw_performance,
            ]),
            'top')

        self.ui = urwid.Frame(
            self.body,
            header=title,
            footer=footer)

    def _manage_panels(self, panel):

        panel.visible = not panel.visible
        if panel.visible:
            panel.show()
            if panel.focus_support:
                self.toggled_panels.set_focus(panel)
        else:
            panel.hide()

    def _switch_panel(self):

        current = self.toggled_panels.get_focus()
        logger.debug(f"toggled panels pile, current focus is {current}")

        # contents returns  MonitoredFocusList containing a tuple of (object, weight)
        active_panels = [p[0] for p in self.toggled_panels.contents if p[0].visible]
        if len(active_panels) == 0:
            logger.debug("tab not relevant - no optional panels active")
            return
        if len(active_panels) == 1:
            logger.debug("tab pressed, but ignored, since there is only one panel shown")
            return

        logger.debug(f"active panels are {active_panels}")

        panel_idx = active_panels.index(current) + 1

        if panel_idx > len(active_panels) - 1:
            logger.debug("panel idx is too big, resetting")
            next_panel = active_panels[0]
        else:
            logger.debug("panel idx ok to use")
            next_panel = active_panels[panel_idx]

        self.toggled_panels.set_focus(next_panel)

    def keypress(self, key):
        if key in ('q', 'Q'):
            raise urwid.ExitMainLoop()

        if key in ('h', 'H'):
            self.help.visible = not self.help.visible
            if self.help.visible:
                self.loop.widget = urwid.Overlay(
                    self.help,
                    self.ui,
                    align=("relative", 50),
                    valign=("relative", 50),
                    width=("relative", 60),
                    height=35, min_width=50, min_height=35)
            else:
                # reset the main loop widget to remove the help overlay
                self.loop.widget = self.ui

        if not self.help.visible:

            if key in ('p', 'P'):
                self._manage_panels(self.pool_info)

            elif key in ('r', 'R'):
                self._manage_panels(self.rbd_performance)

            elif key in ('i', 'I'):
                self._manage_panels(self.io_load_graphs)

            elif key in ('a', 'A'):
                self._manage_panels(self.alerts)

            elif key in ('g', 'G'):
                self._manage_panels(self.rgw_performance)

            elif key == 'tab':
                logger.info("main loop processing a tab keypress")
                self._switch_panel()

    @timeit
    def _update_panels(self):
        for panel_name in self.panels:
            panel = getattr(self, panel_name)
            if panel.visible:
                panel.update()

    def update(self, loop_object, data):
        # Update the metrics
        self.refresh_countdown -= 1
        if self.refresh_countdown == 0:
            self.refresh_countdown = self.refresh_interval

            self.metrics.update()
            self._update_panels()

        self.refresh_timer.update(self.refresh_countdown)

        self.loop.set_alarm_at(time.time() + 1, self.update, None)

    def run(self):

        self._build_ui()

        self.loop = urwid.MainLoop(
            self.ui,
            palette=palette,
            unhandled_input=self.keypress)

        self.loop.set_alarm_at(time.time() + 1, self.update, None)
        try:
            self.loop.run()
        except urwid.widget.WidgetError:
            print("Window is too small to display the cmon UI. Needs to be at least 140 chars wide")
            sys.exit(1)
