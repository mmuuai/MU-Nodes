import json
import math
import re
import shutil
import tempfile
import uuid
from pathlib import Path

from .video_compress import _materialize_source


TOLERANCE = 0.05
CONTEXT_SECONDS = 3.0
LANGUAGE_TAG = re.compile(r"</?d>|\[/?[A-Za-z][A-Za-z -]*\]", re.IGNORECASE)


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label}必须是数字")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label}必须是有效数字")
    return round(number, 3)


def _required_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}不能为空")
    return value.strip()


def _format_time(seconds):
    minutes, remainder = divmod(max(0.0, seconds), 60)
    return f"{int(minutes):02d}:{remainder:06.3f}"


def _normalize_dialogue_text(value):
    text = LANGUAGE_TAG.sub("", _required_text(value, "dialogue.text")).strip()
    if not text:
        raise ValueError("dialogue.text清理标签后不能为空")
    return text


def parse_analysis_plan(data, source_duration=None):
    if not isinstance(data, dict) or data.get("schema_version") != "3.0":
        raise ValueError("全片规划必须使用 schema_version 3.0")
    global_data = data.get("global")
    windows = data.get("analysis_windows")
    if not isinstance(global_data, dict):
        raise ValueError("全片规划 global 必须是JSON对象")
    if not isinstance(windows, list) or not windows:
        raise ValueError("全片规划 analysis_windows 必须是非空数组")

    target_start = _number(global_data.get("target_start_seconds"), "target_start_seconds")
    target_end = _number(global_data.get("target_end_seconds"), "target_end_seconds")
    if target_start < 0 or target_end <= target_start:
        raise ValueError("全片规划的目标时间范围无效")
    declared_source = global_data.get("source_duration_seconds")
    full_source = (
        source_duration is not None
        and target_start == 0
        and isinstance(declared_source, (int, float))
        and abs(float(declared_source) - target_end) <= TOLERANCE
    )
    if full_source:
        target_end = round(float(source_duration), 3)
        global_data["source_duration_seconds"] = target_end
        global_data["target_end_seconds"] = target_end
        windows[-1] = dict(windows[-1])
        windows[-1]["source_end_seconds"] = target_end
        windows[-1]["duration_seconds"] = round(
            target_end - float(windows[-1]["source_start_seconds"]), 3
        )
    global_data["target_duration_seconds"] = round(target_end - target_start, 3)

    normalized = []
    previous_end = target_start
    for position, source in enumerate(windows, start=1):
        if not isinstance(source, dict):
            raise ValueError(f"第{position}个分析窗口必须是JSON对象")
        start = _number(source.get("source_start_seconds"), f"分析窗口{position}起点")
        end = _number(source.get("source_end_seconds"), f"分析窗口{position}终点")
        if abs(start - previous_end) > TOLERANCE:
            raise ValueError(f"分析窗口{position - 1}与{position}存在空隙或重叠")
        if end <= start:
            raise ValueError(f"分析窗口{position}时间范围无效")
        if end > target_end + TOLERANCE:
            end = target_end
        item = dict(source)
        item.update(
            index=position,
            source_start_seconds=start,
            source_end_seconds=end,
            duration_seconds=round(end - start, 3),
        )
        item["content_summary"] = _required_text(
            item.get("content_summary"), f"分析窗口{position}.content_summary"
        )
        item["start_anchor"] = _required_text(
            item.get("start_anchor"), f"分析窗口{position}.start_anchor"
        )
        item["end_anchor"] = _required_text(
            item.get("end_anchor"), f"分析窗口{position}.end_anchor"
        )
        item["cut_reason"] = _required_text(
            item.get("cut_reason"), f"分析窗口{position}.cut_reason"
        )
        normalized.append(item)
        previous_end = end
        if end >= target_end - TOLERANCE:
            break
    if not normalized or abs(normalized[-1]["source_end_seconds"] - target_end) > TOLERANCE:
        raise ValueError("分析窗口没有连续覆盖到目标范围终点")
    data["analysis_windows"] = normalized
    return data


def build_window_inputs(video, plan, user_idea, clip_video, probe_duration):
    from comfy_api.latest import InputImpl

    source_path, temporary_source = _materialize_source(video)
    output_dir = Path(tempfile.gettempdir()) / "mmuuai-comfyui" / "h3-windows"
    output_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    videos, prompts, indexes = [], [], []
    try:
        source_duration = probe_duration(source_path, ffprobe)
        plan = parse_analysis_plan(plan, source_duration)
        target_start = plan["global"]["target_start_seconds"]
        target_end = plan["global"]["target_end_seconds"]
        for window in plan["analysis_windows"]:
            clip_start = max(target_start, window["source_start_seconds"] - CONTEXT_SECONDS)
            clip_end = min(target_end, window["source_end_seconds"] + CONTEXT_SECONDS)
            output_path = output_dir / f"window-{window['index']}-{uuid.uuid4().hex}.mp4"
            clip_video(source_path, clip_start, clip_end - clip_start, output_path, ffmpeg)
            context = {
                "schema_version": plan["schema_version"],
                "global": plan["global"],
                "analysis_window": window,
                "attached_video": {
                    "source_start_seconds": round(clip_start, 3),
                    "source_end_seconds": round(clip_end, 3),
                    "core_start_in_attached_video_seconds": round(
                        window["source_start_seconds"] - clip_start, 3
                    ),
                    "core_end_in_attached_video_seconds": round(
                        window["source_end_seconds"] - clip_start, 3
                    ),
                },
            }
            prompt = (
                "用户原始想法：\n"
                f"{str(user_idea).strip()}\n\n"
                "当前自然分析窗口上下文：\n"
                f"{json.dumps(context, ensure_ascii=False)}\n\n"
                "只输出 analysis_window 核心区间内的H3分段；附件前后额外画面只用于理解边界。"
            )
            videos.append(InputImpl.VideoFromFile(str(output_path)))
            prompts.append(prompt)
            indexes.append(window["index"])
    finally:
        if temporary_source:
            Path(temporary_source).unlink(missing_ok=True)
    return videos, prompts, indexes, json.dumps(plan, ensure_ascii=False)


def _dialogue_text(dialogue, speaker_map):
    speaker_id = _required_text(dialogue.get("speaker_id"), "dialogue.speaker_id")
    speaker = speaker_map.get(speaker_id)
    if speaker is None:
        raise ValueError(f"dialogue引用了未定义的Speaker {speaker_id}")
    language = _required_text(dialogue.get("language", "Chinese"), "dialogue.language")
    text = _normalize_dialogue_text(dialogue.get("text"))
    line = f"{speaker['subject']} ({speaker_id}) says <d>[{language}] {text}</d>"
    if speaker.get("audio_reference"):
        line += f", using voice reference {speaker['audio_reference']}"
    delivery = dialogue.get("delivery")
    if isinstance(delivery, str) and delivery.strip():
        line += f", {delivery.strip()}"
    return line + "."


def _render_segment(source, speaker_map, position):
    start = _number(source.get("source_start_seconds"), f"分段{position}起点")
    end = _number(source.get("source_end_seconds"), f"分段{position}终点")
    duration = round(end - start, 3)
    if duration <= 0 or duration > 15 + TOLERANCE:
        raise ValueError(f"分段{position}时长必须大于0且不超过15秒，实际{duration:g}秒")
    shots = source.get("shots")
    if not isinstance(shots, list) or not shots:
        raise ValueError(f"分段{position}.shots必须是非空数组")
    parts = []
    previous_time = start
    for shot_position, shot in enumerate(shots, start=1):
        if not isinstance(shot, dict):
            raise ValueError(f"分段{position}镜头{shot_position}必须是JSON对象")
        shot_time = _number(
            shot.get("source_time_seconds"), f"分段{position}镜头{shot_position}时间"
        )
        if shot_time < start - TOLERANCE or shot_time > end + TOLERANCE:
            raise ValueError(f"分段{position}镜头{shot_position}不在本段时间范围内")
        if shot_time < previous_time - TOLERANCE:
            raise ValueError(f"分段{position}镜头时间没有按顺序排列")
        description = _required_text(
            shot.get("description"), f"分段{position}镜头{shot_position}.description"
        )
        prefix = f"[Shot {shot_position}]"
        if shot_position > 1:
            prefix += f" At {_format_time(shot_time - start)},"
        shot_text = f"{prefix} {description}"
        dialogues = shot.get("dialogues", [])
        if not isinstance(dialogues, list):
            raise ValueError(f"分段{position}镜头{shot_position}.dialogues必须是数组")
        if dialogues:
            shot_text += " " + " ".join(
                _dialogue_text(dialogue, speaker_map) for dialogue in dialogues
            )
        parts.append(shot_text)
        previous_time = shot_time
    result = dict(source)
    result.update(
        index=position,
        source_start_seconds=start,
        source_end_seconds=end,
        duration_seconds=duration,
        detailed_description=" ".join(parts),
    )
    result.pop("shots", None)
    return result


def _split_overlong_segment(source, label):
    start = _number(source.get("source_start_seconds"), f"{label}起点")
    end = _number(source.get("source_end_seconds"), f"{label}终点")
    if end - start <= 15 + TOLERANCE:
        return [source]
    shots = source.get("shots")
    if not isinstance(shots, list) or not shots:
        raise ValueError(f"{label}超过15秒且没有真实镜头边界可用于拆分")
    shot_times = sorted(
        {
            _number(shot.get("source_time_seconds"), f"{label}镜头时间")
            for shot in shots
            if isinstance(shot, dict)
        }
    )
    boundaries = [start]
    cursor = start
    while end - cursor > 15 + TOLERANCE:
        candidates = [
            value
            for value in shot_times
            if cursor + TOLERANCE < value <= cursor + 15 + TOLERANCE
        ]
        if not candidates:
            raise ValueError(f"{label}超过15秒，且15秒以内没有可用的真实镜头边界")
        cursor = max(candidates)
        boundaries.append(cursor)
    boundaries.append(end)

    chunks = []
    for offset, (chunk_start, chunk_end) in enumerate(
        zip(boundaries, boundaries[1:])
    ):
        chunk = dict(source)
        chunk_shots = [
            shot
            for shot in shots
            if chunk_start - TOLERANCE
            <= _number(shot.get("source_time_seconds"), f"{label}镜头时间")
            < chunk_end - TOLERANCE
        ]
        if not chunk_shots:
            raise ValueError(f"{label}自动拆分后的区间没有镜头数据")
        boundary_state = _required_text(
            chunk_shots[0].get("description"), f"{label}边界镜头描述"
        )
        chunk.update(
            source_start_seconds=chunk_start,
            source_end_seconds=chunk_end,
            duration_seconds=round(chunk_end - chunk_start, 3),
            shots=chunk_shots,
            summary=(
                _required_text(source.get("summary"), f"{label}.summary")
                + f" Part {offset + 1} of {len(boundaries) - 1}."
            ),
        )
        if offset:
            chunk["opening_state"] = f"At the shared cut boundary, {boundary_state}"
        if offset < len(boundaries) - 2:
            next_shot = next(
                shot
                for shot in shots
                if abs(
                    _number(shot.get("source_time_seconds"), f"{label}镜头时间")
                    - chunk_end
                )
                <= TOLERANCE
            )
            chunk["ending_state"] = (
                "At the shared cut boundary immediately before: "
                + _required_text(next_shot.get("description"), f"{label}边界镜头描述")
            )
        chunks.append(chunk)
    return chunks


def collect_window_details(plan, detail_texts, load_json):
    plan = parse_analysis_plan(plan)
    windows = plan["analysis_windows"]
    if len(detail_texts) != len(windows):
        raise ValueError(f"窗口结果数量不完整：收到{len(detail_texts)}个，规划要求{len(windows)}个")
    speaker_map = {
        item["speaker_id"]: item for item in plan["global"].get("speaker_map", [])
    }
    collected = []
    for window_position, (window, text) in enumerate(zip(windows, detail_texts), start=1):
        data = load_json(text, f"第{window_position}个分析窗口结果")
        if data.get("validation_error"):
            raise ValueError(f"分析窗口{window_position}失败：{data['validation_error']}")
        if data.get("window_index") != window_position:
            raise ValueError(f"分析窗口{window_position}返回了错误的 window_index")
        segments = data.get("segments")
        if not isinstance(segments, list) or not segments:
            raise ValueError(f"分析窗口{window_position}没有返回segments")
        previous_end = window["source_start_seconds"]
        for source_position, source in enumerate(segments, start=1):
            for chunk in _split_overlong_segment(
                source, f"分析窗口{window_position}分段{source_position}"
            ):
                segment = _render_segment(chunk, speaker_map, len(collected) + 1)
                if abs(segment["source_start_seconds"] - previous_end) > TOLERANCE:
                    raise ValueError(f"分析窗口{window_position}内部H3分段存在空隙或重叠")
                collected.append(segment)
                previous_end = segment["source_end_seconds"]
        if abs(previous_end - window["source_end_seconds"]) > TOLERANCE:
            raise ValueError(f"分析窗口{window_position}没有完整覆盖自己的核心区间")

    global_data = plan["global"]
    compact = {
        "schema_version": "1.1",
        "global": {
            "target_duration_seconds": global_data["target_duration_seconds"],
            "target_start_seconds": global_data["target_start_seconds"],
            "target_end_seconds": global_data["target_end_seconds"],
            "task_types": global_data["task_types"],
            "continuity_context": " ".join(global_data.get("continuity_rules", [])),
            "reference_definitions": global_data["reference_definitions"],
            "character_relationships": global_data.get("character_relationships", []),
            "speaker_map": global_data.get("speaker_map", []),
        },
        "segments": collected,
    }
    report = f"汇总完成：{len(windows)}个自然分析窗口，共{len(collected)}个H3分段"
    return json.dumps(compact, ensure_ascii=False), report, len(collected)
