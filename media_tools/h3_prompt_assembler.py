from .h3_plan import duration_label, parse_compact_h3_plan


def _format_subject_state(item, zh=False):
    objects = ", ".join(item["held_objects"]) or "none"
    if zh:
        objects = "、".join(item["held_objects"]) or "无"
        return (
            f"{item['subject']}：锚点={item['anchor']}；位置={item['position']}；"
            f"朝向={item['facing']}；姿势={item['posture']}；视线={item['gaze']}；"
            f"手持道具={objects}"
        )
    return (
        f"{item['subject']}: anchor={item['anchor']}; position={item['position']}; "
        f"facing={item['facing']}; posture={item['posture']}; gaze={item['gaze']}; "
        f"held_objects={objects}"
    )


def _spatial_lines(plan, segment):
    layout = plan.get("spatial_layout")
    if not layout:
        return []
    zh = plan.get("output_language") == "zh-CN"
    labels = {
        "coordinate": "空间坐标系" if zh else "Spatial coordinate system",
        "anchors": "环境锚点" if zh else "Environment anchors",
        "positions": "固定人物位置" if zh else "Fixed subject positions",
        "baseline": "摄影机基线" if zh else "Camera baseline",
        "direction": "屏幕方向规则" if zh else "Screen-direction rule",
        "handoff": "关键帧衔接" if zh else "Keyframe handoff",
        "baseline_anchor": "基准摄影机锚点" if zh else "Baseline camera anchor",
        "allowed_anchors": "允许摄影机锚点" if zh else "Allowed camera anchors",
        "screen_order": "基准画面从左到右顺序" if zh else "Baseline screen order from left to right",
        "opening_composition": "强制分段开场构图" if zh else "Mandatory segment opening composition",
        "opening_anchor": "开场摄影机锚点" if zh else "Opening camera anchor",
        "opening_camera": "开场摄影机状态" if zh else "Opening camera state",
        "opening_subjects": "开场人物状态" if zh else "Opening subject states",
        "transition": "本段空间变化" if zh else "Spatial transition in this segment",
        "ending_anchor": "结束摄影机锚点" if zh else "Ending camera anchor",
        "ending_camera": "结束摄影机状态" if zh else "Ending camera state",
        "ending_subjects": "结束人物状态" if zh else "Ending subject states",
    }
    separator = "：" if zh else ": "
    lines = [
        f"{labels['coordinate']}{separator}{layout['coordinate_system']}",
        f"{labels['anchors']}{separator}" + " | ".join(
            f"{item['anchor_id']}={item['description']}"
            for item in layout["environment_anchors"]
        ),
        f"{labels['positions']}{separator}" + " | ".join(
            (
                f"{item['subject']} 位于 {item['anchor']}（{item['position']}），朝向 {item['facing']}"
                if zh
                else f"{item['subject']} at {item['anchor']} ({item['position']}), facing {item['facing']}"
            )
            for item in layout["fixed_subject_positions"]
        ),
        f"{labels['baseline']}{separator}{layout['camera_baseline']}",
        f"{labels['direction']}{separator}{layout['screen_direction_rule']}",
        f"{labels['handoff']}{separator}{layout['keyframe_handoff']}",
    ]
    if layout.get("baseline_camera_anchor"):
        lines.extend([
            f"{labels['baseline_anchor']}{separator}{layout['baseline_camera_anchor']}",
            f"{labels['allowed_anchors']}{separator}" + ", ".join(layout["allowed_camera_anchors"]),
            f"{labels['screen_order']}{separator}"
            + " -> ".join(layout["baseline_screen_order"]),
            f"{labels['opening_composition']}{separator}{layout['segment_opening_composition']}",
        ])
    grammar = layout.get("camera_grammar")
    if grammar:
        lines.extend([
            ("摄影机轴线半区：" if zh else "Camera axis side: ")
            + grammar["axis_side"],
            ("同侧安全弧线：" if zh else "Same-side safe arc: ")
            + grammar["safe_arc"],
            ("剪辑风格：" if zh else "Editing profile: ")
            + grammar["editing_profile"],
            ("允许运镜库：" if zh else "Movement palette: ")
            + ", ".join(grammar["movement_palette"]),
            ("叙事切镜触发：" if zh else "Narrative cut triggers: ")
            + " | ".join(grammar["cut_triggers"]),
            ("同侧镜头机位库：" if zh else "Same-side shot palette: ")
            + " | ".join(
                f"{item['anchor_id']}[{', '.join(item['framing_options'])}; {item['lens']}]: {item['description']}"
                for item in grammar["shot_palette"]
            ),
        ])
    opening = segment.get("opening_spatial_state")
    ending = segment.get("ending_spatial_state")
    if opening:
        if opening.get("camera_anchor"):
            lines.append(f"{labels['opening_anchor']}{separator}{opening['camera_anchor']}")
        lines.append(f"{labels['opening_camera']}{separator}{opening['camera_state']}")
        lines.append(f"{labels['opening_subjects']}{separator}" + " | ".join(
            _format_subject_state(item, zh) for item in opening["subject_states"]
        ))
        lines.append(
            "强制第一帧规则：第一帧必须逐字呈现上述开场人物状态；不得在第一帧前预先完成、暗示或改写任何移动、视线、姿势或道具变化。"
            if zh
            else "Mandatory first-frame rule: Frame 1 must show the Opening subject states exactly as written. Do not pre-complete, imply, or paraphrase any movement, gaze change, posture change, or prop action before frame 1."
        )
    if segment.get("spatial_transition"):
        lines.append(f"{labels['transition']}{separator}{segment['spatial_transition']}")
    if ending:
        if ending.get("camera_anchor"):
            lines.append(f"{labels['ending_anchor']}{separator}{ending['camera_anchor']}")
        lines.append(f"{labels['ending_camera']}{separator}{ending['camera_state']}")
        lines.append(f"{labels['ending_subjects']}{separator}" + " | ".join(
            _format_subject_state(item, zh) for item in ending["subject_states"]
        ))
        lines.append(
            "强制边界衔接：下一段必须先从上述结束人物状态开始，再发生任何新的可见动作。"
            if zh
            else "Mandatory boundary handoff: The next segment must begin from these exact Ending subject states before any new visible action occurs."
        )
    return lines


def _shot_plan_lines(plan, segment):
    shot_plan = segment.get("shot_plan") or []
    if not shot_plan:
        return []
    zh = plan.get("output_language") == "zh-CN"
    lines = ["镜头执行计划：" if zh else "Shot execution plan:"]
    for item in shot_plan:
        start = duration_label(item["start_seconds"])
        subjects = ", ".join(item["subjects"])
        if zh:
            lines.append(
                f"[Shot {item['shot_number']}] 起始={start}秒；机位={item['camera_anchor']}；"
                f"景别={item['framing']}；运镜={item['movement']}；主体={subjects}；"
                f"切镜触发={item['cut_trigger']}；叙事目的={item['narrative_purpose']}"
            )
        else:
            lines.append(
                f"[Shot {item['shot_number']}] start={start}s; anchor={item['camera_anchor']}; "
                f"framing={item['framing']}; movement={item['movement']}; subjects={subjects}; "
                f"cut trigger={item['cut_trigger']}; narrative purpose={item['narrative_purpose']}"
            )
    return lines


def _compact_spatial_lock(plan):
    layout = plan.get("spatial_layout")
    if not layout:
        return None
    zh = plan.get("output_language") == "zh-CN"
    positions = ("；" if zh else "; ").join(
        f"{item['subject']}{item['position']}"
        for item in layout["fixed_subject_positions"]
    )
    order = " -> ".join(layout["baseline_screen_order"])
    if zh:
        return (
            f"连续性：{positions}；基准画面左到右={order}；"
            "摄影机始终保持在场景同一侧，不得越轴、镜像、换位或瞬移。"
        )
    return (
        f"Continuity: {positions}; baseline screen order={order}; keep the camera "
        "on the same side of the scene; no axis crossing, mirroring, "
        "seat swapping, or teleporting."
    )


def _format_shot_lines(text):
    return text.replace(" [Shot ", "\n[Shot ")


def _segment_block(plan, segment):
    zh = plan.get("output_language") == "zh-CN"
    definitions = plan["reference_definitions"]
    usage = segment["reference_usage"]
    used_tags = set(usage)
    included_relationships = [
        item
        for item in plan.get("character_relationships", [])
        if any(subject in used_tags for subject in item["subjects"])
    ]
    definition_tags = set(used_tags)
    for item in included_relationships:
        definition_tags.update(item["subjects"])
    subject_lines = [
        f"{tag}: {definitions[tag]['definition']}"
        for tag in definitions
        if tag in definition_tags
    ]
    retention_lines = [
        f"{tag} (appears in {item['locations']}): {item['retention_mode']} - {item['detail']}"
        for tag, item in usage.items()
    ]
    detail_parts = [
        item
        for item in (
            _compact_spatial_lock(plan),
            _format_shot_lines(segment["detailed_description"]),
        )
        if item
    ]
    task_prefix = " + ".join(plan["task_types"])
    body = "\n\n".join(
        [
            "subject_definitions:\n" + ("\n".join(subject_lines) or "N/A"),
            f"summary:\n[{task_prefix}] {segment['summary']}",
            "retention_analysis:\n" + ("\n".join(retention_lines) or "N/A"),
            "detailed_description:\n" + "\n".join(detail_parts),
            "overall_soundscape:\n" + segment["overall_soundscape"],
            "non_diegetic_music:\n" + segment["non_diegetic_music"],
        ]
    )
    return body


def _validation_report(plan):
    segments = plan["segments"]
    exact_fifteen_count = sum(
        1 for segment in segments if abs(segment["duration_seconds"] - 15) < 0.001
    )
    warnings = list(plan.get("warnings", []))
    if (
        not plan.get("standard_segment_duration")
        and len(segments) >= 4
        and exact_fifteen_count / len(segments) >= 0.75
    ):
        warnings.append("多数分段恰好为15秒，请确认切点来自自然语义、动作或剪辑边界")
    lines = [
        "校验通过",
        f"分段数：{len(segments)}",
        f"目标总时长：{duration_label(plan['target_duration_seconds'])}秒",
        f"分段总时长：{duration_label(plan['total_duration_seconds'])}秒",
        f"公共引用定义：{len(plan['reference_definitions'])}个",
    ]
    lines.extend(f"警告：{warning}" for warning in warnings)
    return "\n".join(lines)


def assemble_compact_h3_plan(text):
    plan = parse_compact_h3_plan(text)
    markdown = "\n\n".join(_segment_block(plan, segment) for segment in plan["segments"])
    return markdown, _validation_report(plan), plan


class MmuuAIH3PromptAssemblerNode:
    CATEGORY = "MU/工具"
    FUNCTION = "assemble"
    RETURN_TYPES = ("STRING", "STRING", "INT", "FLOAT")
    RETURN_NAMES = ("完整H3分段提示词", "校验报告", "实际分段数", "总时长（秒）")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "精简分段JSON": ("STRING", {"forceInput": True}),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **_kwargs):
        return float("nan")

    def assemble(self, 精简分段JSON):
        markdown, report, plan = assemble_compact_h3_plan(精简分段JSON)
        return (
            markdown,
            report,
            len(plan["segments"]),
            float(plan["total_duration_seconds"]),
        )
