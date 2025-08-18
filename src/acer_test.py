from edid_models import *
from simple_test import simple_test

header = Header(
    manufacturer_id='ACR',
    product_code='B106',
    serial_num=0,
    manufacture_week=0,
    manufacture_year=1990,
    edid_version='1.4'
)

displayParameters = BasicDisplayParameters(
    video_params=BasicDisplayParameters.DigitalParameters(
        bit_depth=BasicDisplayParameters.DigitalParameters.BitDepth.BD_10,
        interface=BasicDisplayParameters.DigitalParameters.Interface.DISPLAY_PORT
    ),
    horizontal_size=60,
    vertical_size=34,
    gamma=2.2,
    suported_features=BasicDisplayParameters.SupportedFeatures (
                    dpms_standby=False,
                    dpms_suspend=False,
                    dpms_active_off=True,
                    display_type=BasicDisplayParameters.SupportedFeatures.DigitalDisplayType.RGB444_YCrCb444_YCrCb422,
                    standard_srgb=False,
                    dtd_block_1_is_preferred=False,
                    continuous_timings=True
                )
)

chromaticityCoordinates = ChromaticityCoordinates(
    red_x = 688,
    red_y = 326,
    green_x = 213,
    green_y = 727,
    blue_x = 152,
    blue_y = 57,
    white_x = 320,
    white_y = 337
)

standardTimings = [
    StandardTiming(
        x_resolution=1280,
        aspect_ratio='4:3',
        vertical_freq=60
    ),
    StandardTiming(
        x_resolution=1280,
        aspect_ratio='5:4',
        vertical_freq=60
    ),
    StandardTiming(
        x_resolution=1280,
        aspect_ratio='16:9',
        vertical_freq=60
    ),
    StandardTiming(
        x_resolution=1280,
        aspect_ratio='16:10',
        vertical_freq=60
    ),
    StandardTiming(
        x_resolution=1440,
        aspect_ratio='16:10',
        vertical_freq=60
    ),
    StandardTiming(
        x_resolution=1680,
        aspect_ratio='16:10',
        vertical_freq=60
    ),
    StandardTiming(
        x_resolution=1920,
        aspect_ratio='16:9',
        vertical_freq=60
    )
]

detailedTimingDescriptor_0 = DetailedTimingDescriptor(
    pixel_clock = 533.25,
    hor_pixels = 3840,
    hor_blnk_pixels = 160,
    vert_pixels = 2160,
    vert_blnk_pixels = 62,
    hor_front_porch = 48,
    hor_synch_pulse = 32,
    vert_front_porch = 3,
    vert_synch_pulse = 5,
    hor_size_mm = 597,
    vert_size_mm = 336,
    hor_border_pixels = 0,
    vert_border_pixels = 0,
    interlaced = False,
    stereo = DetailedTimingDescriptor.StereoMode.NONE,
    sync = DetailedTimingDescriptor.DigitalSeparateSync(
            positive_vert_sync_polarity=False
        )
)

detailedTimingDescriptor_1 = DetailedTimingDescriptor(
    pixel_clock = 262.92,
    hor_pixels = 3840,
    hor_blnk_pixels = 160,
    vert_pixels = 2160,
    vert_blnk_pixels = 31,
    hor_front_porch = 8,
    hor_synch_pulse = 32,
    vert_front_porch = 17,
    vert_synch_pulse = 8,
    hor_size_mm = 597,
    vert_size_mm = 336,
    hor_border_pixels = 0,
    vert_border_pixels = 0,
    interlaced = False,
    stereo = DetailedTimingDescriptor.StereoMode.NONE,
    sync = DetailedTimingDescriptor.DigitalSeparateSync(
            positive_vert_sync_polarity=False
        )
)

monitor_range_limits = MonitorRangeLimits(
    vert_freq_min=24,
    vert_freq_max=144,
    hor_freq_min=10,
    hor_freq_max=510,
    pixel_clock_freq_max=107,
    extended_timing_info_type=MonitorRangeLimits.ExtendedTimingInfoType.NONE
)

edid_name = MonitorName('XV273K')

base_edid = BaseEDID(
    header = header,
    basic_display_parameters = displayParameters,
    chromaticity_coordinates = chromaticityCoordinates,
    established_timing = '234800',
    standard_timings = standardTimings,
    descriptors = [
                    detailedTimingDescriptor_0,
                    detailedTimingDescriptor_1,
                    monitor_range_limits,
                    edid_name
                   ],
    extension_blocks = [
        detailedTimingDescriptor_0,
        detailedTimingDescriptor_1
    ]
)

# Simple test case
with(open('../resources/acer-xv273k-corrected_difdb.hex', 'r')) as file:
    expected_acer = file.read()

# with open("acer_mimic.bin", "wb") as binary_file:
#         binary_file.write(base_edid.as_bytes)

simple_test(base_edid, expected_acer, print_bad_bytes=False, print_expected=True)
