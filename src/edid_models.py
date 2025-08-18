import re
import string

from enum import Enum
from functools import reduce
from math import floor
from textwrap import wrap
from warnings import warn

LSB8_BITMASK = int('0xFF',0)
LSB4_BITMASK = int('0x0F',0)

def bytes_to_hex_block(byte_array, width=16):

    hex_str = ' '.join(format(byte, '02x') for byte in byte_array)
    return '\n'.join(wrap(hex_str, width=width * 3)).upper()

class EdidPropertyValue:
    def __init__(self, value, byte_val, byte_range):
        self.value = value
        self.as_bytes = byte_val
        self._byte_range = byte_range

    @property
    def byte_range(self):
        if isinstance(self._byte_range, list):
            return self._byte_range
        else:
            return [self._byte_range, self._byte_range + 1]

    @property
    def block_size(self):
        if isinstance(self.value, list):
            size = (self.byte_range[1] - self.byte_range[0]) / len(self.value)
        elif isinstance(self.value, ByteBlock):
            return self.value.block_size
        else:
            size = self.byte_range[1] - self.byte_range[0]

        assert (size % 1) == 0, f'Non integer block size found for {self.value.__class__.__name__}'

        return int(size)

class EdidProperty:

    def __init__(self, fget=None, fset=None, byte_range=None, byte_converter = lambda x: x.to_bytes()):
        self._getter = fget
        self._setter = fset
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

    # This is hacky and I don't like it, but it works
    @property
    def byte_range():
        pass

    @byte_range.setter
    def byte_range(self, value):
        self._byte_range = value

class ByteBlock:

    def get_edid_props(self) -> list[EdidPropertyValue]:
        return [getattr(self,a) for a in self.edid_prop_names]

    def data_at_position(self, position):
        # returns the data that contains the specified byte
        properties = self.edid_prop_names

        for prop in properties:
            byte_range = getattr(self, prop).byte_range

            if position in range(*byte_range):
                prop_inst = getattr(self, prop)
                prop_value = prop_inst.value

                if isinstance(prop_value, list):
                    if all('data_at_position' in dir(prop) for prop in prop_value):

                        block_size = prop_inst.block_size

                        depth = position - byte_range[0]
                        block_num = floor(depth / block_size)

                        prop_value = prop_value[block_num].data_at_position(int(depth - block_num * block_size))

                        prop = f'{prop}{block_num}'


                elif 'data_at_position' in dir(prop_value):
                    prop_value = prop_value.data_at_position(int(position - byte_range[0]))

                if not prop_value:
                    prop_value = 'not found'

                return {'byte' : position, 'name' : prop, 'value' : prop_value, 'range' : byte_range}

        return False

    @property
    def as_bytes(self):
        # Prevent infinite recursion
        members = dir(self)
        members.remove('as_bytes')

        properties = self.get_edid_props()
        sorted_properties = sorted(properties, key=lambda prop: (prop.byte_range[0]))
        sorted_prop_lengths = [prop.block_size for prop in sorted_properties]

        bytes_list = []

        for prop, length in zip(sorted_properties, sorted_prop_lengths):
            prop_bytes = bytes(0)

            # Pad each item in list individually
            if isinstance(prop.value, list):
                for idx, item in enumerate(prop.value):
                    if len(item.as_bytes) > length:
                        raise Exception(f'returned more bytes than size of byte range for {item.__class__.__name__}{idx}')
                    prop_bytes = prop_bytes + item.as_bytes + bytes(length - len(item.as_bytes))

            elif len(prop.as_bytes) > length:
                raise Exception(
                    f'returned more bytes than size of byte range for {prop.value.__class__.__name__}\n'
                    + f'byte range expected: {length} bytes\n'
                    + f'but recieved {len(prop.as_bytes)} bytes'
                                )

            else:
                prop_bytes = prop.as_bytes + bytes(length - len(prop.as_bytes))

            bytes_list.append(prop_bytes)

        if len(bytes_list) > 0:
            return reduce(lambda x, y: x + y, bytes_list)
        else:
            pass

    @property
    def block_size(self):
        properties = self.get_edid_props()
        total_block_size = 0

        for prop in properties:
            total_block_size += prop.block_size

        return total_block_size

    @property
    def edid_prop_names(self) -> list[str]:
        edid_props = []

        for cls in [self] + self.__class__.mro():
            for attr, attr_type in cls.__dict__.items():
                if 'EdidProperty' in str(attr_type):
                    edid_props.append(attr)

        return edid_props

    def __str__(self):
        return bytes_to_hex_block(self.as_bytes)

class BaseEDID(ByteBlock):
    def __init__(self, header, basic_display_parameters, chromaticity_coordinates, standard_timings, descriptors, num_ext_blocks, established_timing='000000'):
        if not isinstance(standard_timings, list):
            standard_timings = [standard_timings]

        assert all(c in string.hexdigits for c in established_timing), 'Red green lsb must be a 6 digit hexadecimal string'
        assert all(isinstance(timing, StandardTiming) for timing in standard_timings) and 1 <= len(standard_timings) <= 8, 'Standard timings must be a list of at least 1 and at most 8 standard timing objects'
        assert isinstance(descriptors, list) and len(descriptors) == 4, 'Descriptors must be a list of 4 descriptor objects'
        assert isinstance(descriptors[0], DetailedTimingDescriptor), 'Descriptor 1 must be a detailed timing descriptor'

        self._header = header
        self._basic_display_parameters = basic_display_parameters
        self._chromaticity_coordinates = chromaticity_coordinates
        self._established_timing = established_timing
        self._standard_timings = standard_timings
        self._descriptors = descriptors
        self._num_ext_blocks = num_ext_blocks

        self._checksum = 0
        edid_sum = sum(self.as_bytes)
        self._checksum = 256 - edid_sum % 256


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

    @EdidProperty
    def descriptors(self):
        return self._descriptors

    @descriptors.setter
    def descriptors(self, value):
        self._descriptors = value

    @descriptors.byte_converter
    def descriptors(value):
        return reduce(lambda x, y: x + y, [descriptor.as_bytes for descriptor in value])

    descriptors.byte_range = [54,126]

    # ===============================================================================================

    @EdidProperty
    def num_ext_blocks(self):
        return self._num_ext_blocks

    @num_ext_blocks.setter
    def num_ext_blocks(self, value):
        self._num_ext_blocks = value

    num_ext_blocks.byte_range = 126

    # ===============================================================================================

    @EdidProperty
    def checksum(self):
        return self._checksum

    checksum.byte_range = 127

class Header(ByteBlock):

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
    def fixed_pattern(self):
        return "00FFFFFFFFFFFF00"

    @fixed_pattern.byte_converter
    def fixed_pattern(value):
        return bytes.fromhex(value)

    fixed_pattern.byte_range = [0,8]


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

    manufacture_week.byte_range = 16

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

    manufacture_year.byte_range = 17

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

    edid_version.byte_range = [18,20]

class BasicDisplayParameters(ByteBlock):

    class DigitalParameters(ByteBlock):

        class BitDepth(Enum):
            UNDEFINED=0
            BD_6=1
            BD_8=2
            BD_10=3
            BD_12=4
            BD_14=5
            BD_16=6

        class Interface(Enum):
            UNDEFINED=0
            DVI=1
            HDMIa=2
            HDMIb=3
            MDDI=4
            DISPLAY_PORT=5

        def __init__(self, bit_depth, interface):
            self._bit_depth = bit_depth
            self._interface = interface

        @EdidProperty
        def parameters_bitmap(self):
            return (
                (1 << 7)
                + (self._bit_depth.value << 4)
                + self._interface.value
            )

        parameters_bitmap.byte_range = 0

    class AnalogueParameters(ByteBlock):

        class WhiteAndSyncLevels(Enum):
            w07s03=0
            w0714s0286=1
            w1s04=2
            w07s0=3

        def __init__(
                self,
                white_sync_lvls : WhiteAndSyncLevels,
                BTB : bool,
                separate_sync_support : bool,
                composite_sync_support : bool,
                sync_on_green : bool,
                serration_on_vsync_pulse : bool
                ):

            self._white_sync_lvls = white_sync_lvls
            self._BTB = BTB
            self._separate_sync_support = separate_sync_support
            self._composite_sync_support = composite_sync_support
            self._sync_on_green = sync_on_green
            self._serration_on_vsync_pulse = serration_on_vsync_pulse

            if (composite_sync_support or sync_on_green) and not serration_on_vsync_pulse:
                warn('Serration on vsync pulse must be true when using composite sync or sync on green, forcing true...')
                self._serration_on_vsync_pulse = True

        @EdidProperty
        def parameters_bitmap(self):
            return (
                + (self._white_sync_lvls.value << 5)
                + (int(self._BTB) << 4)
                + (int(self._separate_sync_support) << 3)
                + (int(self._composite_sync_support) << 2)
                + (int(self._sync_on_green) << 1)
                + int(self._serration_on_vsync_pulse)
            )

        parameters_bitmap.byte_range = 0

    class SupportedFeatures(ByteBlock):

        class DigitalDisplayType(Enum):
            RGB444=0
            RGB444_YCrCb444=1
            RGB444_YCrCb422=2
            RGB444_YCrCb444_YCrCb422=3

        class AnalogueDisplayType(Enum):
            MONOCHROME=0
            RGB=1
            NON_RGB=2
            UNDEFINED=3

        def __init__(
                self,
                dpms_standby : bool,
                dpms_suspend : bool,
                dpms_active_off : bool,
                display_type : DigitalDisplayType | AnalogueDisplayType,
                standard_srgb : bool,
                dtd_block_1_is_preferred : bool,
                continuous_timings : bool
                ):
            self._dpms_standby = dpms_standby
            self._dpms_suspend = dpms_suspend
            self._dpms_active_off = dpms_active_off
            self._display_type = display_type
            self._standard_srgb = standard_srgb
            self._dtd_block_1_is_preferred = dtd_block_1_is_preferred
            self._continuous_timings = continuous_timings

        @EdidProperty
        def feature_bitmap(self):
            return (
                (int(self._dpms_standby) << 7)
                + (int(self._dpms_suspend) << 6)
                + (int(self._dpms_active_off) << 5)
                + (self._display_type.value << 3)
                + (int(self._standard_srgb) << 2)
                + (int(self._dtd_block_1_is_preferred) << 1)
                + int(self._continuous_timings)
            )

        feature_bitmap.byte_range = 0

    def __init__(
            self,
            video_params=DigitalParameters(
                bit_depth=DigitalParameters.BitDepth.BD_10,
                interface=DigitalParameters.Interface.DISPLAY_PORT
            ),
            horizontal_size=100,
            vertical_size=56,
            gamma=2.2,
            suported_features : SupportedFeatures=SupportedFeatures (
                    dpms_standby=True,
                    dpms_suspend=True,
                    dpms_active_off=True,
                    display_type=SupportedFeatures.DigitalDisplayType.RGB444_YCrCb444,
                    standard_srgb=False,
                    dtd_block_1_is_preferred=True,
                    continuous_timings=False
                )
            ):

        assert 1 <= horizontal_size <= 255, 'Horizontal size must be an integer 1 - 255'
        assert 1 <= vertical_size <= 255, 'Vertical size must be an integer 1 - 255'
        assert 1.00 <= gamma <= 3.54, 'Gamma must be an integer 1.00 - 3.54'

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
        return value.as_bytes

    video_params.byte_range = 0

    # ===============================================================================================

    @EdidProperty
    def horizontal_size(self):
        return self._horizontal_size

    @horizontal_size.setter
    def horizontal_size(self, value):
        self._horizontal_size = value

    horizontal_size.byte_range = 1

    # ===============================================================================================

    @EdidProperty
    def vertical_size(self):
        return self._vertical_size

    @vertical_size.setter
    def vertical_size(self, value):
        self._vertical_size = value

    vertical_size.byte_range = 2

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

    gamma.byte_range = 3
    # ===============================================================================================

    @EdidProperty
    def suported_features(self):
        return self._suported_features

    @suported_features.setter
    def suported_features(self, value):
        self._suported_features = value

    @suported_features.byte_converter
    def suported_features(value):
        return value.as_bytes

    suported_features.byte_range = 4

class ChromaticityCoordinates(ByteBlock):

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

    red_green_lsb.byte_range = 0

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

    blue_white_lsb.byte_range = 1

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

    red_x_msb.byte_range = 2

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

    red_y_msb.byte_range = 3

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

    green_xy_msb.byte_range = [4,6]

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

    blue_xy_msb.byte_range = [6,8]

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

    white_xy_msb.byte_range = [8,10]

class StandardTiming(ByteBlock):

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
        return (int(value / 8 - 31) & LSB8_BITMASK).to_bytes()

    x_resolution.byte_range = 0

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


    vertical_timing.byte_range = 1

class DetailedTimingDescriptor(ByteBlock):

    class StereoMode(Enum):
        NONE=0
        RIGHT_SYNC=1
        LEFT_SYNC=2
        INTERLEAVED_RIGHT=3
        INTERLEAVED_LEFT=4
        INTERLEAVED_FOUR_WAY=5
        INTERLEAVED_SBS=6

    class AnalogueSync():

        def __init__(self, serration=False, bipolar=False, sync_on_rgb=False):
            self._serration = int(serration)
            self._sync_type = int(self._bipolar)
            self._sync_on_rgb = int(sync_on_rgb)

        @property
        def value(self):
            return (
                ( self._sync_type << 3 )
                + ( self._serration << 1 )
                + ( self._sync_on_rgb )
            )

    class DigitalSync():

        def __init__(self, serration=False, positive_sync_polarity=False):
            self._serration = int(serration)
            self._sync_polarity = int(positive_sync_polarity)

        @property
        def value(self):
            return (
                ( 2 << 3 )
                + ( self._serration << 1 )
                + ( self._positive_sync_polarity )
            )

    class DigitalSeparateSync():

        def __init__(self, positive_vert_sync_polarity=True, positive_hor_sync_polarity=True):
            self._positive_vert_sync_polarity = int(positive_vert_sync_polarity)
            self._positive_hor_sync_polarity = int(positive_hor_sync_polarity)

        @property
        def value(self):
            return (
                ( 3 << 3 )
                + ( self._positive_vert_sync_polarity << 2 )
                + ( self._positive_hor_sync_polarity << 1 )
            )

    def __init__(
            self,
            pixel_clock=594,
            hor_pixels=3840,
            hor_blnk_pixels=560,
            vert_pixels=2160,
            vert_blnk_pixels=90,
            hor_front_porch=176,
            hor_synch_pulse=88,
            vert_front_porch=8,
            vert_synch_pulse=10,
            hor_size_mm=1000,
            vert_size_mm=562,
            hor_border_pixels=0,
            vert_border_pixels=0,
            interlaced=False,
            stereo=StereoMode.NONE,
            sync=DigitalSeparateSync()
        ):

        assert 0.01 <= pixel_clock <= 655.35, 'Pixel clock must be between 0.01 - 655.35 MHz'

        self._pixel_clock = pixel_clock
        self._hor_pixels = hor_pixels
        self._hor_blnk_pixels = hor_blnk_pixels
        self._vert_pixels = vert_pixels
        self._vert_blnk_pixels = vert_blnk_pixels
        self._hor_front_porch = hor_front_porch
        self._hor_synch_pulse = hor_synch_pulse
        self._vert_front_porch = vert_front_porch
        self._vert_synch_pulse = vert_synch_pulse
        self._hor_size_mm = hor_size_mm
        self._vert_size_mm = vert_size_mm
        self._hor_border_pixels = hor_border_pixels
        self._vert_border_pixels = vert_border_pixels
        self._interlaced = interlaced
        self._stereo = stereo
        self._sync = sync


    @EdidProperty
    def pixel_clock(self):
        return self._pixel_clock

    @pixel_clock.setter
    def pixel_clock(self, value):
        self._pixel_clock = value

    @pixel_clock.byte_converter
    def pixel_clock(value):
        return (value * 100).to_bytes(2, 'little')

    pixel_clock.byte_range = [0,2]

    # ===============================================================================================

    @EdidProperty
    def hor_pixels(self):
        return self._hor_pixels

    @hor_pixels.setter
    def hor_pixels(self, value):
        self._hor_pixels = value

    @hor_pixels.byte_converter
    def hor_pixels(value):
        return (value & LSB8_BITMASK).to_bytes()

    hor_pixels.byte_range = 2

    # ===============================================================================================

    @EdidProperty
    def hor_blnk_pixels(self):
        return self._hor_blnk_pixels

    @hor_blnk_pixels.setter
    def hor_blnk_pixels(self, value):
        self._hor_blnk_pixels = value

    @hor_blnk_pixels.byte_converter
    def hor_blnk_pixels(value):
        return (value & LSB8_BITMASK).to_bytes()

    hor_blnk_pixels.byte_range = 3

    # ===============================================================================================

    @EdidProperty
    def hor_act_blank_msb(self):
        # https://glenwing.github.io/docs/VESA-EEDID-A2.pdf#page=33
        # horizontal pixels are 12 bit numbers
        return int(format((self._hor_pixels >> 8) & 15, '04b')[:4] + format((self._hor_blnk_pixels >> 8) & 15, '04b')[:4],2)

    hor_act_blank_msb.byte_range = 4

    # ===============================================================================================

    @EdidProperty
    def vert_pixels(self):
        return self._vert_pixels

    @vert_pixels.setter
    def vert_pixels(self, value):
        self._vert_pixels = value

    @vert_pixels.byte_converter
    def vert_pixels(value):
        return (value & LSB8_BITMASK).to_bytes()

    vert_pixels.byte_range = 5

    # ===============================================================================================

    @EdidProperty
    def vert_blnk_pixels(self):
        return self._vert_blnk_pixels

    @vert_blnk_pixels.setter
    def vert_blnk_pixels(self, value):
        self._vert_blnk_pixels = value

    @vert_blnk_pixels.byte_converter
    def vert_blnk_pixels(value):
        return (value & LSB8_BITMASK).to_bytes()

    vert_blnk_pixels.byte_range = 6

    # ===============================================================================================

    @EdidProperty
    def vert_act_blank_msb(self):
        # https://glenwing.github.io/docs/VESA-EEDID-A2.pdf#page=33
        # horizontal pixels are 12 bit numbers
        return (((self._vert_pixels >> 8) & LSB4_BITMASK ) << 4 ) + ( (self._vert_blnk_pixels >> 8) & LSB4_BITMASK )

    vert_act_blank_msb.byte_range = 7

    # ===============================================================================================

    @EdidProperty
    def hor_front_porch(self):
        return self._hor_front_porch

    @hor_front_porch.setter
    def hor_front_porch(self, value):
        self._hor_front_porch = value

    @hor_front_porch.byte_converter
    def hor_front_porch(value):
        # https://glenwing.github.io/docs/VESA-EEDID-A2.pdf#page=33
        # horizontal porch is a 10 bit number
        return (value & LSB8_BITMASK).to_bytes()

    hor_front_porch.byte_range = 8

    # ===============================================================================================

    @EdidProperty
    def hor_synch_pulse(self):
        return self._hor_synch_pulse

    @hor_synch_pulse.setter
    def hor_synch_pulse(self, value):
        self._hor_synch_pulse = value

    @hor_synch_pulse.byte_converter
    def hor_synch_pulse(value):
        # https://glenwing.github.io/docs/VESA-EEDID-A2.pdf#page=33
        # horizontal sync is a 10 bit number
        return (value & LSB8_BITMASK).to_bytes()

    hor_synch_pulse.byte_range = 9

    # ===============================================================================================

    @EdidProperty
    def vert_porch_sync_lsb(self):
        # https://glenwing.github.io/docs/VESA-EEDID-A2.pdf#page=33
        # vertical sync and porch are 6 bit numbers
        return ((self._vert_front_porch & LSB4_BITMASK ) << 4 ) + ( self._vert_synch_pulse & LSB4_BITMASK )

    vert_porch_sync_lsb.byte_range = 10

    # ===============================================================================================

    @EdidProperty
    def porch_sync_msb(self):
        return (
                    ((self._hor_front_porch & ~LSB8_BITMASK ) >> 2 )
                    + (( self._hor_synch_pulse & ~LSB8_BITMASK ) >> 4 )
                    + (( self._vert_front_porch & ~LSB4_BITMASK ) >> 2 )
                    + (( self._vert_synch_pulse & ~LSB4_BITMASK ) >> 4 )
                )

    porch_sync_msb.byte_range = 11

    # ===============================================================================================

    @EdidProperty
    def hor_size_mm(self):
        return self._hor_size_mm & LSB8_BITMASK

    @hor_size_mm.setter
    def hor_size_mm(self, value):
        self._hor_size_mm = value

    hor_size_mm.byte_range = 12

    # ===============================================================================================

    @EdidProperty
    def vert_size_mm(self):
        return self._vert_size_mm & LSB8_BITMASK

    @vert_size_mm.setter
    def vert_size_mm(self, value):
        self._vert_size_mm = value

    vert_size_mm.byte_range = 13

    # ===============================================================================================

    @EdidProperty
    def image_size_msb(self):
        return (((self._hor_size_mm >> 8) & LSB4_BITMASK ) << 4 ) + ( (self._vert_size_mm >> 8) & LSB4_BITMASK )

    image_size_msb.byte_range = 14

    # ===============================================================================================

    @EdidProperty
    def hor_border_pixels(self):
        return self._hor_border_pixels

    @hor_border_pixels.setter
    def hor_border_pixels(self, value):
        self._hor_border_pixels = value

    hor_border_pixels.byte_range = 15

    # ===============================================================================================

    @EdidProperty
    def vert_border_pixels(self):
        return self._vert_border_pixels

    @vert_border_pixels.setter
    def vert_border_pixels(self, value):
        self._vert_border_pixels = value

    vert_border_pixels.byte_range = 16

    # ===============================================================================================

    @EdidProperty
    def features(self):
        return (
            ( self._interlaced << 7 )
            + ( self._stereo.value << 5 )
            + self._sync.value
        )

    features.byte_range = 17

class MonitorDescriptor(ByteBlock):

    class DescriptorType(Enum):
        DUMMY=0x10
        ADDITIONAL_STANDARD_TIMING_3=0xF7
        CVT_TIMING_CODES=0xF8
        DISPLAY_COLOR_MANAGEMENT=0xF9
        ADDITIONAL_STANDARD_TIMING_6x2BYTE=0xFA
        ADDITIONAL_STANDARD_TIMING_2x5BYTE=0xFB
        MONITOR_NAME=0xFC
        MONITOR_RANGE_LIMITS=0xFD
        TEXT=0xFE
        MONITOR_SERIAL_NUMBER=0xFF

    def __init__(self, descriptor_data):
        self._descriptor_data = descriptor_data

    @EdidProperty
    def monitor_descriptor_header(self):
        return 0

    monitor_descriptor_header.byte_range = [0,3]

class MonitorText(MonitorDescriptor):

    def __init__(self, text, type=MonitorDescriptor.DescriptorType.TEXT):
        assert len(text) < 13, 'Text must be less than 13 bytes/characters'

        self._text = text
        self._type = type


    @EdidProperty
    def type(self):
        return self._type

    @type.byte_converter
    def type(value):
        return value.value.to_bytes()

    type.byte_range = 3

    # ===============================================================================================

    @EdidProperty
    def reserved(self):
        return 0

    reserved.byte_range = 4

    # ===============================================================================================

    @EdidProperty
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        self._text = value

    @text.byte_converter
    def text(value):
        byte_val = value.encode('ascii')

        length = len(byte_val)
        padding = (0x20).to_bytes() * ( 12 - length )

        return (
            byte_val
            + 0x0A.to_bytes()
            + padding
        )

    text.byte_range = [5,18]

class MonitorName(MonitorText):

    def __init__(self, name):
        super().__init__(name, type=MonitorDescriptor.DescriptorType.MONITOR_NAME)

class MonitorSerialNumber(MonitorText):

    def __init__(self, serial_num):
        super().__init__(serial_num, type=MonitorDescriptor.DescriptorType.MONITOR_SERIAL_NUMBER)

class MonitorRangeLimits(MonitorDescriptor):

    class ExtendedTimingInfoType(Enum):
        DEFAULT_GTF=0x00
        NONE=0x01
        SECONDARY_GTF=0x02
        CVT=0x04

    def __init__(
            self,
            hor_offset_max=0,
            hor_offset_min=0,
            vert_offset_max=0,
            vert_offset_min=0,
            vert_freq_min=59,
            vert_freq_max=61,
            hor_freq_min=134,
            hor_freq_max=136,
            pixel_clock_freq_max=60,
            extended_timing_info_type=ExtendedTimingInfoType.DEFAULT_GTF,
            video_timing_parameters=None
            ):
        self._hor_offset_max = hor_offset_max
        self._hor_offset_min = hor_offset_min
        self._vert_offset_max = vert_offset_max
        self._vert_offset_min = vert_offset_min
        self._vert_freq_min = vert_freq_min
        self._vert_freq_max = vert_freq_max
        self._hor_freq_min = hor_freq_min
        self._hor_freq_max = hor_freq_max
        self._pixel_clock_freq_max = pixel_clock_freq_max
        self._extended_timing_info_type = extended_timing_info_type
        self._video_timing_parameters = video_timing_parameters

    @EdidProperty
    def type(self):
        return MonitorDescriptor.DescriptorType.MONITOR_RANGE_LIMITS

    @type.byte_converter
    def type(value):
        return value.value.to_bytes()

    type.byte_range = 3

    # ===============================================================================================

    @EdidProperty
    def range_limit_offsets(self):
        return (
            self._hor_offset_max << 3
            + self._hor_offset_min << 2
            + self._vert_offset_max << 1
            + self._vert_offset_min
        )

    range_limit_offsets.byte_range = 4

    # ===============================================================================================

    @EdidProperty
    def vert_freq_min(self):
        return self._vert_freq_min

    @vert_freq_min.setter
    def vert_freq_min(self, value):
        self._vert_freq_min = value

    vert_freq_min.byte_range = 5

    # ===============================================================================================

    @EdidProperty
    def vert_freq_max(self):
        return self._vert_freq_max

    @vert_freq_max.setter
    def vert_freq_max(self, value):
        self._vert_freq_max = value

    vert_freq_max.byte_range = 6

    # ===============================================================================================

    @EdidProperty
    def hor_freq_min(self):
        return self._hor_freq_min

    @hor_freq_min.setter
    def hor_freq_min(self, value):
        self._hor_freq_min = value

    hor_freq_min.byte_range = 7

    # ===============================================================================================

    @EdidProperty
    def hor_freq_max(self):
        return self._hor_freq_max

    @hor_freq_max.setter
    def hor_freq_max(self, value):
        self._hor_freq_max = value

    hor_freq_max.byte_range = 8

    # ===============================================================================================

    @EdidProperty
    def pixel_clock_freq_max(self):
        return self._pixel_clock_freq_max

    @pixel_clock_freq_max.setter
    def pixel_clock_freq_max(self, value):
        self._pixel_clock_freq_max = value

    pixel_clock_freq_max.byte_range = 9

    # ===============================================================================================

    @EdidProperty
    def extended_timing_info_type(self):
        return self._extended_timing_info_type

    @extended_timing_info_type.setter
    def extended_timing_info_type(self, value):
        self._extended_timing_info_type = value

    @extended_timing_info_type.byte_converter
    def extended_timing_info_type(value):
        return value.value.to_bytes()

    extended_timing_info_type.byte_range = 10

    # ===============================================================================================

    @EdidProperty
    def video_timing_parameters(self):
        return self._video_timing_parameters

    @video_timing_parameters.setter
    def video_timing_parameters(self, value):
        self._video_timing_parameters = value

    @video_timing_parameters.byte_converter
    def video_timing_parameters(value):
        if value is not None:
            byte_val = value.to_bytes()
        else:
            byte_val = bytes()

        length = len(byte_val)
        padding = (0x20).to_bytes() * ( 6 - length )

        return (
            byte_val
            + 0x0A.to_bytes()
            + padding
        )

    video_timing_parameters.byte_range = [11,18]