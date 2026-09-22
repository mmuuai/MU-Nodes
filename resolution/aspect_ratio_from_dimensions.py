from math import log


SUPPORTED_ASPECT_RATIOS = ((16, 9), (9, 16), (3, 4), (4, 3), (1, 1))


class MmuuAIAspectRatioFromDimensionsV001:
    CATEGORY = "MU/工具"
    FUNCTION = "calculate"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("画面比例",)
    DESCRIPTION = "将输入尺寸按相近度归类为 16:9、9:16、3:4、4:3 或 1:1。"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "宽度": ("INT", {"default": 1920, "min": 1, "max": 65536}),
                "高度": ("INT", {"default": 1080, "min": 1, "max": 65536}),
            }
        }

    def calculate(self, 宽度, 高度):
        width, height = int(宽度), int(高度)
        if width <= 0 or height <= 0:
            raise ValueError("宽度和高度必须大于 0")
        input_ratio = width / height
        closest_ratio = min(
            SUPPORTED_ASPECT_RATIOS,
            key=lambda ratio: abs(log(input_ratio / (ratio[0] / ratio[1]))),
        )
        return (f"{closest_ratio[0]}:{closest_ratio[1]}",)
