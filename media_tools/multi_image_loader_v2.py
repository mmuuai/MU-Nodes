import os


MAX_IMAGES = 50
PATHS_FIELD = "图片路径"
INTERPOLATIONS = {
    "兰索斯（高质量）": "lanczos",
    "双三次": "bicubic",
    "双线性": "bilinear",
    "区域平均": "area",
    "最近邻": "nearest-exact",
}


def _parse_paths(value):
    paths = [line.strip() for line in str(value or "").splitlines() if line.strip()]
    if len(paths) > MAX_IMAGES:
        raise ValueError(f"最多只能加载{MAX_IMAGES}张图片")
    return paths


def _resolve_image(value, label):
    import folder_paths

    path = folder_paths.get_annotated_filepath(value)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{label}不存在：{value}")
    return path


def _load_image(value):
    from nodes import LoadImage

    return LoadImage().load_image(value)[0]


def _aligned(value, multiple):
    return max(multiple, round(value / multiple) * multiple)


def _target_size(width, height, short_side, multiple):
    if short_side <= 0:
        return width, height
    scale = short_side / min(width, height)
    return _aligned(width * scale, multiple), _aligned(height * scale, multiple)


def _resize_settings(kwargs):
    interpolation = kwargs.get("插值算法", "兰索斯（高质量）")
    short_side = int(kwargs.get("短边尺寸", 720))
    multiple = int(kwargs.get("尺寸倍数", 16))
    if interpolation not in INTERPOLATIONS:
        raise ValueError(f"不支持的插值算法：{interpolation}")
    if short_side < 0:
        raise ValueError("短边尺寸不能小于0")
    if multiple < 1:
        raise ValueError("尺寸倍数不能小于1")
    return short_side, interpolation, multiple


def _resize_image(image, short_side, interpolation, multiple):
    if short_side <= 0:
        return image
    import comfy.utils

    height, width = image.shape[1:3]
    target_width, target_height = _target_size(width, height, short_side, multiple)
    if (target_width, target_height) == (width, height):
        return image
    samples = image.movedim(-1, 1)
    resized = comfy.utils.common_upscale(
        samples,
        target_width,
        target_height,
        INTERPOLATIONS[interpolation],
        "disabled",
    )
    return resized.movedim(1, -1)


class MmuuAIMultiImageLoaderV2Node:
    CATEGORY = "MU/加载"
    FUNCTION = "load"
    RETURN_TYPES = ("IMAGE",) * MAX_IMAGES
    RETURN_NAMES = tuple(f"图片{i}" for i in range(1, MAX_IMAGES + 1))

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                PATHS_FIELD: ("STRING", {"default": "", "multiline": True}),
                "插值算法": (list(INTERPOLATIONS), {"default": "兰索斯（高质量）"}),
                "短边尺寸": ("INT", {"default": 720, "min": 0, "max": 8192, "step": 8}),
                "尺寸倍数": ("INT", {"default": 16, "min": 1, "max": 256, "step": 1}),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        try:
            _resize_settings(kwargs)
            paths = _parse_paths(kwargs.get(PATHS_FIELD, ""))
            for index, value in enumerate(paths, 1):
                _resolve_image(value, f"图片{index}")
        except (FileNotFoundError, OSError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        paths = _parse_paths(kwargs.get(PATHS_FIELD, ""))
        settings = _resize_settings(kwargs)
        files = tuple(
            (value, os.path.getmtime(_resolve_image(value, f"图片{index}")))
            for index, value in enumerate(paths, 1)
        )
        return settings, files

    def load(self, **kwargs):
        paths = _parse_paths(kwargs.get(PATHS_FIELD, ""))
        short_side, interpolation, multiple = _resize_settings(kwargs)
        outputs = [
            _resize_image(_load_image(value), short_side, interpolation, multiple)
            for value in paths
        ]
        outputs.extend([None] * (MAX_IMAGES - len(outputs)))
        return tuple(outputs)
