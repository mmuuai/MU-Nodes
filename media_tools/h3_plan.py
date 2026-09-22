import json
import math
import re


REFERENCE_TAG = re.compile(r"^<(Subject|Picture|Video|Audio) [1-9]\d*>$")
ALLOWED_TASK_TYPES = {
    "reference generation",
    "keyframe completion",
    "video editing",
    "video continuation",
    "audio reuse",
    "audio reference",
}
VISIBLE_RETENTION_MODES = {
    "fully_preserved",
    "partially_preserved",
    "attribute_transfer",
    "weak_reference",
}
AUDIO_RETENTION_MODES = {
    "fully_copy",
    "partially_copy",
    "reference",
    "weak_reference",
}
ALLOWED_CAMERA_FRAMINGS = {
    "wide",
    "medium_wide",
    "medium",
    "medium_close_up",
    "close_up",
    "insert",
    "over_shoulder",
}
ALLOWED_CAMERA_MOVEMENTS = {
    "static",
    "push_in",
    "pull_out",
    "pan",
    "slider",
    "rack_focus",
    "follow",
}
CAMERA_EDITING_PROFILES = {
    "restrained": (2, 3),
    "balanced": (3, 5),
    "dynamic": (4, 6),
    "one_take": (1, 1),
}
CAMERA_MINIMUM_SHOT_DURATION = {
    "restrained": 3.0,
    "balanced": 2.0,
    "dynamic": 1.5,
    "one_take": 15.0,
}
SHOT_MARKER = re.compile(
    r"\[Shot (\d+)\](?: At (\d{2}):(\d{2})\.(\d{3}),)?"
)
DIALOGUE_TAG = re.compile(
    r"<d>\[([A-Za-z][A-Za-z -]*)\] ([^<\r\n]+)</d>"
)
ANY_DIALOGUE_TAG = re.compile(r"<d>.*?</d>", re.DOTALL)
UNLABELED_CUT = re.compile(
    r"(?<!\] )At \d{2}:\d{2}\.\d{3},\s*(?:cut|return)\b"
    r"|(?:^|(?<=[.!?])\s+)(?:cut(?:\s+\w+){0,2}\s+to|return to)\b",
    re.IGNORECASE,
)
PRECOMPLETED_BOUNDARY_ACTION = re.compile(
    r"\b(?:has|have|had)\s+(?:just\s+)?"
    r"(?:lowered|resumed|turned|set|placed|picked|raised|changed|moved|shifted|leaned)\b"
    r"|\balready\s+(?:lowered|resumed|turned|set|placed|picked|raised|changed|moved|shifted|leaned)\b",
    re.IGNORECASE,
)


def duration_label(seconds):
    return f"{seconds:.3f}".rstrip("0").rstrip(".")


def _strip_json_fence(text):
    normalized = str(text).strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", normalized, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else normalized


def _merge_usage_item(existing, incoming):
    if not isinstance(existing, dict) or not isinstance(incoming, dict):
        return existing
    for field in ("locations", "detail"):
        current = existing.get(field)
        added = incoming.get(field)
        if isinstance(added, str) and added.strip():
            if not isinstance(current, str) or not current.strip():
                existing[field] = added.strip()
            elif added.strip() not in current:
                existing[field] = f"{current.strip()}, {added.strip()}"
    return existing


def _replace_reference_aliases(value, aliases):
    if isinstance(value, dict):
        return {
            aliases.get(key, key): _replace_reference_aliases(child, aliases)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_replace_reference_aliases(child, aliases) for child in value]
    if isinstance(value, str):
        for source, target in aliases.items():
            value = value.replace(source, target)
    return value


def _normalize_compact_references(data):
    if not isinstance(data, dict):
        return data
    global_data = data.get("global")
    if not isinstance(global_data, dict):
        return data
    definitions = global_data.get("reference_definitions")
    if not isinstance(definitions, list):
        return data

    used_subject_numbers = {
        int(match.group(1))
        for item in definitions
        if isinstance(item, dict)
        and isinstance(item.get("tag"), str)
        and (match := re.fullmatch(r"<Subject ([1-9]\d*)>", item["tag"]))
    }
    next_subject = max(used_subject_numbers, default=0) + 1
    aliases = {}
    for item in definitions:
        tag = item.get("tag") if isinstance(item, dict) else None
        if isinstance(tag, str) and re.fullmatch(r"<(?:Environment|Scene) [1-9]\d*>", tag):
            aliases[tag] = f"<Subject {next_subject}>"
            next_subject += 1
    if aliases:
        data = _replace_reference_aliases(data, aliases)
        global_data = data["global"]
        definitions = global_data["reference_definitions"]

    defined_tags = {
        item.get("tag") for item in definitions if isinstance(item, dict)
    }
    definitions_by_tag = {
        item.get("tag"): item for item in definitions if isinstance(item, dict)
    }
    for mapping in global_data.get("speaker_map", []):
        if not isinstance(mapping, dict):
            continue
        subject_tag = mapping.get("subject")
        if not isinstance(subject_tag, str) or subject_tag in defined_tags:
            continue
        match = re.fullmatch(r"<Subject ([1-9]\d*)>", subject_tag)
        if not match:
            continue
        picture_tag = f"<Picture {match.group(1)}>"
        picture = definitions_by_tag.get(picture_tag)
        if not isinstance(picture, dict):
            continue
        definitions.append(
            {
                "tag": subject_tag,
                "definition": f"The target subject whose visible identity is defined by {picture_tag}.",
                "retention_mode": "fully_preserved",
                "retention_detail": picture.get("retention_detail") or f"Preserve the visible identity from {picture_tag}.",
            }
        )
        defined_tags.add(subject_tag)
        definitions_by_tag[subject_tag] = definitions[-1]
    picture_aliases = {}
    for item in definitions:
        if not isinstance(item, dict):
            continue
        subject_tag = item.get("tag")
        if not isinstance(subject_tag, str) or not subject_tag.startswith("<Subject "):
            continue
        source_text = f"{item.get('definition', '')} {item.get('retention_detail', '')}"
        for picture_tag in re.findall(r"<Picture [1-9]\d*>", source_text):
            if picture_tag not in defined_tags:
                picture_aliases[picture_tag] = subject_tag

    for mapping in global_data.get("speaker_map", []):
        if not isinstance(mapping, dict):
            continue
        audio_tag = mapping.get("audio_reference")
        if not isinstance(audio_tag, str) or not audio_tag.startswith("<Audio "):
            continue
        if audio_tag in defined_tags:
            continue
        speaker_id = mapping.get("speaker_id", "speaker")
        subject = mapping.get("subject", "the mapped subject")
        definitions.append(
            {
                "tag": audio_tag,
                "definition": f"The voice reference for {subject} ({speaker_id}).",
                "retention_mode": "reference",
                "retention_detail": "Use the referenced voice identity, delivery, and vocal character.",
            }
        )
        defined_tags.add(audio_tag)

    for segment in data.get("segments", []):
        if not isinstance(segment, dict):
            continue
        usage = segment.get("reference_usage")
        if not isinstance(usage, dict):
            continue
        for source_tag, item in list(usage.items()):
            target_tag = picture_aliases.get(source_tag, source_tag)
            if target_tag != source_tag:
                if target_tag in usage:
                    _merge_usage_item(usage[target_tag], item)
                else:
                    usage[target_tag] = item
                del usage[source_tag]
        for item in usage.values():
            if isinstance(item, dict):
                locations = item.get("locations")
                if not isinstance(locations, str) or not locations.strip():
                    item["locations"] = "this segment"
    return data


def _replace_speaker_ids(value, aliases):
    if isinstance(value, dict):
        return {key: _replace_speaker_ids(child, aliases) for key, child in value.items()}
    if isinstance(value, list):
        return [_replace_speaker_ids(child, aliases) for child in value]
    if isinstance(value, str):
        return re.sub(r"\bS\d+\b", lambda match: aliases.get(match.group(0), match.group(0)), value)
    return value


def _normalize_output_language(data):
    if not isinstance(data, dict):
        return data
    global_data = data.get("global")
    if not isinstance(global_data, dict):
        return data
    top_level = data.get("output_language")
    if "output_language" not in global_data and top_level in {"en", "zh-CN"}:
        global_data["output_language"] = top_level
        data.pop("output_language", None)
    return data


def _normalize_speaker_order(data):
    if not isinstance(data, dict):
        return data
    global_data = data.get("global")
    speaker_map = global_data.get("speaker_map") if isinstance(global_data, dict) else None
    if not isinstance(speaker_map, list) or not speaker_map:
        return data

    declared = [
        item.get("speaker_id")
        for item in speaker_map
        if isinstance(item, dict) and isinstance(item.get("speaker_id"), str)
    ]
    seen = []
    for segment in data.get("segments", []):
        if not isinstance(segment, dict):
            continue
        detailed = segment.get("detailed_description")
        if not isinstance(detailed, str):
            continue
        for match in re.finditer(r"\((S\d+)\)[^<>]{0,80}<d>", detailed):
            speaker_id = match.group(1)
            if speaker_id in declared and speaker_id not in seen:
                seen.append(speaker_id)
    seen.extend(speaker_id for speaker_id in declared if speaker_id not in seen)
    aliases = {speaker_id: f"S{index}" for index, speaker_id in enumerate(seen, 1)}
    if all(source == target for source, target in aliases.items()):
        return data

    normalized = _replace_speaker_ids(data, aliases)
    normalized["global"]["speaker_map"].sort(
        key=lambda item: int(item["speaker_id"][1:])
    )
    return normalized


def _normalize_usage_locations(data):
    if not isinstance(data, dict):
        return data
    for segment in data.get("segments", []):
        if not isinstance(segment, dict):
            continue
        detailed = segment.get("detailed_description")
        usage = segment.get("reference_usage")
        if not isinstance(detailed, str) or not isinstance(usage, dict):
            continue
        markers = list(SHOT_MARKER.finditer(detailed))
        if not markers:
            continue
        for tag, item in usage.items():
            if not isinstance(tag, str) or not isinstance(item, dict):
                continue
            shot_numbers = []
            for index, marker in enumerate(markers):
                end = markers[index + 1].start() if index + 1 < len(markers) else len(detailed)
                if tag in detailed[marker.start():end]:
                    shot_numbers.append(int(marker.group(1)))
            if shot_numbers:
                item["locations"] = ", ".join(
                    f"[Shot {number}]" for number in shot_numbers
                )
    return data


def _normalize_camera_grammar_usage(data):
    if not isinstance(data, dict):
        return data
    global_data = data.get("global")
    layout = global_data.get("spatial_layout") if isinstance(global_data, dict) else None
    grammar = layout.get("camera_grammar") if isinstance(layout, dict) else None
    if not isinstance(grammar, dict):
        return data
    movements = grammar.get("movement_palette")
    if not isinstance(movements, list):
        return data
    for segment in data.get("segments", []):
        if not isinstance(segment, dict):
            continue
        for shot in segment.get("shot_plan", []):
            movement = shot.get("movement") if isinstance(shot, dict) else None
            if movement in ALLOWED_CAMERA_MOVEMENTS and movement not in movements:
                movements.append(movement)
    return data


class CompactH3PlanParser:
    def __init__(self, data):
        self.data = data
        self.errors = []
        self.warnings = []
        self.definitions = {}
        self.speaker_ids = set()
        self.speaker_subjects = {}
        self.require_spatial = str(data.get("schema_version", "")).startswith("3.") if isinstance(data, dict) else False
        version_match = re.fullmatch(r"(\d+)\.(\d+)", str(data.get("schema_version", ""))) if isinstance(data, dict) else None
        self.require_screen_lock = bool(
            version_match and (int(version_match.group(1)), int(version_match.group(2))) >= (3, 3)
        )
        self.require_standard_segments = bool(
            version_match and (int(version_match.group(1)), int(version_match.group(2))) >= (3, 4)
        )
        self.require_fixed_segments = bool(
            version_match and (int(version_match.group(1)), int(version_match.group(2))) >= (3, 5)
        )
        self.require_strict_boundary = bool(
            version_match and (int(version_match.group(1)), int(version_match.group(2))) >= (3, 6)
        )
        self.require_camera_grammar = bool(
            version_match and (int(version_match.group(1)), int(version_match.group(2))) >= (3, 7)
        )
        self.spatial_anchors = set()
        self.fixed_spatial_subjects = set()
        self.baseline_camera_anchor = ""
        self.allowed_camera_anchors = set()
        self.segment_opening_composition = ""
        self.camera_movements = set()
        self.camera_editing_profile = "balanced"

    def nonempty_string(self, value, path):
        if not isinstance(value, str) or not value.strip():
            self.errors.append(f"{path} 必须是非空字符串")
            return ""
        return value.strip()

    def positive_number(self, value, path, maximum=None):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            self.errors.append(f"{path} 必须是大于0的数字")
            return 0.0
        number = float(value)
        if maximum is not None and number > maximum:
            self.errors.append(f"{path} 不得超过{maximum}秒")
        return number

    def nonnegative_number(self, value, path):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            self.errors.append(f"{path} 必须是大于等于0的数字")
            return 0.0
        return float(value)

    def parse_global(self):
        global_data = self.data.get("global")
        if not isinstance(global_data, dict):
            self.errors.append("global 必须是JSON对象")
            global_data = {}
        target_duration = self.positive_number(
            global_data.get("target_duration_seconds"), "global.target_duration_seconds"
        )
        target_start = self.nonnegative_number(
            global_data.get("target_start_seconds", 0), "global.target_start_seconds"
        )
        target_end = self.positive_number(
            global_data.get("target_end_seconds", target_start + target_duration),
            "global.target_end_seconds",
        )
        if abs((target_end - target_start) - target_duration) > 0.05:
            self.errors.append("global 的目标时间范围与 target_duration_seconds 不一致")
        task_types = global_data.get("task_types")
        if not isinstance(task_types, list) or not task_types:
            self.errors.append("global.task_types 必须是非空数组")
            task_types = []
        else:
            invalid = [item for item in task_types if item not in ALLOWED_TASK_TYPES]
            if invalid:
                self.errors.append(f"global.task_types 含不支持的任务类型：{invalid}")
            if len(task_types) != len(set(task_types)):
                self.errors.append("global.task_types 不得重复")
        continuity = global_data.get("continuity_context", "")
        if not isinstance(continuity, str):
            self.errors.append("global.continuity_context 必须是字符串")
            continuity = ""
        output_language = global_data.get("output_language", "en")
        if output_language not in {"en", "zh-CN"}:
            self.errors.append("global.output_language 只能是 en 或 zh-CN")
            output_language = "en"
        self.parse_definitions(global_data.get("reference_definitions", []))
        spatial_layout = self.parse_spatial_layout(global_data.get("spatial_layout"))
        relationships = self.parse_relationships(global_data.get("character_relationships", []))
        speaker_map = self.parse_speaker_map(global_data.get("speaker_map", []))
        self.speaker_ids = {
            item["speaker_id"] for item in speaker_map if item.get("speaker_id")
        }
        self.speaker_subjects = {
            item["speaker_id"]: item["subject"]
            for item in speaker_map
            if item.get("speaker_id") and item.get("subject")
        }
        return (
            target_duration,
            target_start,
            target_end,
            task_types,
            continuity.strip(),
            output_language,
            spatial_layout,
            relationships,
            speaker_map,
        )

    def parse_spatial_layout(self, value):
        if value is None and not self.require_spatial:
            return None
        if not isinstance(value, dict):
            self.errors.append("global.spatial_layout 必须是JSON对象")
            value = {}
        coordinate_system = self.nonempty_string(
            value.get("coordinate_system"), "global.spatial_layout.coordinate_system"
        )
        camera_baseline = self.nonempty_string(
            value.get("camera_baseline"), "global.spatial_layout.camera_baseline"
        )
        screen_direction_rule = self.nonempty_string(
            value.get("screen_direction_rule"), "global.spatial_layout.screen_direction_rule"
        )
        keyframe_handoff = self.nonempty_string(
            value.get("keyframe_handoff"), "global.spatial_layout.keyframe_handoff"
        )

        anchors = value.get("environment_anchors")
        if not isinstance(anchors, list) or not anchors:
            self.errors.append("global.spatial_layout.environment_anchors 必须是非空数组")
            anchors = []
        parsed_anchors = []
        for index, item in enumerate(anchors):
            path = f"global.spatial_layout.environment_anchors[{index}]"
            if not isinstance(item, dict):
                self.errors.append(f"{path} 必须是JSON对象")
                continue
            anchor_id = self.nonempty_string(item.get("anchor_id"), f"{path}.anchor_id")
            description = self.nonempty_string(item.get("description"), f"{path}.description")
            if anchor_id in self.spatial_anchors:
                self.errors.append(f"{path}.anchor_id 重复：{anchor_id}")
            if anchor_id:
                self.spatial_anchors.add(anchor_id)
            parsed_anchors.append({"anchor_id": anchor_id, "description": description})

        positions = value.get("fixed_subject_positions")
        if not isinstance(positions, list) or not positions:
            self.errors.append("global.spatial_layout.fixed_subject_positions 必须是非空数组")
            positions = []
        parsed_positions = []
        for index, item in enumerate(positions):
            path = f"global.spatial_layout.fixed_subject_positions[{index}]"
            if not isinstance(item, dict):
                self.errors.append(f"{path} 必须是JSON对象")
                continue
            subject = self.nonempty_string(item.get("subject"), f"{path}.subject")
            anchor = self.nonempty_string(item.get("anchor"), f"{path}.anchor")
            position = self.nonempty_string(item.get("position"), f"{path}.position")
            facing = self.nonempty_string(item.get("facing"), f"{path}.facing")
            if subject not in self.definitions:
                self.errors.append(f"{path}.subject 引用了未定义标签")
            if anchor not in self.spatial_anchors:
                self.errors.append(f"{path}.anchor 引用了未定义空间锚点")
            if subject in self.fixed_spatial_subjects:
                self.errors.append(f"{path}.subject 重复：{subject}")
            if subject:
                self.fixed_spatial_subjects.add(subject)
            parsed_positions.append({
                "subject": subject,
                "anchor": anchor,
                "position": position,
                "facing": facing,
            })

        baseline_camera_anchor = ""
        allowed_camera_anchors = []
        baseline_screen_order = []
        segment_opening_composition = ""
        if self.require_screen_lock or value.get("baseline_camera_anchor") is not None:
            baseline_camera_anchor = self.nonempty_string(
                value.get("baseline_camera_anchor"),
                "global.spatial_layout.baseline_camera_anchor",
            )
            allowed_value = value.get("allowed_camera_anchors")
            if not isinstance(allowed_value, list) or not allowed_value:
                self.errors.append(
                    "global.spatial_layout.allowed_camera_anchors 必须是非空数组"
                )
                allowed_value = []
            allowed_camera_anchors = [
                item.strip() for item in allowed_value if isinstance(item, str) and item.strip()
            ]
            if len(allowed_camera_anchors) != len(allowed_value):
                self.errors.append(
                    "global.spatial_layout.allowed_camera_anchors 必须全部为非空字符串"
                )
            if len(allowed_camera_anchors) != len(set(allowed_camera_anchors)):
                self.errors.append(
                    "global.spatial_layout.allowed_camera_anchors 不得重复"
                )
            for anchor in allowed_camera_anchors:
                if anchor not in self.spatial_anchors:
                    self.errors.append(
                        "global.spatial_layout.allowed_camera_anchors 引用了未定义锚点："
                        f"{anchor}"
                    )
            if baseline_camera_anchor not in allowed_camera_anchors:
                self.errors.append(
                    "global.spatial_layout.baseline_camera_anchor 必须属于 allowed_camera_anchors"
                )

            order_value = value.get("baseline_screen_order")
            if not isinstance(order_value, list) or not order_value:
                self.errors.append(
                    "global.spatial_layout.baseline_screen_order 必须是非空数组"
                )
                order_value = []
            baseline_screen_order = []
            for item in order_value:
                if not isinstance(item, str) or not item.strip():
                    continue
                subject_match = re.match(r"<Subject [1-9]\d*>", item.strip())
                baseline_screen_order.append(
                    subject_match.group(0) if subject_match else item.strip()
                )
            if len(baseline_screen_order) != len(set(baseline_screen_order)):
                self.errors.append(
                    "global.spatial_layout.baseline_screen_order 不得重复"
                )
            if set(baseline_screen_order) != self.fixed_spatial_subjects:
                self.errors.append(
                    "global.spatial_layout.baseline_screen_order 必须恰好包含全部固定人物"
                )
            segment_opening_composition = self.nonempty_string(
                value.get("segment_opening_composition"),
                "global.spatial_layout.segment_opening_composition",
            )
            self.baseline_camera_anchor = baseline_camera_anchor
            self.allowed_camera_anchors = set(allowed_camera_anchors)
            self.segment_opening_composition = segment_opening_composition
        camera_grammar = self.parse_camera_grammar(value.get("camera_grammar"))
        return {
            "coordinate_system": coordinate_system,
            "environment_anchors": parsed_anchors,
            "fixed_subject_positions": parsed_positions,
            "camera_baseline": camera_baseline,
            "screen_direction_rule": screen_direction_rule,
            "keyframe_handoff": keyframe_handoff,
            "baseline_camera_anchor": baseline_camera_anchor or None,
            "allowed_camera_anchors": allowed_camera_anchors,
            "baseline_screen_order": baseline_screen_order,
            "segment_opening_composition": segment_opening_composition or None,
            "camera_grammar": camera_grammar,
        }

    def parse_camera_grammar(self, value):
        if value is None and not self.require_camera_grammar:
            return None
        if not isinstance(value, dict):
            self.errors.append("global.spatial_layout.camera_grammar 必须是JSON对象")
            value = {}
        path = "global.spatial_layout.camera_grammar"
        axis_side = self.nonempty_string(value.get("axis_side"), f"{path}.axis_side")
        safe_arc = self.nonempty_string(value.get("safe_arc"), f"{path}.safe_arc")
        editing_profile = self.nonempty_string(
            value.get("editing_profile"), f"{path}.editing_profile"
        )
        if editing_profile not in CAMERA_EDITING_PROFILES:
            self.errors.append(
                f"{path}.editing_profile 只能是 "
                + ", ".join(CAMERA_EDITING_PROFILES)
            )
            editing_profile = "balanced"
        self.camera_editing_profile = editing_profile
        minimum_anchors = 1 if editing_profile == "one_take" else 2
        if self.require_camera_grammar and len(self.allowed_camera_anchors) < minimum_anchors:
            self.errors.append(
                f"3.7 {editing_profile} 至少需要{minimum_anchors}个同侧允许摄影机锚点"
            )

        movements = value.get("movement_palette")
        if not isinstance(movements, list) or not movements:
            self.errors.append(f"{path}.movement_palette 必须是非空数组")
            movements = []
        parsed_movements = [
            item.strip() for item in movements if isinstance(item, str) and item.strip()
        ]
        invalid_movements = sorted(set(parsed_movements) - ALLOWED_CAMERA_MOVEMENTS)
        if invalid_movements:
            self.errors.append(f"{path}.movement_palette 含不支持运镜：{invalid_movements}")
        minimum_movements = 1 if editing_profile == "one_take" else 2
        if self.require_camera_grammar and len(set(parsed_movements)) < minimum_movements:
            self.errors.append(
                f"3.7 {editing_profile} movement_palette 至少需要{minimum_movements}种运镜"
            )
        self.camera_movements = set(parsed_movements)

        cut_triggers = value.get("cut_triggers")
        if not isinstance(cut_triggers, list) or not cut_triggers:
            self.errors.append(f"{path}.cut_triggers 必须是非空数组")
            cut_triggers = []
        parsed_triggers = [
            item.strip() for item in cut_triggers if isinstance(item, str) and item.strip()
        ]

        palette = value.get("shot_palette")
        if not isinstance(palette, list) or not palette:
            self.errors.append(f"{path}.shot_palette 必须是非空数组")
            palette = []
        parsed_palette = []
        palette_anchors = set()
        for index, item in enumerate(palette):
            item_path = f"{path}.shot_palette[{index}]"
            if not isinstance(item, dict):
                self.errors.append(f"{item_path} 必须是JSON对象")
                continue
            anchor_id = self.nonempty_string(item.get("anchor_id"), f"{item_path}.anchor_id")
            description = self.nonempty_string(
                item.get("description"), f"{item_path}.description"
            )
            lens = self.nonempty_string(item.get("lens"), f"{item_path}.lens")
            framings = item.get("framing_options")
            if not isinstance(framings, list) or not framings:
                self.errors.append(f"{item_path}.framing_options 必须是非空数组")
                framings = []
            parsed_framings = [
                framing.strip()
                for framing in framings
                if isinstance(framing, str) and framing.strip()
            ]
            invalid_framings = sorted(set(parsed_framings) - ALLOWED_CAMERA_FRAMINGS)
            if invalid_framings:
                self.errors.append(
                    f"{item_path}.framing_options 含不支持景别：{invalid_framings}"
                )
            if anchor_id not in self.allowed_camera_anchors:
                self.errors.append(f"{item_path}.anchor_id 不属于允许机位")
            if anchor_id in palette_anchors:
                self.errors.append(f"{item_path}.anchor_id 重复：{anchor_id}")
            palette_anchors.add(anchor_id)
            parsed_palette.append({
                "anchor_id": anchor_id,
                "description": description,
                "lens": lens,
                "framing_options": parsed_framings,
            })
        if self.require_camera_grammar and palette_anchors != self.allowed_camera_anchors:
            self.errors.append("3.7 shot_palette 必须恰好覆盖全部允许摄影机锚点")
        return {
            "axis_side": axis_side,
            "safe_arc": safe_arc,
            "editing_profile": editing_profile,
            "movement_palette": parsed_movements,
            "cut_triggers": parsed_triggers,
            "shot_palette": parsed_palette,
        }

    def parse_relationships(self, relationships):
        if not isinstance(relationships, list):
            self.errors.append("global.character_relationships 必须是数组")
            return []
        parsed = []
        for index, item in enumerate(relationships):
            path = f"global.character_relationships[{index}]"
            if not isinstance(item, dict):
                self.errors.append(f"{path} 必须是JSON对象")
                continue
            subjects = item.get("subjects")
            relationship = self.nonempty_string(item.get("relationship"), f"{path}.relationship")
            if not isinstance(subjects, list) or not subjects:
                self.errors.append(f"{path}.subjects 必须是非空数组")
                subjects = []
            elif any(subject not in self.definitions for subject in subjects):
                self.errors.append(f"{path}.subjects 引用了未定义标签")
            parsed.append({"subjects": subjects, "relationship": relationship})
        return parsed

    def parse_speaker_map(self, speaker_map):
        if not isinstance(speaker_map, list):
            self.errors.append("global.speaker_map 必须是数组")
            return []
        parsed = []
        seen = set()
        for index, item in enumerate(speaker_map):
            path = f"global.speaker_map[{index}]"
            if not isinstance(item, dict):
                self.errors.append(f"{path} 必须是JSON对象")
                continue
            speaker_id = self.nonempty_string(item.get("speaker_id"), f"{path}.speaker_id")
            subject = self.nonempty_string(item.get("subject"), f"{path}.subject")
            audio = item.get("audio_reference")
            if isinstance(audio, str) and not audio.strip():
                audio = None
            if speaker_id in seen:
                self.errors.append(f"{path}.speaker_id 重复：{speaker_id}")
            seen.add(speaker_id)
            if subject not in self.definitions:
                self.errors.append(f"{path}.subject 引用了未定义标签")
            if audio is not None and audio not in self.definitions:
                self.errors.append(f"{path}.audio_reference 引用了未定义标签")
            parsed.append(
                {
                    "speaker_id": speaker_id,
                    "subject": subject,
                    "audio_reference": audio,
                }
            )
        return parsed

    def normalize_detailed_timeline(self, detailed, source_start, duration, path):
        markers = list(SHOT_MARKER.finditer(detailed))
        timed = []
        for marker in markers[1:]:
            if marker.group(2) is None:
                continue
            timed.append(
                int(marker.group(2)) * 60
                + int(marker.group(3))
                + int(marker.group(4)) / 1000
            )
        if not timed or source_start <= 0 or not any(value >= duration for value in timed):
            return detailed
        if not all(source_start < value < source_start + duration for value in timed):
            return detailed

        index = 0
        def replace(marker):
            nonlocal index
            index += 1
            if index == 1 or marker.group(2) is None:
                return marker.group(0)
            absolute = (
                int(marker.group(2)) * 60
                + int(marker.group(3))
                + int(marker.group(4)) / 1000
            )
            relative = absolute - source_start
            minutes = int(relative // 60)
            seconds = relative - minutes * 60
            return f"[Shot {marker.group(1)}] At {minutes:02d}:{seconds:06.3f},"

        self.warnings.append(f"{path} 已将全片绝对镜头时间换算为本段相对时间")
        return SHOT_MARKER.sub(replace, detailed)

    def parse_definitions(self, definitions):
        if not isinstance(definitions, list):
            self.errors.append("global.reference_definitions 必须是数组")
            return
        for index, item in enumerate(definitions):
            path = f"global.reference_definitions[{index}]"
            if not isinstance(item, dict):
                self.errors.append(f"{path} 必须是JSON对象")
                continue
            tag = self.nonempty_string(item.get("tag"), f"{path}.tag")
            definition = self.nonempty_string(item.get("definition"), f"{path}.definition")
            mode = self.nonempty_string(item.get("retention_mode"), f"{path}.retention_mode")
            detail = self.nonempty_string(item.get("retention_detail"), f"{path}.retention_detail")
            if tag and not REFERENCE_TAG.fullmatch(tag):
                self.errors.append(f"{path}.tag 不是有效H3引用标签：{tag}")
            if tag in self.definitions:
                self.errors.append(f"检测到重复引用定义：{tag}")
            allowed = AUDIO_RETENTION_MODES if tag.startswith("<Audio ") else VISIBLE_RETENTION_MODES
            if mode and mode not in allowed:
                self.errors.append(f"{path}.retention_mode 与引用类型不匹配：{mode}")
            if tag:
                self.definitions[tag] = {
                    "definition": definition,
                    "retention_mode": mode,
                    "retention_detail": detail,
                }

    def parse_usage(self, usage, path):
        if not isinstance(usage, dict):
            self.errors.append(f"{path} 必须是JSON对象")
            return {}
        parsed = {}
        for tag, item in usage.items():
            usage_path = f"{path}[{tag}]"
            if tag not in self.definitions:
                self.errors.append(f"{usage_path} 引用了未定义标签")
                continue
            if not isinstance(item, dict):
                self.errors.append(f"{usage_path} 必须是JSON对象")
                continue
            locations = self.nonempty_string(item.get("locations"), f"{usage_path}.locations")
            detail = item.get("detail", "")
            if not isinstance(detail, str):
                self.errors.append(f"{usage_path}.detail 必须是字符串")
                detail = ""
            mode = item.get("retention_mode", self.definitions[tag]["retention_mode"])
            allowed = AUDIO_RETENTION_MODES if tag.startswith("<Audio ") else VISIBLE_RETENTION_MODES
            if mode not in allowed:
                self.errors.append(f"{usage_path}.retention_mode 与引用类型不匹配：{mode}")
            parsed[tag] = {
                "locations": locations,
                "detail": detail.strip() or self.definitions[tag]["retention_detail"],
                "retention_mode": mode,
            }
        return parsed

    def validate_detailed_description(self, detailed, path, duration, usage):
        markers = list(SHOT_MARKER.finditer(detailed))
        if not markers:
            self.errors.append(f"{path} 必须包含 [Shot 1]")
            return

        for position, marker in enumerate(markers, start=1):
            number = int(marker.group(1))
            timestamp = marker.group(2)
            if number != position:
                self.errors.append(
                    f"{path} 的镜头编号必须从1连续递增，"
                    f"第{position}个标签实际为 [Shot {number}]"
                )
            if position == 1:
                if timestamp is not None:
                    self.errors.append(f"{path} 的 [Shot 1] 不得带时间")
                continue
            if timestamp is None:
                self.errors.append(f"{path} 的 [Shot {number}] 必须带 At MM:SS.mmm 时间")

        timed_markers = []
        for marker in markers[1:]:
            if marker.group(2) is None:
                continue
            seconds = (
                int(marker.group(2)) * 60
                + int(marker.group(3))
                + int(marker.group(4)) / 1000
            )
            timed_markers.append(seconds)
            if seconds <= 0 or seconds >= duration:
                self.errors.append(
                    f"{path} 的 [Shot {marker.group(1)}] 时间"
                    f" {duration_label(seconds)}秒必须位于当前分段内"
                )
        if any(current <= previous for previous, current in zip(timed_markers, timed_markers[1:])):
            self.errors.append(f"{path} 的后续镜头时间必须严格递增")

        if UNLABELED_CUT.search(detailed):
            self.errors.append(
                f"{path} 检测到没有新 [Shot N] 标签的切镜或返回镜头描述"
            )

        raw_dialogues = list(ANY_DIALOGUE_TAG.finditer(detailed))
        valid_dialogues = list(DIALOGUE_TAG.finditer(detailed))
        if len(raw_dialogues) != len(valid_dialogues):
            self.errors.append(
                f"{path} 的对白必须使用 <d>[Language] 对白</d> 格式，语言标签后保留空格"
            )
        for dialogue in valid_dialogues:
            prefix = detailed[max(0, dialogue.start() - 120):dialogue.start()]
            speaker = re.search(
                r"(<Subject [1-9]\d*>) \((S\d+)\) says\s*$", prefix
            )
            if speaker is None:
                self.errors.append(
                    f"{path} 的每条对白前必须紧邻完整的 <Subject N> (Sx) says"
                )
                continue
            subject, speaker_id = speaker.group(1), speaker.group(2)
            if self.speaker_ids and speaker_id not in self.speaker_ids:
                self.errors.append(
                    f"{path} 的对白使用了未在 speaker_map 定义的 {speaker_id}"
                )
            expected_subject = self.speaker_subjects.get(speaker_id)
            if expected_subject and subject != expected_subject:
                self.errors.append(
                    f"{path} 的 {speaker_id} 必须由 {expected_subject} 发声，实际为 {subject}"
                )

        for tag, item in usage.items():
            if tag not in detailed:
                self.errors.append(
                    f"{path} 必须在实际使用位置明确写出引用标签 {tag}"
                )
                continue
            location_shots = {
                int(number)
                for number in re.findall(r"\[Shot (\d+)\]", item["locations"])
            }
            for shot_number in sorted(location_shots):
                if shot_number < 1 or shot_number > len(markers):
                    self.errors.append(
                        f"{path} 的 {tag} 引用了不存在的 [Shot {shot_number}]"
                    )
                    continue
                start = markers[shot_number - 1].start()
                end = markers[shot_number].start() if shot_number < len(markers) else len(detailed)
                if tag not in detailed[start:end]:
                    self.errors.append(
                        f"{path} 的 {tag} 声明用于 [Shot {shot_number}]，"
                        "但该镜头正文没有写出此标签"
                    )

    def parse_spatial_state(self, value, path):
        if value is None and not self.require_spatial:
            return None
        if not isinstance(value, dict):
            self.errors.append(f"{path} 必须是JSON对象")
            value = {}
        camera_state = self.nonempty_string(value.get("camera_state"), f"{path}.camera_state")
        camera_anchor = None
        if self.require_screen_lock or value.get("camera_anchor") is not None:
            camera_anchor = self.nonempty_string(
                value.get("camera_anchor"), f"{path}.camera_anchor"
            )
            if camera_anchor not in self.allowed_camera_anchors:
                self.errors.append(f"{path}.camera_anchor 不属于允许机位")
        states = value.get("subject_states")
        if not isinstance(states, list):
            self.errors.append(f"{path}.subject_states 必须是数组")
            states = []
        parsed = []
        seen = set()
        for index, item in enumerate(states):
            item_path = f"{path}.subject_states[{index}]"
            if not isinstance(item, dict):
                self.errors.append(f"{item_path} 必须是JSON对象")
                continue
            subject = self.nonempty_string(item.get("subject"), f"{item_path}.subject")
            anchor = self.nonempty_string(item.get("anchor"), f"{item_path}.anchor")
            position = self.nonempty_string(item.get("position"), f"{item_path}.position")
            facing = self.nonempty_string(item.get("facing"), f"{item_path}.facing")
            posture = self.nonempty_string(item.get("posture"), f"{item_path}.posture")
            gaze = self.nonempty_string(item.get("gaze"), f"{item_path}.gaze")
            held_objects = item.get("held_objects")
            if not isinstance(held_objects, list) or any(not isinstance(name, str) for name in held_objects):
                self.errors.append(f"{item_path}.held_objects 必须是字符串数组")
                held_objects = []
            if subject not in self.definitions:
                self.errors.append(f"{item_path}.subject 引用了未定义标签")
            if anchor not in self.spatial_anchors:
                self.errors.append(f"{item_path}.anchor 引用了未定义空间锚点")
            if subject in seen:
                self.errors.append(f"{item_path}.subject 重复：{subject}")
            seen.add(subject)
            parsed.append({
                "subject": subject,
                "anchor": anchor,
                "position": position,
                "facing": facing,
                "posture": posture,
                "gaze": gaze,
                "held_objects": sorted(name.strip() for name in held_objects if name.strip()),
            })
        missing = sorted(self.fixed_spatial_subjects - seen)
        if missing:
            self.errors.append(f"{path}.subject_states 缺少固定人物：{missing}")
        return {
            "camera_anchor": camera_anchor,
            "camera_state": camera_state,
            "subject_states": sorted(parsed, key=lambda item: item["subject"]),
        }

    @staticmethod
    def _spatial_subject_map(state):
        if not state:
            return None
        return {item["subject"]: item for item in state["subject_states"]}

    def validate_spatial_continuity(self, segments):
        for previous, current in zip(segments, segments[1:]):
            ending = self._spatial_subject_map(previous.get("ending_spatial_state"))
            opening = self._spatial_subject_map(current.get("opening_spatial_state"))
            if ending is not None and opening is not None and ending != opening:
                self.errors.append(
                    f"分段{previous['index']} ending_spatial_state 与"
                    f"分段{current['index']} opening_spatial_state 的人物空间状态不一致"
                )

    def parse_shot_plan(self, value, path, detailed, duration):
        if value is None and not self.require_camera_grammar:
            return []
        if not isinstance(value, list):
            self.errors.append(f"{path} 必须是数组")
            value = []
        markers = list(SHOT_MARKER.finditer(detailed))
        minimum_shots, maximum_shots = CAMERA_EDITING_PROFILES.get(
            self.camera_editing_profile, (2, 4)
        )
        if self.require_camera_grammar and not minimum_shots <= len(value) <= maximum_shots:
            self.errors.append(
                f"{path} 在 {self.camera_editing_profile} 模式下必须包含"
                f"{minimum_shots}至{maximum_shots}个Shot"
            )
        if len(value) != len(markers):
            self.errors.append(
                f"{path} 数量必须与 detailed_description 的Shot数量一致"
            )
        parsed = []
        for index, item in enumerate(value, 1):
            item_path = f"{path}[{index - 1}]"
            if not isinstance(item, dict):
                self.errors.append(f"{item_path} 必须是JSON对象")
                continue
            shot_number = item.get("shot_number")
            if shot_number != index:
                self.errors.append(f"{item_path}.shot_number 必须为 {index}")
            start_seconds = self.nonnegative_number(
                item.get("start_seconds"), f"{item_path}.start_seconds"
            )
            camera_anchor = self.nonempty_string(
                item.get("camera_anchor"), f"{item_path}.camera_anchor"
            )
            framing = self.nonempty_string(item.get("framing"), f"{item_path}.framing")
            movement = self.nonempty_string(item.get("movement"), f"{item_path}.movement")
            subjects = item.get("subjects")
            if not isinstance(subjects, list) or not subjects:
                self.errors.append(f"{item_path}.subjects 必须是非空数组")
                subjects = []
            elif any(subject not in self.definitions for subject in subjects):
                self.errors.append(f"{item_path}.subjects 引用了未定义标签")
            cut_trigger = self.nonempty_string(
                item.get("cut_trigger"), f"{item_path}.cut_trigger"
            )
            narrative_purpose = self.nonempty_string(
                item.get("narrative_purpose"), f"{item_path}.narrative_purpose"
            )
            if camera_anchor not in self.allowed_camera_anchors:
                self.errors.append(f"{item_path}.camera_anchor 不属于允许机位")
            if framing not in ALLOWED_CAMERA_FRAMINGS:
                self.errors.append(f"{item_path}.framing 不受支持：{framing}")
            if movement not in self.camera_movements:
                self.errors.append(f"{item_path}.movement 不在全片运镜库：{movement}")
            expected_start = 0.0
            if index > 1 and index <= len(markers):
                marker = markers[index - 1]
                if marker.group(2) is not None:
                    expected_start = (
                        int(marker.group(2)) * 60
                        + int(marker.group(3))
                        + int(marker.group(4)) / 1000
                    )
            if abs(start_seconds - expected_start) > 0.05:
                self.errors.append(
                    f"{item_path}.start_seconds 必须与 [Shot {index}] 时间一致"
                )
            if start_seconds >= duration:
                self.errors.append(f"{item_path}.start_seconds 必须位于分段时长内")
            parsed.append({
                "shot_number": shot_number,
                "start_seconds": start_seconds,
                "camera_anchor": camera_anchor,
                "framing": framing,
                "movement": movement,
                "subjects": subjects,
                "cut_trigger": cut_trigger,
                "narrative_purpose": narrative_purpose,
            })
        if self.require_camera_grammar and parsed:
            if parsed[0]["camera_anchor"] != self.baseline_camera_anchor:
                self.errors.append(f"{path}[0].camera_anchor 必须使用全片基准机位")
            if len(parsed) > 1 and len({item["camera_anchor"] for item in parsed}) < 2:
                self.errors.append(f"{path} 每段至少使用2个同侧机位")
            if len(parsed) > 1 and len({item["framing"] for item in parsed}) < 2:
                self.errors.append(f"{path} 每段至少使用2种景别")
            if (
                self.camera_editing_profile in {"balanced", "dynamic"}
                and not any(item["movement"] != "static" for item in parsed)
            ):
                self.errors.append(f"{path} 每段至少需要1个非静态运镜")
            minimum_duration = CAMERA_MINIMUM_SHOT_DURATION[self.camera_editing_profile]
            shot_durations = []
            for index, item in enumerate(parsed):
                end_seconds = (
                    parsed[index + 1]["start_seconds"]
                    if index + 1 < len(parsed)
                    else duration
                )
                shot_duration = end_seconds - item["start_seconds"]
                shot_durations.append(shot_duration)
                if shot_duration + 0.05 < minimum_duration:
                    self.errors.append(
                        f"{path}[{index}].shot_duration 不得少于"
                        f"{duration_label(minimum_duration)}秒"
                    )
            if (
                self.camera_editing_profile in {"restrained", "balanced"}
                and len(shot_durations) >= 3
                and max(shot_durations) - min(shot_durations) <= 0.1
            ):
                self.errors.append(f"{path} 不得把分段机械等分为等时长镜头")
        return parsed

    def validate_camera_variety(self, segments):
        if not self.require_camera_grammar:
            return
        previous_signature = None
        for segment in segments:
            signature = tuple(
                item["movement"]
                for item in segment.get("shot_plan", [])
                if item["movement"] != "static"
            )
            if (
                self.camera_editing_profile in {"balanced", "dynamic"}
                and signature
                and signature == previous_signature
            ):
                self.warnings.append(
                    f"分段{segment['index']}与前一段重复完全相同的运镜组合，请确认是有意的风格重复"
                )
            previous_signature = signature

    def parse_segment(self, segment, position):
        path = f"segments[{position - 1}]"
        if not isinstance(segment, dict):
            self.errors.append(f"{path} 必须是JSON对象")
            return None
        index = segment.get("index")
        if isinstance(index, bool) or not isinstance(index, int):
            self.errors.append(f"{path}.index 必须是整数")
            index = 0
        elif index != position:
            self.errors.append(f"{path}.index 应为连续编号 {position}，实际为 {index}")
        source_start = self.nonnegative_number(
            segment.get("source_start_seconds"), f"{path}.source_start_seconds"
        )
        source_end = self.positive_number(
            segment.get("source_end_seconds"), f"{path}.source_end_seconds"
        )
        duration = self.positive_number(segment.get("duration_seconds"), f"{path}.duration_seconds", 15)
        source_duration = source_end - source_start
        if source_end <= source_start:
            self.errors.append(f"{path} 的源视频结束时间必须晚于开始时间")
        elif abs(source_duration - duration) > 0.05:
            self.errors.append(
                f"{path}.duration_seconds 与源视频区间不一致："
                f"{duration_label(duration)}秒 != {duration_label(source_duration)}秒"
            )
        summary = self.nonempty_string(segment.get("summary"), f"{path}.summary")
        if summary.startswith("["):
            self.errors.append(f"{path}.summary 只写摘要正文，不要重复任务类型前缀")
        detailed = self.nonempty_string(
            segment.get("detailed_description"), f"{path}.detailed_description"
        )
        detailed = re.sub(r"\[/([A-Za-z][A-Za-z -]*)\](?=</d>)", "", detailed)
        detailed = self.normalize_detailed_timeline(
            detailed, source_start, duration, f"{path}.detailed_description"
        )
        if self.require_strict_boundary and position > 1:
            markers = list(SHOT_MARKER.finditer(detailed))
            if markers:
                first_end = markers[1].start() if len(markers) > 1 else len(detailed)
                if PRECOMPLETED_BOUNDARY_ACTION.search(detailed[markers[0].start():first_end]):
                    self.errors.append(
                        f"{path}.detailed_description 的 [Shot 1] 在第一帧前偷跳了边界动作"
                    )
        usage = self.parse_usage(
            segment.get("reference_usage", {}), f"{path}.reference_usage"
        )
        opening_spatial_state = self.parse_spatial_state(
            segment.get("opening_spatial_state"), f"{path}.opening_spatial_state"
        )
        ending_spatial_state = self.parse_spatial_state(
            segment.get("ending_spatial_state"), f"{path}.ending_spatial_state"
        )
        shot_plan = self.parse_shot_plan(
            segment.get("shot_plan"), f"{path}.shot_plan", detailed, duration
        )
        if self.require_screen_lock and opening_spatial_state:
            if opening_spatial_state["camera_anchor"] != self.baseline_camera_anchor:
                self.errors.append(
                    f"{path}.opening_spatial_state.camera_anchor 必须使用全片基准机位"
                )
            if opening_spatial_state["camera_state"] != self.segment_opening_composition:
                self.errors.append(
                    f"{path}.opening_spatial_state.camera_state 必须逐字复制统一开场构图"
                )
        spatial_transition = None
        if self.require_spatial or segment.get("spatial_transition") is not None:
            spatial_transition = self.nonempty_string(
                segment.get("spatial_transition"), f"{path}.spatial_transition"
            )
        if detailed:
            self.validate_detailed_description(
                detailed, f"{path}.detailed_description", duration, usage
            )
        return {
            "index": index,
            "source_start_seconds": source_start,
            "source_end_seconds": source_end,
            "duration_seconds": duration,
            "summary": summary,
            "detailed_description": detailed,
            "opening_state": self.nonempty_string(segment.get("opening_state"), f"{path}.opening_state"),
            "ending_state": self.nonempty_string(segment.get("ending_state"), f"{path}.ending_state"),
            "opening_spatial_state": opening_spatial_state,
            "ending_spatial_state": ending_spatial_state,
            "spatial_transition": spatial_transition,
            "shot_plan": shot_plan,
            "overall_soundscape": self.nonempty_string(
                segment.get("overall_soundscape"), f"{path}.overall_soundscape"
            ),
            "non_diegetic_music": self.nonempty_string(
                segment.get("non_diegetic_music"), f"{path}.non_diegetic_music"
            ),
            "reference_usage": usage,
        }

    def validate_source_timeline(self, segments, target_start, target_end):
        if not segments:
            return
        tolerance = 0.05
        if abs(segments[0]["source_start_seconds"] - target_start) > tolerance:
            self.errors.append("第1段的 source_start_seconds 必须等于目标范围起点")
        for previous, current in zip(segments, segments[1:]):
            gap = current["source_start_seconds"] - previous["source_end_seconds"]
            if abs(gap) > tolerance:
                relation = "空隙" if gap > 0 else "重叠"
                self.errors.append(
                    f"分段{previous['index']}与分段{current['index']}的源视频区间存在"
                    f"{duration_label(abs(gap))}秒{relation}"
                )
        if target_end and abs(segments[-1]["source_end_seconds"] - target_end) > tolerance:
            self.errors.append(
                "最后一段没有覆盖到目标范围终点："
                f"{duration_label(segments[-1]['source_end_seconds'])}秒 != "
                f"{duration_label(target_end)}秒"
            )

    def validate_standard_segments(self, segments, target_start, target_end, target_duration):
        if not self.require_standard_segments or not target_duration:
            return
        tolerance = 0.05
        if self.require_fixed_segments:
            expected_count = round(target_duration / 15)
            if abs(target_duration - expected_count * 15) > tolerance:
                self.errors.append("3.5目标总时长必须是15秒的整数倍")
            if len(segments) != expected_count:
                self.errors.append(
                    f"3.5固定分段数必须为 {expected_count}，实际为 {len(segments)}"
                )
            for index, segment in enumerate(segments):
                expected_start = target_start + index * 15
                expected_end = expected_start + 15
                if abs(segment["source_start_seconds"] - expected_start) > tolerance:
                    self.errors.append(
                        f"分段{segment['index']}起点必须为{duration_label(expected_start)}秒"
                    )
                if abs(segment["duration_seconds"] - 15) > tolerance:
                    self.errors.append(
                        f"分段{segment['index']}必须严格为15秒，实际为"
                        f"{duration_label(segment['duration_seconds'])}秒"
                    )
                if abs(segment["source_end_seconds"] - expected_end) > tolerance:
                    self.errors.append(
                        f"分段{segment['index']}终点必须为{duration_label(expected_end)}秒"
                    )
            return
        expected_count = math.ceil(target_duration / 15)
        if len(segments) != expected_count:
            self.errors.append(
                f"3.4标准分段数必须为 ceil({duration_label(target_duration)} / 15) "
                f"= {expected_count}，实际为 {len(segments)}"
            )
        for index, segment in enumerate(segments):
            expected_start = target_start + index * 15
            remaining = target_end - expected_start
            expected_duration = min(15.0, max(0.0, remaining))
            expected_end = expected_start + expected_duration
            if abs(segment["source_start_seconds"] - expected_start) > tolerance:
                self.errors.append(
                    f"分段{segment['index']}起点必须为{duration_label(expected_start)}秒"
                )
            if abs(segment["duration_seconds"] - expected_duration) > tolerance:
                label = "15秒" if index < expected_count - 1 or expected_duration == 15 else "真实余数"
                self.errors.append(
                    f"分段{segment['index']}必须使用{label}，实际为"
                    f"{duration_label(segment['duration_seconds'])}秒"
                )
            if abs(segment["source_end_seconds"] - expected_end) > tolerance:
                self.errors.append(
                    f"分段{segment['index']}终点必须为{duration_label(expected_end)}秒"
                )

    def reconcile_duration(self, segments, target_duration, total_duration):
        difference = round(target_duration - total_duration, 6)
        if abs(difference) <= 0.05:
            return target_duration

        tolerance = min(3.0, max(0.5, target_duration * 0.01))
        if abs(difference) > tolerance:
            self.errors.append(
                "分段时长总和与目标总时长不一致："
                f"{duration_label(total_duration)}秒 != {duration_label(target_duration)}秒"
            )
            return total_duration

        remaining = difference
        for segment in reversed(segments):
            if remaining > 0:
                adjustment = min(remaining, 15.0 - segment["duration_seconds"])
            else:
                adjustment = max(remaining, 0.1 - segment["duration_seconds"])
            segment["duration_seconds"] = round(segment["duration_seconds"] + adjustment, 6)
            remaining = round(remaining - adjustment, 6)
            if abs(remaining) <= 0.000001:
                break

        if abs(remaining) > 0.000001:
            self.errors.append(
                "无法在0.1至15秒范围内自动校正分段总时长："
                f"仍相差{duration_label(abs(remaining))}秒"
            )
            return total_duration

        self.warnings.append(
            "已自动校正轻微时长加总偏差："
            f"{duration_label(total_duration)}秒 -> {duration_label(target_duration)}秒"
        )
        return target_duration

    def parse(self):
        if not isinstance(self.data, dict):
            raise ValueError("精简分段数据的顶层必须是JSON对象")
        (
            target_duration,
            target_start,
            target_end,
            task_types,
            continuity,
            output_language,
            spatial_layout,
            relationships,
            speaker_map,
        ) = self.parse_global()
        source_segments = self.data.get("segments")
        if not isinstance(source_segments, list) or not source_segments:
            self.errors.append("segments 必须是非空数组")
            source_segments = []
        segments = [
            parsed
            for position, segment in enumerate(source_segments, start=1)
            if (parsed := self.parse_segment(segment, position)) is not None
        ]
        self.validate_source_timeline(segments, target_start, target_end)
        self.validate_standard_segments(
            segments, target_start, target_end, target_duration
        )
        self.validate_spatial_continuity(segments)
        self.validate_camera_variety(segments)
        total_duration = sum(segment["duration_seconds"] for segment in segments)
        if target_duration:
            total_duration = self.reconcile_duration(
                segments, target_duration, total_duration
            )
        if self.errors:
            raise ValueError("精简H3分段数据校验失败：\n- " + "\n- ".join(self.errors))
        return {
            "task_types": task_types,
            "target_duration_seconds": target_duration,
            "target_start_seconds": target_start,
            "target_end_seconds": target_end,
            "continuity_context": continuity,
            "output_language": output_language,
            "spatial_layout": spatial_layout,
            "reference_definitions": self.definitions,
            "character_relationships": relationships,
            "speaker_map": speaker_map,
            "segments": segments,
            "total_duration_seconds": total_duration,
            "warnings": self.warnings,
            "standard_segment_duration": self.require_standard_segments,
        }


def parse_compact_h3_plan(text):
    normalized = _strip_json_fence(text)
    try:
        data = json.loads(normalized)
    except json.JSONDecodeError as error:
        preview = re.sub(r"\s+", " ", normalized).strip()[:200] or "[empty response]"
        raise ValueError(
            f"精简分段数据不是有效JSON：第{error.lineno}行第{error.colno}列，"
            f"{error.msg}；响应开头：{preview}"
        ) from error
    data = _normalize_output_language(data)
    data = _normalize_compact_references(data)
    data = _normalize_speaker_order(data)
    data = _normalize_usage_locations(data)
    data = _normalize_camera_grammar_usage(data)
    return CompactH3PlanParser(data).parse()
