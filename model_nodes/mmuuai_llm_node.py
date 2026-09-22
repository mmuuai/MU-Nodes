from .common import KEY_ADVERTISEMENT, api_key_from_value, choice, collect_images, raw_response
from .media import MAX_IMAGES, MAX_VIDEOS
from .mmuuai_client import MmuuAIClient
from .mmuuai_media import uploaded_file, video_upload
from .mmuuai_parameters import build_parameters, upload_parameter
from .models import LLM_MODEL_IDS


class MmuuAIDirectLLMModelNode:
    CATEGORY = "MU/接口"
    FUNCTION = "execute"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("文本", "原始响应")

    @classmethod
    def INPUT_TYPES(cls):
        optional = {f"图片{i}": ("IMAGE",) for i in range(1, MAX_IMAGES + 1)}
        optional.update({f"视频{i}": ("VIDEO",) for i in range(1, MAX_VIDEOS + 1)})
        return {
            "required": {
                "模型": choice(tuple(LLM_MODEL_IDS), "OpenAI｜LLM｜GPT-5.6 Luna"),
                "key": ("STRING", {"default": KEY_ADVERTISEMENT, "password": True}),
                "自定义模型名称或ID": ("STRING", {"default": ""}),
                "系统提示词": ("STRING", {"default": "", "multiline": True, "dynamicPrompts": False}),
                "提示词": ("STRING", {"default": "", "multiline": True, "dynamicPrompts": False}),
                "温度": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "思考强度": choice(("自动（模型默认）", "最少", "低", "中", "高", "极高", "最高")),
                "最大令牌数": ("INT", {"default": 128000, "min": 1, "max": 128000, "step": 1}),
                "回答详细度（GPT）": choice(("自动（模型默认）", "简洁", "标准", "详细")),
                "推理模式（统一响应）": choice(("标准", "专业")),
                "超时时间（秒，0不限）": ("INT", {"default": 600, "min": 0, "max": 2147483647, "step": 1}),
            },
            "optional": optional,
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def execute(self, **values):
        client = MmuuAIClient(
            api_key_from_value(values["key"]), values["超时时间（秒，0不限）"]
        )
        resource = client.resolve_model(
            values["模型"], values["自定义模型名称或ID"], LLM_MODEL_IDS
        )
        parameters = build_parameters(resource, _parameter_requests(values))
        files = _upload_inputs(client, resource, collect_images(values), values)
        messages = []
        if values["系统提示词"].strip():
            messages.append({"role": "system", "content": values["系统提示词"]})
        messages.append({"role": "user", "content": values["提示词"]})
        task_input = {"messages": messages}
        if parameters:
            task_input["parameters"] = parameters
        if files:
            task_input["files"] = files
        response = client.run_model(resource, task_input)
        result = response.get("result") if isinstance(response, dict) else None
        text = result.get("text") if isinstance(result, dict) else None
        if not isinstance(text, str):
            raise RuntimeError("mmuuai LLM 结果中没有文本")
        return text, raw_response(response)


def _parameter_requests(values):
    requests = [
        (("temperature",), values["温度"], "number"),
        (("max_output_tokens", "maxOutputTokens", "max_tokens", "maxTokens"), values["最大令牌数"], "number"),
    ]
    if values["思考强度"] != "自动（模型默认）":
        requests.append((("reasoning_effort", "reasoningEffort", "thinking_level", "thinkingLevel"), values["思考强度"], "semantic"))
    if values["回答详细度（GPT）"] != "自动（模型默认）":
        requests.append((("verbosity", "text_verbosity", "textVerbosity"), values["回答详细度（GPT）"], "semantic"))
    if values["推理模式（统一响应）"] == "专业":
        requests.append((("reasoning_mode", "reasoningMode"), "专业", "semantic"))
    return requests


def _upload_inputs(client, resource, images, values):
    files = []
    image_parameter = upload_parameter(resource, "image")
    if images and not image_parameter:
        raise ValueError("所选 mmuuai 模型不支持图片附件")
    for index, data in enumerate(images, 1):
        files.append(uploaded_file(client, data, "image", f"image-{index}.png", "image/png", image_parameter))
    videos = [values.get(f"视频{index}") for index in range(1, MAX_VIDEOS + 1)]
    videos = [video for video in videos if video is not None]
    video_parameter = upload_parameter(resource, "video")
    if videos and not video_parameter:
        raise ValueError("所选 mmuuai 模型不支持视频附件")
    for index, video in enumerate(videos, 1):
        data, file_name, mime_type = video_upload(video, index)
        files.append(uploaded_file(client, data, "video", file_name, mime_type, video_parameter))
    return files
