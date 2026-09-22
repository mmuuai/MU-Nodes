import math
import shutil
import subprocess
import tempfile
import uuid
from collections import deque
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import requests

from .utility_nodes import download_video
from .multi_video_loader import _input_videos, _resolve_video
from .video_compress import _materialize_source


MAX_SEGMENTS = 50
_ANALYSIS_EDGE = 96
SEGMENT_BUNDLE_TYPE = "MU_VIDEO_SEGMENTS"
_BASE_SCENE_THRESHOLD_MAX = 0.28
_SCENE_THRESHOLD_MAD_SCALE = 4.0
_MIN_SCENE_THRESHOLD_MARGIN = 0.015


@dataclass(frozen=True)
class VideoSegmentBundle:
    """Keeps generated segment files compactly connected between MU nodes."""

    paths: tuple[str, ...]
    output_fps: int

    @property
    def count(self):
        return len(self.paths)


def _probe_video(path, ffprobe):
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=avg_frame_rate,duration",
        "-of",
        "default=noprint_wrappers=1:nokey=0",
        str(path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "未知错误")[-1000:].strip()
        raise RuntimeError(f"读取视频信息失败：{detail}")
    values = dict(
        line.split("=", 1) for line in completed.stdout.splitlines() if "=" in line
    )
    try:
        numerator, denominator = values["avg_frame_rate"].split("/", 1)
        frame_rate = float(numerator) / float(denominator)
        duration = float(values["duration"])
    except (KeyError, ValueError, ZeroDivisionError) as error:
        raise RuntimeError("视频缺少可读取的帧率或时长") from error
    if not math.isfinite(frame_rate) or frame_rate <= 0 or not math.isfinite(duration) or duration <= 0:
        raise RuntimeError("视频帧率或时长无效")
    return frame_rate, duration


def _analysis_frame(frame):
    pixels = frame.to_ndarray(format="gray")
    height, width = pixels.shape
    step = max(1, math.ceil(max(height, width) / _ANALYSIS_EDGE))
    return pixels[::step, ::step].astype(np.float32) / 255.0


def _adaptive_scene_threshold(base_threshold, deltas):
    """Set a robust local threshold without letting camera motion hide hard cuts."""
    if not deltas:
        return base_threshold
    baseline = float(np.median(deltas))
    deviations = np.abs(np.asarray(deltas, dtype=np.float32) - baseline)
    mad = float(np.median(deviations))
    threshold = baseline + max(_MIN_SCENE_THRESHOLD_MARGIN, mad * _SCENE_THRESHOLD_MAD_SCALE)
    return min(_BASE_SCENE_THRESHOLD_MAX, max(base_threshold, threshold))


def _scene_boundaries(path, duration, sensitivity):
    """Return scene-change times using a motion-robust adaptive delta threshold."""
    detection_gap_seconds = 0.5
    # 1 is deliberately conservative; 100 also catches gentler edits.
    threshold = 0.28 - ((sensitivity - 1) / 99.0) * 0.23
    threshold = max(0.02, min(0.28, threshold))
    previous = None
    deltas = deque(maxlen=12)
    boundaries = []
    last_boundary = 0.0
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        for frame in container.decode(stream):
            if frame.time is None:
                continue
            now = max(0.0, float(frame.time))
            current = _analysis_frame(frame)
            if previous is not None:
                delta = float(np.mean(np.abs(current - previous)))
                dynamic_threshold = _adaptive_scene_threshold(threshold, deltas)
                if now - last_boundary >= detection_gap_seconds and delta >= dynamic_threshold:
                    boundaries.append(now)
                    last_boundary = now
                deltas.append(delta)
            previous = current
    return [value for value in boundaries if detection_gap_seconds <= value < duration]


def _enforce_max_duration(boundaries, duration, max_duration, min_scene_seconds):
    boundaries = sorted({round(value, 6) for value in boundaries if 0 < value < duration})
    if max_duration <= 1e-6:
        result = [0.0]
        for boundary in boundaries:
            if boundary - result[-1] >= min_scene_seconds - 1e-6:
                result.append(boundary)
        if duration - result[-1] > 1e-6:
            result.append(round(duration, 6))
        return list(zip(result, result[1:]))

    result = [0.0]
    cursor = 0.0
    while duration - cursor > max_duration + 1e-6:
        deadline = cursor + max_duration
        natural_cuts = [
            boundary
            for boundary in boundaries
            if cursor + min_scene_seconds - 1e-6 <= boundary <= deadline + 1e-6
        ]
        end = natural_cuts[-1] if natural_cuts else deadline
        result.append(round(end, 6))
        cursor = end
    if duration - cursor > 1e-6:
        result.append(round(duration, 6))
    if len(result) >= 3 and result[-1] - result[-2] < min_scene_seconds - 1e-6:
        previous_start = result[-3]
        if duration - previous_start <= max_duration + 1e-6:
            result.pop(-2)
        else:
            adjusted_boundary = round(duration - min_scene_seconds, 6)
            if adjusted_boundary > previous_start + 1e-6:
                result[-2] = adjusted_boundary
    return list(zip(result, result[1:]))


def _video_filter(short_edge):
    if short_edge == 0:
        return None
    return f"scale='if(gt(iw,ih),-2,{short_edge})':'if(gt(iw,ih),{short_edge},-2)'"


def split_video(
    video,
    max_duration_seconds,
    min_scene_seconds,
    sensitivity,
    output_fps,
    output_short_edge,
):
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    source_path, temporary_source = _materialize_source(video)
    output_dir = Path(tempfile.gettempdir()) / "mmuuai-comfyui" / "smart-video-segments"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = []
    try:
        _source_fps, duration = _probe_video(source_path, ffprobe)
        boundaries = _scene_boundaries(source_path, duration, sensitivity)
        segments = _enforce_max_duration(
            boundaries,
            duration,
            max_duration_seconds,
            min_scene_seconds,
        )
        if len(segments) > MAX_SEGMENTS:
            raise ValueError(
                f"按当前设置会生成 {len(segments)} 段，超过节点最多 {MAX_SEGMENTS} 段的输出上限；"
                "请增大最长时长或先截短输入视频"
            )
        filter_value = _video_filter(output_short_edge)
        for index, (start, end) in enumerate(segments, start=1):
            output_path = output_dir / f"segment-{index:02d}-{uuid.uuid4().hex}.mp4"
            command = [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(source_path),
                "-ss",
                f"{start:.6f}",
                "-t",
                f"{end - start:.6f}",
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
            ]
            if filter_value:
                command.extend(["-vf", filter_value])
            command.extend(
                [
                    "-r",
                    str(output_fps),
                    "-c:v",
                    "libopenh264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-movflags",
                    "+faststart",
                    str(output_path),
                ]
            )
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
            if completed.returncode != 0 or not output_path.exists() or output_path.stat().st_size == 0:
                output_path.unlink(missing_ok=True)
                detail = (completed.stderr or completed.stdout or "未知错误")[-1500:].strip()
                raise RuntimeError(f"第{index}段视频导出失败：{detail}")
            output_paths.append(output_path)
    finally:
        if temporary_source:
            Path(temporary_source).unlink(missing_ok=True)
    return output_paths


def _source_video(
    video,
    uploaded_video,
    images,
    audio,
    video_url,
    connected_video_url,
    output_fps,
    connect_timeout,
    wait_timeout,
):
    video_url = str(video_url or "").strip()
    connected_video_url = str(connected_video_url or "").strip()
    resolved_upload = _resolve_video(uploaded_video, "上传视频") if uploaded_video else None
    if resolved_upload:
        if video is not None or images is not None:
            raise ValueError("上传视频不能与 VIDEO 或图片序列同时提供")
        from comfy_api.latest import InputImpl

        return InputImpl.VideoFromFile(resolved_upload)
    if video_url and connected_video_url:
        raise ValueError("节点内视频URL与视频URL输入只能提供一个")
    resolved_url = video_url or connected_video_url
    supplied = (
        int(video is not None)
        + int(resolved_upload is not None)
        + int(images is not None)
        + int(bool(resolved_url))
    )
    if supplied != 1:
        raise ValueError("请且仅提供上传视频、视频URL、VIDEO、图片序列四种来源中的一种")
    from comfy_api.latest import InputImpl, Types

    if video is not None:
        return video
    if resolved_url:
        session = requests.Session()
        try:
            buffer = download_video(session, resolved_url, connect_timeout, wait_timeout)
            return InputImpl.VideoFromFile(buffer)
        finally:
            session.close()
    components = Types.VideoComponents(
        images=images,
        audio=audio,
        frame_rate=Fraction(str(float(output_fps))),
    )
    return InputImpl.VideoFromComponents(components, bit_depth=8)


class MmuuAISmartVideoSegmenterNode:
    CATEGORY = "MU/媒体处理"
    FUNCTION = "split"
    RETURN_TYPES = (SEGMENT_BUNDLE_TYPE, "STRING", "INT")
    RETURN_NAMES = ("切片结果", "切分报告", "片段数")

    @classmethod
    def INPUT_TYPES(cls):
        local_video_options = _input_videos()
        return {
            "required": {
                "视频URL": ("STRING", {"default": "", "multiline": False, "placeholder": "https://example.com/video.mp4"}),
                "最长时长（秒，0不限制）": ("FLOAT", {"default": 15.0, "min": 0.0, "max": 600.0, "step": 0.1}),
                "最短镜头（秒，0不限制）": ("FLOAT", {"default": 5.0, "min": 0.0, "max": 600.0, "step": 0.1}),
                "切镜灵敏度（1-100）": ("INT", {"default": 50, "min": 1, "max": 100, "step": 1}),
                "输出帧率": ("INT", {"default": 24, "min": 1, "max": 120, "step": 1}),
                "输出短边尺寸（0保持原尺寸）": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 2}),
                "URL连接超时（秒）": ("INT", {"default": 30, "min": 1, "max": 300, "step": 1}),
                "URL等待超时（秒，0不限）": ("INT", {"default": 600, "min": 0, "max": 86400, "step": 1}),
            },
            "optional": {
                "上传视频": (local_video_options, {"default": "", "video_upload": True}),
                "视频": ("VIDEO",),
                "视频URL输入": ("STRING", {"forceInput": True}),
                "图片序列": ("IMAGE",),
                "音频": ("AUDIO",),
            }
        }

    @classmethod
    def VALIDATE_INPUTS(cls, **values):
        uploaded_video = values.get("上传视频", "")
        if not uploaded_video:
            return True
        try:
            _resolve_video(uploaded_video, "上传视频")
        except (FileNotFoundError, OSError) as error:
            return str(error)
        return True

    def split(self, **values):
        source = _source_video(
            values.get("视频"),
            values.get("上传视频", ""),
            values.get("图片序列"),
            values.get("音频"),
            values.get("视频URL", ""),
            values.get("视频URL输入", ""),
            int(values["输出帧率"]),
            int(values["URL连接超时（秒）"]),
            int(values["URL等待超时（秒，0不限）"]),
        )
        output_paths = split_video(
            source,
            float(values["最长时长（秒，0不限制）"]),
            float(values["最短镜头（秒，0不限制）"]),
            int(values["切镜灵敏度（1-100）"]),
            int(values["输出帧率"]),
            int(values["输出短边尺寸（0保持原尺寸）"]),
        )
        bundle = VideoSegmentBundle(
            paths=tuple(str(path) for path in output_paths),
            output_fps=int(values["输出帧率"]),
        )
        report = (
            f"智能切分完成：{len(output_paths)} 段｜最长 {values['最长时长（秒，0不限制）']} 秒｜"
            f"最短镜头 {values['最短镜头（秒，0不限制）']} 秒｜"
            f"灵敏度 {values['切镜灵敏度（1-100）']}｜"
            f"输出 {values['输出帧率']} fps｜短边 {values['输出短边尺寸（0保持原尺寸）']}"
        )
        return (bundle, report, len(output_paths))


class MmuuAIGetVideoSegmentNode:
    CATEGORY = "MU/媒体处理"
    FUNCTION = "get_segment"
    RETURN_TYPES = ("VIDEO", "IMAGE", "AUDIO", "STRING", "INT")
    RETURN_NAMES = ("视频", "图片序列", "音频", "片段信息", "实际序号")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "切片结果": (SEGMENT_BUNDLE_TYPE,),
                "片段序号": ("INT", {"default": 1, "min": 1, "max": MAX_SEGMENTS, "step": 1}),
            },
        }

    def get_segment(self, **values):
        bundle = values["切片结果"]
        if not isinstance(bundle, VideoSegmentBundle):
            raise TypeError("切片结果必须连接到 MU｜智能视频切片 节点")
        requested_index = int(values["片段序号"])
        if requested_index > bundle.count:
            # A workflow commonly has one getter/save branch per possible
            # segment.  When the source is shorter than that template, block
            # this branch silently so existing segments still preview/save.
            from comfy_execution.graph import ExecutionBlocker

            return tuple(ExecutionBlocker(None) for _ in self.RETURN_TYPES)
        from comfy_api.latest import InputImpl

        video = InputImpl.VideoFromFile(bundle.paths[requested_index - 1])
        components = video.get_components()
        info = f"第 {requested_index}/{bundle.count} 段｜{bundle.output_fps} fps"
        return (video, components.images, components.audio, info, requested_index)
