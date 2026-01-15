from edid_models import bytes_to_hex_block, Header, BasicDisplayParameters, ChromaticityCoordinates, StandardTiming, DetailedTimingDescriptor, MonitorSerialNumber, MonitorRangeLimits, MonitorName, BaseEDID
from display_id_models import DisplayIDTimings, DisplayId

header = Header(
    manufacturer_id='ACR',
    product_code='b106',
    serial_num=0,
    manufacture_week=0,
    manufacture_year=1990,
    edid_version='1.4'
)

displayParameters = BasicDisplayParameters(
    video_params=BasicDisplayParameters.DigitalParameters(
        bit_depth = BasicDisplayParameters.DigitalParameters.BitDepth.BD_10,
        interface = BasicDisplayParameters.DigitalParameters.Interface.DISPLAY_PORT
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
    red_x = 0.672,
    red_y = 0.318,
    green_x = 0.208,
    green_y = 0.710,
    blue_x = 0.148,
    blue_y = 0.056,
    white_x = 0.3125,
    white_y = 0.329
)

standardTimings = []

standardTimings.append(
    StandardTiming(
        x_resolution=1280,
        aspect_ratio='4:3',
        vertical_freq=60
    )
)

standardTimings.append(
    StandardTiming(
        x_resolution=1280,
        aspect_ratio='5:4',
        vertical_freq=60
    )
)

standardTimings.append(
    StandardTiming(
        x_resolution=1280,
        aspect_ratio='16:9',
        vertical_freq=60
    )
)

standardTimings.append(
    StandardTiming(
        x_resolution=1280,
        aspect_ratio='16:10',
        vertical_freq=60
    )
)

standardTimings.append(
    StandardTiming(
        x_resolution=1440,
        aspect_ratio='16:10',
        vertical_freq=60
    )
)

standardTimings.append(
    StandardTiming(
        x_resolution=1680,
        aspect_ratio='16:10',
        vertical_freq=60
    )
)

standardTimings.append(
    StandardTiming(
        x_resolution=1920,
        aspect_ratio='16:9',
        vertical_freq=60
    )
)

dtd_descriptors = []


dtd_descriptors.append(
      DetailedTimingDescriptor(
        pixel_clock = 462.31,
        hor_pixels = 2304,
        hor_blnk_pixels = 80,
        vert_pixels = 1536,
        vert_blnk_pixels = 80,
        hor_front_porch = 8,
        hor_synch_pulse = 32,
        vert_front_porch = 8,
        vert_synch_pulse = 8,
        hor_size_mm = 291,
        vert_size_mm = 194,
        hor_border_pixels = 0,
        vert_border_pixels = 0,
        interlaced = False,
        stereo = DetailedTimingDescriptor.StereoMode.NONE,
        sync = DetailedTimingDescriptor.DigitalSeparateSync(positive_vert_sync_polarity=False)
    )
)

dtd_descriptors.append(
      DetailedTimingDescriptor(
        pixel_clock = 364.75,
        hor_pixels = 2142,
        hor_blnk_pixels = 809,
        vert_pixels = 960,
        vert_blnk_pixels = 70,
        hor_front_porch = 8,
        hor_synch_pulse = 32,
        vert_front_porch = 8,
        vert_synch_pulse = 8,
        hor_size_mm = 214,
        vert_size_mm = 96,
        hor_border_pixels = 0,
        vert_border_pixels = 0,
        interlaced = False,
        stereo = DetailedTimingDescriptor.StereoMode.NONE,
        sync = DetailedTimingDescriptor.DigitalSeparateSync(positive_vert_sync_polarity=False)
    )
)

dtd_descriptors.append(
    MonitorRangeLimits(
        vert_freq_min=24,
        vert_freq_max=144,
        hor_freq_min=10,
        hor_freq_max=510,
        pixel_clock_freq_max=107,
        extended_timing_info_type=MonitorRangeLimits.ExtendedTimingInfoType.NONE
    )
)

dtd_descriptors.append(
    MonitorName('XV273K')
)

did_descriptors = []

# 1080p 120Hz
did_descriptors.append(
    DisplayIDTimings.TypeVII.Descriptor(
        pixel_clock=274560,
        horizontal_active_pixels=1920,
        horizontal_blank_pixels=80,
        horizontal_front_porch=8,
        horizontal_sync_positive=False,
        horizontal_sync_width=32,
        vertical_active_pixels=1080,
        vertical_blank_pixels=64,
        vertical_front_porch=50,
        vertical_sync_positive=True,
        vertical_sync_width=8,
        scanning_type=DisplayIDTimings.TypeVII.ScanningType.PROGRESSIVE,
        stereo_3d=DisplayIDTimings.TypeVII.Stereo3D.MONO,
        preferred=False
    )
)

# 3840 120Hz
did_descriptors.append(
    DisplayIDTimings.TypeVII.Descriptor(
        pixel_clock=1066510,
        horizontal_active_pixels=3840,
        horizontal_blank_pixels=161,
        horizontal_front_porch=48,
        horizontal_sync_positive=True,
        horizontal_sync_width=34,
        vertical_active_pixels=2160,
        vertical_blank_pixels=4+6+53,
        vertical_front_porch=4,
        vertical_sync_positive=False,
        vertical_sync_width=6,
        scanning_type=DisplayIDTimings.TypeVII.ScanningType.PROGRESSIVE,
        stereo_3d=DisplayIDTimings.TypeVII.Stereo3D.MONO,
        preferred=False
    )
)

detailed_timings = DisplayIDTimings.TypeVII(
    0, 
    False,
    timing_descriptors = did_descriptors
)

display_id = DisplayId(product_type=DisplayId.ProductType.EXTENSION_SECTION, section_type=DisplayId.SectionType.EDID_EXTENSION_BLOCK, data_blocks=[detailed_timings])


base_edid = BaseEDID(
    header = header,
    basic_display_parameters = displayParameters,
    chromaticity_coordinates = chromaticityCoordinates,
    standard_timings = standardTimings,
    established_timing='234800',
    descriptors = dtd_descriptors,
                   extension_blocks=[display_id]
)

# print(base_edid)

with open("did_test_out.bin", "wb") as binary_file:
    binary_file.write(base_edid.as_bytes)

from simple_test import simple_test

with(open('../resources/did_test_exp.hex', 'r')) as file:
        expected = file.read()

simple_test(base_edid, expected, print_bad_bytes=True)