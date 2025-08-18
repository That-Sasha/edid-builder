import itertools
import re

from edid_models import *
from math import ceil, floor


def get_parameters(object, field_name, first_byte_relative):
    parameters = []
    child_prop_names = [a for a in dir(object) if 'EdidPropertyValue' in str(type(getattr(object, a)))]

    child_prop_names= sorted(child_prop_names, key = lambda name: (getattr(object, name).byte_range[0]))

    for child_name in child_prop_names:

        child_wrapper = getattr(object, child_name)
        child_instance = child_wrapper.value

        grandchild_props_names = [a for a in dir(child_instance) if 'EdidPropertyValue' in str(type(getattr(child_instance, a)))]

        byte_range = child_wrapper.byte_range

        child_start_byte = first_byte_relative + byte_range[0]
        child_end_byte = first_byte_relative + byte_range[1] - 1

        if isinstance(child_instance, list):
            if all(isinstance(child_item, ByteBlock) for child_item in child_instance):
                block_size = (byte_range[1] - byte_range[0]) / len(child_instance)

                for num, child_item in enumerate(child_instance):

                    parameters.extend(get_parameters(child_item, f'{child_name}{num}', child_start_byte + num * block_size))
            else:
                parameters.append({'field' : child_name, 'instance' : child_wrapper, 'bytes' : [int(child_start_byte), int(child_end_byte)]})
        elif grandchild_props_names:
            parameters.extend(get_parameters(child_instance, child_name, first_byte_relative + byte_range[0]))
        else:
            parameters.append({'field' : child_name, 'instance' : child_wrapper, 'bytes' : [int(child_start_byte), int(child_end_byte)]})

    return list(map(lambda x: {'field' : f'{field_name}.{x['field']}', 'instance' : x['instance'], 'bytes' : x['bytes']}, parameters))

def describe_params(object, field_name):
    parameters = get_parameters(object, field_name, 0)
    parameters = list(map(lambda x: {'field' : x['field'], 'instance' : x['instance'], 'bytes' : f'{x['bytes'][0]} - {x['bytes'][1]}', 'hex' : ' '.join(format(byte, '02x') for byte in x['instance'].as_bytes).upper(), 'value' : x['instance'].value}, parameters))

    widths = {}
    columns = ['Bytes', 'Field', 'Hex', 'Value']

    for key in columns:
        max_width = max([len(str(x)) for x in [param[key.lower()] for param in parameters]])
        widths[key.lower()] = (ceil(max_width / 5) + 1 ) * 5

    # Header
    rows = [''.join([col.ljust(widths[col.lower()]) for col in columns])]

    for param in parameters:
        rows.append(''.join([str(param[col.lower()]).ljust(widths[col.lower()]) for col in columns]))

    return rows

def simple_test(test_class, expected, print_bad_bytes=True):

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

    bad_bytes = sorted(set(bad_bytes))

    if len(bad_bytes) > 0:
        error_string = [
            '\nMismatch in bytes: ' + ', '.join([str(x) for x in bad_bytes]),
            '',
            highlight_match,
            '\033[95m'
        ]

        if print_bad_bytes:
            error_string.append('Bad fields: ')

            all_params = describe_params(test_class, test_class.__class__.__name__)
            error_string.append(all_params[0])

            for bad_byte in bad_bytes:
                for param in all_params[1:]:
                    if bad_byte in range(int(param.split(' ')[0]), int(param.split(' ')[2]) + 1) and param not in error_string:
                        error_string.append(param)

        error_string = '\n'.join(error_string)

        assert False, error_string
    else:
        print(f'Simple test success!\n{highlight_match}')


# Simple test case
with(open('../resources/3840x2160.hex', 'r')) as file:
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
    video_params=BasicDisplayParameters.AnalogueParameters(
                white_sync_lvls=BasicDisplayParameters.AnalogueParameters.WhiteAndSyncLevels.w07s0,
                BTB=False,
                separate_sync_support=True,
                composite_sync_support=True,
                sync_on_green=False,
                serration_on_vsync_pulse=True
            ),
    horizontal_size=100,
    vertical_size=56,
    gamma=2.2,
    suported_features=BasicDisplayParameters.SupportedFeatures (
                    dpms_standby=True,
                    dpms_suspend=True,
                    dpms_active_off=True,
                    display_type=BasicDisplayParameters.SupportedFeatures.AnalogueDisplayType.RGB,
                    standard_srgb=False,
                    dtd_block_1_is_preferred=True,
                    continuous_timings=False
                )
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

detailedTimingDescriptor = DetailedTimingDescriptor(
    pixel_clock = 594,
    hor_pixels = 3840,
    hor_blnk_pixels = 560,
    vert_pixels = 2160,
    vert_blnk_pixels = 90,
    hor_front_porch = 176,
    hor_synch_pulse = 88,
    vert_front_porch = 8,
    vert_synch_pulse = 10,
    hor_size_mm = 1000,
    vert_size_mm = 562,
    hor_border_pixels = 0,
    vert_border_pixels = 0,
    interlaced = False,
    stereo = DetailedTimingDescriptor.StereoMode.NONE,
    sync = DetailedTimingDescriptor.DigitalSeparateSync()
)

serial_number = MonitorSerialNumber('Linux #0')

monitor_range_limits = MonitorRangeLimits()

edid_name = MonitorName('3840x2160')

base_edid = BaseEDID(
    header = header,
    basic_display_parameters = displayParameters,
    chromaticity_coordinates = chromaticityCoordinates,
    standard_timings = standardTiming,
    descriptors = [
                    detailedTimingDescriptor,
                    serial_number,
                    monitor_range_limits,
                    edid_name
                   ],
    num_ext_blocks = 0
)

simple_test(base_edid, expected, print_bad_bytes=False)

rows = describe_params(base_edid, 'base_edid')

[print(row) for row in rows]
print()
print(f'Edid built from {len(rows)} unique parameters')