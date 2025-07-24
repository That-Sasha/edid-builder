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

    @property
    def manufacturer_id(self):
        # read the wiki, this id encoding fucking sucks
        class ManufacturerId:

            def __init__(self, value):
                self._value = value

            @property
            def value(self):
                return self._value

            @property
            def bytes(self):
                return int('0' + ''.join([format(ord(x) - 64, '05b') for x in self._value.upper()]),2).to_bytes(2)

            @property
            def byte_range(self):
                return [8,10]

        return ManufacturerId(self._manufacturer_id)

    @manufacturer_id.setter
    def manufacturer_id(self, value):
        self._manufacturer_id = value

    @property
    def product_code(self):
        class ProductCode:

            def __init__(self, value):
                self._value = value

            @property
            def value(self):
                return self._value

            @property
            def bytes(self):
                return bytes.fromhex(self._value)

            @property
            def byte_range(self):
                return [10,12]

        return ProductCode(self._product_code)

    @product_code.setter
    def product_code(self, value):
        self._product_code = value

    @property
    def serial_num(self):
        class SerialNum:

            def __init__(self, value):
                self._value = value

            @property
            def value(self):
                return self._value

            @property
            def bytes(self):
                return self._value.to_bytes(4)

            @property
            def byte_range(self):
                return [12,16]

        return SerialNum(self._serial_num)

    @serial_num.setter
    def serial_num(self, value):
        self._serial_num = value

    @property
    def manufacture_week(self):
        class ManufactureWeek:

            def __init__(self, value):
                self._value = value

            @property
            def value(self):
                return self._value

            @property
            def bytes(self):
                return self._value.to_bytes()

            @property
            def byte_range(self):
                return [16,17]

        return ManufactureWeek(self._manufacture_week)

    @manufacture_week.setter
    def manufacture_week(self, value):
        self._manufacture_week = value

    @property
    def manufacture_year(self):
        class ManufactureYear:

            def __init__(self, value):
                self._value = value

            @property
            def value(self):
                return self._value

            @property
            def bytes(self):
                return (self._value - 1990).to_bytes()

            @property
            def byte_range(self):
                return [17,18]

        return ManufactureYear(self._manufacture_year)

    @manufacture_year.setter
    def manufacture_year(self, value):
        self._manufacture_year = value

    @property
    def edid_version(self):
        class EdidVersion:

            def __init__(self, value):
                self._value = value

            @property
            def value(self):
                return self._value

            @property
            def bytes(self):
                return bytes([int(x) for x in self._value.split('.')])

            @property
            def byte_range(self):
                return [18,20]

        return EdidVersion(self._edid_version)

    @edid_version.setter
    def edid_version(self, value):
        self._edid_version = value

    @property
    def bytes(self):
        return (
            bytes.fromhex(self.HEADER_PATTERN)
            + self.manufacturer_id.bytes
            + self.product_code.bytes
            + self.serial_num.bytes
            + self.manufacture_week.bytes
            + self.manufacture_year.bytes
            + self.edid_version.bytes
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
        return bytes_to_hex_block(self.bytes)

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

