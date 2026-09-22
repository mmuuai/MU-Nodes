import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import torch


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "mu_nodes_measurement_test"
spec = importlib.util.spec_from_file_location(
    PACKAGE,
    ROOT / "__init__.py",
    submodule_search_locations=[str(ROOT)],
)
plugin = importlib.util.module_from_spec(spec)
sys.modules[PACKAGE] = plugin
spec.loader.exec_module(plugin)


class MeasurementNodeTests(unittest.TestCase):
    def test_nodes_are_registered_with_expected_categories(self):
        expected = {
            "MmuuAIAspectRatioFromDimensionsV001": ("MU｜宽高比判断", "MU/工具"),
            "MmuuAIFrameCountCalculatorV001": ("MU｜时长与帧数计算", "MU/工具"),
            "MmuuAIVideoInfoNodeV001": ("MU｜获取视频信息", "MU/媒体处理"),
        }
        for node_id, (display_name, category) in expected.items():
            self.assertIn(node_id, plugin.NODE_CLASS_MAPPINGS)
            self.assertEqual(plugin.NODE_DISPLAY_NAME_MAPPINGS[node_id], display_name)
            self.assertEqual(plugin.NODE_CLASS_MAPPINGS[node_id].CATEGORY, category)

    def test_aspect_ratio_is_classified_to_nearest_supported_ratio(self):
        node = plugin.NODE_CLASS_MAPPINGS["MmuuAIAspectRatioFromDimensionsV001"]()
        self.assertEqual(node.calculate(1920, 1080), ("16:9",))
        self.assertEqual(node.calculate(1000, 1800), ("9:16",))
        self.assertEqual(node.calculate(720, 950), ("3:4",))
        self.assertEqual(node.calculate(1300, 1000), ("4:3",))
        self.assertEqual(node.calculate(1100, 1000), ("1:1",))
        self.assertEqual(node.calculate(3440, 1440), ("16:9",))
        with self.assertRaisesRegex(ValueError, "大于 0"):
            node.calculate(0, 1080)

    def test_duration_calculator_outputs_rounded_integer_and_exact_float(self):
        node = plugin.NODE_CLASS_MAPPINGS["MmuuAIFrameCountCalculatorV001"]()
        self.assertEqual(node.calculate(24, **{"时长（秒）": 2}), (48, 48.0))
        self.assertEqual(node.calculate(23.976, **{"时长（秒）": 1.5}), (36, 35.964))
        with self.assertRaisesRegex(ValueError, "帧率"):
            node.calculate(0, **{"时长（秒）": 1})

    def test_video_info_uses_video_frame_rate_and_sequence_dimensions(self):
        node = plugin.NODE_CLASS_MAPPINGS["MmuuAIVideoInfoNodeV001"]()
        images = torch.zeros((48, 720, 1280, 3))
        video = Mock()
        video.get_components.return_value = SimpleNamespace(
            images=images,
            frame_rate=24,
        )

        self.assertEqual(
            node.get_info(30, 视频=video),
            (1280, 720, 24.0, 48, 2.0),
        )

    def test_video_info_uses_configured_rate_for_image_sequences(self):
        node = plugin.NODE_CLASS_MAPPINGS["MmuuAIVideoInfoNodeV001"]()
        images = torch.zeros((60, 1080, 1920, 3))
        self.assertEqual(
            node.get_info(30, 图片序列=images),
            (1920, 1080, 30.0, 60, 2.0),
        )

    def test_video_info_requires_exactly_one_input_and_valid_tensor(self):
        node = plugin.NODE_CLASS_MAPPINGS["MmuuAIVideoInfoNodeV001"]()
        with self.assertRaisesRegex(ValueError, "请且仅连接"):
            node.get_info(24)
        with self.assertRaisesRegex(ValueError, "请且仅连接"):
            node.get_info(24, 视频=Mock(), 图片序列=torch.zeros((1, 2, 2, 3)))
        with self.assertRaisesRegex(ValueError, "图片序列必须"):
            node.get_info(24, 图片序列=torch.zeros((1, 2, 3)))


if __name__ == "__main__":
    unittest.main()
