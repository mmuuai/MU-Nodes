import json
import re


REFERENCE = re.compile(r"^<(?:Subject|Picture|Video|Audio) [1-9]\d*>$")
SHOT = re.compile(r"\[Shot (\d+)\](?: At (\d{2}):(\d{2})\.(\d{3}),)?")
DIALOGUE = re.compile(r"<d>\[([A-Za-z][A-Za-z -]*)\] ([^<\r\n]+)</d>")
ANY_DIALOGUE = re.compile(r"<d>.*?</d>", re.DOTALL)
EXACT_SPEAKER = re.compile(r"(<Subject [1-9]\d*>) \((S\d+)\) says\s*$")
PROFILES = {"restrained": (2, 3, 3.0), "balanced": (3, 5, 2.0), "dynamic": (4, 6, 1.5), "one_take": (1, 1, 15.0)}
FRAMINGS = {"wide", "medium_wide", "medium", "medium_close_up", "close_up", "insert", "over_shoulder"}
MOVEMENTS = {"static", "push_in", "pull_out", "pan", "slider", "rack_focus", "follow"}
REQUIRED_BLOCKS = ("subject_definitions", "summary", "retention_analysis", "detailed_description", "overall_soundscape", "non_diegetic_music")


def _required(mapping, key, path, errors):
    value = mapping.get(key) if isinstance(mapping, dict) else None
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}.{key} must be a non-empty string")
        return ""
    return value.strip()


def _time(marker):
    if marker.group(2) is None:
        return 0.0
    return int(marker.group(2)) * 60 + int(marker.group(3)) + int(marker.group(4)) / 1000


def _load(text):
    raw = str(text or "").strip()
    fenced = re.fullmatch(r"\x60\x60\x60(?:json)?\s*(.*?)\s*\x60\x60\x60", raw, re.I | re.S)
    if fenced:
        raw = fenced.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"LLM output is not valid JSON: line {error.lineno}, column {error.colno}: {error.msg}") from error


def _validate_state(state, path, fixed_subjects, allowed_anchors, errors):
    if not isinstance(state, dict):
        errors.append(f"{path} must be an object")
        return None
    camera_anchor = _required(state, "camera_anchor", path, errors)
    camera_state = _required(state, "camera_state", path, errors)
    if camera_anchor not in allowed_anchors:
        errors.append(f"{path}.camera_anchor is not allowed")
    values = state.get("subject_states")
    if not isinstance(values, list):
        errors.append(f"{path}.subject_states must be an array")
        values = []
    parsed = []
    for index, item in enumerate(values):
        item_path = f"{path}.subject_states[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_path} must be an object")
            continue
        subject = _required(item, "subject", item_path, errors)
        parsed.append({
            "subject": subject,
            "anchor": _required(item, "anchor", item_path, errors),
            "position": _required(item, "position", item_path, errors),
            "facing": _required(item, "facing", item_path, errors),
            "posture": _required(item, "posture", item_path, errors),
            "gaze": _required(item, "gaze", item_path, errors),
            "held_objects": sorted(str(value).strip() for value in item.get("held_objects", []) if str(value).strip()),
        })
    if {item["subject"] for item in parsed} != fixed_subjects:
        errors.append(f"{path}.subject_states must contain every fixed subject exactly once")
    return {"camera_anchor": camera_anchor, "camera_state": camera_state, "subject_states": sorted(parsed, key=lambda item: item["subject"])}


def _state_line(item, zh):
    objects = ("、".join(item["held_objects"]) or "无") if zh else (", ".join(item["held_objects"]) or "none")
    if zh:
        return f"{item['subject']}：锚点={item['anchor']}；位置={item['position']}；朝向={item['facing']}；姿势={item['posture']}；视线={item['gaze']}；手持道具={objects}"
    return f"{item['subject']}: anchor={item['anchor']}; position={item['position']}; facing={item['facing']}; posture={item['posture']}; gaze={item['gaze']}; held_objects={objects}"


def validate(data):
    errors, warnings = [], []
    if not isinstance(data, dict) or data.get("schema_version") != "3.7":
        raise ValueError("schema_version must be 3.7")
    global_data = data.get("global")
    if not isinstance(global_data, dict):
        raise ValueError("global must be an object")
    language = global_data.get("output_language", "en")
    if language not in {"en", "zh-CN"}:
        errors.append("global.output_language must be en or zh-CN")
    target_duration = global_data.get("target_duration_seconds")
    if not isinstance(target_duration, (int, float)) or target_duration <= 0 or abs(target_duration / 15 - round(target_duration / 15)) > 0.001:
        errors.append("target_duration_seconds must be a positive multiple of 15")
        target_duration = 0
    definitions_list = global_data.get("reference_definitions")
    if not isinstance(definitions_list, list) or not definitions_list:
        errors.append("global.reference_definitions must be a non-empty array")
        definitions_list = []
    definitions = {}
    for index, item in enumerate(definitions_list):
        path = f"global.reference_definitions[{index}]"
        tag = item.get("tag") if isinstance(item, dict) else None
        if not isinstance(tag, str) or not REFERENCE.fullmatch(tag):
            errors.append(f"{path}.tag is invalid")
            continue
        definitions[tag] = {
            "definition": _required(item, "definition", path, errors),
            "retention_mode": _required(item, "retention_mode", path, errors),
            "retention_detail": _required(item, "retention_detail", path, errors),
        }
    layout = global_data.get("spatial_layout")
    if not isinstance(layout, dict):
        errors.append("global.spatial_layout must be an object")
        layout = {}
    anchors_list = layout.get("environment_anchors")
    if not isinstance(anchors_list, list) or not anchors_list:
        errors.append("environment_anchors must be a non-empty array")
        anchors_list = []
    anchor_descriptions = {}
    for index, item in enumerate(anchors_list):
        anchor_id = _required(item, "anchor_id", f"environment_anchors[{index}]", errors)
        anchor_descriptions[anchor_id] = _required(item, "description", f"environment_anchors[{index}]", errors)
    fixed = layout.get("fixed_subject_positions")
    if not isinstance(fixed, list) or not fixed:
        errors.append("fixed_subject_positions must be a non-empty array")
        fixed = []
    fixed_subjects = {item.get("subject") for item in fixed if isinstance(item, dict)}
    allowed = layout.get("allowed_camera_anchors")
    if not isinstance(allowed, list) or not allowed:
        errors.append("allowed_camera_anchors must be a non-empty array")
        allowed = []
    allowed_set = set(allowed)
    baseline = _required(layout, "baseline_camera_anchor", "spatial_layout", errors)
    opening_composition = _required(layout, "segment_opening_composition", "spatial_layout", errors)
    if baseline not in allowed_set:
        errors.append("baseline_camera_anchor must be allowed")
    grammar = layout.get("camera_grammar")
    if not isinstance(grammar, dict):
        errors.append("camera_grammar must be an object")
        grammar = {}
    profile = grammar.get("editing_profile")
    if profile not in PROFILES:
        errors.append("editing_profile is invalid")
        profile = "balanced"
    movement_palette = grammar.get("movement_palette")
    if not isinstance(movement_palette, list):
        movement_palette = []
    palette = grammar.get("shot_palette")
    if not isinstance(palette, list) or {item.get("anchor_id") for item in palette if isinstance(item, dict)} != allowed_set:
        errors.append("shot_palette must cover all allowed camera anchors")
        palette = []
    speaker_map = global_data.get("speaker_map")
    if not isinstance(speaker_map, list):
        errors.append("speaker_map must be an array")
        speaker_map = []
    speaker_subjects = {item.get("speaker_id"): item.get("subject") for item in speaker_map if isinstance(item, dict)}
    segments = data.get("segments")
    if not isinstance(segments, list) or len(segments) != round(target_duration / 15):
        errors.append("segments count does not match target duration")
        segments = segments if isinstance(segments, list) else []
    previous_ending = None
    previous_movements = None
    normalized_segments = []
    for position, segment in enumerate(segments, 1):
        path = f"segments[{position - 1}]"
        if not isinstance(segment, dict):
            errors.append(f"{path} must be an object")
            continue
        if segment.get("index") != position or segment.get("duration_seconds") != 15:
            errors.append(f"{path} must be segment {position} with duration 15")
        if segment.get("source_start_seconds") != (position - 1) * 15 or segment.get("source_end_seconds") != position * 15:
            errors.append(f"{path} timeline must use exact 15-second windows")
        detailed = _required(segment, "detailed_description", path, errors)
        markers = list(SHOT.finditer(detailed))
        if not markers or not detailed.startswith("[Shot 1] ") or markers[0].group(2) is not None:
            errors.append(f"{path}.detailed_description must start with untimed [Shot 1]")
        shot_plan = segment.get("shot_plan")
        minimum, maximum, minimum_duration = PROFILES[profile]
        if not isinstance(shot_plan, list) or not minimum <= len(shot_plan) <= maximum or len(shot_plan) != len(markers):
            errors.append(f"{path}.shot_plan count is invalid for {profile}")
            shot_plan = shot_plan if isinstance(shot_plan, list) else []
        parsed_plan = []
        for index, shot in enumerate(shot_plan, 1):
            shot_path = f"{path}.shot_plan[{index - 1}]"
            if not isinstance(shot, dict):
                errors.append(f"{shot_path} must be an object")
                continue
            start = shot.get("start_seconds")
            expected = _time(markers[index - 1]) if index <= len(markers) else None
            if shot.get("shot_number") != index or not isinstance(start, (int, float)) or expected is None or abs(start - expected) > 0.05:
                errors.append(f"{shot_path} number/time does not match detailed_description")
            camera_anchor = shot.get("camera_anchor")
            framing = shot.get("framing")
            movement = shot.get("movement")
            if camera_anchor not in allowed_set:
                errors.append(f"{shot_path}.camera_anchor is not allowed")
            if framing not in FRAMINGS:
                errors.append(f"{shot_path}.framing is invalid")
            if movement not in MOVEMENTS:
                errors.append(f"{shot_path}.movement is invalid")
            if movement not in movement_palette:
                movement_palette.append(movement)
            subjects = shot.get("subjects")
            if not isinstance(subjects, list) or not subjects or any(subject not in definitions for subject in subjects):
                errors.append(f"{shot_path}.subjects is invalid")
            parsed_plan.append({
                "shot_number": index, "start_seconds": start, "camera_anchor": camera_anchor,
                "framing": framing, "movement": movement, "subjects": subjects or [],
                "cut_trigger": _required(shot, "cut_trigger", shot_path, errors),
                "narrative_purpose": _required(shot, "narrative_purpose", shot_path, errors),
            })
        if parsed_plan:
            if parsed_plan[0]["camera_anchor"] != baseline:
                errors.append(f"{path}.shot_plan must start at baseline camera")
            if len(parsed_plan) > 1 and len({item["camera_anchor"] for item in parsed_plan}) < 2:
                errors.append(f"{path}.shot_plan needs at least two same-side anchors")
            if len(parsed_plan) > 1 and len({item["framing"] for item in parsed_plan}) < 2:
                errors.append(f"{path}.shot_plan needs at least two framings")
            durations = [(parsed_plan[i + 1]["start_seconds"] if i + 1 < len(parsed_plan) else 15) - item["start_seconds"] for i, item in enumerate(parsed_plan)]
            if any(value + 0.05 < minimum_duration for value in durations):
                errors.append(f"{path}.shot_plan contains a shot below the minimum duration")
            if profile in {"restrained", "balanced"} and len(durations) >= 3 and max(durations) - min(durations) <= 0.1:
                errors.append(f"{path}.shot_plan mechanically divides the segment")
            signature = tuple(item["movement"] for item in parsed_plan if item["movement"] != "static")
            if profile in {"balanced", "dynamic"} and signature and signature == previous_movements:
                warnings.append(f"segment {position} repeats the previous movement signature")
            previous_movements = signature
        opening = _validate_state(segment.get("opening_spatial_state"), f"{path}.opening_spatial_state", fixed_subjects, allowed_set, errors)
        ending = _validate_state(segment.get("ending_spatial_state"), f"{path}.ending_spatial_state", fixed_subjects, allowed_set, errors)
        if opening and (opening["camera_anchor"] != baseline or opening["camera_state"] != opening_composition):
            errors.append(f"{path}.opening_spatial_state must use the baseline composition")
        if previous_ending is not None and opening and previous_ending["subject_states"] != opening["subject_states"]:
            errors.append(f"{path} does not copy the previous ending subject states")
        previous_ending = ending
        raw_dialogues = list(ANY_DIALOGUE.finditer(detailed))
        valid_dialogues = list(DIALOGUE.finditer(detailed))
        if len(raw_dialogues) != len(valid_dialogues):
            errors.append(f"{path} contains invalid dialogue tags")
        for dialogue in valid_dialogues:
            prefix = detailed[max(0, dialogue.start() - 120):dialogue.start()]
            speaker = EXACT_SPEAKER.search(prefix)
            if not speaker or speaker_subjects.get(speaker.group(2)) != speaker.group(1):
                errors.append(f"{path} contains an invalid Subject/Speaker dialogue")
        usage = segment.get("reference_usage")
        if not isinstance(usage, dict) or not usage:
            errors.append(f"{path}.reference_usage must be a non-empty object")
            usage = {}
        for tag, item in usage.items():
            if tag not in definitions or not isinstance(item, dict):
                errors.append(f"{path}.reference_usage contains an invalid tag")
                continue
            locations = []
            for index, marker in enumerate(markers):
                end = markers[index + 1].start() if index + 1 < len(markers) else len(detailed)
                if tag in detailed[marker.start():end]:
                    locations.append(f"[Shot {index + 1}]")
            if not locations:
                errors.append(f"{path}.reference_usage {tag} is not used in any Shot")
            item["locations"] = ", ".join(locations)
            item["retention_mode"] = item.get("retention_mode") or definitions[tag]["retention_mode"]
            item["detail"] = str(item.get("detail") or definitions[tag]["retention_detail"]).strip()
        normalized_segments.append({**segment, "shot_plan": parsed_plan, "opening_spatial_state": opening, "ending_spatial_state": ending, "reference_usage": usage})
    grammar["movement_palette"] = movement_palette
    if errors:
        raise ValueError("H3 deterministic validation failed:\n- " + "\n- ".join(errors))
    data["segments"] = normalized_segments
    return data, definitions, warnings


def _spatial_lines(data, segment, zh):
    layout = data["global"]["spatial_layout"]
    grammar = layout["camera_grammar"]
    labels = {
        "coordinate": "空间坐标系" if zh else "Spatial coordinate system",
        "anchors": "环境锚点" if zh else "Environment anchors",
        "positions": "固定主体位置" if zh else "Fixed subject positions",
        "baseline": "摄影机基线" if zh else "Camera baseline",
        "direction": "屏幕方向规则" if zh else "Screen-direction rule",
        "handoff": "关键帧衔接" if zh else "Keyframe handoff",
        "screen": "基准画面从左到右顺序" if zh else "Baseline screen order from left to right",
    }
    colon = "：" if zh else ": "
    lines = [
        f"{labels['coordinate']}{colon}{layout['coordinate_system']}",
        f"{labels['anchors']}{colon}" + " | ".join(f"{item['anchor_id']}={item['description']}" for item in layout["environment_anchors"]),
        f"{labels['positions']}{colon}" + " | ".join(f"{item['subject']}@{item['anchor']}：{item['position']}；{item['facing']}" for item in layout["fixed_subject_positions"]),
        f"{labels['baseline']}{colon}{layout['camera_baseline']}",
        f"{labels['direction']}{colon}{layout['screen_direction_rule']}",
        f"{labels['handoff']}{colon}{layout['keyframe_handoff']}",
        f"baseline_camera_anchor: {layout['baseline_camera_anchor']}",
        "allowed_camera_anchors: " + ", ".join(layout["allowed_camera_anchors"]),
        f"{labels['screen']}{colon}" + " -> ".join(layout["baseline_screen_order"]),
        ("强制分段开场构图：" if zh else "Mandatory segment opening composition: ") + layout["segment_opening_composition"],
        ("剪辑风格：" if zh else "Editing profile: ") + grammar["editing_profile"],
        ("摄影机轴线半区：" if zh else "Camera axis side: ") + grammar["axis_side"],
        ("同侧安全弧线：" if zh else "Same-side safe arc: ") + grammar["safe_arc"],
        ("允许运镜库：" if zh else "Movement palette: ") + ", ".join(grammar["movement_palette"]),
        ("叙事切镜触发：" if zh else "Narrative cut triggers: ") + " | ".join(grammar["cut_triggers"]),
        ("同侧镜头机位库：" if zh else "Same-side shot palette: ") + " | ".join(f"{item['anchor_id']}[{', '.join(item['framing_options'])}; {item['lens']}]: {item['description']}" for item in grammar["shot_palette"]),
    ]
    opening, ending = segment["opening_spatial_state"], segment["ending_spatial_state"]
    lines.extend([
        ("开场摄影机锚点：" if zh else "Opening camera anchor: ") + opening["camera_anchor"],
        ("开场摄影机状态：" if zh else "Opening camera state: ") + opening["camera_state"],
        ("开场主体状态：" if zh else "Opening subject states: ") + " | ".join(_state_line(item, zh) for item in opening["subject_states"]),
        "强制第一帧规则：第一帧必须逐字呈现上述开场状态，不得提前完成任何动作。" if zh else "Mandatory first-frame rule: show the opening states exactly before any new action.",
        ("本段空间变化：" if zh else "Spatial transition: ") + segment["spatial_transition"],
        ("结束摄影机锚点：" if zh else "Ending camera anchor: ") + ending["camera_anchor"],
        ("结束摄影机状态：" if zh else "Ending camera state: ") + ending["camera_state"],
        ("结束主体状态：" if zh else "Ending subject states: ") + " | ".join(_state_line(item, zh) for item in ending["subject_states"]),
        "强制边界衔接：下一段必须先从上述结束状态开始。" if zh else "Mandatory boundary handoff: the next segment starts from these exact ending states.",
    ])
    return lines


def assemble(text):
    data, definitions, warnings = validate(_load(text))
    global_data = data["global"]
    zh = global_data.get("output_language") == "zh-CN"
    blocks = []
    for segment in data["segments"]:
        usage = segment["reference_usage"]
        used = set(usage)
        relationships = [item for item in global_data.get("character_relationships", []) if any(subject in used for subject in item.get("subjects", []))]
        definition_tags = used | {subject for item in relationships for subject in item.get("subjects", [])}
        subject_lines = [f"{tag}: {definitions[tag]['definition']}" for tag in definitions if tag in definition_tags]
        retention = [f"{tag} (appears in {item['locations']}): {item['retention_mode']} - {item['detail']}" for tag, item in usage.items()]
        layout = global_data["spatial_layout"]
        positions = ("；" if zh else "; ").join(f"{item['subject']}{item['position']}" for item in layout["fixed_subject_positions"])
        order = " -> ".join(layout["baseline_screen_order"])
        lock = (
            f"连续性：{positions}；基准画面左到右={order}；摄影机始终保持在场景同一侧，不得越轴、镜像、换位或瞬移。"
            if zh else
            f"Continuity: {positions}; baseline screen order={order}; keep the camera on the same side of the scene; no axis crossing, mirroring, seat swapping, or teleporting."
        )
        detail = [lock, segment["detailed_description"].replace(" [Shot ", "\n[Shot ")]
        body = "\n\n".join([
            "subject_definitions:\n" + "\n".join(subject_lines),
            "summary:\n[" + " + ".join(global_data["task_types"]) + "] " + segment["summary"],
            "retention_analysis:\n" + "\n".join(retention),
            "detailed_description:\n" + "\n".join(detail),
            "overall_soundscape:\n" + segment["overall_soundscape"],
            "non_diegetic_music:\n" + segment["non_diegetic_music"],
        ])
        blocks.append(body)
    report = f"校验通过\n分段数：{len(blocks)}\n目标总时长：{global_data['target_duration_seconds']}秒\n警告数：{len(warnings)}"
    return "\n\n<<<H3_SEGMENT_BREAK>>>\n\n".join(blocks), report, json.dumps(data, ensure_ascii=False), str(len(blocks))
