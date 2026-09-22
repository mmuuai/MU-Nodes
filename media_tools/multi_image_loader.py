import os


MAX_IMAGES = 10
IMAGE_FIELDS = tuple(f"图片文件{i}" for i in range(1, MAX_IMAGES + 1))


def _input_images():
    import folder_paths

    input_dir = folder_paths.get_input_directory()
    files = []
    for root, _, names in os.walk(input_dir):
        for name in names:
            relative = os.path.relpath(os.path.join(root, name), input_dir).replace("\\", "/")
            files.append(relative)
    try:
        files = folder_paths.filter_files_content_types(files, ["image"])
    except Exception:
        extensions = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff")
        files = [name for name in files if name.lower().endswith(extensions)]
    return [""] + sorted(files)


def _resolve_image(value, label):
    if not value:
        return None
    import folder_paths

    path = folder_paths.get_annotated_filepath(value)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{label}不存在：{value}")
    return path


def _load_image(value):
    from nodes import LoadImage

    return LoadImage().load_image(value)[0]


class MmuuAIMultiImageLoaderNode:
    CATEGORY = "MU/加载"
    FUNCTION = "load"
    RETURN_TYPES = ("IMAGE",) * MAX_IMAGES
    RETURN_NAMES = tuple(f"图片{i}" for i in range(1, MAX_IMAGES + 1))

    @classmethod
    def INPUT_TYPES(cls):
        options = _input_images()
        return {
            "required": {
                name: (options, {"default": "", "image_upload": True})
                for name in IMAGE_FIELDS
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        for index, name in enumerate(IMAGE_FIELDS, 1):
            value = kwargs.get(name, "")
            if value:
                try:
                    _resolve_image(value, f"图片文件{index}")
                except (FileNotFoundError, OSError) as error:
                    return str(error)
        return True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        fingerprints = []
        for index, name in enumerate(IMAGE_FIELDS, 1):
            value = kwargs.get(name, "")
            path = _resolve_image(value, f"图片文件{index}") if value else None
            fingerprints.append((value, os.path.getmtime(path) if path else None))
        return tuple(fingerprints)

    def load(self, **kwargs):
        outputs = []
        for index, name in enumerate(IMAGE_FIELDS, 1):
            value = kwargs.get(name, "")
            _resolve_image(value, f"图片文件{index}") if value else None
            outputs.append(_load_image(value) if value else None)
        return tuple(outputs)
