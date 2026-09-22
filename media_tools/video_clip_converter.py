import math

import torch

from .video_image_converter import _create_video


def _clip_bounds(frame_count, frame_rate, start_seconds, end_seconds):
    start = max(0.0, float(start_seconds or 0.0))
    end = max(0.0, float(end_seconds or 0.0))
    if end and end <= start:
        raise ValueError("结束时间必须大于开始时间")
    duration = frame_count / float(frame_rate)
    if start and start >= duration:
        raise ValueError("开始时间超出视频时长")
    start_index = min(frame_count - 1, max(0, int(math.floor(start * frame_rate))))
    end_index = frame_count if not end else min(
        frame_count, max(start_index + 1, int(math.ceil(end * frame_rate)))
    )
    if end_index <= start_index:
        raise ValueError("时间范围没有包含任何视频帧")
    return start_index, end_index


def _clip_audio(audio, frame_rate, start_index, end_index):
    if not isinstance(audio, dict):
        return audio
    waveform = audio.get("waveform")
    sample_rate = audio.get("sample_rate")
    if not isinstance(waveform, torch.Tensor) or not sample_rate:
        return audio
    sample_start = max(0, int(round(start_index / frame_rate * int(sample_rate))))
    sample_end = min(
        waveform.shape[-1],
        max(sample_start + 1, int(round(end_index / frame_rate * int(sample_rate)))),
    )
    clipped = dict(audio)
    clipped["waveform"] = waveform[..., sample_start:sample_end]
    return clipped


class MmuuAIVideoClipConverterNode:
    CATEGORY = "MU/媒体处理"
    FUNCTION = "convert"
    RETURN_TYPES = ("VIDEO", "IMAGE")
    RETURN_NAMES = ("视频", "图片序列")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "开始时间（秒，0不限制）": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 86400.0, "step": 0.1}),
                "结束时间（秒，0不限制）": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 86400.0, "step": 0.1}),
                "图片序列帧率": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0, "step": 1.0}),
                "图片生成视频位深": ("INT", {"default": 8, "min": 8, "max": 10, "step": 2}),
            },
            "optional": {
                "视频": ("VIDEO",),
                "图片序列": ("IMAGE",),
            },
        }

    def convert(self, **values):
        video = values.get("视频")
        images = values.get("图片序列")
        if (video is None) == (images is None):
            raise ValueError("请且仅连接视频或图片序列中的一个")

        if video is not None:
            components = video.get_components()
            source_images = components.images
            audio = components.audio
            frame_rate = float(components.frame_rate)
            bit_depth = int(video.get_bit_depth())
        else:
            source_images = images
            audio = None
            frame_rate = float(values["图片序列帧率"])
            bit_depth = int(values["图片生成视频位深"])

        if not isinstance(source_images, torch.Tensor) or source_images.ndim < 4 or source_images.shape[0] < 1:
            raise ValueError("输入没有可处理的图片帧")
        start_index, end_index = _clip_bounds(
            int(source_images.shape[0]),
            frame_rate,
            values["开始时间（秒，0不限制）"],
            values["结束时间（秒，0不限制）"],
        )
        clipped_images = source_images[start_index:end_index].contiguous()
        clipped_audio = _clip_audio(audio, frame_rate, start_index, end_index)
        clipped_video = _create_video(
            clipped_images,
            clipped_audio,
            frame_rate,
            bit_depth,
        )
        return clipped_video, clipped_images
