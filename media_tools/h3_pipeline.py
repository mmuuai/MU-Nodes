import json
import math
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from .video_compress import _materialize_source
from .h3_windows import (
    build_window_inputs,
    collect_window_details,
    parse_analysis_plan,
)


JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def _load_json(text, label):
    normalized = str(text).strip()
    match = JSON_FENCE.fullmatch(normalized)
    if match:
        normalized = match.group(1).strip()
    try:
        return json.loads(normalized)
    except json.JSONDecodeError as error:
        repaired = re.sub(
            r'(?m)^(\s*)_anchor\s*:',
            r'\1"start_anchor":',
            normalized,
        )
        if repaired != normalized:
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass
        raise ValueError(
            f"{label}不是有效JSON：第{error.lineno}行第{error.colno}列，{error.msg}"
        ) from error


def _split_long_segments(segments):
    normalized = []
    for segment in segments:
        if not isinstance(segment, dict):
            normalized.append(segment)
            continue
        start = segment.get("source_start_seconds")
        end = segment.get("source_end_seconds")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in (start, end)):
            normalized.append(segment)
            continue
        duration = end - start
        if duration <= 15:
            normalized.append(segment)
            continue
        chunk_count = math.ceil(duration / 15)
        chunk_duration = duration / chunk_count
        for offset in range(chunk_count):
            chunk = dict(segment)
            chunk_start = round(start + chunk_duration * offset, 3)
            chunk_end = round(end if offset == chunk_count - 1 else start + chunk_duration * (offset + 1), 3)
            chunk["source_start_seconds"] = chunk_start
            chunk["source_end_seconds"] = chunk_end
            chunk["duration_seconds"] = round(chunk_end - chunk_start, 3)
            if offset:
                chunk["start_anchor"] = "Continuation of the same planned source interval."
            if offset < chunk_count - 1:
                chunk["end_anchor"] = "The state at this split point within the planned source interval."
            normalized.append(chunk)
    for index, segment in enumerate(normalized, start=1):
        if isinstance(segment, dict):
            segment["index"] = index
    return normalized


def _timeline_filler(start, end):
    duration = end - start
    if duration <= 0.05:
        return []
    chunk_count = max(1, math.ceil(duration / 15))
    chunk_duration = duration / chunk_count
    generated = []
    for offset in range(chunk_count):
        chunk_start = round(start + chunk_duration * offset, 3)
        chunk_end = round(
            end if offset == chunk_count - 1 else start + chunk_duration * (offset + 1),
            3,
        )
        generated.append(
            {
                "source_start_seconds": chunk_start,
                "source_end_seconds": chunk_end,
                "duration_seconds": round(chunk_end - chunk_start, 3),
                "content_summary": "Analyze this source interval directly in step 2.",
                "start_anchor": "The first frame of this source interval.",
                "end_anchor": "The final frame of this source interval.",
            }
        )
    return generated


def _complete_segment_timeline(segments, target_start):
    completed = []
    inserted_count = 0
    previous_end = target_start
    for segment in segments:
        if not isinstance(segment, dict):
            completed.append(segment)
            continue
        start = segment.get("source_start_seconds")
        end = segment.get("source_end_seconds")
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for value in (start, end)
        ):
            completed.append(segment)
            continue
        if start > previous_end + 0.05:
            filler = _timeline_filler(previous_end, start)
            completed.extend(filler)
            inserted_count += len(filler)
        elif start < previous_end - 0.05:
            if end <= previous_end + 0.05:
                continue
            segment = dict(segment)
            segment["source_start_seconds"] = round(previous_end, 3)
            segment["duration_seconds"] = round(end - previous_end, 3)
        completed.append(segment)
        previous_end = end
    for index, segment in enumerate(completed, start=1):
        if isinstance(segment, dict):
            segment["index"] = index
    return completed, inserted_count


def parse_full_plan(text, source_duration=None):
    data = _load_json(text, "全片规划")
    if not isinstance(data, dict) or data.get("schema_version") != "2.0":
        raise ValueError("全片规划必须使用 schema_version 2.0")
    global_data = data.get("global")
    segments = data.get("segments")
    if not isinstance(global_data, dict):
        raise ValueError("全片规划 global 必须是JSON对象")
    if not isinstance(segments, list) or not segments:
        raise ValueError("全片规划 segments 必须是非空数组")

    target_start = global_data.get("target_start_seconds")
    target_end = global_data.get("target_end_seconds")
    target_duration = global_data.get("target_duration_seconds")
    target_values = (target_start, target_end, target_duration)
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        for value in target_values
    ):
        raise ValueError("全片规划的目标起点、终点和总时长必须是数字")
    declared_source_duration = global_data.get("source_duration_seconds")
    full_source_plan = (
        isinstance(source_duration, (int, float))
        and source_duration > 0
        and target_start == 0
        and isinstance(declared_source_duration, (int, float))
        and abs(declared_source_duration - target_end) <= 0.05
    )
    if full_source_plan:
        original_target_end = target_end
        target_end = round(float(source_duration), 3)
        target_duration = target_end
        global_data["source_duration_seconds"] = target_end
        global_data["target_end_seconds"] = target_end
        global_data["target_duration_seconds"] = target_duration
        if abs(original_target_end - target_end) > 0.05:
            retained_segments = []
            for segment in segments:
                start = segment.get("source_start_seconds") if isinstance(segment, dict) else None
                if not isinstance(start, (int, float)) or start >= target_end - 0.05:
                    break
                if segment.get("source_end_seconds", 0) > target_end:
                    segment["source_end_seconds"] = target_end
                    segment["duration_seconds"] = round(target_end - start, 3)
                retained_segments.append(segment)
            segments[:] = retained_segments
            for index, segment in enumerate(segments, start=1):
                segment["index"] = index
            global_data["duration_corrected_from_file"] = original_target_end
    if target_start < 0 or target_end <= target_start or target_duration <= 0:
        raise ValueError("全片规划的目标时间范围无效")
    if abs((target_end - target_start) - target_duration) > 0.05:
        raise ValueError("全片规划的目标区间与总时长不一致")
    segments[:] = _split_long_segments(segments)
    completed_segments, inserted_count = _complete_segment_timeline(segments, target_start)
    segments[:] = completed_segments
    if inserted_count:
        global_data["auto_completed_middle_segments"] = inserted_count
    previous_end = None
    duration_sum = 0.0
    for position, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict) or segment.get("index") != position:
            raise ValueError(f"全片规划第{position}段的 index 必须连续")
        start = segment.get("source_start_seconds")
        end = segment.get("source_end_seconds")
        duration = segment.get("duration_seconds")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in (start, end, duration)):
            raise ValueError(f"全片规划第{position}段的时间必须是数字")
        if start < 0 or end <= start:
            raise ValueError(f"全片规划第{position}段的时间范围无效")
        calculated_duration = round(end - start, 3)
        if calculated_duration <= 0 or calculated_duration > 15:
            raise ValueError(f"全片规划第{position}段的时间范围无效")
        if abs(calculated_duration - duration) > 0.05:
            segment["duration_seconds"] = calculated_duration
            duration = calculated_duration
        if previous_end is not None and abs(start - previous_end) > 0.05:
            raise ValueError(f"全片规划第{position - 1}段与第{position}段存在空隙或重叠")
        previous_end = end
        duration_sum += duration

    first_start = segments[0]["source_start_seconds"]
    last_end = segments[-1]["source_end_seconds"]
    if abs(first_start - target_start) > 0.05:
        raise ValueError(
            f"全片规划没有从目标范围起点开始：{first_start:g}秒 != {target_start:g}秒"
        )
    if last_end > target_end + 0.05:
        raise ValueError(
            f"全片规划超过目标范围终点：{last_end:g}秒 > {target_end:g}秒"
        )

    original_count = len(segments)
    remaining = target_end - last_end
    if remaining > 0.05:
        filler = _timeline_filler(last_end, target_end)
        missing_count = len(filler)
        segments.extend(filler)
        for index, segment in enumerate(segments, start=1):
            segment["index"] = index
        global_data["auto_completed_tail_segments"] = missing_count
        last_end = segments[-1]["source_end_seconds"]
        duration_sum = sum(segment["duration_seconds"] for segment in segments)

    minimum_count = math.ceil(target_duration / 15)
    if len(segments) < minimum_count:
        raise ValueError(
            f"全片规划分段数量不足：收到{len(segments)}段，至少需要{minimum_count}段"
        )
    if abs(last_end - target_end) > 0.05:
        raise ValueError(
            f"全片规划没有覆盖到目标范围终点：{last_end:g}秒 != {target_end:g}秒"
        )
    if abs(duration_sum - target_duration) > 0.05:
        raise ValueError(
            f"全片规划分段时长总和不完整：{duration_sum:g}秒 != {target_duration:g}秒"
        )
    return data


def _clip_video(source_path, start, duration, output_path, ffmpeg="ffmpeg"):
    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        str(start),
        "-i",
        source_path,
        "-t",
        str(duration),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
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
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        output_path.unlink(missing_ok=True)
        detail = (completed.stderr or completed.stdout or "未知错误")[-2000:].strip()
        raise RuntimeError(f"第{start:g}秒开始的视频切片失败：{detail}")
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"第{start:g}秒开始的视频切片没有生成有效文件")


def _probe_video_duration(source_path, ffprobe="ffprobe"):
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            source_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "未知错误")[-1000:].strip()
        raise RuntimeError(f"无法读取视频真实时长：{detail}")
    try:
        duration = float(completed.stdout.strip())
    except ValueError as error:
        raise RuntimeError("无法读取视频真实时长：ffprobe 未返回有效数字") from error
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError("无法读取视频真实时长：时长无效")
    return duration


def build_segment_inputs(video, plan_text, user_idea):
    raw_plan = _load_json(plan_text, "全片规划")
    if raw_plan.get("schema_version") == "3.0":
        return build_window_inputs(
            video,
            raw_plan,
            user_idea,
            _clip_video,
            _probe_video_duration,
        )
    from comfy_api.latest import InputImpl

    source_path, temporary_source = _materialize_source(video)
    output_dir = Path(tempfile.gettempdir()) / "mmuuai-comfyui" / "h3-segments"
    output_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    videos = []
    prompts = []
    indexes = []
    try:
        ffprobe = shutil.which("ffprobe") or "ffprobe"
        source_duration = _probe_video_duration(source_path, ffprobe)
        plan = parse_full_plan(plan_text, source_duration)
        for segment in plan["segments"]:
            output_path = output_dir / f"segment-{segment['index']}-{uuid.uuid4().hex}.mp4"
            _clip_video(
                source_path,
                segment["source_start_seconds"],
                segment["duration_seconds"],
                output_path,
                ffmpeg,
            )
            context = {
                "schema_version": plan["schema_version"],
                "global": plan["global"],
                "segment": segment,
            }
            prompt = (
                "用户原始想法：\n"
                f"{str(user_idea).strip()}\n\n"
                "全片规划上下文：\n"
                f"{json.dumps(context, ensure_ascii=False)}\n\n"
                f"当前 segment_index：{segment['index']}"
            )
            videos.append(InputImpl.VideoFromFile(str(output_path)))
            prompts.append(prompt)
            indexes.append(segment["index"])
    finally:
        if temporary_source:
            Path(temporary_source).unlink(missing_ok=True)
    normalized_plan = json.dumps(plan, ensure_ascii=False)
    return videos, prompts, indexes, normalized_plan


def collect_segment_details(plan_text, detail_texts):
    raw_plan = _load_json(plan_text, "全片规划")
    if raw_plan.get("schema_version") == "3.0":
        return collect_window_details(raw_plan, detail_texts, _load_json)
    plan = parse_full_plan(plan_text)
    if len(detail_texts) != len(plan["segments"]):
        raise ValueError(
            f"单段详写结果数量不完整：收到{len(detail_texts)}段，规划要求{len(plan['segments'])}段"
        )
    details = []
    for position, text in enumerate(detail_texts, start=1):
        data = _load_json(text, f"第{position}个单段详写结果")
        if data.get("validation_error"):
            raise ValueError(f"第{position}个单段详写失败：{data['validation_error']}")
        segment = data.get("segment")
        if not isinstance(segment, dict):
            raise ValueError(f"第{position}个单段详写结果缺少 segment")
        segment = dict(segment)
        expected = plan["segments"][position - 1]
        for field in ("index", "source_start_seconds", "source_end_seconds", "duration_seconds"):
            segment[field] = expected[field]
        details.append(segment)

    global_data = plan["global"]
    compact = {
        "schema_version": "1.1",
        "global": {
            "target_duration_seconds": global_data["target_duration_seconds"],
            "target_start_seconds": global_data.get("target_start_seconds", 0),
            "target_end_seconds": global_data.get(
                "target_end_seconds",
                global_data["target_duration_seconds"],
            ),
            "task_types": global_data["task_types"],
            "continuity_context": " ".join(global_data.get("continuity_rules", [])),
            "reference_definitions": global_data["reference_definitions"],
            "character_relationships": global_data.get("character_relationships", []),
            "speaker_map": global_data.get("speaker_map", []),
        },
        "segments": details,
    }
    auto_completed = global_data.get("auto_completed_tail_segments", 0)
    auto_completed_middle = global_data.get("auto_completed_middle_segments", 0)
    report = f"汇总完成：{len(details)}段单段详写结果与全片规划一致"
    if auto_completed_middle:
        report += f"；其中{auto_completed_middle}段为计算节点补齐的中间索引"
    if auto_completed:
        report += f"；其中{auto_completed}段为计算节点补齐的尾部索引"
    return json.dumps(compact, ensure_ascii=False), report, len(details)


class MmuuAIH3PlanVideoBatchNode:
    CATEGORY = "MU/工具"
    FUNCTION = "split"
    RETURN_TYPES = ("VIDEO", "STRING", "INT", "STRING")
    RETURN_NAMES = ("逐个分析窗口视频", "逐个窗口模型输入", "窗口索引", "规范化全片规划JSON")
    OUTPUT_IS_LIST = (True, True, True, False)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "视频": ("VIDEO",),
                "全片规划JSON": ("STRING", {"forceInput": True}),
                "用户想法": ("STRING", {"forceInput": True}),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **_kwargs):
        return float("nan")

    def split(self, 视频, 全片规划JSON, 用户想法):
        return build_segment_inputs(视频, 全片规划JSON, 用户想法)


class MmuuAIH3SegmentCollectorNode:
    CATEGORY = "MU/工具"
    FUNCTION = "collect"
    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("完整精简分段JSON", "汇总报告", "实际分段数")
    INPUT_IS_LIST = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "全片规划JSON": ("STRING", {"forceInput": True}),
                "单段详写JSON": ("STRING", {"forceInput": True}),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **_kwargs):
        return float("nan")

    def collect(self, 全片规划JSON, 单段详写JSON):
        if not 全片规划JSON:
            raise ValueError("没有收到全片规划JSON")
        return collect_segment_details(全片规划JSON[0], 单段详写JSON)
