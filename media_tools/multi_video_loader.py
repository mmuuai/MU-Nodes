import os


MAX_VIDEOS = 6
VIDEO_FIELDS = tuple(f"视频文件{i}" for i in range(1, MAX_VIDEOS + 1))


def _input_videos():
    import folder_paths

    input_dir = folder_paths.get_input_directory()
    files = []
    for root, _, names in os.walk(input_dir):
        for name in names:
            relative = os.path.relpath(os.path.join(root, name), input_dir).replace("\\", "/")
            files.append(relative)
    try:
        files = folder_paths.filter_files_content_types(files, ["video"])
    except Exception:
        extensions = (".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v")
        files = [name for name in files if name.lower().endswith(extensions)]
    return [""] + sorted(files)


def _resolve_video(value, label):
    if not value:
        return None
    import folder_paths

    path = folder_paths.get_annotated_filepath(value)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{label}不存在：{value}")
    return path


def _video_from_file(path):
    from comfy_api.latest import InputImpl

    return InputImpl.VideoFromFile(path)


class MmuuAIMultiVideoLoaderNode:
    CATEGORY = "MU/加载"
    FUNCTION = "load"
    RETURN_TYPES = ("VIDEO",) * MAX_VIDEOS
    RETURN_NAMES = tuple(f"视频{i}" for i in range(1, MAX_VIDEOS + 1))

    @classmethod
    def INPUT_TYPES(cls):
        options = _input_videos()
        return {
            "required": {
                name: (options, {"default": "", "video_upload": True})
                for name in VIDEO_FIELDS
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        for index, name in enumerate(VIDEO_FIELDS, 1):
            value = kwargs.get(name, "")
            if value:
                try:
                    _resolve_video(value, f"视频文件{index}")
                except (FileNotFoundError, OSError) as error:
                    return str(error)
        return True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        fingerprints = []
        for index, name in enumerate(VIDEO_FIELDS, 1):
            value = kwargs.get(name, "")
            path = _resolve_video(value, f"视频文件{index}") if value else None
            fingerprints.append((value, os.path.getmtime(path) if path else None))
        return tuple(fingerprints)

    def load(self, **kwargs):
        outputs = []
        for index, name in enumerate(VIDEO_FIELDS, 1):
            path = _resolve_video(kwargs.get(name, ""), f"视频文件{index}")
            outputs.append(_video_from_file(path) if path else None)
        return tuple(outputs)
