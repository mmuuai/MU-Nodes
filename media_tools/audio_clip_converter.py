import math

import torch


def _audio_clip_bounds(audio, start_seconds, end_seconds):
    if not isinstance(audio, dict):
        raise ValueError("输入不是有效音频")
    waveform = audio.get("waveform")
    sample_rate = audio.get("sample_rate")
    if not isinstance(waveform, torch.Tensor) or waveform.ndim < 1 or not sample_rate:
        raise ValueError("输入不是有效音频")
    sample_rate = int(sample_rate)
    sample_count = int(waveform.shape[-1])
    if sample_count < 1:
        raise ValueError("输入音频没有可处理的采样")

    start = max(0.0, float(start_seconds or 0.0))
    end = max(0.0, float(end_seconds or 0.0))
    if end and end <= start:
        raise ValueError("结束时间必须大于开始时间")

    duration = sample_count / sample_rate
    if start and start >= duration:
        raise ValueError("开始时间超出音频时长")
    start_sample = min(sample_count - 1, max(0, int(math.floor(start * sample_rate))))
    end_sample = sample_count if not end else min(
        sample_count,
        max(start_sample + 1, int(math.ceil(end * sample_rate))),
    )
    if end_sample <= start_sample:
        raise ValueError("时间范围没有包含任何音频采样")
    return start_sample, end_sample


class MmuuAIAudioClipConverterNode:
    CATEGORY = "MU/媒体处理"
    FUNCTION = "clip"
    RETURN_TYPES = ("AUDIO",)
    RETURN_NAMES = ("音频",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "开始时间（秒，0不限制）": (
                    "FLOAT",
                    {"default": 0.0, "min": 0.0, "max": 86400.0, "step": 0.1},
                ),
                "结束时间（秒，0不限制）": (
                    "FLOAT",
                    {"default": 0.0, "min": 0.0, "max": 86400.0, "step": 0.1},
                ),
            },
            "optional": {
                "音频": ("AUDIO",),
            },
        }

    def clip(self, 音频=None, **values):
        if 音频 is None:
            raise ValueError("请连接音频")
        start_sample, end_sample = _audio_clip_bounds(
            音频,
            values.get("开始时间（秒，0不限制）"),
            values.get("结束时间（秒，0不限制）"),
        )
        clipped = dict(音频)
        clipped["waveform"] = 音频["waveform"][..., start_sample:end_sample].contiguous()
        return (clipped,)
