import importlib.util
import io
import json
from pathlib import Path
from fractions import Fraction
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import torch


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "mu_nodes_test"
spec = importlib.util.spec_from_file_location(
    PACKAGE,
    ROOT / "__init__.py",
    submodule_search_locations=[str(ROOT)],
)
plugin = importlib.util.module_from_spec(spec)
sys.modules[PACKAGE] = plugin
spec.loader.exec_module(plugin)


EXPECTED_IDS = {
    "MmuuAILLMModelNodeV001",
    "MmuuAIImageModelNodeV001",
    "MmuuAILLMModelNodeV002",
    "MmuuAIImageModelNodeV002",
    "MmuuAIGoogleImageModelNodeV001",
    "MmuuAIGeminiVideoUploadNodeV001",
    "MmuuAIGeminiVideoLLMNodeV001",
    "MmuuAIMultiImageLoaderNodeV001",
    "MmuuAIMultiImageLoaderNodeV002",
    "MmuuAIMediaParserNodeV001",
    "MmuuAIMediaParserNodeV002",
    "MmuuAIMultiVideoLoaderNodeV001",
    "MmuuAIMultiVideoLoaderNodeV002",
    "MmuuAILinkListSplitterNodeV001",
    "MmuuAIMediaUrlLoaderNodeV001",
    "MmuuAIMultiStringMergeNodeV001",
    "MmuuAIH3SystemPromptLanguageNodeV001",
    "MmuuAISegmentPromptSplitterNodeV001",
    "MmuuAITextViewerNodeV001",
    "MmuuAIH3PromptAssemblerNodeV001",
    "MmuuAIH3PlanVideoBatchNodeV001",
    "MmuuAIH3SegmentCollectorNodeV001",
    "MmuuAIVideoCompressNodeV001",
    "MmuuAIVideoClipConverterNodeV001",
    "MmuuAIAudioClipConverterNodeV001",
    "MmuuAIVideoImageConverterNodeV001",
    "MmuuAISmartVideoSegmenterNodeV001",
    "MmuuAIGetVideoSegmentNodeV001",
    "MmuuAIRHWorkflowNodeV001",
    "MmuuAIResolutionSelectorV2",
}

EXPECTED_CATEGORIES = {
    "MmuuAILLMModelNodeV001": "MU/接口",
    "MmuuAIImageModelNodeV001": "MU/接口",
    "MmuuAILLMModelNodeV002": "MU/接口",
    "MmuuAIImageModelNodeV002": "MU/接口",
    "MmuuAIGoogleImageModelNodeV001": "MU/接口",
    "MmuuAIGeminiVideoUploadNodeV001": "MU/接口",
    "MmuuAIGeminiVideoLLMNodeV001": "MU/接口",
    "MmuuAIMediaParserNodeV001": "MU/接口",
    "MmuuAIMediaParserNodeV002": "MU/接口",
    "MmuuAIRHWorkflowNodeV001": "MU/接口",
    "MmuuAIMultiStringMergeNodeV001": "MU/文本",
    "MmuuAIH3SystemPromptLanguageNodeV001": "MU/文本",
    "MmuuAITextViewerNodeV001": "MU/文本",
    "MmuuAIMultiImageLoaderNodeV001": "MU/加载",
    "MmuuAIMultiImageLoaderNodeV002": "MU/加载",
    "MmuuAIMultiVideoLoaderNodeV001": "MU/加载",
    "MmuuAIMultiVideoLoaderNodeV002": "MU/加载",
    "MmuuAIMediaUrlLoaderNodeV001": "MU/加载",
    "MmuuAIVideoCompressNodeV001": "MU/媒体处理",
    "MmuuAIVideoClipConverterNodeV001": "MU/媒体处理",
    "MmuuAIAudioClipConverterNodeV001": "MU/媒体处理",
    "MmuuAIVideoImageConverterNodeV001": "MU/媒体处理",
    "MmuuAISmartVideoSegmenterNodeV001": "MU/媒体处理",
    "MmuuAIGetVideoSegmentNodeV001": "MU/媒体处理",
    "MmuuAISegmentPromptSplitterNodeV001": "MU/工具",
    "MmuuAIH3PromptAssemblerNodeV001": "MU/工具",
    "MmuuAILinkListSplitterNodeV001": "MU/工具",
    "MmuuAIH3PlanVideoBatchNodeV001": "MU/工具",
    "MmuuAIH3SegmentCollectorNodeV001": "MU/工具",
    "MmuuAIResolutionSelectorV2": "MU/工具",
}


class MUNodeRegistryTests(unittest.TestCase):
    def test_registry_contains_only_confirmed_nodes(self):
        self.assertEqual(set(plugin.NODE_CLASS_MAPPINGS), EXPECTED_IDS)
        self.assertEqual(set(plugin.NODE_DISPLAY_NAME_MAPPINGS), EXPECTED_IDS)
        self.assertTrue(all(name.startswith("MU｜") for name in plugin.NODE_DISPLAY_NAME_MAPPINGS.values()))

    def test_node_categories_match_the_test_workflow_groups(self):
        self.assertEqual(
            {node_id: node_type.CATEGORY for node_id, node_type in plugin.NODE_CLASS_MAPPINGS.items()},
            EXPECTED_CATEGORIES,
        )

    def test_h3_system_prompt_language_selector_preserves_core_or_appends_overlay(self):
        node_type = plugin.NODE_CLASS_MAPPINGS[
            "MmuuAIH3SystemPromptLanguageNodeV001"
        ]
        node = node_type()
        schema = node_type.INPUT_TYPES()["required"]

        self.assertEqual(schema["输出语言"][0], ("英文", "中文"))
        self.assertEqual(schema["输出语言"][1]["default"], "中文")
        self.assertEqual(node.select("核心规则", "中文覆盖", "英文"), ("核心规则",))
        self.assertEqual(
            node.select("核心规则", "中文覆盖", "中文"),
            ("核心规则\n\n中文覆盖",),
        )

    def test_resolution_selector_v2_has_only_size_controls_and_outputs(self):
        node_type = plugin.NODE_CLASS_MAPPINGS["MmuuAIResolutionSelectorV2"]
        schema = node_type.INPUT_TYPES()

        self.assertEqual(tuple(schema["required"]), ("类型", "分辨率", "画面比例"))
        self.assertEqual(schema["required"]["类型"][0], ("图片", "视频"))
        self.assertEqual(node_type.RETURN_NAMES, ("宽度", "高度"))

    def test_resolution_selector_v2_uses_ordered_ratios_and_lowercase_resolutions(self):
        node_type = plugin.NODE_CLASS_MAPPINGS["MmuuAIResolutionSelectorV2"]
        schema = node_type.INPUT_TYPES()["required"]

        self.assertEqual(
            schema["画面比例"][0],
            ("1:1", "5:4", "4:5", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16", "2:1", "1:2", "21:9", "9:21"),
        )
        self.assertEqual(schema["分辨率"][0], ("1k", "2k", "4k", "6k", "8k", "480p", "720p", "1080p"))

    def test_resolution_selector_v2_calculates_image_and_video_dimensions(self):
        node = plugin.NODE_CLASS_MAPPINGS["MmuuAIResolutionSelectorV2"]()

        self.assertEqual(node.select_size("图片", "6k", "16:9"), (6144, 3456))
        self.assertEqual(node.select_size("视频", "2k", "16:9"), (2560, 1440))
        self.assertEqual(node.select_size("视频", "6k", "9:16"), (3240, 5760))

    def test_resolution_selector_v2_frontend_has_dynamic_chinese_outputs(self):
        source = (ROOT / "web" / "js" / "resolution_selector_v2_1.js").read_text(encoding="utf-8")

        self.assertIn('node.outputs[0].name = `宽度：${width}`', source)
        self.assertIn('node.outputs[1].name = `高度：${height}`', source)
        self.assertNotIn("fps", source.lower())

    def test_media_parser_exposes_attachment_inputs_and_renamed_models(self):
        node_type = plugin.NODE_CLASS_MAPPINGS["MmuuAIMediaParserNodeV001"]
        schema = node_type.INPUT_TYPES()
        self.assertEqual(
            schema["required"]["模型"][0],
            ("单个视频解析", "主页视频批量解析", "音视频转写文字（文件/URL）"),
        )
        self.assertEqual(schema["optional"]["视频文件"], ("VIDEO",))
        self.assertEqual(schema["optional"]["音频文件"], ("AUDIO",))
        self.assertNotIn("基础地址", schema["required"])

    def test_public_media_url_encodes_non_ascii_path_and_query(self):
        public_https_url = plugin.media_tools.http_client.public_https_url

        normalized = public_https_url(
            "https://example.com/视频/样例.mp4?标题=春天&token=a%2Fb",
            resolve=False,
        )

        self.assertEqual(
            normalized,
            "https://example.com/%E8%A7%86%E9%A2%91/%E6%A0%B7%E4%BE%8B.mp4?%E6%A0%87%E9%A2%98=%E6%98%A5%E5%A4%A9&token=a%2Fb",
        )

    def test_media_parser_accepts_upstream_share_link_value(self):
        node_type = plugin.NODE_CLASS_MAPPINGS["MmuuAIMediaParserNodeV001"]

        node_type._require_url("c8cn9lo1ts821qo2-zepi0p2hov5p")

        with self.assertRaisesRegex(ValueError, "媒体分享链接"):
            node_type._require_url("")

    def test_audio_attachment_is_uploaded_before_transcription(self):
        node = plugin.NODE_CLASS_MAPPINGS["MmuuAIMediaParserNodeV001"]()
        audio = {"waveform": torch.zeros((1, 1, 160)), "sample_rate": 16000}
        session = Mock()
        with patch.object(plugin.media_tools.node, "upload_transcription_file", return_value="oss://bucket/input.wav") as upload:
            source = node._transcription_input(session, "https://example.com", "secret", "", None, audio, 600)
        self.assertEqual(source, "oss://bucket/input.wav")
        self.assertEqual(upload.call_args.args[4], "input.wav")
        self.assertGreater(len(upload.call_args.args[3].getvalue()), 44)

    def test_mmuuai_media_parser_keeps_outputs_and_uses_one_platform_key(self):
        node_type = plugin.NODE_CLASS_MAPPINGS["MmuuAIMediaParserNodeV002"]
        schema = node_type.INPUT_TYPES()

        self.assertEqual(tuple(schema["required"])[:2], ("模型", "key"))
        self.assertEqual(schema["required"]["key"][1]["default"], "获取key：https://mmuu.ai")
        self.assertEqual(node_type.RETURN_NAMES, ("文本", "视频链接", "音频链接", "封面链接", "原始响应"))
        self.assertIn("上游Key兼容", plugin.NODE_DISPLAY_NAME_MAPPINGS["MmuuAIMediaParserNodeV001"])
        self.assertEqual(plugin.NODE_DISPLAY_NAME_MAPPINGS["MmuuAIMediaParserNodeV002"], "MU｜媒体解析")

    def test_mmuuai_media_parser_builds_each_model_contract(self):
        node_type = plugin.NODE_CLASS_MAPPINGS["MmuuAIMediaParserNodeV002"]
        values = {
            "媒体链接": "https://example.com/share",
            "主页解析页数": 3,
            "视频文件": None,
            "音频文件": None,
        }

        single = node_type._task_input(Mock(), {}, "单个视频解析", values)
        playlist = node_type._task_input(Mock(), {}, "主页视频批量解析", values)
        transcript = node_type._task_input(Mock(), {}, "音视频转写文字（文件/URL）", values)

        self.assertEqual(single, {"parameters": {"url": "https://example.com/share"}})
        self.assertEqual(
            playlist,
            {"parameters": {"url": "https://example.com/share", "page_count": 3}},
        )
        self.assertEqual(
            transcript,
            {"parameters": {"video_url": "https://example.com/share"}},
        )

    def test_mmuuai_media_parser_maps_normalized_result_parts(self):
        result = plugin.media_tools.mmuuai_node._result_outputs(
            {
                "text": "标题",
                "parts": [
                    {"type": "text", "text": "标题"},
                    {"type": "video", "url": "https://cdn.example/video.mp4"},
                    {"type": "audio", "url": "https://cdn.example/audio.mp3"},
                    {"type": "image", "url": "https://cdn.example/cover.jpg"},
                ],
            }
        )

        self.assertEqual(result[0], "标题")
        self.assertEqual(result[1], ["https://cdn.example/video.mp4"])
        self.assertEqual(result[2], ["https://cdn.example/audio.mp3"])
        self.assertEqual(result[3], ["https://cdn.example/cover.jpg"])

    def test_video_image_converter_has_only_two_connection_inputs(self):
        node_type = plugin.NODE_CLASS_MAPPINGS["MmuuAIVideoImageConverterNodeV001"]
        schema = node_type.INPUT_TYPES()
        self.assertEqual(set(schema["optional"]), {"视频", "图片序列"})
        self.assertEqual(node_type.RETURN_NAMES, ("视频", "图片序列"))

    def test_video_image_converter_extracts_video_components(self):
        images = torch.zeros((3, 4, 5, 3))
        audio = {"waveform": torch.zeros((1, 1, 100)), "sample_rate": 16000}
        components = SimpleNamespace(images=images, audio=audio, frame_rate=Fraction(24, 1))
        video = Mock()
        video.get_components.return_value = components
        video.get_bit_depth.return_value = 10
        node = plugin.NODE_CLASS_MAPPINGS["MmuuAIVideoImageConverterNodeV001"]()

        result = node.convert(视频=video, 图片生成视频帧率=30.0, 图片生成视频位深=8)

        self.assertIs(result[0], video)
        self.assertIs(result[1], images)

    def test_video_image_converter_rebuilds_with_source_audio_and_fps(self):
        source_images = torch.zeros((3, 4, 5, 3))
        edited_images = torch.ones((3, 4, 5, 3))
        audio = {"waveform": torch.zeros((1, 1, 100)), "sample_rate": 16000}
        video = Mock()
        video.get_components.return_value = SimpleNamespace(
            images=source_images,
            audio=audio,
            frame_rate=Fraction(25, 1),
        )
        video.get_bit_depth.return_value = 8
        node = plugin.NODE_CLASS_MAPPINGS["MmuuAIVideoImageConverterNodeV001"]()
        module = plugin.media_tools.video_image_converter

        with patch.object(module, "_create_video", return_value="new-video") as create:
            result = node.convert(
                视频=video,
                图片序列=edited_images,
                图片生成视频帧率=30.0,
                图片生成视频位深=10,
            )

        self.assertEqual(result[0], "new-video")
        self.assertIs(result[1], edited_images)
        create.assert_called_once_with(edited_images, audio, 25.0, 8)

    def test_smart_video_segmenter_exposes_adjustable_duration_and_compact_bundle(self):
        node_type = plugin.NODE_CLASS_MAPPINGS["MmuuAISmartVideoSegmenterNodeV001"]
        module = plugin.media_tools.smart_video_segmenter
        with patch.object(module, "_input_videos", return_value=[""]):
            input_schema = node_type.INPUT_TYPES()
        schema = input_schema["required"]

        self.assertEqual(schema["最长时长（秒，0不限制）"][1]["default"], 15.0)
        self.assertEqual(schema["最长时长（秒，0不限制）"][1]["min"], 0.0)
        self.assertGreater(schema["最长时长（秒，0不限制）"][1]["max"], 15.0)
        self.assertEqual(schema["最短镜头（秒，0不限制）"][1]["default"], 5.0)
        self.assertEqual(schema["最短镜头（秒，0不限制）"][1]["min"], 0.0)
        self.assertNotIn("最短镜头（帧）", schema)
        self.assertEqual(schema["输出帧率"][1]["default"], 24)
        self.assertNotIn("输入图片序列帧率", schema)
        self.assertIn("输出短边尺寸（0保持原尺寸）", schema)
        self.assertNotIn("输出宽度（0保持原比例）", schema)
        self.assertNotIn("输出高度（0保持原比例）", schema)
        self.assertEqual(node_type.RETURN_TYPES, ("MU_VIDEO_SEGMENTS", "STRING", "INT"))
        self.assertEqual(node_type.RETURN_NAMES, ("切片结果", "切分报告", "片段数"))
        self.assertEqual(schema["视频URL"][1]["default"], "")
        self.assertTrue(input_schema["optional"]["上传视频"][1]["video_upload"])
        self.assertEqual(
            set(input_schema["optional"]),
            {"上传视频", "视频", "视频URL输入", "图片序列", "音频"},
        )

    def test_smart_video_segmenter_returns_compact_bundle(self):
        node = plugin.NODE_CLASS_MAPPINGS["MmuuAISmartVideoSegmenterNodeV001"]()
        module = plugin.media_tools.smart_video_segmenter
        values = {
            "视频": Mock(),
            "上传视频": "",
            "视频URL": "",
            "最长时长（秒，0不限制）": 15.0,
            "最短镜头（秒，0不限制）": 5.0,
            "切镜灵敏度（1-100）": 50,
            "输出帧率": 24,
            "输出短边尺寸（0保持原尺寸）": 0,
            "URL连接超时（秒）": 30,
            "URL等待超时（秒，0不限）": 600,
        }
        with patch.object(module, "_source_video", return_value="source"):
            with patch.object(module, "split_video", return_value=[Path("one.mp4"), Path("two.mp4")]):
                bundle, report, count = node.split(**values)

        self.assertEqual(bundle.paths, ("one.mp4", "two.mp4"))
        self.assertEqual(bundle.output_fps, 24)
        self.assertEqual(count, 2)
        self.assertIn("智能切分完成：2 段", report)

    def test_get_video_segment_uses_one_compact_bundle_input(self):
        node_type = plugin.NODE_CLASS_MAPPINGS["MmuuAIGetVideoSegmentNodeV001"]
        schema = node_type.INPUT_TYPES()["required"]
        bundle = plugin.media_tools.smart_video_segmenter.VideoSegmentBundle(("one.mp4",), 24)

        self.assertEqual(schema["切片结果"], ("MU_VIDEO_SEGMENTS",))
        self.assertEqual(node_type.RETURN_TYPES[:3], ("VIDEO", "IMAGE", "AUDIO"))
        source = (ROOT / "media_tools" / "smart_video_segmenter.py").read_text(encoding="utf-8")
        self.assertIn("ExecutionBlocker(None)", source)

    def test_smart_video_segmenter_requires_one_source_and_allows_audio_with_images(self):
        segmenter = plugin.media_tools.smart_video_segmenter

        with self.assertRaisesRegex(ValueError, "仅提供"):
            segmenter._source_video(None, "", None, None, "", "", 24, 30, 600)
        with self.assertRaisesRegex(ValueError, "仅提供"):
            segmenter._source_video(Mock(), "", Mock(), None, "", "", 24, 30, 600)
        with self.assertRaisesRegex(ValueError, "只能提供一个"):
            segmenter._source_video(None, "", None, None, "https://one", "https://two", 24, 30, 600)

    def test_smart_video_segmenter_uses_last_eligible_cut_within_each_window(self):
        segmenter = plugin.media_tools.smart_video_segmenter
        segments = segmenter._enforce_max_duration(
            boundaries=[2.0, 4.0, 6.0, 8.0, 16.0],
            duration=30.0,
            max_duration=15.0,
            min_scene_seconds=5.0,
        )

        self.assertEqual(segments, [(0.0, 8.0), (8.0, 16.0), (16.0, 30.0)])
        self.assertTrue(all(end - start <= 15.0 for start, end in segments))

    def test_smart_video_segmenter_adaptive_threshold_is_robust_to_motion(self):
        segmenter = plugin.media_tools.smart_video_segmenter

        # A moving shot can have a high, steady delta; a hard cut should still
        # clear the local threshold instead of being suppressed by baseline * 3.5.
        threshold = segmenter._adaptive_scene_threshold(0.166, [0.09, 0.10, 0.11, 0.10])
        self.assertLess(threshold, 0.166 + 0.03)
        self.assertEqual(
            segmenter._adaptive_scene_threshold(0.05, [0.2, 0.25, 0.2, 0.25]),
            0.28,
        )
    def test_smart_video_segmenter_ignores_a_cut_shorter_than_minimum_scene(self):
        segmenter = plugin.media_tools.smart_video_segmenter
        segments = segmenter._enforce_max_duration(
            boundaries=[2.0, 16.0],
            duration=33.0,
            max_duration=15.0,
            min_scene_seconds=5.0,
        )

        self.assertEqual(segments, [(0.0, 15.0), (15.0, 28.0), (28.0, 33.0)])

    def test_smart_video_segmenter_forces_maximum_duration_when_no_cut_exists(self):
        segmenter = plugin.media_tools.smart_video_segmenter
        segments = segmenter._enforce_max_duration(
            boundaries=[],
            duration=31.0,
            max_duration=15.0,
            min_scene_seconds=5.0,
        )

        self.assertEqual(segments, [(0.0, 15.0), (15.0, 26.0), (26.0, 31.0)])

    def test_smart_video_segmenter_uses_only_minimum_scene_when_maximum_is_zero(self):
        segmenter = plugin.media_tools.smart_video_segmenter
        segments = segmenter._enforce_max_duration(
            boundaries=[2.0, 4.0, 6.0, 8.0, 16.0],
            duration=20.0,
            max_duration=0.0,
            min_scene_seconds=5.0,
        )

        self.assertEqual(segments, [(0.0, 6.0), (6.0, 16.0), (16.0, 20.0)])

    def test_smart_video_segmenter_does_not_filter_natural_cuts_when_minimum_is_zero(self):
        segmenter = plugin.media_tools.smart_video_segmenter
        segments = segmenter._enforce_max_duration(
            boundaries=[2.0, 4.0, 6.0, 8.0],
            duration=10.0,
            max_duration=0.0,
            min_scene_seconds=0.0,
        )

        self.assertEqual(segments, [(0.0, 2.0), (2.0, 4.0), (4.0, 6.0), (6.0, 8.0), (8.0, 10.0)])

    def test_smart_video_segmenter_builds_short_edge_size_filter(self):
        segmenter = plugin.media_tools.smart_video_segmenter

        self.assertIsNone(segmenter._video_filter(0))
        self.assertEqual(
            segmenter._video_filter(720),
            "scale='if(gt(iw,ih),-2,720)':'if(gt(iw,ih),720,-2)'",
        )

    def test_multi_video_loader_has_six_video_outputs(self):
        node_type = plugin.NODE_CLASS_MAPPINGS["MmuuAIMultiVideoLoaderNodeV001"]
        module = plugin.media_tools.multi_video_loader
        with patch.object(module, "_input_videos", return_value=["", "one.mp4"]):
            schema = node_type.INPUT_TYPES()

        self.assertEqual(tuple(schema["required"]), tuple(f"视频文件{i}" for i in range(1, 7)))
        self.assertTrue(all(value[1]["video_upload"] for value in schema["required"].values()))
        self.assertEqual(node_type.RETURN_TYPES, ("VIDEO",) * 6)
        self.assertEqual(node_type.RETURN_NAMES, tuple(f"视频{i}" for i in range(1, 7)))

    def test_multi_video_loader_preserves_slots_and_skips_empty_files(self):
        node = plugin.NODE_CLASS_MAPPINGS["MmuuAIMultiVideoLoaderNodeV001"]()
        module = plugin.media_tools.multi_video_loader

        with patch.object(module, "_resolve_video", side_effect=lambda value, _label: f"C:/{value}" if value else None):
            with patch.object(module, "_video_from_file", side_effect=lambda path: f"VIDEO:{path}"):
                result = node.load(视频文件1="one.mp4", 视频文件3="three.mp4")

        self.assertEqual(
            result,
            ("VIDEO:C:/one.mp4", None, "VIDEO:C:/three.mp4", None, None, None),
        )

    def test_multi_video_loader_v2_has_fifty_video_outputs(self):
        node_type = plugin.NODE_CLASS_MAPPINGS["MmuuAIMultiVideoLoaderNodeV002"]
        schema = node_type.INPUT_TYPES()

        self.assertEqual(tuple(schema["required"]), ("视频路径",))
        self.assertEqual(node_type.RETURN_TYPES, ("VIDEO",) * 50)
        self.assertEqual(node_type.RETURN_NAMES, tuple(f"视频{i}" for i in range(1, 51)))

    def test_multi_video_loader_v2_returns_none_for_unused_outputs(self):
        node = plugin.NODE_CLASS_MAPPINGS["MmuuAIMultiVideoLoaderNodeV002"]()
        module = plugin.media_tools.multi_video_loader_v2

        with patch.object(module, "_resolve_video", side_effect=lambda value, _label: f"C:/{value}"):
            with patch.object(module, "_video_from_file", side_effect=lambda path: f"VIDEO:{path}"):
                result = node.load(视频路径="one.mp4\ntwo.mp4")

        self.assertEqual(result[:3], ("VIDEO:C:/one.mp4", "VIDEO:C:/two.mp4", None))
        self.assertEqual(result[2:], (None,) * 48)

    def test_multi_video_loader_v2_rejects_more_than_fifty_videos(self):
        node = plugin.NODE_CLASS_MAPPINGS["MmuuAIMultiVideoLoaderNodeV002"]()
        paths = "\n".join(f"video-{index}.mp4" for index in range(51))

        with self.assertRaisesRegex(ValueError, "最多只能加载50个视频"):
            node.load(视频路径=paths)

    def test_multi_video_loader_v2_frontend_uses_fixed_and_dynamic_outputs(self):
        source = (ROOT / "web" / "js" / "multi_video_loader_v2_1.js").read_text(encoding="utf-8")

        self.assertIn("const MAX_VIDEOS = 50", source)
        self.assertIn("const FIXED_OUTPUTS = 6", source)
        self.assertIn('api.fetchApi("/upload/image"', source)
        self.assertIn("Math.max(FIXED_OUTPUTS, videoCount, linkedDynamicOutput(node))", source)

    def test_multi_image_loader_has_ten_image_outputs(self):
        node_type = plugin.NODE_CLASS_MAPPINGS["MmuuAIMultiImageLoaderNodeV001"]
        module = plugin.media_tools.multi_image_loader
        with patch.object(module, "_input_images", return_value=["", "one.png"]):
            schema = node_type.INPUT_TYPES()

        self.assertEqual(tuple(schema["required"]), tuple(f"图片文件{i}" for i in range(1, 11)))
        self.assertTrue(all(value[1]["image_upload"] for value in schema["required"].values()))
        self.assertEqual(node_type.RETURN_TYPES, ("IMAGE",) * 10)
        self.assertEqual(node_type.RETURN_NAMES, tuple(f"图片{i}" for i in range(1, 11)))

    def test_multi_image_loader_preserves_slots_and_skips_empty_files(self):
        node = plugin.NODE_CLASS_MAPPINGS["MmuuAIMultiImageLoaderNodeV001"]()
        module = plugin.media_tools.multi_image_loader

        with patch.object(module, "_resolve_image", side_effect=lambda value, _label: f"C:/{value}" if value else None):
            with patch.object(module, "_load_image", side_effect=lambda value: f"IMAGE:{value}"):
                result = node.load(图片文件2="two.png", 图片文件6="six.png")

        self.assertEqual(
            result,
            (None, "IMAGE:two.png", None, None, None, "IMAGE:six.png", None, None, None, None),
        )

    def test_multi_image_loader_v2_has_fifty_image_outputs(self):
        node_type = plugin.NODE_CLASS_MAPPINGS["MmuuAIMultiImageLoaderNodeV002"]
        schema = node_type.INPUT_TYPES()

        self.assertEqual(
            tuple(schema["required"]),
            ("图片路径", "插值算法", "短边尺寸", "尺寸倍数"),
        )
        self.assertEqual(schema["required"]["插值算法"][1]["default"], "兰索斯（高质量）")
        self.assertEqual(schema["required"]["短边尺寸"][1]["default"], 720)
        self.assertEqual(schema["required"]["尺寸倍数"][1]["default"], 16)
        self.assertEqual(node_type.RETURN_TYPES, ("IMAGE",) * 50)
        self.assertEqual(node_type.RETURN_NAMES, tuple(f"图片{i}" for i in range(1, 51)))

    def test_multi_image_loader_v2_returns_none_for_unused_outputs(self):
        node = plugin.NODE_CLASS_MAPPINGS["MmuuAIMultiImageLoaderNodeV002"]()
        module = plugin.media_tools.multi_image_loader_v2

        with patch.object(module, "_load_image", side_effect=lambda value: f"IMAGE:{value}"):
            with patch.object(module, "_resize_image", side_effect=lambda image, *_args: image):
                result = node.load(图片路径="one.png\ntwo.png")

        self.assertEqual(result[:3], ("IMAGE:one.png", "IMAGE:two.png", None))
        self.assertEqual(result[2:], (None,) * 48)

    def test_multi_image_loader_v2_scales_short_side_and_aligns_dimensions(self):
        module = plugin.media_tools.multi_image_loader_v2

        self.assertEqual(module._target_size(1600, 900, 720, 8), (1280, 720))
        self.assertEqual(module._target_size(901, 1601, 720, 32), (704, 1280))
        self.assertEqual(module._target_size(901, 1601, 0, 32), (901, 1601))

    def test_multi_image_loader_v2_rejects_more_than_fifty_images(self):
        node = plugin.NODE_CLASS_MAPPINGS["MmuuAIMultiImageLoaderNodeV002"]()
        paths = "\n".join(f"image-{index}.png" for index in range(51))

        with self.assertRaisesRegex(ValueError, "最多只能加载50张图片"):
            node.load(图片路径=paths)

    def test_multi_image_loader_v2_frontend_uses_fixed_and_dynamic_outputs(self):
        source = (ROOT / "web" / "js" / "multi_image_loader_v2_2.js").read_text(encoding="utf-8")

        self.assertIn("const MAX_IMAGES = 50", source)
        self.assertIn("const FIXED_OUTPUTS = 6", source)
        self.assertIn('api.fetchApi("/upload/image"', source)
        self.assertIn("Math.max(FIXED_OUTPUTS, imageCount, linkedDynamicOutput(node))", source)
        self.assertIn("border: 1px solid", source)
        self.assertIn("border: 1px dashed", source)

    def test_llm_and_image_nodes_have_separate_model_and_parameter_contracts(self):
        llm = plugin.NODE_CLASS_MAPPINGS["MmuuAILLMModelNodeV001"]
        image = plugin.NODE_CLASS_MAPPINGS["MmuuAIImageModelNodeV001"]
        llm_schema = llm.INPUT_TYPES()
        image_schema = image.INPUT_TYPES()

        llm_models = llm_schema["optional"]["模型"][0]
        image_models = image_schema["optional"]["模型"][0]
        self.assertEqual(
            tuple(llm_schema["required"])[:5],
            ("请求协议", "URL", "自定义URL", "模型名称", "key"),
        )
        self.assertEqual(
            tuple(image_schema["required"])[:6],
            ("请求协议", "URL", "自定义URL", "模型名称", "key", "图片请求模式"),
        )
        self.assertNotIn("平台", llm_schema["required"])
        self.assertNotIn("平台", image_schema["required"])
        self.assertEqual(llm_schema["required"]["key"][1]["default"], "获取key：https://mmuu.ai")
        self.assertEqual(image_schema["required"]["key"][1]["default"], "获取key：https://mmuu.ai")
        self.assertTrue(all("｜LLM｜" in label for label in llm_models))
        self.assertTrue(all("｜图片｜" in label for label in image_models))
        self.assertEqual(llm.RETURN_TYPES, ("STRING", "STRING"))
        self.assertEqual(image.RETURN_TYPES, ("IMAGE", "STRING"))
        self.assertNotIn("分辨率", llm_schema["required"])
        self.assertNotIn("最大令牌数", image_schema["required"])
        self.assertIn("视频1", llm_schema["optional"])
        self.assertNotIn("视频1", image_schema["optional"])

    def test_mmuuai_direct_nodes_keep_old_workflows_and_use_one_key(self):
        llm = plugin.NODE_CLASS_MAPPINGS["MmuuAILLMModelNodeV002"]
        image = plugin.NODE_CLASS_MAPPINGS["MmuuAIImageModelNodeV002"]

        self.assertIn("MmuuAILLMModelNodeV001", plugin.NODE_CLASS_MAPPINGS)
        self.assertIn("MmuuAIImageModelNodeV001", plugin.NODE_CLASS_MAPPINGS)
        self.assertEqual(plugin.NODE_DISPLAY_NAME_MAPPINGS["MmuuAILLMModelNodeV002"], "MU｜LLM模型")
        self.assertEqual(plugin.NODE_DISPLAY_NAME_MAPPINGS["MmuuAIImageModelNodeV002"], "MU｜图片模型")
        self.assertIn("UK兼容", plugin.NODE_DISPLAY_NAME_MAPPINGS["MmuuAILLMModelNodeV001"])
        self.assertIn("UK兼容", plugin.NODE_DISPLAY_NAME_MAPPINGS["MmuuAIImageModelNodeV001"])
        for node_type in (llm, image):
            required = node_type.INPUT_TYPES()["required"]
            self.assertEqual(tuple(required)[:2], ("模型", "key"))
            self.assertEqual(required["key"][1]["default"], "获取key：https://mmuu.ai")
            self.assertIn("自定义模型名称或ID", required)

    def test_llm_node_routes_each_platform_to_its_existing_protocol(self):
        node_type = plugin.NODE_CLASS_MAPPINGS["MmuuAILLMModelNodeV001"]
        module = plugin.model_nodes.llm_node

        class Client:
            def __init__(self):
                self.calls = []

            def post_json(self, endpoint, payload, headers=None):
                self.calls.append(("json", endpoint))
                return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}

            def post_sse(self, endpoint, payload, headers=None, retry_on_disconnect=False):
                self.calls.append(("sse", endpoint))
                return [{"type": "response.output_text.delta", "delta": "ok"}]

        cases = (
            ("GPT", "OpenAI｜LLM｜GPT-5.6 Luna", ("sse", "v1/responses")),
            ("Gemini", "Google｜LLM｜Gemini 3.6 Flash", ("sse", "v1beta/models/gemini-3.6-flash:streamGenerateContent?alt=sse")),
            ("Claude", "Anthropic｜LLM｜Claude Sonnet 5", ("sse", "v1/messages")),
            ("Grok", "xAI｜LLM｜Grok 4.6", ("sse", "v1/responses")),
        )
        for platform, label, expected in cases:
            client = Client()
            values = {
                "系统提示词": "", "提示词": "test", "温度": 1.0,
                "思考强度": "自动（模型默认）", "最大令牌数": 1024,
                "回答详细度（GPT）": "自动（模型默认）",
                "推理模式（统一响应）": "标准",
            }
            model = module.resolve_model(label, module.LLM_MODEL_IDS)
            node_type._request(client, platform, model, [], [], values)
            self.assertEqual(client.calls, [expected])

    def test_image_node_switches_between_generation_and_editing(self):
        node_type = plugin.NODE_CLASS_MAPPINGS["MmuuAIImageModelNodeV001"]

        class Client:
            def __init__(self):
                self.calls = []

            def post_json(self, endpoint, payload, headers=None):
                self.calls.append(("json", endpoint, payload))
                return {"data": []}

            def post_multipart(self, endpoint, data, files):
                self.calls.append(("multipart", endpoint, data, files))
                return {"data": []}

        values = {
            "提示词": "test", "分辨率": "1K", "尺寸": "1:1",
            "质量": "high", "审核强度": "自动（上游默认）",
        }
        client = Client()
        node_type._request(client, "Grok", "grok-imagine-image", [], values)
        node_type._request(client, "Grok", "grok-imagine-image", [b"png"], values)
        self.assertEqual(client.calls[0][:2], ("json", "v1/images/generations/async"))
        self.assertEqual(client.calls[1][:2], ("json", "v1/images/generations/async"))
        self.assertEqual(client.calls[1][2]["model"], "grok-imagine-image")
        self.assertIn("image_urls", client.calls[1][2])

    def test_openai_image_edit_uses_multipart_reference_files(self):
        node_type = plugin.model_nodes.image_node.MmuuAIImageModelNode

        class Client:
            def __init__(self):
                self.calls = []

            def post_multipart(self, endpoint, data, files):
                self.calls.append((endpoint, data, files))
                return {"task_id": "task-1"}

        values = {
            "提示词": "把参考图中的角色合并到一张图里",
            "分辨率": "4K",
            "尺寸": "3:2",
            "质量": "自动",
            "审核强度": "自动（上游默认）",
            "图片请求模式": "账号模式（OAuth）",
        }
        client = Client()
        result = node_type._request(
            client,
            "GPT",
            "gpt-image-2.5-sunburst",
            [b"png-1", b"png-2", b"png-3"],
            values,
        )

        self.assertEqual(result, {"task_id": "task-1"})
        endpoint, data, files = client.calls[0]
        self.assertEqual(endpoint, "v1/images/edits/async")
        self.assertEqual(data["model"], "gpt-image-2.5-sunburst")
        self.assertNotIn("image_urls", data)
        self.assertEqual([field for field, _ in files], ["image[0]", "image[1]", "image[2]"])

    def test_openai_api_mode_uses_generation_image_urls(self):
        node_type = plugin.model_nodes.image_node.MmuuAIImageModelNode

        class Client:
            def __init__(self):
                self.calls = []

            def post_json(self, endpoint, payload, headers=None):
                self.calls.append((endpoint, payload))
                return {"task_id": "task-1"}

        values = {
            "提示词": "把参考图中的角色合并到一张图里",
            "分辨率": "4K",
            "尺寸": "3:2",
            "质量": "自动",
            "审核强度": "自动（上游默认）",
            "图片请求模式": "API模式（尺寸参数）",
        }
        client = Client()
        result = node_type._request(
            client, "GPT", "gpt-image-2.5-sunburst", [b"png-1", b"png-2"], values,
        )

        self.assertEqual(result, {"task_id": "task-1"})
        endpoint, payload = client.calls[0]
        self.assertEqual(endpoint, "v1/images/generations/async")
        self.assertEqual(len(payload["image_urls"]), 2)

    def test_model_label_selects_platform_and_advertisement_is_not_a_key(self):
        common = plugin.model_nodes.common

        self.assertEqual(common.platform_for_model("OpenAI｜LLM｜GPT-5.6 Luna"), "GPT")
        self.assertEqual(common.platform_for_model("Google｜图片｜Nano Banana 2"), "Gemini")
        self.assertEqual(common.platform_for_model("Anthropic｜LLM｜Claude Sonnet 5"), "Claude")
        self.assertEqual(common.platform_for_model("xAI｜LLM｜Grok 4.6"), "Grok")
        with self.assertRaisesRegex(ValueError, "请填写所选模型对应的 key"):
            common.api_key_from_value("获取key：https://mmuu.ai")

    def test_gemini_image_uses_async_images_contract(self):
        node_type = plugin.model_nodes.image_node.MmuuAIImageModelNode

        class Client:
            def __init__(self):
                self.calls = []

            def post_json(self, endpoint, payload):
                self.calls.append((endpoint, payload))
                return {"task_id": "task-1"}

        values = {
            "提示词": "test", "分辨率": "2K", "尺寸": "1536x1024",
            "质量": "自动", "审核强度": "自动（上游默认）",
        }
        client = Client()
        node_type._request(client, "Gemini", "gemini-3.1-flash-image-preview", [b"png"], values)
        endpoint, payload = client.calls[0]
        self.assertEqual(endpoint, "v1/images/generations/async")
        self.assertEqual(payload["resolution"], "2K")
        self.assertEqual(payload["size"], "3:2")
        self.assertIn("image_urls", payload)

    def test_gemini_image_falls_back_to_legacy_native_only_after_404(self):
        node_type = plugin.model_nodes.image_node.MmuuAIImageModelNode
        error_type = plugin.model_nodes.client.UpstreamHTTPError

        class Client:
            def __init__(self):
                self.calls = []

            def post_json(self, endpoint, payload):
                self.calls.append((endpoint, payload))
                if endpoint in ("v1/images/generations/async", "v1/images/generations"):
                    raise error_type(404, "Images API is not supported for this platform")
                return {"candidates": []}

        values = {
            "提示词": "test", "分辨率": "自动", "尺寸": "自动",
            "质量": "自动", "审核强度": "自动（上游默认）",
        }
        client = Client()
        node_type._request(client, "Gemini", "gemini-3.1-flash-image", [], values)
        self.assertEqual(client.calls[-1][0], "v1beta/models/gemini-3.1-flash-image:generateContent")
        self.assertNotIn("imageConfig", client.calls[-1][1]["generationConfig"])

    def test_llm_parameters_are_only_mapped_to_supported_protocols(self):
        protocols = plugin.model_nodes.protocols
        openai = protocols.build_openai_response(
            "gpt-5.6-luna", "", "test", [], 1.0, 2048, "最少", "详细", "专业",
        )
        self.assertEqual(openai["reasoning"], {"effort": "none", "mode": "pro"})
        self.assertEqual(openai["text"], {"verbosity": "high"})

        _, gemini = protocols.build_gemini(
            "gemini-3.6-flash", "", "test", [], [], 1.0, 2048, None, "高",
        )
        self.assertEqual(
            gemini["generationConfig"]["thinkingConfig"], {"thinkingLevel": "HIGH"},
        )
        claude = protocols.build_claude(
            "claude-sonnet-5", "", "test", [], 1.0, 2048, "极高",
        )
        self.assertEqual(claude["output_config"], {"effort": "xhigh"})

        _, gemini_image = protocols.build_gemini(
            "gemini-3.1-flash-image-preview", "", "test", [], [], 1.0, 1,
            ("2K", "1536x1024"), "自动（模型默认）",
        )
        config = gemini_image["generationConfig"]
        self.assertNotIn("responseFormat", config)
        self.assertEqual(
            config["imageConfig"], {"imageSize": "2K", "aspectRatio": "3:2"},
        )

    def test_temperature_retries_only_after_explicit_parameter_rejection(self):
        module = plugin.model_nodes.llm_node
        error_type = plugin.model_nodes.client.UpstreamHTTPError

        class Client:
            def __init__(self):
                self.payloads = []

            def post_sse(self, _endpoint, payload, _headers=None):
                self.payloads.append(payload)
                if len(self.payloads) == 1:
                    raise error_type(400, "Unsupported parameter: temperature")
                return [{"type": "response.output_text.delta", "delta": "ok"}]

        client = Client()
        result = module._post_sse_with_temperature_fallback(
            client, "v1/responses", {"model": "gpt", "temperature": 1.0},
        )
        self.assertEqual(result[0]["delta"], "ok")
        self.assertIn("temperature", client.payloads[0])
        self.assertNotIn("temperature", client.payloads[1])

        class UnknownFailureClient:
            def post_sse(self, _endpoint, _payload, _headers=None):
                raise error_type(400, "Invalid prompt")

        with self.assertRaises(error_type):
            module._post_sse_with_temperature_fallback(
                UnknownFailureClient(), "v1/responses", {"temperature": 1.0},
            )

    def test_http_errors_are_concise_and_machine_classifiable(self):
        error_type = plugin.model_nodes.client.UpstreamHTTPError

        self.assertTrue(
            error_type(400, "`temperature` is deprecated").rejects_parameter("temperature")
        )
        self.assertEqual(str(error_type(502, "mmuu.uk | 502: Bad gateway")), "UK 连接上游失败（HTTP 502）")
        self.assertIn("没有可用的 Grok 图片账号", str(
            error_type(503, "No eligible Grok media accounts")
        ))

    def test_image_task_polling_uses_poll_url_and_returns_final_result(self):
        client_type = plugin.model_nodes.client.UKClient
        client = object.__new__(client_type)
        client.wait_timeout = 10
        calls = []
        responses = iter((
            {"status": "processing"},
            {"status": "completed", "result": {"data": [{"url": "https://example.test/a.png"}]}},
        ))

        def get_json(endpoint):
            calls.append(endpoint)
            return next(responses)

        client.get_json = get_json
        with patch.object(plugin.model_nodes.client.time, "sleep"):
            result = client.poll_image_task({
                "task_id": "imgtask_123", "status": "processing",
                "poll_url": "/v1/images/tasks/imgtask_123",
            })
        self.assertEqual(calls, ["v1/images/tasks/imgtask_123"] * 2)
        self.assertEqual(result["data"][0]["url"], "https://example.test/a.png")

    def test_image_resolution_validation_reports_actual_pixels(self):
        validation = plugin.model_nodes.image_node._resolution_validation(
            torch.zeros((1, 1024, 1536, 3)), "4K", "3:2",
        )
        self.assertEqual(validation["实际像素"], "1536x1024")
        self.assertFalse(validation["符合请求分辨率"])
        self.assertTrue(validation["符合请求尺寸"])
        self.assertIn("警告", validation)

    def test_image_resolution_validation_reports_ratio_mismatch(self):
        validation = plugin.model_nodes.image_node._resolution_validation(
            torch.zeros((1, 1024, 1024, 3)), "1K", "3:2",
        )
        self.assertTrue(validation["符合请求分辨率"])
        self.assertFalse(validation["符合请求尺寸"])
        self.assertIn("实际比例", validation["警告"])

    def test_image_async_submission_falls_back_only_after_404(self):
        module = plugin.model_nodes.image_node
        error_type = plugin.model_nodes.client.UpstreamHTTPError

        class Client:
            def __init__(self, error):
                self.error = error
                self.calls = []

            def post_json(self, endpoint, _payload):
                self.calls.append(endpoint)
                if len(self.calls) == 1:
                    raise self.error
                return {"data": [{"b64_json": "value"}]}

        disabled = Client(error_type(404, "async image tasks are not enabled"))
        result = module._post_json_prefer_async(disabled, "v1/images/generations", {})
        self.assertIn("data", result)
        self.assertEqual(
            disabled.calls, ["v1/images/generations/async", "v1/images/generations"],
        )

        unavailable = Client(error_type(503, "Service temporarily unavailable"))
        with self.assertRaises(error_type):
            module._post_json_prefer_async(unavailable, "v1/images/generations", {})
        self.assertEqual(unavailable.calls, ["v1/images/generations/async"])

    def test_grok_edit_falls_back_to_multipart_for_public_url_rejection(self):
        module = plugin.model_nodes.image_node
        error_type = plugin.model_nodes.client.UpstreamHTTPError

        class Client:
            def __init__(self):
                self.json_calls = []
                self.multipart_calls = []

            def post_json(self, endpoint, payload):
                self.json_calls.append((endpoint, payload))
                if endpoint.endswith("/async"):
                    raise error_type(404, "async image tasks are not enabled")
                raise error_type(400, "image_urls[0] must be an absolute http(s) URL")

            def post_multipart(self, endpoint, data, files):
                self.multipart_calls.append((endpoint, data, files))
                return {"data": [{"b64_json": "value"}]}

        client = Client()
        values = {
            "提示词": "test", "分辨率": "1K", "尺寸": "1:1",
            "质量": "自动", "审核强度": "自动（上游默认）",
        }
        result = module.MmuuAIImageModelNode._request(
            client, "Grok", "grok-imagine-image", [b"png"], values,
        )
        self.assertIn("data", result)
        self.assertEqual(client.multipart_calls[0][0], "v1/images/edits/async")
        self.assertEqual(client.multipart_calls[0][1]["model"], "grok-imagine-image")

    def test_image_moderation_is_sent_only_to_supported_official_model(self):
        module = plugin.model_nodes.image_node
        official = module.build_image_payload(
            "gpt-image-2-official", "test", "自动", "自动", "自动", "低",
        )
        regular = module.build_image_payload(
            "gpt-image-2", "test", "自动", "自动", "自动", "低",
        )
        self.assertEqual(official["moderation"], "low")
        self.assertNotIn("moderation", regular)

    def test_model_nodes_frontend_uses_dynamic_media_inputs(self):
        source = (ROOT / "web" / "js" / "dynamic_model_inputs_v5.js").read_text(encoding="utf-8")

        self.assertIn("MmuuAILLMModelNodeV001", source)
        self.assertIn("MmuuAIImageModelNodeV001", source)
        self.assertIn("MmuuAILLMModelNodeV002", source)
        self.assertIn("MmuuAIImageModelNodeV002", source)
        self.assertIn('["视频", "VIDEO", 6]', source)
        self.assertIn('MmuuAIImageModelNodeV001: [["图片", "IMAGE", 16]]', source)
        self.assertIn('MmuuAIImageModelNodeV002: [["图片", "IMAGE", 16]]', source)
        self.assertIn('MmuuAIGoogleImageModelNodeV001: [["图片", "IMAGE", 14]]', source)
        self.assertIn("function seriesNumber(name, prefix)", source)
        self.assertIn("node.disconnectInput?.(index)", source)
        self.assertIn("migrateLegacyWidgets", source)
        self.assertIn("item.callback?.(value)", source)
        self.assertIn("nodeType.prototype.onConfigure", source)

    def test_google_image_gateway_uses_apimart_contract_and_alias(self):
        node_type = plugin.model_nodes.google_image_node.MmuuAIGoogleImageModelNode
        payload = node_type._gateway_payload(
            "gemini-3.1-flash-image",
            {
                "提示词": "一只猪",
                "分辨率": "2K",
                "尺寸": "16:9",
                "内容审核": True,
                "Google搜索": True,
                "Google图片搜索": True,
            },
            [b"png"],
        )
        self.assertEqual(payload["model"], "gemini-3.1-flash-image-preview")
        self.assertEqual(payload["resolution"], "2K")
        self.assertEqual(payload["size"], "16:9")
        self.assertEqual(payload["n"], 1)
        self.assertTrue(payload["image_urls"][0].startswith("data:image/"))
        self.assertTrue(payload["nsfw_check"])
        self.assertTrue(payload["google_search"])
        self.assertTrue(payload["google_image_search"])

    def test_google_image_gateway_submits_to_documented_generation_route(self):
        client = Mock()
        client.post_json.return_value = {"data": []}

        result = plugin.model_nodes.google_image_node._post_gateway_image(client, {"model": "nano-banana-2-ext"})

        self.assertEqual(result, {"data": []})
        client.post_json.assert_called_once_with(
            "v1/images/generations", {"model": "nano-banana-2-ext"}
        )

    def test_gemini_text_extractor_ignores_null_sse_events(self):
        payload = [
            None,
            {"candidates": [{"content": {"parts": [{"text": "第一段"}]}}]},
            None,
            {"candidates": [{"content": {"parts": [{"text": "第二段"}]}}]},
        ]

        self.assertEqual(
            plugin.model_nodes.protocols.extract_gemini_text(payload),
            "第一段第二段",
        )

    def test_llm_node_can_be_used_as_direct_api_output(self):
        self.assertTrue(plugin.NODE_CLASS_MAPPINGS["MmuuAILLMModelNodeV001"].OUTPUT_NODE)

    def test_text_viewer_keeps_original_output_and_formats_json_preview(self):
        node_type = plugin.NODE_CLASS_MAPPINGS["MmuuAITextViewerNodeV001"]
        schema = node_type.INPUT_TYPES()

        self.assertEqual(schema["required"]["格式"][0], ("TXT", "MD", "JSON"))
        self.assertEqual(schema["optional"]["文本输入"], ("STRING", {"forceInput": True}))
        result = node_type().view("JSON", "manual", '{"name":"木易","count":2}')
        self.assertEqual(result["result"], ('{"name":"木易","count":2}',))
        self.assertEqual(result["ui"]["原始文本"], ['{"name":"木易","count":2}'])
        self.assertEqual(result["ui"]["格式状态"], ["JSON格式有效"])
        self.assertIn('\n  "name": "木易"', result["ui"]["文本预览"][0])

    def test_text_viewer_preserves_invalid_json_and_frontend_uses_segments(self):
        node_type = plugin.NODE_CLASS_MAPPINGS["MmuuAITextViewerNodeV001"]
        raw = '{"unfinished":'
        result = node_type().view("JSON", raw)
        self.assertEqual(result["result"], (raw,))
        self.assertEqual(result["ui"]["文本预览"], [raw])
        self.assertIn("JSON格式错误", result["ui"]["格式状态"][0])

        source = (ROOT / "web" / "js" / "text_viewer_v1.js").read_text(encoding="utf-8")
        self.assertIn('["TXT", "MD", "JSON"]', source)
        self.assertIn("renderMarkdown", source)
        self.assertIn("JSON.parse", source)
        self.assertIn('textValue(message, "原始文本")', source)
        self.assertNotIn('class="mu-text-editor"', source)
        self.assertIn('node._muTextViewer', source)
        self.assertIn('editorWidget.inputEl', source)
        self.assertIn('formatWidget', source)
        self.assertNotIn("mu-text-preview", source)

    def test_segment_splitter_frontend_reveals_outputs_as_they_are_connected(self):
        source = (ROOT / "web" / "js" / "dynamic_segment_outputs.js").read_text(
            encoding="utf-8",
        )

        self.assertIn("MmuuAISegmentPromptSplitterNodeV001", source)
        self.assertIn("highestLinked + 1", source)
        self.assertIn("Math.max(1", source)
        self.assertIn("MAX_SEGMENTS = 80", source)
        self.assertIn("nodeType.prototype.onConnectionsChange", source)

    def _strict_h3_compact(self, detailed_description):
        return {
            "schema_version": "2.0",
            "global": {
                "target_start_seconds": 0,
                "target_end_seconds": 10,
                "target_duration_seconds": 10,
                "task_types": ["reference generation"],
                "continuity_context": "Keep the person and room stable.",
                "reference_definitions": [{
                    "tag": "<Subject 1>",
                    "definition": "The person defined by <Picture 1>.",
                    "retention_mode": "fully_preserved",
                    "retention_detail": "Preserve the visible identity.",
                }],
                "character_relationships": [],
                "speaker_map": [{
                    "speaker_id": "S1",
                    "subject": "<Subject 1>",
                    "audio_reference": None,
                }],
            },
            "segments": [{
                "index": 1,
                "source_start_seconds": 0,
                "source_end_seconds": 10,
                "duration_seconds": 10,
                "reference_usage": {
                    "<Subject 1>": {"locations": "[Shot 1]", "detail": ""},
                },
                "summary": "The person completes the exchange.",
                "opening_state": "The person faces the camera.",
                "ending_state": "The person holds the final expression.",
                "detailed_description": detailed_description,
                "overall_soundscape": "Quiet room tone.",
                "non_diegetic_music": "N/A",
            }],
        }

    def _spatial_h3_compact(self):
        compact = self._strict_h3_compact("[Shot 1] <Subject 1> faces the camera.")
        compact["schema_version"] = "3.0"
        compact["global"]["spatial_layout"] = {
            "coordinate_system": "Use the dining table as the fixed world-space origin.",
            "environment_anchors": [{
                "anchor_id": "table_west_seat",
                "description": "The fixed chair at the west head of the table.",
            }],
            "fixed_subject_positions": [{
                "subject": "<Subject 1>",
                "anchor": "table_west_seat",
                "position": "centered on the west head chair",
                "facing": "east toward the table",
            }],
            "camera_baseline": "South-east three-quarter view without mirroring the room.",
            "screen_direction_rule": "Preserve world-space positions across all reverse shots.",
            "keyframe_handoff": "Use the previous segment final frame as the next first-frame reference when available.",
        }
        state = {
            "camera_state": "South-east medium shot facing north-west.",
            "subject_states": [{
                "subject": "<Subject 1>",
                "anchor": "table_west_seat",
                "position": "centered on the west head chair",
                "facing": "east toward the table",
                "posture": "seated upright",
                "gaze": "toward the opposite side of the table",
                "held_objects": ["chopsticks"],
            }],
        }
        compact["segments"][0]["opening_spatial_state"] = state
        compact["segments"][0]["ending_spatial_state"] = json.loads(json.dumps(state))
        compact["segments"][0]["spatial_transition"] = "No subject changes anchor or seat."
        return compact

    def _screen_locked_h3_compact(self):
        compact = self._spatial_h3_compact()
        compact["schema_version"] = "3.3"
        layout = compact["global"]["spatial_layout"]
        layout["environment_anchors"].append({
            "anchor_id": "south_camera_mark",
            "description": "The fixed camera mark south of the table.",
        })
        opening_composition = (
            "At south_camera_mark, eye level, facing north in a stable medium shot "
            "with <Subject 1> centered on the west head chair."
        )
        layout.update({
            "baseline_camera_anchor": "south_camera_mark",
            "allowed_camera_anchors": ["south_camera_mark"],
            "baseline_screen_order": ["<Subject 1>"],
            "segment_opening_composition": opening_composition,
        })
        for field in ("opening_spatial_state", "ending_spatial_state"):
            compact["segments"][0][field]["camera_anchor"] = "south_camera_mark"
        compact["segments"][0]["opening_spatial_state"]["camera_state"] = (
            opening_composition
        )
        return compact

    def _camera_grammar_h3_compact(self):
        compact = self._screen_locked_h3_compact()
        compact["schema_version"] = "3.7"
        compact["global"]["target_end_seconds"] = 15
        compact["global"]["target_duration_seconds"] = 15
        layout = compact["global"]["spatial_layout"]
        layout["environment_anchors"].extend([
            {
                "anchor_id": "southwest_close_mark",
                "description": "同侧人物近景机位。",
            },
            {
                "anchor_id": "southwest_insert_mark",
                "description": "同侧道具插入镜头机位。",
            },
        ])
        layout["allowed_camera_anchors"] = [
            "south_camera_mark",
            "southwest_close_mark",
            "southwest_insert_mark",
        ]
        layout["camera_grammar"] = {
            "axis_side": "southwest_safe_half_plane",
            "safe_arc": "摄影机始终位于餐桌西南侧二十度安全弧线内。",
            "editing_profile": "balanced",
            "movement_palette": ["static", "push_in", "rack_focus"],
            "cut_triggers": ["说话人变化", "人物反应", "道具动作"],
            "shot_palette": [
                {
                    "anchor_id": "south_camera_mark",
                    "description": "固定全员宽镜。",
                    "lens": "35mm",
                    "framing_options": ["wide", "medium_wide"],
                },
                {
                    "anchor_id": "southwest_close_mark",
                    "description": "同侧人物中近景。",
                    "lens": "50mm",
                    "framing_options": ["medium_close_up", "close_up"],
                },
                {
                    "anchor_id": "southwest_insert_mark",
                    "description": "手机或水杯插入镜头。",
                    "lens": "70mm",
                    "framing_options": ["insert"],
                },
            ],
        }
        segment = compact["segments"][0]
        segment["source_end_seconds"] = 15
        segment["duration_seconds"] = 15
        segment["detailed_description"] = (
            "[Shot 1] <Subject 1> faces the camera. "
            "[Shot 2] At 00:04.000, <Subject 1> reacts in close-up. "
            "[Shot 3] At 00:08.000, <Subject 1> reaches for the cup."
        )
        segment["reference_usage"]["<Subject 1>"]["locations"] = (
            "[Shot 1], [Shot 2], [Shot 3]"
        )
        segment["shot_plan"] = [
            {
                "shot_number": 1,
                "start_seconds": 0,
                "camera_anchor": "south_camera_mark",
                "framing": "wide",
                "movement": "static",
                "subjects": ["<Subject 1>"],
                "cut_trigger": "建立空间",
                "narrative_purpose": "确认人物与环境关系",
            },
            {
                "shot_number": 2,
                "start_seconds": 4,
                "camera_anchor": "southwest_close_mark",
                "framing": "close_up",
                "movement": "push_in",
                "subjects": ["<Subject 1>"],
                "cut_trigger": "人物反应",
                "narrative_purpose": "强调惊讶表情",
            },
            {
                "shot_number": 3,
                "start_seconds": 8,
                "camera_anchor": "southwest_insert_mark",
                "framing": "insert",
                "movement": "rack_focus",
                "subjects": ["<Subject 1>"],
                "cut_trigger": "道具动作",
                "narrative_purpose": "突出水杯动作",
            },
        ]
        return compact

    def test_h3_assembler_accepts_strict_shots_and_speaker_dialogue(self):
        compact = self._strict_h3_compact(
            "[Shot 1] <Subject 1> (S1) says <d>[Chinese] 第一句。</d> "
            "[Shot 2] At 00:05.000, cut to a close-up as <Subject 1> reacts."
        )

        _markdown, report, assembled = (
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )
        )

        self.assertIn("校验通过", report)
        self.assertEqual(len(assembled["segments"]), 1)

    def test_h3_assembler_requires_and_emits_spatial_contract_for_schema_v3(self):
        compact = self._spatial_h3_compact()

        markdown, _report, assembled = (
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )
        )

        self.assertEqual(assembled["spatial_layout"]["fixed_subject_positions"][0]["subject"], "<Subject 1>")
        self.assertIn("Continuity:", markdown)
        self.assertIn("<Subject 1>centered on the west head chair", markdown)
        self.assertNotIn("Opening subject states:", markdown)
        self.assertNotIn("Ending subject states:", markdown)
        for header in (
            "subject_definitions:\n",
            "summary:\n",
            "retention_analysis:\n",
            "detailed_description:\n",
            "overall_soundscape:\n",
            "non_diegetic_music:\n",
        ):
            self.assertEqual(markdown.count(header), 1)
        self.assertNotIn("```", markdown)
        self.assertNotIn("\nspatial_transition:\n", markdown)

        del compact["global"]["spatial_layout"]
        with self.assertRaisesRegex(ValueError, "spatial_layout"):
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )

    def test_h3_assembler_rejects_cross_segment_spatial_drift(self):
        compact = self._spatial_h3_compact()
        compact["global"]["target_end_seconds"] = 20
        compact["global"]["target_duration_seconds"] = 20
        compact["segments"][0]["source_end_seconds"] = 10
        second = json.loads(json.dumps(compact["segments"][0]))
        second["index"] = 2
        second["source_start_seconds"] = 10
        second["source_end_seconds"] = 20
        second["opening_spatial_state"]["subject_states"][0]["position"] = "moved to the east chair"
        compact["segments"].append(second)

        with self.assertRaisesRegex(ValueError, "人物空间状态不一致"):
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )

    def test_h3_assembler_requires_locked_opening_composition_for_schema_v33(self):
        compact = self._screen_locked_h3_compact()

        markdown, _report, assembled = (
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )
        )

        self.assertEqual(
            assembled["spatial_layout"]["baseline_camera_anchor"],
            "south_camera_mark",
        )
        self.assertIn("baseline screen order=<Subject 1>", markdown)
        self.assertIn("keep the camera on the same side", markdown)

        compact_with_roles = self._screen_locked_h3_compact()
        compact_with_roles["global"]["spatial_layout"]["baseline_screen_order"] = [
            "<Subject 1> presenter"
        ]
        _markdown, _report, normalized = (
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact_with_roles)
            )
        )
        self.assertEqual(
            normalized["spatial_layout"]["baseline_screen_order"],
            ["<Subject 1>"],
        )

        compact["global"]["spatial_layout"]["environment_anchors"].append({
            "anchor_id": "north_camera_mark",
            "description": "A forbidden reverse-side camera mark north of the table.",
        })
        compact["global"]["spatial_layout"]["allowed_camera_anchors"].append(
            "north_camera_mark"
        )
        compact["segments"][0]["opening_spatial_state"]["camera_anchor"] = (
            "north_camera_mark"
        )
        with self.assertRaisesRegex(ValueError, "必须使用全片基准机位"):
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )

    def test_h3_assembler_requires_fifteen_second_windows_for_schema_v34(self):
        compact = self._screen_locked_h3_compact()
        compact["schema_version"] = "3.4"
        compact["global"]["target_end_seconds"] = 31
        compact["global"]["target_duration_seconds"] = 31
        first = compact["segments"][0]
        first["source_end_seconds"] = 15
        first["duration_seconds"] = 15
        second = json.loads(json.dumps(first))
        second.update({
            "index": 2,
            "source_start_seconds": 15,
            "source_end_seconds": 30,
            "duration_seconds": 15,
        })
        third = json.loads(json.dumps(first))
        third.update({
            "index": 3,
            "source_start_seconds": 30,
            "source_end_seconds": 31,
            "duration_seconds": 1,
        })
        compact["segments"] = [first, second, third]

        _markdown, report, assembled = (
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )
        )
        self.assertEqual(
            [item["duration_seconds"] for item in assembled["segments"]],
            [15, 15, 1],
        )
        self.assertNotIn("多数分段恰好为15秒", report)

        compact["segments"][1]["duration_seconds"] = 14
        with self.assertRaisesRegex(ValueError, "分段2必须使用15秒"):
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )

    def test_h3_assembler_rejects_any_short_segment_for_schema_v35(self):
        compact = self._screen_locked_h3_compact()
        compact["schema_version"] = "3.5"
        compact["global"]["target_end_seconds"] = 30
        compact["global"]["target_duration_seconds"] = 30
        first = compact["segments"][0]
        first["source_end_seconds"] = 15
        first["duration_seconds"] = 15
        second = json.loads(json.dumps(first))
        second.update({
            "index": 2,
            "source_start_seconds": 15,
            "source_end_seconds": 30,
            "duration_seconds": 15,
        })
        compact["segments"] = [first, second]

        _markdown, report, assembled = (
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )
        )
        self.assertEqual(
            [item["duration_seconds"] for item in assembled["segments"]],
            [15, 15],
        )
        self.assertNotIn("多数分段恰好为15秒", report)

        compact["segments"][1]["duration_seconds"] = 14
        with self.assertRaisesRegex(ValueError, "分段2必须严格为15秒"):
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )

    def test_h3_assembler_rejects_precompleted_boundary_action_for_schema_v36(self):
        compact = self._screen_locked_h3_compact()
        compact["schema_version"] = "3.6"
        compact["global"]["target_end_seconds"] = 30
        compact["global"]["target_duration_seconds"] = 30
        first = compact["segments"][0]
        first["source_end_seconds"] = 15
        first["duration_seconds"] = 15
        second = json.loads(json.dumps(first))
        second.update({
            "index": 2,
            "source_start_seconds": 15,
            "source_end_seconds": 30,
            "duration_seconds": 15,
            "detailed_description": (
                "[Shot 1] <Subject 1> has just lowered the water glass."
            ),
        })
        compact["segments"] = [first, second]

        with self.assertRaisesRegex(ValueError, "第一帧前偷跳了边界动作"):
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )

    def test_h3_assembler_emits_chinese_content_with_official_labels_preserved(self):
        compact = self._screen_locked_h3_compact()
        compact["output_language"] = "zh-CN"
        compact["global"]["character_relationships"] = [{
            "subjects": ["<Subject 1>"],
            "relationship": "这是当前画面的主要人物。",
        }]
        compact["segments"][0]["opening_state"] = "人物坐在固定位置。"
        compact["segments"][0]["ending_state"] = "人物保持固定位置。"

        markdown, _report, assembled = (
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact, ensure_ascii=False)
            )
        )

        self.assertEqual(assembled["output_language"], "zh-CN")
        for header in (
            "subject_definitions:",
            "summary:",
            "retention_analysis:",
            "detailed_description:",
            "overall_soundscape:",
            "non_diegetic_music:",
        ):
            self.assertIn(header, markdown)
        self.assertNotIn("空间坐标系：", markdown)
        self.assertNotIn("开场人物状态：", markdown)
        self.assertNotIn("强制第一帧规则：", markdown)
        self.assertNotIn("关系：", markdown)
        self.assertIn("连续性：", markdown)
        self.assertNotIn("开场状态：人物坐在固定位置。", markdown)
        self.assertIn(compact["segments"][0]["detailed_description"].replace(" [Shot ", "\n[Shot "), markdown)
        self.assertNotIn("\nscene:\n", markdown)
        self.assertNotIn("\naction:\n", markdown)
        self.assertFalse(markdown.startswith("## 分段"))
        self.assertNotIn("Spatial coordinate system:", markdown)

    def test_h3_assembler_requires_creative_same_side_camera_grammar_for_v37(self):
        compact = self._camera_grammar_h3_compact()

        markdown, _report, assembled = (
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact, ensure_ascii=False)
            )
        )
        self.assertEqual(len(assembled["segments"][0]["shot_plan"]), 3)
        self.assertIn("Continuity:", markdown)
        self.assertNotIn("Same-side shot palette:", markdown)
        self.assertNotIn("Shot execution plan:", markdown)
        self.assertIn(compact["segments"][0]["detailed_description"].replace(" [Shot ", "\n[Shot "), markdown)

        compact_with_unlisted_movement = self._camera_grammar_h3_compact()
        compact_with_unlisted_movement["segments"][0]["shot_plan"][2]["movement"] = (
            "pull_out"
        )
        _markdown, _report, normalized = (
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact_with_unlisted_movement, ensure_ascii=False)
            )
        )
        self.assertIn(
            "pull_out",
            normalized["spatial_layout"]["camera_grammar"]["movement_palette"],
        )

        compact["segments"][0]["shot_plan"] = compact["segments"][0]["shot_plan"][:1]
        with self.assertRaisesRegex(ValueError, "3至5个Shot"):
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact, ensure_ascii=False)
            )

    def test_h3_assembler_rejects_repeated_camera_movement_signature_for_v37(self):
        compact = self._camera_grammar_h3_compact()
        compact["global"]["target_end_seconds"] = 30
        compact["global"]["target_duration_seconds"] = 30
        first = compact["segments"][0]
        first["source_end_seconds"] = 15
        first["duration_seconds"] = 15
        second = json.loads(json.dumps(first))
        second.update({
            "index": 2,
            "source_start_seconds": 15,
            "source_end_seconds": 30,
        })
        compact["segments"] = [first, second]

        _markdown, report, _assembled = (
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact, ensure_ascii=False)
            )
        )
        self.assertIn("重复完全相同的运镜组合", report)

    def test_h3_assembler_rejects_mechanically_equal_shot_durations_for_v37(self):
        compact = self._camera_grammar_h3_compact()
        compact["segments"][0]["detailed_description"] = (
            "[Shot 1] <Subject 1> faces the camera. "
            "[Shot 2] At 00:05.000, <Subject 1> reacts. "
            "[Shot 3] At 00:10.000, <Subject 1> reaches for the cup."
        )
        compact["segments"][0]["shot_plan"][1]["start_seconds"] = 5
        compact["segments"][0]["shot_plan"][2]["start_seconds"] = 10

        with self.assertRaisesRegex(ValueError, "不得把分段机械等分"):
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact, ensure_ascii=False)
            )

    def test_rh_cloud_assembler_emits_strict_blocks_and_rejects_direct_markdown(self):
        cloud = importlib.import_module(f"{PACKAGE}.rh_workflow.h3_cloud_assembler")
        compact = self._camera_grammar_h3_compact()
        compact["global"]["output_language"] = "zh-CN"

        full, report, normalized, count = cloud.assemble(
            json.dumps(compact, ensure_ascii=False)
        )

        self.assertEqual(count, "1")
        self.assertIn("校验通过", report)
        self.assertEqual(json.loads(normalized)["schema_version"], "3.7")
        for header in (
            "subject_definitions:",
            "summary:",
            "retention_analysis:",
            "detailed_description:",
            "overall_soundscape:",
            "non_diegetic_music:",
        ):
            self.assertEqual(full.count(header), 1)
        self.assertNotIn("### subject_definitions", full)
        self.assertNotIn("`", full)
        self.assertIn(compact["segments"][0]["detailed_description"].replace(" [Shot ", "\n[Shot "), full)
        self.assertNotIn("\nscene:\n", full)
        self.assertNotIn("\naction:\n", full)
        self.assertIn("连续性：", full)
        self.assertNotIn("开场主体状态：", full)
        self.assertNotIn("镜头执行计划：", full)
        self.assertFalse(full.startswith("## 分段"))

        with self.assertRaisesRegex(ValueError, "not valid JSON"):
            cloud.assemble("## 分段1，时长：15秒\n### subject_definitions")

    def test_h3_assembler_rejects_first_shot_timestamp_and_unlabeled_cut(self):
        compact = self._strict_h3_compact(
            "[Shot 1] At 00:00.000, the person faces the camera. "
            "At 00:05.000, cut to a close-up."
        )

        with self.assertRaisesRegex(ValueError, "Shot 1.*不得带时间"):
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )

        compact["segments"][0]["detailed_description"] = (
            "[Shot 1] The person faces the camera. At 00:05.000, cut to a close-up."
        )
        with self.assertRaisesRegex(ValueError, "没有新.*Shot N"):
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )

        compact["segments"][0]["detailed_description"] = (
            "[Shot 1] <Subject 1> faces the camera. "
            "[Shot 2] At 00:05.000, the person reacts. Cut back to a wide shot."
        )
        compact["segments"][0]["reference_usage"]["<Subject 1>"]["locations"] = (
            "[Shot 1], [Shot 2]"
        )
        with self.assertRaisesRegex(ValueError, "没有新.*Shot N"):
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )

    def test_h3_assembler_rejects_invalid_dialogue_format_and_speaker(self):
        compact = self._strict_h3_compact(
            "[Shot 1] He says <d>[Chinese]缺少空格和Speaker。</d>"
        )

        with self.assertRaisesRegex(ValueError, "语言标签后保留空格"):
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )

        compact["segments"][0]["detailed_description"] = (
            "[Shot 1] He says <d>[Chinese] 缺少Speaker。</d>"
        )
        with self.assertRaisesRegex(ValueError, "紧邻完整的.*Subject N.*says"):
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )

        compact["segments"][0]["detailed_description"] = (
            "[Shot 1] <Subject 1> (S1) turns toward the camera and says "
            "<d>[Chinese] Speaker与says不紧邻。</d>"
        )
        with self.assertRaisesRegex(ValueError, "紧邻完整的.*Subject N.*says"):
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )

    def test_h3_assembler_rejects_speaker_subject_mismatch(self):
        compact = self._strict_h3_compact(
            "[Shot 1] <Subject 2> (S1) says <d>[Chinese] 错误人物。</d>"
        )
        compact["global"]["reference_definitions"].append({
            "tag": "<Subject 2>",
            "definition": "A second person defined by <Picture 2>.",
            "retention_mode": "fully_preserved",
            "retention_detail": "Preserve the second person.",
        })
        compact["segments"][0]["reference_usage"] = {
            "<Subject 2>": {"locations": "[Shot 1]", "detail": ""},
        }
        with self.assertRaisesRegex(ValueError, "S1 必须由 <Subject 1> 发声"):
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )

    def test_h3_assembler_derives_reference_locations_from_shot_text(self):
        compact = self._strict_h3_compact(
            "[Shot 1] <Subject 1> faces the camera. "
            "[Shot 2] At 00:05.000, the camera shows the empty room."
        )
        compact["segments"][0]["reference_usage"]["<Subject 1>"]["locations"] = "[Shot 2]"

        _markdown, _report, assembled = (
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )
        )
        self.assertEqual(
            assembled["segments"][0]["reference_usage"]["<Subject 1>"]["locations"],
            "[Shot 1]",
        )

        compact["segments"][0]["detailed_description"] = (
            "[Shot 1] The empty room is visible. "
            "[Shot 2] At 00:05.000, the camera moves closer."
        )
        with self.assertRaisesRegex(ValueError, "实际使用位置.*Subject 1"):
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )

    def test_h3_assembler_includes_definitions_for_relationship_subjects(self):
        compact = self._strict_h3_compact("[Shot 1] <Subject 1> faces the camera.")
        compact["global"]["reference_definitions"].append({
            "tag": "<Subject 2>",
            "definition": "The off-screen relative defined by <Picture 2>.",
            "retention_mode": "fully_preserved",
            "retention_detail": "Preserve the relative's visible identity.",
        })
        compact["global"]["character_relationships"] = [{
            "subjects": ["<Subject 1>", "<Subject 2>"],
            "relationship": "They are members of the same family.",
        }]

        markdown, _report, _assembled = (
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )
        )

        self.assertIn("<Subject 2>: The off-screen relative", markdown)

    def test_h3_assembler_normalizes_empty_audio_and_absolute_shot_times(self):
        compact = self._strict_h3_compact(
            "[Shot 1] <Subject 1> faces the camera. "
            "[Shot 2] At 00:20.000, <Subject 1> reacts."
        )
        compact["global"]["target_start_seconds"] = 15
        compact["global"]["target_end_seconds"] = 30
        compact["global"]["target_duration_seconds"] = 15
        compact["global"]["speaker_map"][0]["audio_reference"] = ""
        compact["segments"][0]["source_start_seconds"] = 15
        compact["segments"][0]["source_end_seconds"] = 30
        compact["segments"][0]["duration_seconds"] = 15
        compact["segments"][0]["reference_usage"]["<Subject 1>"]["locations"] = (
            "[Shot 1], [Shot 2]"
        )

        markdown, report, assembled = (
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )
        )

        self.assertIn("[Shot 2] At 00:05.000", markdown)
        self.assertIsNone(assembled["speaker_map"][0]["audio_reference"])
        self.assertIn("绝对镜头时间换算", report)

    def test_h3_assembler_normalizes_speakers_by_first_dialogue(self):
        compact = self._strict_h3_compact(
            "[Shot 1] <Subject 1> (S1) says <d>[Chinese] 父亲。</d> "
            "<Subject 2> (S3) says <d>[Chinese] 女儿。</d> "
            "<Subject 3> (S2) says <d>[Chinese] 母亲。</d>"
        )
        compact["global"]["reference_definitions"].extend([
            {
                "tag": "<Subject 2>",
                "definition": "The daughter defined by <Picture 2>.",
                "retention_mode": "fully_preserved",
                "retention_detail": "Preserve the daughter.",
            },
            {
                "tag": "<Subject 3>",
                "definition": "The mother defined by <Picture 3>.",
                "retention_mode": "fully_preserved",
                "retention_detail": "Preserve the mother.",
            },
        ])
        compact["global"]["speaker_map"].extend([
            {"speaker_id": "S2", "subject": "<Subject 3>", "audio_reference": None},
            {"speaker_id": "S3", "subject": "<Subject 2>", "audio_reference": None},
        ])
        compact["segments"][0]["reference_usage"].update({
            "<Subject 2>": {"locations": "[Shot 1]", "detail": ""},
            "<Subject 3>": {"locations": "[Shot 1]", "detail": ""},
        })

        markdown, _report, assembled = (
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )
        )

        self.assertEqual(
            [(item["speaker_id"], item["subject"]) for item in assembled["speaker_map"]],
            [("S1", "<Subject 1>"), ("S2", "<Subject 2>"), ("S3", "<Subject 3>")],
        )
        self.assertIn("<Subject 2> (S2) says", markdown)
        self.assertIn("<Subject 3> (S3) says", markdown)

    def test_h3_two_stage_nodes_use_comfy_list_mapping(self):
        batch = plugin.NODE_CLASS_MAPPINGS["MmuuAIH3PlanVideoBatchNodeV001"]
        collector = plugin.NODE_CLASS_MAPPINGS["MmuuAIH3SegmentCollectorNodeV001"]

        self.assertEqual(batch.OUTPUT_IS_LIST, (True, True, True, False))
        self.assertEqual(batch.RETURN_NAMES[-1], "规范化全片规划JSON")
        self.assertTrue(collector.INPUT_IS_LIST)
        self.assertEqual(
            tuple(batch.INPUT_TYPES()["required"]),
            ("视频", "全片规划JSON", "用户想法"),
        )

    def test_h3_segment_collector_builds_assembler_compatible_json(self):
        pipeline = plugin.media_tools.h3_pipeline
        plan = {
            "schema_version": "2.0",
            "global": {
                "target_start_seconds": 10,
                "target_end_seconds": 22,
                "target_duration_seconds": 12,
                "task_types": ["reference generation"],
                "continuity_rules": ["Keep the character and room stable."],
                "reference_definitions": [
                    {
                        "tag": "<Subject 1>",
                        "definition": "The target person defined by <Picture 1>.",
                        "retention_mode": "fully_preserved",
                        "retention_detail": "Preserve the visible identity.",
                    },
                    {
                        "tag": "<Audio 1>",
                        "definition": "The voice reference for the target person.",
                        "retention_mode": "reference",
                        "retention_detail": "Use the referenced voice identity.",
                    },
                ],
                "character_relationships": [
                    {
                        "subjects": ["<Subject 1>"],
                        "relationship": "The central presenter.",
                    }
                ],
                "speaker_map": [
                    {
                        "speaker_id": "S1",
                        "subject": "<Subject 1>",
                        "audio_reference": "<Audio 1>",
                    }
                ],
            },
            "segments": [
                {
                    "index": 1,
                    "source_start_seconds": 10,
                    "source_end_seconds": 22,
                    "duration_seconds": 12,
                }
            ],
        }
        detail = {
            "schema_version": "2.0",
            "segment_index": 1,
            "validation_error": None,
            "segment": {
                "index": 1,
                "source_start_seconds": None,
                "source_end_seconds": 22,
                "duration_seconds": 12,
                "reference_usage": {
                    "<Subject 1>": {
                        "locations": "[Shot 1]",
                        "detail": "The presenter remains visible.",
                    },
                    "<Audio 1>": {
                        "locations": "[Shot 1] dialogue",
                        "detail": "Use the mapped voice reference for S1.",
                    },
                },
                "summary": "The character completes the exchange.",
                "opening_state": "The character faces the camera.",
                "ending_state": "The character holds the final expression.",
                "detailed_description": (
                    "[Shot 1] <Subject 1> (S1) says "
                    "<d>[Chinese] 测试。</d> using the <Audio 1> voice reference."
                ),
                "overall_soundscape": "Quiet room tone.",
                "non_diegetic_music": "N/A",
            },
        }

        compact_text, report, count = pipeline.collect_segment_details(
            json.dumps(plan),
            [json.dumps(detail)],
        )
        compact = json.loads(compact_text)

        self.assertEqual(count, 1)
        self.assertIn("1段", report)
        self.assertEqual(compact["schema_version"], "1.1")
        self.assertEqual(compact["segments"][0]["index"], 1)
        self.assertEqual(compact["segments"][0]["source_start_seconds"], 10)
        self.assertEqual(compact["global"]["target_start_seconds"], 10)
        self.assertEqual(compact["global"]["target_end_seconds"], 22)
        self.assertEqual(compact["global"]["speaker_map"][0]["speaker_id"], "S1")
        self.assertEqual(
            compact["global"]["continuity_context"],
            "Keep the character and room stable.",
        )
        markdown, _validation, assembled = plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
            compact_text
        )
        self.assertEqual(assembled["target_start_seconds"], 10)
        self.assertEqual(assembled["target_end_seconds"], 22)
        self.assertNotIn("Relationships:", markdown)
        self.assertNotIn("Speaker map:", markdown)

    def test_h3_natural_window_plan_keeps_content_selected_boundaries(self):
        windows = plugin.media_tools.h3_windows
        plan = {
            "schema_version": "3.0",
            "global": {
                "source_duration_seconds": 240,
                "target_start_seconds": 0,
                "target_end_seconds": 240,
                "target_duration_seconds": 240,
            },
            "analysis_windows": [
                {
                    "index": 1,
                    "source_start_seconds": 0,
                    "source_end_seconds": 126.8,
                    "duration_seconds": 126.8,
                    "content_summary": "The first scene completes.",
                    "start_anchor": "The opening frame.",
                    "end_anchor": "The first scene ends.",
                    "cut_reason": "A completed scene change.",
                },
                {
                    "index": 2,
                    "source_start_seconds": 126.8,
                    "source_end_seconds": 240,
                    "duration_seconds": 113.2,
                    "content_summary": "The second scene completes.",
                    "start_anchor": "The second scene begins.",
                    "end_anchor": "The final frame.",
                    "cut_reason": "The source video ends.",
                },
            ],
        }

        parsed = windows.parse_analysis_plan(plan, source_duration=241.25)

        self.assertEqual(len(parsed["analysis_windows"]), 2)
        self.assertEqual(parsed["analysis_windows"][0]["source_end_seconds"], 126.8)
        self.assertEqual(parsed["analysis_windows"][1]["source_end_seconds"], 241.25)
        self.assertEqual(parsed["global"]["target_duration_seconds"], 241.25)

    def test_h3_window_collector_builds_relative_shots_and_dialogue_tags(self):
        pipeline = plugin.media_tools.h3_pipeline
        plan = {
            "schema_version": "3.0",
            "global": {
                "source_duration_seconds": 20,
                "target_start_seconds": 0,
                "target_end_seconds": 20,
                "target_duration_seconds": 20,
                "task_types": ["reference generation", "audio reference"],
                "continuity_rules": ["Keep the room stable."],
                "reference_definitions": [{
                    "tag": "<Subject 1>",
                    "definition": "The person defined by <Picture 1>.",
                    "retention_mode": "fully_preserved",
                    "retention_detail": "Preserve the visible identity.",
                }],
                "character_relationships": [],
                "speaker_map": [{
                    "speaker_id": "S1",
                    "subject": "<Subject 1>",
                    "audio_reference": "<Audio 1>",
                }],
            },
            "analysis_windows": [{
                "index": 1,
                "source_start_seconds": 0,
                "source_end_seconds": 20,
                "duration_seconds": 20,
                "content_summary": "One continuous exchange.",
                "start_anchor": "The exchange begins.",
                "end_anchor": "The reaction completes.",
                "cut_reason": "The dialogue sequence is complete.",
            }],
        }
        result = {
            "schema_version": "3.0-window",
            "window_index": 1,
            "validation_error": None,
            "segments": [
                {
                    "source_start_seconds": 0,
                    "source_end_seconds": 10,
                    "duration_seconds": 10,
                    "reference_usage": {"<Subject 1>": {
                        "locations": "[Shot 1], [Shot 2]",
                        "detail": "The person remains visible.",
                    }},
                    "summary": "The person starts speaking.",
                    "opening_state": "The person faces the camera.",
                    "ending_state": "The camera cuts closer.",
                    "shots": [
                        {
                            "source_time_seconds": 0,
                            "description": "A medium shot shows <Subject 1>.",
                            "dialogues": [{
                                "speaker_id": "S1",
                                "language": "Chinese",
                                "text": "<d>[Chinese] 你好。[/Chinese]</d>",
                                "delivery": "On-screen and calm.",
                            }],
                        },
                        {
                            "source_time_seconds": 7,
                            "description": "A close-up shows <Subject 1>'s reaction.",
                            "dialogues": [],
                        },
                    ],
                    "overall_soundscape": "Quiet room tone.",
                    "non_diegetic_music": "N/A",
                },
                {
                    "source_start_seconds": 10,
                    "source_end_seconds": 20,
                    "duration_seconds": 10,
                    "reference_usage": {"<Subject 1>": {
                        "locations": "[Shot 1]",
                        "detail": "The person remains visible.",
                    }},
                    "summary": "The person completes the exchange.",
                    "opening_state": "The close-up continues.",
                    "ending_state": "The person holds the final reaction.",
                    "shots": [{
                        "source_time_seconds": 10,
                        "description": "The close-up continues on <Subject 1>.",
                        "dialogues": [],
                    }],
                    "overall_soundscape": "Quiet room tone.",
                    "non_diegetic_music": "N/A",
                },
            ],
        }

        compact_text, report, count = pipeline.collect_segment_details(
            json.dumps(plan), [json.dumps(result)]
        )
        compact = json.loads(compact_text)

        self.assertEqual(count, 2)
        self.assertIn("1个自然分析窗口", report)
        detailed = compact["segments"][0]["detailed_description"]
        self.assertIn("[Shot 2] At 00:07.000", detailed)
        self.assertIn("<d>[Chinese] 你好。</d>", detailed)
        self.assertNotIn("[/Chinese]", detailed)
        plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(compact_text)

    def test_h3_window_collector_splits_overlong_segment_at_real_shot(self):
        windows = plugin.media_tools.h3_windows
        source = {
            "source_start_seconds": 0,
            "source_end_seconds": 20,
            "duration_seconds": 20,
            "summary": "One long scene.",
            "opening_state": "The first shot begins.",
            "ending_state": "The last shot ends.",
            "shots": [
                {"source_time_seconds": 0, "description": "First shot.", "dialogues": []},
                {"source_time_seconds": 9, "description": "Natural reaction cut.", "dialogues": []},
                {"source_time_seconds": 17, "description": "Final shot.", "dialogues": []},
            ],
        }

        chunks = windows._split_overlong_segment(source, "测试分段")

        self.assertEqual([(item["source_start_seconds"], item["source_end_seconds"]) for item in chunks], [(0, 9), (9, 20)])
        self.assertIn("shared cut boundary", chunks[0]["ending_state"])
        self.assertIn("shared cut boundary", chunks[1]["opening_state"])

    def test_h3_assembler_normalizes_declared_audio_and_picture_aliases(self):
        compact = {
            "schema_version": "1.1",
            "global": {
                "target_duration_seconds": 5,
                "target_start_seconds": 0,
                "target_end_seconds": 5,
                "task_types": ["reference generation", "audio reference"],
                "continuity_context": "Keep the references stable.",
                "reference_definitions": [{
                    "tag": "<Subject 1>",
                    "definition": "The person defined by <Picture 1>.",
                    "retention_mode": "fully_preserved",
                    "retention_detail": "Preserve the visible identity from <Picture 1>.",
                }],
                "character_relationships": [],
                "speaker_map": [{
                    "speaker_id": "S1",
                    "subject": "<Subject 1>",
                    "audio_reference": "<Audio 1>",
                }],
            },
            "segments": [{
                "index": 1,
                "source_start_seconds": 0,
                "source_end_seconds": 5,
                "duration_seconds": 5,
                "reference_usage": {
                    "<Picture 1>": {"locations": "", "detail": "Visible throughout."},
                    "<Audio 1>": {"locations": "[Shot 1] dialogue", "detail": "Use S1 voice."},
                },
                "summary": "The person speaks.",
                "opening_state": "The person faces the camera.",
                "ending_state": "The person finishes speaking.",
                "detailed_description": (
                    "[Shot 1] <Subject 1> (S1) says "
                    "<d>[Chinese] 测试。</d> using the <Audio 1> voice reference."
                ),
                "overall_soundscape": "Quiet room tone.",
                "non_diegetic_music": "N/A",
            }],
        }

        _markdown, _report, assembled = (
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )
        )

        self.assertIn("<Audio 1>", assembled["reference_definitions"])
        self.assertIn("<Subject 1>", assembled["segments"][0]["reference_usage"])
        self.assertNotIn("<Picture 1>", assembled["segments"][0]["reference_usage"])
        self.assertEqual(
            assembled["segments"][0]["reference_usage"]["<Subject 1>"]["locations"],
            "[Shot 1]",
        )

    def test_h3_assembler_normalizes_environment_alias_to_unused_subject(self):
        compact = {
            "schema_version": "1.1",
            "global": {
                "target_duration_seconds": 5,
                "target_start_seconds": 0,
                "target_end_seconds": 5,
                "task_types": ["reference generation"],
                "continuity_context": "Keep <Environment 1> stable.",
                "reference_definitions": [
                    {
                        "tag": "<Subject 1>",
                        "definition": "The person defined by <Picture 1>.",
                        "retention_mode": "fully_preserved",
                        "retention_detail": "Preserve the person.",
                    },
                    {
                        "tag": "<Environment 1>",
                        "definition": "The room defined by <Picture 2>.",
                        "retention_mode": "fully_preserved",
                        "retention_detail": "Preserve the room.",
                    },
                ],
                "character_relationships": [],
                "speaker_map": [],
            },
            "segments": [{
                "index": 1,
                "source_start_seconds": 0,
                "source_end_seconds": 5,
                "duration_seconds": 5,
                "reference_usage": {
                    "<Environment 1>": {
                        "locations": "[Shot 1]",
                        "detail": "The room is visible.",
                    }
                },
                "summary": "The room is established.",
                "opening_state": "The room is visible.",
                "ending_state": "The room remains visible.",
                "detailed_description": "[Shot 1] <Environment 1> is visible.",
                "overall_soundscape": "Quiet room tone.",
                "non_diegetic_music": "N/A",
            }],
        }

        _markdown, _report, assembled = (
            plugin.media_tools.h3_prompt_assembler.assemble_compact_h3_plan(
                json.dumps(compact)
            )
        )

        self.assertIn("<Subject 2>", assembled["reference_definitions"])
        self.assertIn("<Subject 2>", assembled["segments"][0]["reference_usage"])
        self.assertNotIn("<Environment 1>", json.dumps(assembled))

    def test_h3_full_plan_completes_a_contiguous_missing_tail(self):
        pipeline = plugin.media_tools.h3_pipeline
        plan = {
            "schema_version": "2.0",
            "global": {
                "target_start_seconds": 0,
                "target_end_seconds": 526,
                "target_duration_seconds": 526,
            },
            "segments": [
                {
                    "index": index,
                    "source_start_seconds": (index - 1) * 15,
                    "source_end_seconds": index * 15,
                    "duration_seconds": 15,
                }
                for index in range(1, 27)
            ],
        }

        repaired = pipeline.parse_full_plan(json.dumps(plan))

        self.assertEqual(repaired["segments"][-1]["source_end_seconds"], 526)
        self.assertEqual(repaired["global"]["auto_completed_tail_segments"], 10)
        self.assertGreaterEqual(len(repaired["segments"]), 36)
        self.assertTrue(
            all(segment["duration_seconds"] <= 15 for segment in repaired["segments"])
        )

    def test_h3_full_plan_uses_file_duration_for_full_source_plan(self):
        pipeline = plugin.media_tools.h3_pipeline
        plan = {
            "schema_version": "2.0",
            "global": {
                "source_duration_seconds": 40,
                "target_start_seconds": 0,
                "target_end_seconds": 40,
                "target_duration_seconds": 40,
            },
            "segments": [
                {
                    "index": 1,
                    "source_start_seconds": 0,
                    "source_end_seconds": 15,
                    "duration_seconds": 15,
                },
                {
                    "index": 2,
                    "source_start_seconds": 15,
                    "source_end_seconds": 30,
                    "duration_seconds": 15,
                },
                {
                    "index": 3,
                    "source_start_seconds": 30,
                    "source_end_seconds": 40,
                    "duration_seconds": 10,
                },
            ],
        }

        repaired = pipeline.parse_full_plan(json.dumps(plan), source_duration=37.4)

        self.assertEqual(repaired["global"]["target_end_seconds"], 37.4)
        self.assertEqual(repaired["global"]["target_duration_seconds"], 37.4)
        self.assertEqual(repaired["segments"][-1]["source_end_seconds"], 37.4)
        self.assertEqual(repaired["segments"][-1]["duration_seconds"], 7.4)

    def test_h3_full_plan_splits_segments_longer_than_fifteen_seconds(self):
        pipeline = plugin.media_tools.h3_pipeline
        plan = {
            "schema_version": "2.0",
            "global": {
                "target_start_seconds": 0,
                "target_end_seconds": 20,
                "target_duration_seconds": 20,
            },
            "segments": [{
                "index": 1,
                "source_start_seconds": 0,
                "source_end_seconds": 20,
                "duration_seconds": 20,
                "content_summary": "One continuous scene.",
                "start_anchor": "Scene begins.",
                "end_anchor": "Scene ends.",
            }],
        }

        repaired = pipeline.parse_full_plan(json.dumps(plan))

        self.assertEqual(len(repaired["segments"]), 2)
        self.assertEqual(repaired["segments"][0]["duration_seconds"], 10)
        self.assertEqual(repaired["segments"][1]["duration_seconds"], 10)
        self.assertEqual(repaired["segments"][1]["index"], 2)

    def test_h3_full_plan_fills_a_gap_before_the_missing_tail(self):
        pipeline = plugin.media_tools.h3_pipeline
        plan = {
            "schema_version": "2.0",
            "global": {
                "target_start_seconds": 0,
                "target_end_seconds": 40,
                "target_duration_seconds": 40,
            },
            "segments": [
                {
                    "index": 1,
                    "source_start_seconds": 0,
                    "source_end_seconds": 10,
                    "duration_seconds": 10,
                },
                {
                    "index": 2,
                    "source_start_seconds": 10,
                    "source_end_seconds": 20,
                    "duration_seconds": 10,
                },
                {
                    "index": 3,
                    "source_start_seconds": 21,
                    "source_end_seconds": 30,
                    "duration_seconds": 9,
                },
            ],
        }

        repaired = pipeline.parse_full_plan(json.dumps(plan))

        self.assertEqual(repaired["segments"][2]["source_start_seconds"], 20)
        self.assertEqual(repaired["segments"][2]["source_end_seconds"], 21)
        self.assertEqual(repaired["segments"][3]["source_start_seconds"], 21)
        self.assertEqual(repaired["segments"][-1]["source_end_seconds"], 40)
        self.assertEqual(repaired["global"]["auto_completed_middle_segments"], 1)

    def test_h3_full_plan_repairs_the_known_bare_anchor_key(self):
        pipeline = plugin.media_tools.h3_pipeline
        text = """{
          "schema_version": "2.0",
          "global": {
            "target_start_seconds": 0,
            "target_end_seconds": 10,
            "target_duration_seconds": 10
          },
          "segments": [{
            "index": 1,
            "source_start_seconds": 0,
            "source_end_seconds": 10,
            "duration_seconds": 10,
            _anchor: "The first frame.",
            "end_anchor": "The final frame."
          }]
        }"""

        plan = pipeline.parse_full_plan(text)

        self.assertEqual(plan["segments"][0]["start_anchor"], "The first frame.")

    def test_h3_full_plan_derives_duration_from_valid_boundaries(self):
        pipeline = plugin.media_tools.h3_pipeline
        plan = {
            "schema_version": "2.0",
            "global": {
                "target_start_seconds": 0,
                "target_end_seconds": 13,
                "target_duration_seconds": 13,
            },
            "segments": [
                {
                    "index": 1,
                    "source_start_seconds": 0,
                    "source_end_seconds": 13,
                    "duration_seconds": 14,
                }
            ],
        }

        repaired = pipeline.parse_full_plan(json.dumps(plan))

        self.assertEqual(repaired["segments"][0]["duration_seconds"], 13)

    def test_audio_clip_schema_and_time_slice(self):
        node_type = plugin.NODE_CLASS_MAPPINGS["MmuuAIAudioClipConverterNodeV001"]
        schema = node_type.INPUT_TYPES()
        self.assertEqual(schema["optional"]["音频"], ("AUDIO",))
        self.assertEqual(node_type.RETURN_NAMES, ("音频",))

        audio = {"waveform": torch.arange(100).reshape(1, 1, 100), "sample_rate": 10}
        clipped = node_type().clip(
            音频=audio,
            **{"开始时间（秒，0不限制）": 2.0, "结束时间（秒，0不限制）": 7.0},
        )[0]
        self.assertEqual(tuple(clipped["waveform"].shape), (1, 1, 50))
        self.assertEqual(int(clipped["waveform"][0, 0, 0]), 20)

    def test_audio_clip_zero_end_keeps_the_rest(self):
        node_type = plugin.NODE_CLASS_MAPPINGS["MmuuAIAudioClipConverterNodeV001"]
        audio = {"waveform": torch.zeros((1, 2, 100)), "sample_rate": 10}
        clipped = node_type().clip(
            音频=audio,
            **{"开始时间（秒，0不限制）": 4.0, "结束时间（秒，0不限制）": 0.0},
        )[0]
        self.assertEqual(tuple(clipped["waveform"].shape), (1, 2, 60))


if __name__ == "__main__":
    unittest.main()
