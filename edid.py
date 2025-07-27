import itertools
import re
import string

from difflib import SequenceMatcher
from math import floor
from textwrap import wrap

def bytes_to_hex_block(byte_array, width=16):

    hex_str = ' '.join(format(byte, '02x') for byte in byte_array)
    return '\n'.join(wrap(hex_str, width=width * 3)).upper()

def simple_test(test_class, expected):

    actual = str(test_class)

    zipped_list = list(itertools.zip_longest(actual, expected, fillvalue='X'))
    highlight_match = ""
    bad_bytes = []


    for idx, (act, exp) in enumerate(zipped_list):
        if act == 'X':
            highlight_match += exp
        elif act == exp:
            highlight_match += f'\033[92m{act}\033[0m'
        else:
            highlight_match += f'\033[91m{act}\033[0m'
            bad_bytes.append(floor(idx / 3))

    bad_bytes = set(bad_bytes)

    if len(bad_bytes) > 0:

        bad_data_dicts = [header.data_at_position(x) for x in bad_bytes]

        error_string = '\n'.join([
            '\nMismatch in bytes: ' + ', '.join([str(x) for x in bad_bytes]),
            '',
            highlight_match,
            '\033[95m',
            'Bad fields: ',
            *[str(i) for n, i in enumerate(bad_data_dicts) if i not in bad_data_dicts[n + 1:]]
        ])

        assert False, error_string
    else:
        print(f'Simple test success!\n{highlight_match}')


class EdidPropertyValue:
    def __init__(self, value, byte_val, byte_range):
        self.value = value
        self.as_bytes = byte_val
        self._byte_range = byte_range

    @property
    def byte_range(self):
        return self._byte_range


class EdidProperty:

    def __init__(self, getter, setter=None, byte_range=None, byte_converter = lambda x: x.to_bytes()):
        self._getter = getter
        self._setter = setter
        self._byte_range = byte_range
        self._byte_converter = byte_converter

    def __set__(self, obj, value):
        if self.setter is None:
            raise AttributeError
        self._setter(obj, value)

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        if self._getter is None:
            raise AttributeError
        value = self._getter(obj)
        return EdidPropertyValue(value, self._byte_converter(value), self._byte_range)

    def setter(self, setter):
        return type(self)(self._getter, setter, self._byte_range, self._byte_converter)

    def getter(self, getter):
        return type(self)(getter, self._setter, self._byte_range, self._byte_converter)

    def byte_converter(self, converter):
        return type(self)(self._getter, self._setter, self._byte_range, converter)

    def _byte_range_setter(self, value):
        self._byte_range = value

    # This is hacky and I don't like it, but it seems to work
    @property
    def byte_range():
        pass

    @byte_range.setter
    def byte_range(self, value):
        self._byte_range_setter(value)


class Header():
# 20 bytes total
#
# 0 - 7 fixed pattern
# 8 - 9 manufacturer ID big-endian
# 10 - 11 manufacturer product code little-endian
# 12 - 15 serial number little-endian
# 16 and 17 week and year of manufacture respectively
# 18 and 19, major and minor edid version respectively

    HEADER_PATTERN = "00 FF FF FF FF FF FF 00"

    def __init__(self, manufacturer_id='YTS', product_code='B106', serial_num=0, manufacture_week=0, manufacture_year=2025, edid_version='1.4'):


        assert isinstance(manufacturer_id, str) and re.search(r'^[a-zA-Z]{3}$', manufacturer_id), 'Manufacturer ID must be a three character string'
        assert all(c in string.hexdigits for c in product_code), 'Product code must be a 4 digit hexadecimal string'
        assert serial_num <= 4294967294, 'Serial number must be an integer <= 4294967294'
        assert manufacture_week <= 255, 'Week of manufacture must be an integer <= 255'
        assert manufacture_year <= 2245, 'Year of manufacture must be an integer <= 2245'
        assert isinstance(edid_version, str) and re.search(r'^\d\.\d$', edid_version)

        self._manufacturer_id = manufacturer_id
        self._product_code = product_code
        self._serial_num = serial_num
        self._manufacture_week = manufacture_week
        self._manufacture_year = manufacture_year
        self._edid_version = edid_version


    @EdidProperty
    def manufacturer_id(self):
        return self._manufacturer_id

    @manufacturer_id.setter
    def manufacturer_id(self, value):
        self._manufacturer_id = value

    @manufacturer_id.byte_converter
    def manufacturer_id(value):
        return int('0' + ''.join([format(ord(x) - 64, '05b') for x in value.upper()]),2).to_bytes(2)

    manufacturer_id.byte_range = [8,10]

    # ===============================================================================================

    @EdidProperty
    def product_code(self):
        return self._product_code

    @product_code.setter
    def product_code(self, value):
        self._product_code = value

    @product_code.byte_converter
    def product_code(value):
        return bytes.fromhex(value)

    product_code.byte_range = [10,12]

    # ===============================================================================================

    @EdidProperty
    def serial_num(self):
        return self._serial_num

    @serial_num.setter
    def serial_num(self, value):
        self._serial_num = value

    @serial_num.byte_converter
    def serial_num(value):
        return value.to_bytes(4)

    product_code.byte_range = [12,16]

    # ===============================================================================================

    @EdidProperty
    def manufacture_week(self):
        return self._manufacture_week

    @manufacture_week.setter
    def manufacture_week(self, value):
        self._manufacture_week = value

    product_code.byte_range = [16,17]

    # ===============================================================================================

    @EdidProperty
    def manufacture_year(self):
        return self._manufacture_year

    @manufacture_year.setter
    def manufacture_year(self, value):
        self._manufacture_year = value

    @manufacture_year.byte_converter
    def manufacture_year(value):
        return (value - 1990).to_bytes()

    product_code.byte_range = [17,18]

    # ===============================================================================================

    @EdidProperty
    def edid_version(self):
        return self._edid_version

    @edid_version.setter
    def edid_version(self, value):
        self._edid_version = value

    @edid_version.byte_converter
    def edid_version(value):
        return bytes([int(x) for x in value.split('.')])

    product_code.byte_range = [19,20]

    # ===============================================================================================

    @property
    def as_bytes(self):
        return (
            bytes.fromhex(self.HEADER_PATTERN)
            + self.manufacturer_id.as_bytes
            + self.product_code.as_bytes
            + self.serial_num.as_bytes
            + self.manufacture_week.as_bytes
            + self.manufacture_year.as_bytes
            + self.edid_version.as_bytes
            )

    @property
    def byte_range(self):
        return [0,20]

    def data_at_position(self, value):
        # returns the data that contains the specified byte
        properties = [a for a in dir(self) if (f'.{a}.<locals>.'.join(list(map(lambda x: type(x).__name__, [self, getattr(self, a)]))))  in str(type(getattr(self, a)))]
        for prop in properties:
            byte_range = getattr(self, prop).byte_range
            if value in range(*byte_range):
                return {'name' : prop, 'value' : getattr(self, prop).value, 'range' : byte_range}


        return False

    def __str__(self):
        return bytes_to_hex_block(self.as_bytes)


class EstablishedTiming():
    @property
    def bytes(self):
        return bytes(3)

    def __str__(self):
        return bytes_to_hex_block(self.bytes)



# Simple test case
with(open('3840x2160.hex', 'r')) as file:
    expected = file.read()


header = Header(
    manufacturer_id='LNX',
    product_code='0000',
    serial_num=0,
    manufacture_week=5,
    manufacture_year=2012,
    edid_version='1.3'
)

simple_test(header, expected)

