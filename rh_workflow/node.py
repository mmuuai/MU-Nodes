import json

from .api import RHClient
from .media import audio_to_wav, image_to_png, video_to_file


AUTO_FIELD = "自动识别"
FIELD_PREFERENCES = {
    "文本": ("prompt", "text", "content", "string"),
    "图片": ("image", "upload"),
    "音频": ("audio", "upload"),
    "视频": ("video", "upload"),
}
def resolve_field(workflow, node_id, requested, kind):
    node = workflow.get(str(node_id))
    if not isinstance(node, dict):
        raise ValueError(f"RH 工作流中不存在{kind}目标节点：{node_id}")
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError(f"RH 节点 {node_id} 没有可修改的 inputs")
    if requested != AUTO_FIELD:
        if requested not in inputs:
            raise ValueError(f"RH 节点 {node_id} 不包含字段 {requested}")
        return requested
    for candidate in FIELD_PREFERENCES[kind]:
        if candidate in inputs:
            return candidate
    names = "、".join(inputs) or "无"
    raise ValueError(f"无法自动识别 RH 节点 {node_id} 的{kind}字段；可用字段：{names}")


class MmuuAIRHWorkflowNode:
    OUTPUT_NODE = True
    CATEGORY = "MU/接口"
    FUNCTION = "execute"
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务编号", "任务状态", "结果链接", "原始响应")

    @classmethod
    def INPUT_TYPES(cls):
        field = ("STRING", {"default": AUTO_FIELD})
        return {
            "required": {
                "RH密钥": ("STRING", {"default": "", "password": True}),
                "工作流号": ("STRING", {"default": ""}),
                "访问密码": ("STRING", {"default": "", "password": True}),
                "文本节点号": ("STRING", {"default": ""}),
                "文本字段": field,
                "图片节点号": ("STRING", {"default": ""}),
                "图片字段": field,
                "音频节点号": ("STRING", {"default": ""}),
                "音频字段": field,
                "视频节点号": ("STRING", {"default": ""}),
                "视频字段": field,
                "轮询间隔（秒）": ("FLOAT", {"default": 3.0, "min": 1.0, "max": 30.0, "step": 0.5}),
                "超时时间（秒，0不限）": ("INT", {"default": 1800, "min": 0, "max": 2147483647}),
            },
            "optional": {
                "文本": ("STRING", {"forceInput": True}),
                "图片": ("IMAGE",),
                "音频": ("AUDIO",),
                "视频": ("VIDEO",),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def execute(self, **values):
        api_key = values["RH密钥"].strip()
        workflow_id = values["工作流号"].strip()
        if not api_key or not workflow_id:
            raise ValueError("必须填写 RH密钥 和 工作流号")
        connected = [(kind, values.get(kind)) for kind in ("文本", "图片", "音频", "视频")]
        connected = [(kind, value) for kind, value in connected if value is not None]
        if not connected:
            raise ValueError("至少连接一个文本、图片、音频或视频输入")

        client = RHClient(api_key, values["超时时间（秒，0不限）"])
        try:
            workflow = client.get_workflow(workflow_id)
            node_info = []
            for kind, value in connected:
                node_id = values[f"{kind}节点号"].strip()
                if not node_id:
                    raise ValueError(f"连接了{kind}输入，但没有填写{kind}节点号")
                field_name = resolve_field(workflow, node_id, values[f"{kind}字段"].strip(), kind)
                field_value = value if kind == "文本" else self._upload(client, kind, value)
                node_info.append({
                    "nodeId": node_id, "fieldName": field_name, "fieldValue": field_value,
                })
            task_id, submitted = client.create_task(
                workflow_id, node_info, values["访问密码"].strip(),
            )
            status, result = client.wait(
                task_id, values["轮询间隔（秒）"], values["超时时间（秒，0不限）"],
            )
            urls = [item.get("url") for item in result.get("results", []) if item.get("url")]
            raw = json.dumps({"提交": submitted, "结果": result}, ensure_ascii=False)
            return task_id, status, json.dumps(urls, ensure_ascii=False), raw.replace(api_key, "[REDACTED]")
        except Exception as exc:
            message = str(exc).replace(api_key, "[REDACTED]")
            raise RuntimeError(f"mmuuai RH工作流调用失败：{message}") from exc

    @staticmethod
    def _upload(client, kind, value):
        converters = {"图片": image_to_png, "音频": audio_to_wav, "视频": video_to_file}
        content, filename, mime_type = converters[kind](value)
        return client.upload(content, filename, mime_type)
