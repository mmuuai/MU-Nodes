from math import gcd


IMAGE_RESOLUTIONS = ("1k", "2k", "4k", "6k", "8k")
VIDEO_RESOLUTIONS = ("480p", "720p", "1080p", "2k", "4k", "6k", "8k")
ALL_RESOLUTIONS = tuple(dict.fromkeys(IMAGE_RESOLUTIONS + VIDEO_RESOLUTIONS))
ASPECT_RATIOS = (
    "1:1",
    "5:4",
    "4:5",
    "4:3",
    "3:4",
    "3:2",
    "2:3",
    "16:9",
    "9:16",
    "2:1",
    "1:2",
    "21:9",
    "9:21",
)

IMAGE_LONG_EDGES = {"1k": 1024, "2k": 2048, "4k": 4096, "6k": 6144, "8k": 8192}
VIDEO_SHORT_EDGES = {
    "480p": 480,
    "720p": 720,
    "1080p": 1080,
    "2k": 1440,
    "4k": 2160,
    "6k": 3240,
    "8k": 4320,
}


def _ratio_parts(aspect_ratio):
    width, height = (int(value) for value in aspect_ratio.split(":"))
    divisor = gcd(width, height)
    return width // divisor, height // divisor


def _round_to_multiple(value, multiple):
    return max(multiple, int(value / multiple + 0.5) * multiple)


def calculate_dimensions(media_type, resolution, aspect_ratio):
    ratio_width, ratio_height = _ratio_parts(aspect_ratio)
    if media_type == "图片":
        long_edge = IMAGE_LONG_EDGES.get(resolution, IMAGE_LONG_EDGES["1k"])
        if ratio_width >= ratio_height:
            width = long_edge
            height = long_edge * ratio_height / ratio_width
        else:
            width = long_edge * ratio_width / ratio_height
            height = long_edge
        return _round_to_multiple(width, 16), _round_to_multiple(height, 16)

    short_edge = VIDEO_SHORT_EDGES.get(resolution, VIDEO_SHORT_EDGES["1080p"])
    if ratio_width >= ratio_height:
        width = short_edge * ratio_width / ratio_height
        height = short_edge
    else:
        width = short_edge
        height = short_edge * ratio_height / ratio_width
    return _round_to_multiple(width, 2), _round_to_multiple(height, 2)


class MmuuAIResolutionSelectorV2:
    SEARCH_ALIASES = ["MU尺寸选择器V2", "图片视频尺寸", "分辨率选择器"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "类型": (("图片", "视频"), {"default": "图片"}),
                "分辨率": (ALL_RESOLUTIONS, {"default": "1k"}),
                "画面比例": (ASPECT_RATIOS, {"default": "16:9"}),
            },
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("宽度", "高度")
    FUNCTION = "select_size"
    CATEGORY = "MU/工具"
    DESCRIPTION = "按图片或视频的分辨率与画面比例输出宽度和高度。"

    def select_size(self, 类型, 分辨率, 画面比例):
        return calculate_dimensions(类型, 分辨率, 画面比例)
