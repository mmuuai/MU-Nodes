import { app } from "/scripts/app.js";

const NODE_TYPE = "MmuuAIResolutionSelectorV2";
const IMAGE_RESOLUTIONS = ["1k", "2k", "4k", "6k", "8k"];
const VIDEO_RESOLUTIONS = ["480p", "720p", "1080p", "2k", "4k", "6k", "8k"];
const IMAGE_LONG_EDGES = { "1k": 1024, "2k": 2048, "4k": 4096, "6k": 6144, "8k": 8192 };
const VIDEO_SHORT_EDGES = {
  "480p": 480,
  "720p": 720,
  "1080p": 1080,
  "2k": 1440,
  "4k": 2160,
  "6k": 3240,
  "8k": 4320,
};

function widget(node, name) {
  return (node.widgets || []).find((item) => item.name === name);
}

function roundToMultiple(value, multiple) {
  return Math.max(multiple, Math.floor(value / multiple + 0.5) * multiple);
}

function dimensions(node) {
  const mediaType = widget(node, "类型")?.value || "图片";
  const resolution = widget(node, "分辨率")?.value || (mediaType === "图片" ? "1k" : "1080p");
  const [ratioWidth, ratioHeight] = String(widget(node, "画面比例")?.value || "16:9")
    .split(":")
    .map(Number);

  if (mediaType === "图片") {
    const longEdge = IMAGE_LONG_EDGES[resolution] || 1024;
    const width = ratioWidth >= ratioHeight ? longEdge : (longEdge * ratioWidth) / ratioHeight;
    const height = ratioWidth >= ratioHeight ? (longEdge * ratioHeight) / ratioWidth : longEdge;
    return [roundToMultiple(width, 16), roundToMultiple(height, 16)];
  }

  const shortEdge = VIDEO_SHORT_EDGES[resolution] || 1080;
  const width = ratioWidth >= ratioHeight ? (shortEdge * ratioWidth) / ratioHeight : shortEdge;
  const height = ratioWidth >= ratioHeight ? shortEdge : (shortEdge * ratioHeight) / ratioWidth;
  return [roundToMultiple(width, 2), roundToMultiple(height, 2)];
}

function refresh(node, resetResolution = false) {
  const typeWidget = widget(node, "类型");
  const resolutionWidget = widget(node, "分辨率");
  if (!typeWidget || !resolutionWidget) return;

  const isImage = typeWidget.value === "图片";
  const options = isImage ? IMAGE_RESOLUTIONS : VIDEO_RESOLUTIONS;
  resolutionWidget.options.values = options;
  if (resetResolution || !options.includes(resolutionWidget.value)) {
    resolutionWidget.value = isImage ? "1k" : "1080p";
  }

  const [width, height] = dimensions(node);
  if (node.outputs?.[0]) {
    node.outputs[0].name = `宽度：${width}`;
    node.outputs[0].label = `宽度：${width}`;
    node.outputs[0].localized_name = `宽度：${width}`;
  }
  if (node.outputs?.[1]) {
    node.outputs[1].name = `高度：${height}`;
    node.outputs[1].label = `高度：${height}`;
    node.outputs[1].localized_name = `高度：${height}`;
  }
  node.title = `MU｜尺寸选择器 V2 · ${width}×${height}`;
  const computed = node.computeSize?.() || [300, 120];
  node.setSize?.([Math.max(node.size?.[0] || 0, 320), Math.max(computed[1], 120)]);
  node.graph?.setDirtyCanvas?.(true, true);
}

function wrapCallback(node, targetWidget, callback) {
  const original = targetWidget.callback;
  targetWidget.callback = function (...args) {
    const result = original?.apply(this, args);
    callback();
    return result;
  };
}

function prepare(node) {
  if (node._muResolutionV2Prepared) {
    refresh(node);
    return;
  }
  const typeWidget = widget(node, "类型");
  const resolutionWidget = widget(node, "分辨率");
  const ratioWidget = widget(node, "画面比例");
  if (!typeWidget || !resolutionWidget || !ratioWidget) return;

  node._muResolutionV2Prepared = true;
  wrapCallback(node, typeWidget, () => refresh(node, true));
  wrapCallback(node, resolutionWidget, () => refresh(node));
  wrapCallback(node, ratioWidget, () => refresh(node));
  refresh(node);
}

function schedulePrepare(node) {
  for (const delay of [0, 100, 500, 1000]) setTimeout(() => prepare(node), delay);
}

app.registerExtension({
  name: "mmuuai.resolution-selector.v2",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_TYPE) return;
    const originalCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function (...args) {
      const result = originalCreated?.apply(this, args);
      schedulePrepare(this);
      return result;
    };
    const originalConfigured = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (...args) {
      const result = originalConfigured?.apply(this, args);
      schedulePrepare(this);
      return result;
    };
  },
  nodeCreated(node) {
    if (node.comfyClass === NODE_TYPE) schedulePrepare(node);
  },
  loadedGraphNode(node) {
    if (node.comfyClass === NODE_TYPE) schedulePrepare(node);
  },
});
