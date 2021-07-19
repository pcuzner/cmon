
import urwid
import logging

from .common import CmonComponent

logger = logging.getLogger(__name__)


class RefreshTimer(CmonComponent):

    def __init__(self, refresh_interval):
        self.value = refresh_interval
        super().__init__()

    def _build_widget(self):
        return \
            urwid.Padding(
                urwid.Text(f"Refresh in: {self.value:>2}s", align='right'),
                right=2
            )

    def update(self, new_value):
        self.value = new_value
        self.original_widget = self._build_widget()
