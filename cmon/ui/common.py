
import urwid
import logging

from typing import List

logger = logging.getLogger(__name__)

BLOCK_HORIZONTAL = [chr(x) for x in range(0x258F, 0x2587, -1)]


class Icon:

    up = ' \u25b2'
    down = ' \u25bc'
    arrow_right = "\u2794"


class CmonComponent(urwid.Padding):

    def __init__(self, metrics=None, visible=True):
        self.metrics = metrics
        self.visible = visible
        self.focus_support = False
        self.colour = 'normal'
        if self.visible:
            widget = self._build_widget()
        else:
            widget = urwid.BoxAdapter(urwid.ListBox(urwid.SimpleListWalker([])), height=0)
        super().__init__(widget)

    def show(self):
        self.original_widget = self._build_widget()

    def hide(self):
        self.original_widget = urwid.BoxAdapter(urwid.ListBox(urwid.SimpleListWalker([])), height=0)

    def _build_widget(self):
        return urwid.Padding(urwid.Text(""))

    def update(self):
        self.original_widget = self._build_widget()


class CmonTable(CmonComponent):

    table = None

    def update(self):
        logger.debug("in CmonTable update method")
        current_focus = self.table.widget.get_focus_path()
        self.original_widget = self._build_widget()

        try:
            self.table.widget.set_focus_path(current_focus)
            self.table._update_footer(current_focus[1])
        except IndexError:
            # if the table no longer contains active content, the old focus will not
            # apply, catch it and ignore
            pass


class BarChart(urwid.BarGraph):

    colour_schemes = {
        'blue': ('bg 1', 'bg 2'),
        'magenta': ('bg 3', 'bg 4')
    }

    def __init__(self, scheme: str, smooth: bool = True):
        if scheme not in BarChart.colour_schemes:
            raise ValueError(f"Attempted to create a barchart with an unknown color scheme: {scheme}")
        self.colours = BarChart.colour_schemes[scheme]
        satt = None
        c1, c2 = BarChart.colour_schemes[scheme]
        if smooth:
            satt = {(1, 0): f'{c1} smooth', (2, 0): f'{c2} smooth'}
        super().__init__(['bg background', f'{c1}', f'{c2}'], satt=satt)


class HStackBar(urwid.Text):
    """
    Horizontal Stack Bar. Inspired by https://github.com/tonycpsu/urwid-sparkwidgets

    :param items: list of tuple pairs i.e. color,value
    :param width: Width of the widget in characters.
    """

    chars = BLOCK_HORIZONTAL

    def __init__(self, items, width, color_prefix='pgs'):
        self.items = items
        self.width = width
        values = None
        total = None

        filtered_items = [i for i in self.items]
        # ugly brute force method to eliminate values too small to display
        while True:
            values = [i[1] if isinstance(i, tuple) else i
                      for i in filtered_items]

            if not len(values):
                raise Exception(self.items)
            total = sum(values)
            # v_min = min(values)
            # v_max = max(values)
            charwidth = total / self.width
            try:
                i = next(iter(filter(
                    lambda i: (i[1] if isinstance(i, tuple) else i) < charwidth,
                    filtered_items)))
                filtered_items.remove(i)
            except StopIteration:
                break

        charwidth = total / self.width
        # stepwidth = charwidth / len(self.chars)

        self.sparktext = []

        position = 0
        carryover = 0
        nchars = len(self.chars)
        lastcolor = None
        for i, item in enumerate(filtered_items):

            if isinstance(item, tuple):
                bcolor = f"{color_prefix} {item[0]}"
                v = item[1]
            else:
                raise ValueError("invalid item, must be a list of tuples")

            b = position + v + carryover
            if(carryover > 0):
                idx = int(carryover / charwidth * nchars)
                char = self.chars[idx]
                c = (f"{lastcolor}:{bcolor}", char)
                position += charwidth
                self.sparktext.append(c)

            rangewidth = b - position
            rangechars = int(round(rangewidth / charwidth))

            fcolor = bcolor
            chars = " " * rangechars
            position += rangechars * charwidth

            self.sparktext.append((f"{fcolor}:{bcolor}", chars))
            carryover = b - position
            lastcolor = bcolor

        if not self.sparktext:
            self.sparktext = ""

        super().__init__(self.sparktext)


class SingleStat(CmonComponent):
    title = 'TITLE'

    def _format(self):
        return 'WHATEVER'

    def _build_widget(self):
        return urwid.Padding(
            urwid.AttrMap(
                urwid.LineBox(
                    urwid.Text(f"\n{self._format()}\n", align='center'),
                    title=self.title
                ), self.colour),
            align='center',
            width=15
        )


class TableRow(urwid.WidgetWrap):
    def __init__(self, column_list, width_map, col_spacing, row_data):
        self.col_spacing = col_spacing
        self.column_list = column_list
        self.width_map = width_map
        self.row_data = row_data
        widget = self._build_row()
        super().__init__(widget)

    def _build_row(self):
        row_content = []
        for column_name in self.column_list:

            data = str(self.row_data.get(column_name, ""))
            # the text widget handles strings, so we need to cast the row_data to str to avoid attribute errors
            # set a default
            cell = f"{data:<{self.width_map[column_name]}}"
            if data:
                if data[0].isdigit():
                    cell = f"{data:>{self.width_map[column_name]}}"

            row_content.append((self.width_map[column_name], urwid.Text(cell)))  # str(self.row_data.get(column_name, "")))))
        return urwid.AttrMap(urwid.Columns(row_content, dividechars=self.col_spacing), None, focus_map='reversed')


class MyListBox(urwid.ListBox):

    def focus_next(self):
        try:
            self.body.set_focus(self.body.get_next(self.body.get_focus()[1])[1])
        except:  # noqa: E722
            pass

    def focus_previous(self):
        try:
            self.body.set_focus(self.body.get_prev(self.body.get_focus()[1])[1])
        except:  # noqa: E722
            pass


class DataTable(urwid.WidgetWrap):

    dflt_max_rows = 5

    def __init__(self, parent, column_list=None, data=None, description='rows', msg=None, col_spacing=2):
        self.parent = parent
        self.col_spacing = col_spacing
        self.msg = msg
        self.column_list = column_list
        self.data = data
        self.width_map = self._calc_column_widths()
        self.row_description = description

        self.t_head = self._headings()
        self.t_body = None
        self.t_footer = None
        self.row = 1

        self.widget = self._build_table()
        super().__init__(self.widget)

    def _headings(self):
        cols = []
        for col in self.column_list:
            cols.append((self.width_map[col], urwid.Text(col.replace('_', ' ').capitalize())))
        return urwid.Columns(cols, dividechars=self.col_spacing)

    def _build_rows(self) -> List[TableRow]:
        return [TableRow(self.column_list, self.width_map, self.col_spacing, r) for r in self.data]

    def _build_footer(self) -> urwid.Text:
        return \
            urwid.Text(f"{self.row}/{len(self.data)} {self.row_description}")

    def _update_footer(self, row_num: int):
        if row_num + 1 != self.row:
            self.row = row_num + 1  # row_num reflects the index position which starts at 0
            self.t_footer.set_text(f"{self.row}/{len(self.data)} {self.row_description}")

    def _build_table(self):
        body_height = DataTable.dflt_max_rows if len(self.data) > 4 else len(self.data) + 1
        if self.data:
            rows = self._build_rows()
            self.t_footer = self._build_footer()
            self.t_body = MyListBox(urwid.SimpleListWalker(rows))

        else:
            self.t_footer = urwid.Divider(" ")
            self.t_body = MyListBox(
                urwid.SimpleListWalker([
                    urwid.Text(('warning', self.msg))
                ])
            )

        return \
            urwid.Pile([
                self.t_head,
                urwid.BoxAdapter(self.t_body, height=body_height),
                self.t_footer,
            ])

    def _calc_column_widths(self):
        width_map = {}

        for c in self.column_list:
            width_map[c] = len(c)
            for r in self.data:
                col_size = len(str(r.get(c, '')))
                if col_size > width_map[c]:
                    width_map[c] = col_size
        return width_map

    def _move(self, direction: str):
        if direction == 'up':
            self.t_body.focus_previous()
            self._update_footer(self.widget.get_focus_path()[1])
        elif direction == 'down':
            self.t_body.focus_next()
            self._update_footer(self.widget.get_focus_path()[1])

    def keypress(self, size, key):
        logger.debug(f"processing keypress {key} in Datatable")
        if self.t_body:
            if key == 'down':
                self._move('down')
            elif key == 'up':
                self._move('up')

        self.parent.keypress(key)

    def mouse_event(self, size, event, button, col, row, wrow):
        # print(event) # "mouse press"
        # print(button) # button no. 1-5, 1=left, 2=middle, 3=right, 4-wheepup, 5 wheel-down
        logger.debug(f"processing mouse action in Datatable event={event} button={button}")
        if event == 'mouse press':
            if button == 4:
                self._move('up')

            elif button == 5:
                self._move('down')
