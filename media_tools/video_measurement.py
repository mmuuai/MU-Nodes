import math
from numbers import Integral

import torch


def _validate_frame_rate(frame_rate):
    value = float(frame_rate)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("帧率必须是大于 0 的有限数值")
    return value


def _image_sequence_info(images, frame_rate):
    if not isinstance(images, torch.Tensor) or images.ndim != 4:
        raise ValueError("图片序列必须是 [帧数, 高度, 宽度, 通道] 格式")
    frame_count, height, width = (int(images.shape[index]) for index in range(3))
    if min(frame_count, height, width) <= 0:
        raise ValueError("图片序列的帧数、宽度和高度必须大于 0")
    return width, height, _validate_frame_rate(frame_rate), frame_count


class MmuuAIFrameCountCalculatorV001:
    CATEGORY = "MU/工具"
    FUNCTION = "calculate"
    RETURN_TYPES = ("INT", "FLOAT")
    RETURN_NAMES = ("总帧数（整数）", "总帧数（浮点）")
    DESCRIPTION = "根据帧率和时长计算总帧数；整数结果按四舍五入取整。"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "帧率": ("FLOAT", {"default": 24.0, "min": 0.001, "max": 1000.0, "step": 0.001}),
                "时长（秒）": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 86400.0, "step": 0.1}),
            }
        }

    def calculate(self, 帧率, **values):
        duration = float(values["时长（秒）"])
        rate = _validate_frame_rate(帧率)
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("时长必须是大于或等于 0 的有限数值")
        frame_count = rate * duration
        integer_count = math.floor(frame_count + 0.5)
        return integer_count, frame_count


class MmuuAIVideoInfoNodeV001:
    CATEGORY = "MU/媒体处理"
    FUNCTION = "get_info"
    RETURN_TYPES = ("INT", "INT", "FLOAT", "INT", "FLOAT")
    RETURN_NAMES = ("宽度", "高度", "帧率", "总帧数", "时长（秒）")
    DESCRIPTION = "读取 VIDEO 的画面和帧率信息，或读取图片序列并使用指定帧率计算时长。"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "图片序列帧率": ("FLOAT", {"default": 24.0, "min": 0.001, "max": 1000.0, "step": 0.001}),
            },
            "optional": {
                "视频": ("VIDEO",),
                "图片序列": ("IMAGE",),
            },
        }

    def get_info(self, 图片序列帧率, 视频=None, 图片序列=None):
        if (视频 is None) == (图片序列 is None):
            raise ValueError("请且仅连接视频或图片序列中的一个")

        if 视频 is not None:
            components = 视频.get_components()
            width, height, frame_rate, frame_count = _image_sequence_info(
                components.images, components.frame_rate
            )
        else:
            width, height, frame_rate, frame_count = _image_sequence_info(
                图片序列, 图片序列帧率
            )

        duration = frame_count / frame_rate
        return width, height, frame_rate, frame_count, duration
