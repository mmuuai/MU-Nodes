import json


FORMAT_MODES = ("TXT", "MD", "JSON")


def prepare_display(text, mode):
    raw = str(text or "")
    if mode != "JSON" or not raw.strip():
        return raw, ""
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        status = f"JSON格式错误：第{error.lineno}行，第{error.colno}列，{error.msg}"
        return raw, status
    return json.dumps(value, ensure_ascii=False, indent=2), "JSON格式有效"


class MmuuAITextViewerNode:
    CATEGORY = "MU/文本"
    FUNCTION = "view"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("文本",)
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "格式": (FORMAT_MODES, {"default": "TXT"}),
                "文本": (
                    "STRING",
                    {"default": "", "multiline": True, "dynamicPrompts": False},
                ),
            },
            "optional": {
                "文本输入": ("STRING", {"forceInput": True}),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **_kwargs):
        return float("nan")

    def view(self, 格式, 文本, 文本输入=None):
        raw = str(文本输入) if 文本输入 is not None else str(文本 or "")
        display, status = prepare_display(raw, 格式)
        return {
            "ui": {
                "原始文本": [raw],
                "文本预览": [display],
                "格式": [格式],
                "格式状态": [status],
            },
            "result": (raw,),
        }
