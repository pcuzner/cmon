
import time
import math
import logging
import socket
import humanize
import datetime

from typing import Dict, List, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# TERMCOLORS = {
#     "RED": "\N{ESC}[31m",
#     "DEFAULT": "\u001b[0m"
# }


def timeit(f):
    def wrapper(*args, **kwargs):
        st = time.time()
        result = f(*args, **kwargs)
        logger.debug(f"Function '{f.__name__}' elapsed time {time.time() - st}s")
        return result
    return wrapper


def age(timestamp: str) -> str:
    # Prometheus provides 9 digit precision, but datetime is only good for 6
    # so we need to adjust the timestamp to determine the age
    n = ''
    r = timestamp[::-1]
    for ptr in range(len(r)):
        if r[ptr].isdigit():
            n = r[:ptr] + r[ptr + 3:]
            break
    if not n:
        raise ValueError(f"Unable to parse the timestamp : {timestamp}")

    adjusted_dt = datetime.datetime.strptime(n[::-1], '%Y-%m-%dT%H:%M:%S.%fZ')
    return humanize.naturaltime(adjusted_dt)


class Filter:

    def __init__(self, f_spec: Dict[str, str]):
        if 'value' in f_spec:
            self.value = float(f_spec['value'])
        else:
            self.value = None
        for k in f_spec:
            if k != "value":
                setattr(self, k, f_spec[k])


def count_unique(data, var_name):
    summary = {}
    for i in data:
        summary_key = i[var_name]
        if summary_key in summary:
            summary[summary_key] += 1
        else:
            summary[summary_key] = 1
    return summary


def relabel(data, old_label, new_label):
    for i in data:
        i[new_label] = i[old_label]
        del i[old_label]
    return data


def merge_dict_lists_by_key(base_list, updates, key_names: List[str]):
    # FIXME
    # this is function can be slow large lists and multiple keys and should be avoided in
    # those cases e.g 4 lists of 1024 entries, matched by 3 keys = 2sec!
    for base_item in base_list:
        # key = base_item[key_names[0]]
        for update in updates:
            for i in update:
                if all(base_item[k] == i[k] for k in key_names):
                    base_item.update(i)
                    break
    return base_list


def valid_url(url: str) -> Tuple[bool, str]:
    u = urlparse(url)
    if not u.hostname:
        return False, 'hostname missing'
    if not u.port:
        return False, 'http port missing'

    try:
        socket.gethostbyname(u.hostname)
    except socket.gaierror:
        return False, 'Invalid hostname, DNS lookup failed'

    return True, ''


class GraphScale:
    valid_units = ['short', 'dec-bytes', 'bin-bytes']
    # src: https://stackoverflow.com/questions/8506881/nice-label-algorithm-for-charts-with-minimum-ticks

    def __init__(self, minv, maxv, unit: str = 'short'):
        if unit not in GraphScale.valid_units:
            raise ValueError(f"Invalid unit type received ({unit}): needs to be one of {GraphScale.valid_units}")

        self.max_ticks = 3
        self.tick_spacing = 0
        self.lst = 10
        self.min = 0
        self.max = 0
        self.min_point = minv
        self.max_point = maxv
        self.unit = unit
        self.calculate()

    def calculate(self):
        if self.max_point > 3:
            self.lst = self.nice_number(self.max_point - self.min_point, False)
            self.tick_spacing = int(self.nice_number(self.lst / (self.max_ticks - 1), True))
            self.min = int(math.floor(self.min_point / self.tick_spacing) * self.tick_spacing)
            self.max = int(math.ceil(self.max_point / self.tick_spacing) * self.tick_spacing)
        else:
            self.max = self.max_point

    @property
    def labels(self) -> List[Tuple[int, str]]:
        ticks = []
        if self.max_point > 3:
            for n in range(self.tick_spacing, self.max, self.tick_spacing):

                if self.unit == 'short':
                    label = humanize.naturalsize(n, binary=False)
                    v, u = label.split(' ')
                    if u.upper().startswith('BYTE'):  # BYTE or BYTES
                        label = v
                    else:
                        label = f"{v} {u[:-1].upper()}"
                elif self.unit == 'dec-bytes':
                    label = humanize.naturalsize(n, binary=False)
                    label = label.replace('Bytes', 'B')
                elif self.unit == 'bin-bytes':
                    label = humanize.naturalsize(n, binary=True)
                    label = label.replace('Bytes', 'B')

                else:
                    raise ValueError("Invalid unit is set for the scale")
                ticks.append((n, label))
        else:
            ticks = [(0, '0'), (self.max_point, f"{self.max_point:.1f}")]

        return ticks

    def nice_number(self, lst, rround):
        self.lst = lst
        exponent = 0  # exponent of range
        fraction = 0  # fractional part of range
        nice_fraction = 0  # nice, rounded fraction

        exponent = math.floor(math.log10(self.lst))
        fraction = self.lst / math.pow(10, exponent)

        if (self.lst):
            if (fraction < 1.5):
                nice_fraction = 1
            elif (fraction < 3):
                nice_fraction = 2
            elif (fraction < 7):
                nice_fraction = 5
            else:
                nice_fraction = 10
        else:
            if (fraction <= 1):
                nice_fraction = 1
            elif (fraction <= 2):
                nice_fraction = 2
            elif (fraction <= 5):
                nice_fraction = 5
            else:
                nice_fraction = 10

        return nice_fraction * math.pow(10, exponent)

    def set_min_max(self, min_point, max_point) -> None:
        self.min_point = min_point
        self.max_point = max_point
        self.calculate()

    def set_max_ticks(self, max_ticks) -> None:
        self.max_ticks = max_ticks
        self.calculate()

    def __str__(self) -> str:
        s = ""
        s += f"lst = {self.lst}\n"
        s += f"tick_spacing = {self.tick_spacing}\n"
        s += f"min = {self.min}\n"
        s += f"max = {self.max}\n"
        return s
