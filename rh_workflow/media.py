import io
import wave

import numpy as np
from PIL import Image


def image_to_png(value):
    if value is None or len(value) != 1:
        raise ValueError("图片输入必须且只能包含 1 张图片")
    array = np.clip(value[0].detach().cpu().numpy() * 255.0, 0, 255).astype(np.uint8)
    output = io.BytesIO()
    Image.fromarray(array).convert("RGB").save(output, format="PNG")
    return output.getvalue(), "input.png", "image/png"


def audio_to_wav(value):
    if not isinstance(value, dict) or "waveform" not in value or "sample_rate" not in value:
        raise ValueError("音频输入不是有效的 ComfyUI AUDIO")
    waveform = value["waveform"].detach().cpu().float().numpy()
    if waveform.ndim != 3 or waveform.shape[0] != 1:
        raise ValueError("音频输入必须且只能包含 1 个音频")
    pcm = np.clip(waveform[0], -1.0, 1.0)
    pcm = (pcm.T * 32767.0).astype("<i2")
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(pcm.shape[1])
        handle.setsampwidth(2)
        handle.setframerate(int(value["sample_rate"]))
        handle.writeframes(pcm.tobytes())
    return output.getvalue(), "input.wav", "audio/wav"


def video_to_file(value):
    if value is None or not hasattr(value, "get_stream_source"):
        raise ValueError("视频输入不是有效的 ComfyUI VIDEO")
    source = value.get_stream_source()
    if isinstance(source, str):
        with open(source, "rb") as handle:
            content = handle.read()
    else:
        source.seek(0)
        content = source.read()
        source.seek(0)
    container = value.get_container_format().split(",", 1)[0].lower()
    formats = {
        "mp4": ("mp4", "video/mp4"), "mov": ("mov", "video/quicktime"),
        "quicktime": ("mov", "video/quicktime"), "avi": ("avi", "video/x-msvideo"),
        "matroska": ("mkv", "video/x-matroska"), "mkv": ("mkv", "video/x-matroska"),
    }
    if container not in formats:
        raise ValueError(f"RH 不支持当前视频容器：{container}")
    extension, mime_type = formats[container]
    return content, f"input.{extension}", mime_type
