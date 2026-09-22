import os

from .multi_video_loader import _resolve_video, _video_from_file


MAX_VIDEOS = 50
PATHS_FIELD = "视频路径"


def _parse_paths(value):
    paths = [line.strip() for line in str(value or "").splitlines() if line.strip()]
    if len(paths) > MAX_VIDEOS:
        raise ValueError(f"最多只能加载{MAX_VIDEOS}个视频")
    return paths


class MmuuAIMultiVideoLoaderV2Node:
    CATEGORY = "MU/加载"
    FUNCTION = "load"
    RETURN_TYPES = ("VIDEO",) * MAX_VIDEOS
    RETURN_NAMES = tuple(f"视频{i}" for i in range(1, MAX_VIDEOS + 1))

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                PATHS_FIELD: ("STRING", {"default": "", "multiline": True}),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        try:
            paths = _parse_paths(kwargs.get(PATHS_FIELD, ""))
            for index, value in enumerate(paths, 1):
                _resolve_video(value, f"视频{index}")
        except (FileNotFoundError, OSError, ValueError) as error:
            return str(error)
        return True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        paths = _parse_paths(kwargs.get(PATHS_FIELD, ""))
        return tuple(
            (value, os.path.getmtime(_resolve_video(value, f"视频{index}")))
            for index, value in enumerate(paths, 1)
        )

    def load(self, **kwargs):
        paths = _parse_paths(kwargs.get(PATHS_FIELD, ""))
        outputs = [
            _video_from_file(_resolve_video(value, f"视频{index}"))
            for index, value in enumerate(paths, 1)
        ]
        outputs.extend([None] * (MAX_VIDEOS - len(outputs)))
        return tuple(outputs)
