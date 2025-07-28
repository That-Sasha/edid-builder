import itertools
import re
import string

from difflib import SequenceMatcher
from functools import reduce
from math import ceil, floor, log
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

        bad_data_dicts = [test_class.data_at_position(x) for x in bad_bytes]

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

class BaseEDID:
    def __init__(self, header, basic_display_parameters, chromaticity_coordinates, standard_timings, established_timing='000000'):
        if not isinstance(standard_timings, list):
            standard_timings = [standard_timings]
        assert all(c in string.hexdigits for c in established_timing), 'Red green lsb must be a 6 digit hexadecimal string'
        assert all(isinstance(timing, StandardTiming) for timing in standard_timings) and 1 <= len(standard_timings) <= 8, 'Standard timings must be a list of at least 1 and at most 8 standard timing objects'

        self._header = header
        self._basic_display_parameters = basic_display_parameters
        self._chromaticity_coordinates = chromaticity_coordinates
        self._established_timing = established_timing

        self._standard_timings = standard_timings


    @EdidProperty
    def header(self):
        return self._header

    @header.setter
    def header(self, value):
        self._header = value

    @header.byte_converter
    def header(value):
        return value.as_bytes

    header.byte_range = [0,20]

    # ===============================================================================================


    @EdidProperty
    def basic_display_parameters(self):
        return self._basic_display_parameters

    @basic_display_parameters.setter
    def basic_display_parameters(self, value):
        self._basic_display_parameters = value

    @basic_display_parameters.byte_converter
    def basic_display_parameters(value):
        return value.as_bytes

    basic_display_parameters.byte_range = [20,25]

    # ===============================================================================================

    @EdidProperty
    def chromaticity_coordinates(self):
        return self._chromaticity_coordinates

    @chromaticity_coordinates.setter
    def chromaticity_coordinates(self, value):
        self._chromaticity_coordinates = value

    @chromaticity_coordinates.byte_converter
    def chromaticity_coordinates(value):
        return value.as_bytes

    chromaticity_coordinates.byte_range = [25,35]

    # ===============================================================================================

    @EdidProperty
    def established_timing(self):
        return self._established_timing

    @established_timing.setter
    def established_timing(self, value):
        self._established_timing = value

    @established_timing.byte_converter
    def established_timing(value):
        return bytes.fromhex(value)

    established_timing.byte_range = [35,38]

    # ===============================================================================================

    @EdidProperty
    def standard_timings(self):
        return self._standard_timings

    @standard_timings.setter
    def standard_timings(self, value):
        self._standard_timings = value

    @standard_timings.byte_converter
    def standard_timings(value):
        empty_count = 8 - len(value)

        if empty_count > 0:
            value += [StandardTiming.empty()] * empty_count

        return reduce(lambda x, y: x + y, [timing.as_bytes for timing in value])

    standard_timings.byte_range = [38,54]

    # ===============================================================================================


    @property
    def as_bytes(self):
        return (
                self.header.as_bytes +
                self.basic_display_parameters.as_bytes +
                self.chromaticity_coordinates.as_bytes +
                self.established_timing.as_bytes +
                self.standard_timings.as_bytes
            )

    def data_at_position(self, value):
        # TODO - factor ths out and add an offset value or something to calculate absolute position
        # returns the data that contains the specified byte
        properties = [a for a in dir(self) if 'EdidPropertyValue' in str(type(getattr(self, a)))]

        for prop in properties:
            byte_range = getattr(self, prop).byte_range
            print(byte_range)
            if value in range(*byte_range):
                prop_value = getattr(self, prop).value

                if 'data_at_position' in dir(prop_value):
                    prop_value = prop_value.data_at_position(value)

                return {'name' : prop, 'value' : prop_value, 'range' : byte_range}

        return False

    def __str__(self):
        return bytes_to_hex_block(self.as_bytes)

class Header:

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

    serial_num.byte_range = [12,16]

    # ===============================================================================================

    @EdidProperty
    def manufacture_week(self):
        return self._manufacture_week

    @manufacture_week.setter
    def manufacture_week(self, value):
        self._manufacture_week = value

    manufacture_week.byte_range = [16,17]

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

    manufacture_year.byte_range = [17,18]

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

    edid_version.byte_range = [19,20]

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

    def data_at_position(self, value):
        # returns the data that contains the specified byte
        properties = [a for a in dir(self) if 'EdidPropertyValue' in str(type(getattr(self, a)))]

        for prop in properties:
            print(prop)
            byte_range = getattr(self, prop).byte_range
            if value in range(*byte_range):
                return {'name' : prop, 'value' : getattr(self, prop).value, 'range' : byte_range}


        return False

    def __str__(self):
        return bytes_to_hex_block(self.as_bytes)

class BasicDisplayParameters:

    def __init__(self, video_params='B5', horizontal_size=100, vertical_size=56, gamma=2.2, suported_features='FF'):

        assert all(c in string.hexdigits for c in video_params), 'Video parameters must be a 2 digit hexadecimal string'
        assert 1 <= horizontal_size <= 255, 'Horizontal size must be an integer 1 - 255'
        assert 1 <= vertical_size <= 255, 'Vertical size must be an integer 1 - 255'
        assert 1.00 <= gamma <= 3.54, 'Gamma must be an integer 1.00 - 3.54'
        assert all(c in string.hexdigits for c in suported_features), 'Supported features must be a 2 digit hexadecimal string'

        self._video_params = video_params
        self._horizontal_size = horizontal_size
        self._vertical_size = vertical_size
        self._gamma = gamma
        self._suported_features = suported_features


    @EdidProperty
    def video_params(self):
        return self._video_params

    @video_params.setter
    def video_params(self, value):
        self._video_params = value

    @video_params.byte_converter
    def video_params(value):
        return bytes.fromhex(value)

    video_params.byte_range = [0,1]

    # ===============================================================================================

    @EdidProperty
    def horizontal_size(self):
        return self._horizontal_size

    @horizontal_size.setter
    def horizontal_size(self, value):
        self._horizontal_size = value

    horizontal_size.byte_range = [1,2]

    # ===============================================================================================

    @EdidProperty
    def vertical_size(self):
        return self._vertical_size

    @vertical_size.setter
    def vertical_size(self, value):
        self._vertical_size = value

    vertical_size.byte_range = [2,3]

    # ===============================================================================================

    @EdidProperty
    def gamma(self):
        return self._gamma

    @gamma.setter
    def gamma(self, value):
        self._gamma = value

    @gamma.byte_converter
    def gamma(value):
        return int((value - 1) * 100).to_bytes()

    gamma.byte_range = [3,4]

    # ===============================================================================================

    @EdidProperty
    def suported_features(self):
        return self._suported_features

    @suported_features.setter
    def suported_features(self, value):
        self._suported_features = value

    @suported_features.byte_converter
    def suported_features(value):
        return bytes.fromhex(value)

    suported_features.byte_range = [4,5]

    # ===============================================================================================

    @property
    def as_bytes(self):
        return (
                self.video_params.as_bytes +
                self.horizontal_size.as_bytes +
                self.vertical_size.as_bytes +
                self.gamma.as_bytes +
                self.suported_features.as_bytes
            )

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

class ChromaticityCoordinates:

    def __init__(self, red_green_lsb='5E', blue_white_lsb='C0', red_x_msb='A4', red_y_msb='59', green_xy_msb='4A98', blue_xy_msb='2520', white_xy_msb='5054'):

        assert all(c in string.hexdigits for c in red_green_lsb), 'Red green lsb must be a 2 digit hexadecimal string'
        assert all(c in string.hexdigits for c in blue_white_lsb), 'Blue white lsb must be a 2 digit hexadecimal string'
        assert all(c in string.hexdigits for c in red_x_msb), 'Red x msb must be a 2 digit hexadecimal string'
        assert all(c in string.hexdigits for c in red_y_msb), 'Red y msb must be a 2 digit hexadecimal string'
        assert all(c in string.hexdigits for c in green_xy_msb), 'Green msb must be a 4 digit hexadecimal string'
        assert all(c in string.hexdigits for c in blue_xy_msb), 'Blue msb must be a 4 digit hexadecimal string'
        assert all(c in string.hexdigits for c in white_xy_msb), 'White msb must be a 4 digit hexadecimal string'


        self._red_green_lsb = red_green_lsb
        self._blue_white_lsb = blue_white_lsb
        self._red_x_msb = red_x_msb
        self._red_y_msb = red_y_msb
        self._green_xy_msb = green_xy_msb
        self._blue_xy_msb = blue_xy_msb
        self._white_xy_msb = white_xy_msb


    @EdidProperty
    def red_green_lsb(self):
        return self._red_green_lsb

    @red_green_lsb.setter
    def red_green_lsb(self, value):
        self._red_green_lsb = value

    @red_green_lsb.byte_converter
    def red_green_lsb(value):
        return bytes.fromhex(value)

    red_green_lsb.byte_range = [0,1]

    # ===============================================================================================

    @EdidProperty
    def blue_white_lsb(self):
        return self._blue_white_lsb

    @blue_white_lsb.setter
    def blue_white_lsb(self, value):
        self._blue_white_lsb = value

    @blue_white_lsb.byte_converter
    def blue_white_lsb(value):
        return bytes.fromhex(value)

    blue_white_lsb.byte_range = [1,2]

    # ===============================================================================================

    @EdidProperty
    def red_x_msb(self):
        return self._red_x_msb

    @red_x_msb.setter
    def red_x_msb(self, value):
        self._red_x_msb = value

    @red_x_msb.byte_converter
    def red_x_msb(value):
        return bytes.fromhex(value)

    red_x_msb.byte_range = [2,3]

    # ===============================================================================================

    @EdidProperty
    def red_y_msb(self):
        return self._red_y_msb

    @red_y_msb.setter
    def red_y_msb(self, value):
        self._red_y_msb = value

    @red_y_msb.byte_converter
    def red_y_msb(value):
        return bytes.fromhex(value)

    red_y_msb.byte_range = [3,4]

    # ===============================================================================================

    @EdidProperty
    def green_xy_msb(self):
        return self._green_xy_msb

    @green_xy_msb.setter
    def green_xy_msb(self, value):
        self._green_xy_msb = value

    @green_xy_msb.byte_converter
    def green_xy_msb(value):
        return bytes.fromhex(value)

    green_xy_msb.byte_range = [4,5]

    # ===============================================================================================

    @EdidProperty
    def blue_xy_msb(self):
        return self._blue_xy_msb

    @blue_xy_msb.setter
    def blue_xy_msb(self, value):
        self._blue_xy_msb = value

    @blue_xy_msb.byte_converter
    def blue_xy_msb(value):
        return bytes.fromhex(value)

    blue_xy_msb.byte_range = [5,6]

    # ===============================================================================================

    @EdidProperty
    def white_xy_msb(self):
        return self._white_xy_msb

    @white_xy_msb.setter
    def white_xy_msb(self, value):
        self._white_xy_msb = value

    @white_xy_msb.byte_converter
    def white_xy_msb(value):
        return bytes.fromhex(value)

    white_xy_msb.byte_range = [6,7]

    # ===============================================================================================

    @property
    def as_bytes(self):
        return (
                self.red_green_lsb.as_bytes +
                self.blue_white_lsb.as_bytes +
                self.red_x_msb.as_bytes +
                self.red_y_msb.as_bytes +
                self.green_xy_msb.as_bytes +
                self.blue_xy_msb.as_bytes +
                self.white_xy_msb.as_bytes
            )

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

class StandardTiming:

    @staticmethod
    def empty():
        return StandardTiming(x_resolution=256, aspect_ratio='16:10', vertical_freq=61)

    def __init__(self, x_resolution=3840, aspect_ratio='16:9', vertical_freq=60):

        assert x_resolution >= 256, 'x resolution must be at least 256 pixels'
        assert aspect_ratio in ['16:10', '4:3', '5:4', '16:9'], 'Aspect ratio must be one of: 16:10, 4:3, 5:4, 16:9'
        assert 60 <= vertical_freq <= 123, 'Vertical frequency must be 60 - 123'

        self._x_resolution = x_resolution
        self._aspect_ratio = aspect_ratio
        self._vertical_freq = vertical_freq


    @EdidProperty
    def x_resolution(self):
        return self._x_resolution

    @x_resolution.setter
    def x_resolution(self, value):
        self._x_resolution = value

    @x_resolution.byte_converter
    def x_resolution(value):
        num_bytes = ceil( log(value, 2) / 8)
        return int(value / 8 - 31).to_bytes(num_bytes)[-1:]

    x_resolution.byte_range = [0,1]

    # ===============================================================================================

    @EdidProperty
    def vertical_timing(self):
        return {
            'aspect_ratio' : self._aspect_ratio,
            'v_freq' : self._vertical_freq
        }

    @vertical_timing.setter
    def vertical_timing(self, value):
        self._vertical_timing = value

    @vertical_timing.byte_converter
    def vertical_timing(value):
        ar_lookup = {
            '16:10' : '00',
            '4:3' : '01',
            '5:4' : '10',
            '16:9' : '11'
        }

        aspect_ratio = value['aspect_ratio']
        v_freq = value['v_freq']

        return int(ar_lookup[aspect_ratio] + format(v_freq - 60, '06b'), 2).to_bytes()


    vertical_timing.byte_range = [1,2]

    # ===============================================================================================

    @property
    def as_bytes(self):
        return (
                self.x_resolution.as_bytes +
                self.vertical_timing.as_bytes
            )

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

displayParameters = BasicDisplayParameters(
    video_params='6D',
    horizontal_size=100,
    vertical_size=56,
    gamma=2.2,
    suported_features='EA'
)

chromaticityCoordinates = ChromaticityCoordinates(
    red_green_lsb='5E',
    blue_white_lsb='C0',
    red_x_msb='A4',
    red_y_msb='59',
    green_xy_msb='4A98',
    blue_xy_msb='2520',
    white_xy_msb='5054'
)

standardTiming = StandardTiming(
    x_resolution=3840,
    aspect_ratio='16:9',
    vertical_freq=60
)

base_edid = BaseEDID(
    header = header,
    basic_display_parameters = displayParameters,
    chromaticity_coordinates = chromaticityCoordinates,
    standard_timings = standardTiming
)

simple_test(base_edid, expected)
