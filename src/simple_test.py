import itertools

from edid_models import *
from math import floor


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

    bad_bytes = sorted(set(bad_bytes))

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

detailedTimingDescriptor = DetailedTimingDescriptor(
    pixel_clock = 594,
    hor_pixels = 3840,
    hor_blnk_pixels = 560
)


base_edid = BaseEDID(
    header = header,
    basic_display_parameters = displayParameters,
    chromaticity_coordinates = chromaticityCoordinates,
    standard_timings = standardTiming,
    descriptors = [detailedTimingDescriptor] *4
)

simple_test(base_edid, expected)