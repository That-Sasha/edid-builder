from edid_models import bytes_to_hex_block
from enum import Enum
from functools import reduce
from math import floor, gcd
from typing import List

class ByteRange:

    def __set__(self, instance, range):
        assert callable(range) or isinstance(range, list) or isinstance(range, int), 'Byte range must be int or [int] or callable'
        setattr(instance, '_byte_range', range)

    def __get__(self, instance, owner):
        range = getattr(instance, '_byte_range')
        if callable(range):
            calculated_range = range()
        else:
            calculated_range = range
        
        if isinstance(calculated_range, list):
            return calculated_range
        elif isinstance(calculated_range, int):
            return [calculated_range, calculated_range + 1] 

class EdidPropertyValue:

    byte_range = ByteRange()

    def __init__(self, prop_descriptor : EdidProperty, value, byte_range):
        self.prop_descriptor = prop_descriptor
        self.value = value
        self.byte_range = byte_range
    
    @property
    def value(self):
        if callable(self._value):
            return self._value()
        else:
            return self._value
        
    @value.setter
    def value(self, value):
        self._value = value

    @property
    def as_bytes(self):
        return self.prop_descriptor.byte_converter(self.value)
    
    @property
    def block_size(self):
        if isinstance(self.value, list):
            if len(self.value) > 0:
                size = reduce(lambda x, y: x + y, [item.block_size for item in self.value])
            else:
                size = 0
        elif isinstance(self.value, ByteBlock):
            return self.value.block_size
        else:
            size = self.byte_range[1] - self.byte_range[0]

        assert (size % 1) == 0, f'Non integer block size found for {self.__class__.__name__}'

        return size

class EdidInputProperty:
        
    def __set_name__(self, owner, name):
        self.name = name
        self.private_name = f'_{name}'

    def __get__(self, instance, owner):
        return getattr(instance, self.private_name, None)
            
    def __set__(self, instance, value):
        setattr(instance, self.private_name, value)

class EdidProperty:

    default_byte_range = ByteRange()

    def __init__(self, byte_range, byte_converter = None):
        self.default_byte_range = byte_range
        self.default_block_size = self.default_byte_range[1] - self.default_byte_range[0] 
        self.byte_converter = byte_converter if byte_converter is not None else lambda x: x.to_bytes(self.default_block_size)[::-1]

    def __set_name__(self, owner, name):
        self.name = name
            
    def __set__(self, instance : ByteBlock, value):
        # Check if integers fit in the size allowed
        new_block_size = None

        if isinstance(value, int):
            new_block_size = (value.bit_length() + 7) // 8
            
        elif callable(value):
            new_block_size = (value().bit_length() + 7) // 8

        if self.name not in instance.edid_props:
            instance.edid_props[self.name] = EdidPropertyValue(self, value, self.default_byte_range)
            block_size = self.default_block_size
        else:
            block_size = instance.edid_props[self.name].block_size
        

        if new_block_size is not None:
            assert new_block_size <= block_size, f'New value must be {block_size} bytes or less'


        instance.edid_props[self.name].value = value

    def __get__(self, instance, owner):
        return instance._edid_props[self.name]

class ByteBlock:

    @property
    def edid_props(self):
        if not hasattr(self, '_edid_props'):
            self._edid_props = {}
        return self._edid_props
    
    @edid_props.setter
    def edid_props(self, value):
        self._edid_props = value

    def get_edid_props(self) -> list[EdidPropertyValue]:
        return [prop for prop in self.edid_props.values()]

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

        properties = self.get_edid_props()
        sorted_properties = sorted(properties, key=lambda prop: (prop.byte_range[0]))
        sorted_prop_lengths = [prop.block_size for prop in sorted_properties]
        
        bytes_list = []

        last_prop_end = 0
        for prop, length in zip(sorted_properties, sorted_prop_lengths):
            prop_bytes = bytes(0)

            if prop.byte_range[0] != last_prop_end:
                pad_length = prop.byte_range[0] - last_prop_end
                bytes_list.append(bytes(pad_length))

            # Pad each item in list individually
            if isinstance(prop.value, list):
                for idx, item in enumerate(prop.value):
                    # length is for the entire list so we need to check the size of each item instead
                    item_length = item.block_size
                    if len(item.as_bytes) > item_length:
                        raise Exception(f'returned more bytes than size of byte range for {item.__class__.__name__}{idx}\n'
                                    + f'byte range expected: {item_length} bytes\n'
                                    + f'but recieved {len(prop.as_bytes)} bytes'
                                )
                    prop_bytes = prop_bytes + item.as_bytes + bytes(item_length - item.block_size)

            elif len(prop.as_bytes) > length:
                raise Exception(
                    f'returned more bytes than size of byte range for {prop.value.__class__.__name__}\n'
                                    + f'byte range expected: {length} bytes\n'
                                    + f'but recieved {len(prop.as_bytes)} bytes'
                                )

            else:
                prop_bytes = prop.as_bytes + bytes(length - len(prop.as_bytes))

            last_prop_end = prop.byte_range[1]

            bytes_list.append(prop_bytes)

        if len(bytes_list) > 0:
            return reduce(lambda x, y: x + y, bytes_list)
        else:
            pass

    @property
    def block_size(self):
        return len(self.as_bytes)

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

class DisplayId(ByteBlock):
    
    class ProductType(Enum):
        EXTENSION_SECTION=0x00
        TEST_STRUCTURE=0x01
        DISPLAY_PANEL=0x02
        STANDALONE_DISPLAY=0x03
        TELEVISION_RECEIVER=0x04
        REPEATER=0x05
        DIRECT_DRIVE_MONITOR=0x06

    class SectionType(Enum):
        BASE_SECTION=0x00
        EXTENSION_SECTION=0x01
        # If display port, can be used as an edid extension block
        EDID_EXTENSION_BLOCK=0x02 
    
    def byte_offset(self, val):
        if not isinstance(self.section_type, DisplayId.SectionType):
            return val
        
        if self.section_type == DisplayId.SectionType.EDID_EXTENSION_BLOCK:
            return val + 1
        else:
            return val

    # These fields aren't always used, we don't set them unless necessary
    edid_block_tag = EdidProperty(0)
    edid_checksum = EdidProperty(127)

    revision = EdidProperty(0, byte_converter = lambda x: bytes.fromhex(str(x).replace('.', '')))
    length_of_block = EdidProperty(1)
    product_type = EdidProperty(2, byte_converter = lambda x: x.value.to_bytes())
    extension_count = EdidProperty(3)
    data_blocks = EdidProperty(4, lambda val: reduce(lambda x, y: x + y, [descriptor.as_bytes for descriptor in val]))
    checksum = EdidProperty(5)


    # https://www.graniteriverlabs.com.cn/technical-blog/vesa-displayid-1-3-overview/
    def __init__(
                self,
                revision=1.2,
                product_type=ProductType.STANDALONE_DISPLAY,
                section_type : SectionType=SectionType.BASE_SECTION,
                data_blocks : List[ByteBlock]=[]
            ):
        self.revision = revision
        self.length_of_block = 0
        self.product_type = product_type
        self.data_blocks = data_blocks
        self.extension_count = lambda: 0 if section_type == DisplayId.SectionType.EDID_EXTENSION_BLOCK else len(self.data_blocks.value)
        self.checksum = 0
        self.section_type = section_type

    # ===============================================================================================

    # Input Properties

    # ===============================================================================================

    @property
    def section_type(self):
        return self._section_type

    @section_type.setter
    def section_type(self, value):
        self._section_type = value
        # Fix byte ranges and set edid block tag, checksum and length of block
        if self.section_type == DisplayId.SectionType.EDID_EXTENSION_BLOCK:
            self.revision.byte_range = 1
            self.length_of_block.byte_range = 2
            self.product_type.byte_range = 3
            self.extension_count.byte_range = 4
            self.data_blocks.byte_range = lambda: [5,5 + self.data_blocks.block_size]
            self.checksum.byte_range = 126

            self.length_of_block = 121

            self.checksum = 0
            byte_sum = sum(self.as_bytes)
            self.checksum = (256 - byte_sum % 256) % 256
            
            self.edid_block_tag = 112
            self.edid_checksum = 0

            byte_sum = sum(self.as_bytes)
            self.edid_checksum._value = (256 - byte_sum % 256) % 256

        else:
            self.revision.byte_range = 0
            self.length_of_block.byte_range = 1
            self.product_type.byte_range = 2
            self.extension_count.byte_range = 3
            self.data_blocks.byte_range = lambda: [4,4 + self.data_blocks.block_size]
            self.checksum.byte_range = lambda: self.data_blocks.byte_range[1]

            self.length_of_block = lambda: self.data_blocks.block_size

            # Remove these now that we don't need them anymore
            self.edid_props.pop('edid_block_tag', None)
            self.edid_props.pop('edid_checksum', None)

class DisplayIDTimings():

    def aspect_ratio_bits(width : int, height : int):
        denom = gcd(width, height)

        ratio = f'{int(width / denom)}:{int(height / denom)}'

        ratio_lookup = {
            '1:1' : 0,
            '5:4' : 1,
            '4:3' : 2,
            '15:9' : 3,
            '16:9' : 4,
            '16:10' : 5,
            '64:27' : 6,
            '256:135' : 7
        }

        return ratio_lookup.get(ratio, 8)

    class TypeVII(ByteBlock):

        class ScanningType(Enum):
            PROGRESSIVE=0x00
            INTERLACED=0x01
        
        class Stereo3D(Enum):
            MONO=0x00
            STEREO_3D=0x01
            MONO_OR_STEREO_3D=0x02

        class Descriptor(ByteBlock):

            horizontal_front_porch = EdidInputProperty()
            horizontal_sync_positive = EdidInputProperty()
            vertical_front_porch = EdidInputProperty()
            vertical_sync_positive = EdidInputProperty()
            scanning_type  = EdidInputProperty()
            stereo_3d  = EdidInputProperty()
            preferred  = EdidInputProperty()

            pixel_byte_conversion=lambda x: (x - 1).to_bytes(2)[::-1]

            pixel_clock = EdidProperty([0,3], byte_converter = lambda x: (
                (x - 1 & 0xFFFFFF).to_bytes(3)[::-1]
            ))
            timing_options = EdidProperty(3)
            horizontal_active_pixels = EdidProperty([4,6], byte_converter=pixel_byte_conversion)
            horizontal_blank_pixels = EdidProperty([6,8], byte_converter=pixel_byte_conversion)
            horizontal_offset = EdidProperty([8,10], byte_converter=pixel_byte_conversion)
            horizontal_sync_width = EdidProperty([10,12], byte_converter=pixel_byte_conversion)
            vertical_active_pixels = EdidProperty([12,14], byte_converter=pixel_byte_conversion)
            vertical_blank_pixels = EdidProperty([14,16], byte_converter=pixel_byte_conversion)
            vertical_offset = EdidProperty([16,18], byte_converter=pixel_byte_conversion)
            vertical_sync_width = EdidProperty([18,20], byte_converter=pixel_byte_conversion)


            def __init__(
                self,
                pixel_clock : int,
                horizontal_active_pixels : int,
                horizontal_blank_pixels : int,
                horizontal_front_porch : int,
                horizontal_sync_positive : bool,
                horizontal_sync_width : int,
                vertical_active_pixels : int,
                vertical_blank_pixels : int,
                vertical_front_porch : int,
                vertical_sync_positive : bool,
                vertical_sync_width : int,
                scanning_type : DisplayIDTimings.TypeVII.ScanningType,
                stereo_3d : DisplayIDTimings.TypeVII.Stereo3D,
                preferred : bool
            ):
                self.pixel_clock = pixel_clock # In kHz 
                self.horizontal_active_pixels = horizontal_active_pixels
                self.horizontal_blank_pixels = horizontal_blank_pixels

                self.horizontal_front_porch = horizontal_front_porch
                self.horizontal_sync_positive = horizontal_sync_positive

                self.horizontal_offset = lambda: (
                    (self.horizontal_front_porch & 0xFF) +
                    (self.horizontal_front_porch & 0x7F00) +
                    (int(self.horizontal_sync_positive) << 15)
                )

                self.horizontal_sync_width = horizontal_sync_width

                self.vertical_active_pixels = vertical_active_pixels
                self.vertical_blank_pixels = vertical_blank_pixels
                self.vertical_front_porch = vertical_front_porch

                self.vertical_sync_positive = vertical_sync_positive
                self.vertical_offset = lambda: (
                    (self.vertical_front_porch & 0xFF) +
                    (self.vertical_front_porch & 0x7F00) +
                    (int(self.vertical_sync_positive) << 15)
                )
                self.vertical_sync_width = vertical_sync_width

                # Timing options
                self.scanning_type = scanning_type
                self.stereo_3d = stereo_3d
                self.preferred = preferred

                self.timing_options = lambda: (
                    ( 
                        DisplayIDTimings.aspect_ratio_bits(
                            self.horizontal_active_pixels.value, self.vertical_active_pixels.value
                        ) & 0xF 
                    ) + (
                        self.scanning_type.value << 4
                    ) + (
                        self.stereo_3d.value << 5
                    ) + (
                        int(self.preferred) << 7
                    )
                )

        revision = EdidInputProperty()
        dsc_support = EdidInputProperty()

        block_tag = EdidProperty(0)
        revision_dsc_support = EdidProperty(1)
        num_payload_bytes = EdidProperty(2)
        timing_descriptors = EdidProperty(3)

        

        def __init__(
                self,
                revision=0,
                dsc_support=False,
                timing_descriptors: List[Descriptor]=[]
        ):
            self.block_tag = 0x22
            self.revision = revision
            self.dsc_support = dsc_support
            self.revision_dsc_support = lambda: (self.dsc_support << 2) + self.revision
            self.timing_descriptors = timing_descriptors
            self.timing_descriptors.byte_range = [3,3 + self.timing_descriptors.block_size]

            self.num_payload_bytes = lambda: self.timing_descriptors.block_size
