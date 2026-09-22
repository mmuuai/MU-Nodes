from .media_tools.multi_image_loader import MmuuAIMultiImageLoaderNode
from .media_tools.multi_image_loader_v2 import MmuuAIMultiImageLoaderV2Node
from .media_tools.node import MmuuAIMediaParserNode
from .media_tools.mmuuai_node import MmuuAIDirectMediaParserNode
from .media_tools.multi_video_loader import MmuuAIMultiVideoLoaderNode
from .media_tools.multi_video_loader_v2 import MmuuAIMultiVideoLoaderV2Node
from .media_tools.text_nodes import (
    MmuuAIH3SystemPromptLanguageNode,
    MmuuAIMultiStringMergeNode,
)
from .media_tools.text_viewer import MmuuAITextViewerNode
from .media_tools.utility_nodes import (
    MmuuAILinkListSplitterNode,
    MmuuAIMediaUrlLoaderNode,
)
from .media_tools.video_compress import MmuuAIVideoCompressNode
from .media_tools.video_clip_converter import MmuuAIVideoClipConverterNode
from .media_tools.audio_clip_converter import MmuuAIAudioClipConverterNode
from .media_tools.video_image_converter import MmuuAIVideoImageConverterNode
from .media_tools.smart_video_segmenter import (
    MmuuAIGetVideoSegmentNode,
    MmuuAISmartVideoSegmenterNode,
)
from .model_nodes import (
    MmuuAIDirectImageModelNode,
    MmuuAIDirectLLMModelNode,
    MmuuAIImageModelNode,
    MmuuAIGoogleImageModelNode,
    MmuuAILLMModelNode,
)
from .resolution.resolution_selector_v2 import MmuuAIResolutionSelectorV2
from .resolution.aspect_ratio_from_dimensions import MmuuAIAspectRatioFromDimensionsV001
from .media_tools.video_measurement import (
    MmuuAIFrameCountCalculatorV001,
    MmuuAIVideoInfoNodeV001,
)


NODE_CLASS_MAPPINGS = {
    "MmuuAIMultiImageLoaderNodeV001": MmuuAIMultiImageLoaderNode,
    "MmuuAIMultiImageLoaderNodeV002": MmuuAIMultiImageLoaderV2Node,
    "MmuuAIMediaParserNodeV001": MmuuAIMediaParserNode,
    "MmuuAIMediaParserNodeV002": MmuuAIDirectMediaParserNode,
    "MmuuAIMultiVideoLoaderNodeV001": MmuuAIMultiVideoLoaderNode,
    "MmuuAIMultiVideoLoaderNodeV002": MmuuAIMultiVideoLoaderV2Node,
    "MmuuAILinkListSplitterNodeV001": MmuuAILinkListSplitterNode,
    "MmuuAIMediaUrlLoaderNodeV001": MmuuAIMediaUrlLoaderNode,
    "MmuuAIMultiStringMergeNodeV001": MmuuAIMultiStringMergeNode,
    "MmuuAIH3SystemPromptLanguageNodeV001": MmuuAIH3SystemPromptLanguageNode,
    "MmuuAITextViewerNodeV001": MmuuAITextViewerNode,
    "MmuuAIVideoCompressNodeV001": MmuuAIVideoCompressNode,
    "MmuuAIVideoClipConverterNodeV001": MmuuAIVideoClipConverterNode,
    "MmuuAIAudioClipConverterNodeV001": MmuuAIAudioClipConverterNode,
    "MmuuAIVideoImageConverterNodeV001": MmuuAIVideoImageConverterNode,
    "MmuuAISmartVideoSegmenterNodeV001": MmuuAISmartVideoSegmenterNode,
    "MmuuAIGetVideoSegmentNodeV001": MmuuAIGetVideoSegmentNode,
    "MmuuAILLMModelNodeV001": MmuuAILLMModelNode,
    "MmuuAIImageModelNodeV001": MmuuAIImageModelNode,
    "MmuuAILLMModelNodeV002": MmuuAIDirectLLMModelNode,
    "MmuuAIImageModelNodeV002": MmuuAIDirectImageModelNode,
    "MmuuAIGoogleImageModelNodeV001": MmuuAIGoogleImageModelNode,
    "MmuuAIResolutionSelectorV2": MmuuAIResolutionSelectorV2,
    "MmuuAIAspectRatioFromDimensionsV001": MmuuAIAspectRatioFromDimensionsV001,
    "MmuuAIFrameCountCalculatorV001": MmuuAIFrameCountCalculatorV001,
    "MmuuAIVideoInfoNodeV001": MmuuAIVideoInfoNodeV001,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MmuuAIMultiImageLoaderNodeV001": "MU｜多图片加载 V1",
    "MmuuAIMultiImageLoaderNodeV002": "MU｜多图片加载 V2",
    "MmuuAIMediaParserNodeV001": "MU｜媒体解析（上游Key兼容）",
    "MmuuAIMediaParserNodeV002": "MU｜媒体解析",
    "MmuuAIMultiVideoLoaderNodeV001": "MU｜多视频加载 V1",
    "MmuuAIMultiVideoLoaderNodeV002": "MU｜多视频加载 V2",
    "MmuuAILinkListSplitterNodeV001": "MU｜链接列表拆分",
    "MmuuAIMediaUrlLoaderNodeV001": "MU｜媒体链接加载",
    "MmuuAIMultiStringMergeNodeV001": "MU｜多字符串合并",
    "MmuuAIH3SystemPromptLanguageNodeV001": "MU｜H3系统提示词语言选择",
    "MmuuAITextViewerNodeV001": "MU｜文本查看与格式化",
    "MmuuAIVideoCompressNodeV001": "MU｜视频流式压缩",
    "MmuuAIVideoClipConverterNodeV001": "MU｜视频截取",
    "MmuuAIAudioClipConverterNodeV001": "MU｜音频截取",
    "MmuuAIVideoImageConverterNodeV001": "MU｜视频与图片序列转换",
    "MmuuAISmartVideoSegmenterNodeV001": "MU｜智能视频切片",
    "MmuuAIGetVideoSegmentNodeV001": "MU｜获取视频切片",
    "MmuuAILLMModelNodeV001": "MU｜LLM模型（UK兼容）",
    "MmuuAIImageModelNodeV001": "MU｜图片模型（UK兼容）",
    "MmuuAILLMModelNodeV002": "MU｜LLM模型",
    "MmuuAIImageModelNodeV002": "MU｜图片模型",
    "MmuuAIGoogleImageModelNodeV001": "MU｜Google图片模型",
    "MmuuAIResolutionSelectorV2": "MU｜尺寸选择器 V2",
    "MmuuAIAspectRatioFromDimensionsV001": "MU｜宽高比判断",
    "MmuuAIFrameCountCalculatorV001": "MU｜时长与帧数计算",
    "MmuuAIVideoInfoNodeV001": "MU｜获取视频信息",
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
