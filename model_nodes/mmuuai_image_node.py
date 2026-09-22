from .common import KEY_ADVERTISEMENT, api_key_from_value, choice, collect_images, raw_response
from .image_node import _resolution_validation
from .media import MAX_IMAGES, decode_image_batch
from .mmuuai_client import MmuuAIClient
from .mmuuai_media import uploaded_file
from .mmuuai_parameters import build_parameters, upload_parameter
from .models import IMAGE_MODEL_IDS


class MmuuAIDirectImageModelNode:
    CATEGORY = "MU/接口"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("图片", "原始响应")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "模型": choice(tuple(IMAGE_MODEL_IDS), "OpenAI｜图片｜GPT Image 2"),
                "key": ("STRING", {"default": KEY_ADVERTISEMENT, "password": True}),
                "自定义模型名称或ID": ("STRING", {"default": ""}),
                "提示词": ("STRING", {"default": "", "multiline": True, "dynamicPrompts": False}),
                "分辨率": choice(("自动", "1K", "2K", "4K")),
                "尺寸": choice((
                    "自动", "1024x1024", "1536x1024", "1024x1536", "1:1", "3:2", "2:3",
                    "4:3", "3:4", "16:9", "9:16",
                )),
                "质量": choice(("自动", "low", "medium", "high")),
                "审核强度": choice(("自动（上游默认）", "低")),
                "超时时间（秒，0不限）": ("INT", {"default": 600, "min": 0, "max": 2147483647, "step": 1}),
            },
            "optional": {f"图片{i}": ("IMAGE",) for i in range(1, MAX_IMAGES + 1)},
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def execute(self, **values):
        client = MmuuAIClient(
            api_key_from_value(values["key"]), values["超时时间（秒，0不限）"]
        )
        resource = client.resolve_model(
            values["模型"], values["自定义模型名称或ID"], IMAGE_MODEL_IDS
        )
        parameters = build_parameters(resource, _parameter_requests(values))
        images = collect_images(values)
        files = _upload_images(client, resource, images)
        task_input = {"prompt": values["提示词"]}
        if parameters:
            task_input["parameters"] = parameters
        if files:
            task_input["files"] = files
        response = client.run_model(resource, task_input)
        result = response.get("result") if isinstance(response, dict) else None
        image = decode_image_batch(result, client.download_image)
        if image is None:
            raise RuntimeError("mmuuai 图片结果中没有可解析的图片")
        validation = _resolution_validation(image, values["分辨率"], values["尺寸"])
        return image, raw_response({"mmuuai响应": response, "MU返图核验": validation})


def _parameter_requests(values):
    requests = []
    if values["分辨率"] != "自动":
        requests.append((("resolution", "image_size", "imageSize"), values["分辨率"], "option"))
    if values["尺寸"] != "自动":
        requests.append((("size", "aspect_ratio", "aspectRatio"), values["尺寸"], "option"))
    if values["质量"] != "自动":
        requests.append((("quality",), values["质量"], "option"))
    if values["审核强度"] == "低":
        requests.append((("moderation",), "low", "option"))
    return requests


def _upload_images(client, resource, images):
    if not images:
        return []
    parameter = upload_parameter(resource, "image")
    if not parameter:
        raise ValueError("所选 mmuuai 模型不支持图片编辑输入")
    return [
        uploaded_file(client, data, "image", f"image-{index}.png", "image/png", parameter)
        for index, data in enumerate(images, 1)
    ]
