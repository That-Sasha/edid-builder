import re
import string

from enum import Enum
from functools import reduce
from math import floor
from textwrap import wrap

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
    def __init__(self, header, basic_display_parameters, chromaticity_coordinates, standard_timings, descriptors, established_timing='000000'):
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
        return bytes.fromhex(value)

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
