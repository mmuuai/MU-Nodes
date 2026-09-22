import { app } from "/scripts/app.js";

const NODE_TYPE = "MmuuAISegmentPromptSplitterNodeV001";
const COUNT_OUTPUT = "实际分段数";
const PREFIX = "分段";
const MAX_SEGMENTS = 80;

function segmentNumber(output) {
  for (const value of [output?.name, output?.label, output?.localized_name]) {
    const match = /^分段(\d+)$/.exec(String(value || ""));
    const number = Number(match?.[1]);
    if (number >= 1 && number <= MAX_SEGMENTS) return number;
  }
  return 0;
}

function linkedSegments(node, outputs) {
  const linked = new Set();
  for (const output of outputs) {
    const number = segmentNumber(output);
    if (number && output?.links?.length) linked.add(number);
  }
  for (const link of Object.values(node.graph?.links || {})) {
    if (link?.origin_id !== node.id) continue;
    const number = segmentNumber(outputs[link.origin_slot]);
    if (number) linked.add(number);
  }
  return linked;
}

function syncOutputs(node) {
  if (!Array.isArray(node.outputs) || !node.outputs.length) return;

  const oldOutputs = [...node.outputs];
  const countOutput = oldOutputs.find((output) => output?.name === COUNT_OUTPUT) || oldOutputs[0];
  const byNumber = new Map(
    oldOutputs
      .map((output) => [segmentNumber(output), output])
      .filter(([number]) => number > 0),
  );
  const linked = linkedSegments(node, oldOutputs);
  const highestLinked = linked.size ? Math.max(...linked) : 0;
  const visibleCount = Math.min(MAX_SEGMENTS, Math.max(1, highestLinked + 1));

  const linkNumbers = new Map();
  for (const [id, link] of Object.entries(node.graph?.links || {})) {
    if (link?.origin_id !== node.id) continue;
    linkNumbers.set(id, segmentNumber(oldOutputs[link.origin_slot]));
  }

  const nextOutputs = [countOutput];
  for (let number = 1; number <= visibleCount; number += 1) {
    let output = byNumber.get(number);
    if (!output) {
      node.addOutput(`${PREFIX}${number}`, "STRING");
      output = node.outputs.pop();
    }
    output.name = `${PREFIX}${number}`;
    nextOutputs.push(output);
  }
  node.outputs = nextOutputs;

  const slots = new Map(
    node.outputs.map((output, index) => [segmentNumber(output), index]),
  );
  for (const [id, number] of linkNumbers) {
    const link = node.graph?.links?.[id];
    if (link && number && slots.has(number)) link.origin_slot = slots.get(number);
  }

  const computed = node.computeSize();
  node.setSize([Math.max(Number(node.size?.[0]) || 0, computed[0]), computed[1]]);
  node.graph?.setDirtyCanvas?.(true, true);
}

function scheduleSync(node) {
  for (const delay of [0, 100, 500]) setTimeout(() => syncOutputs(node), delay);
}

app.registerExtension({
  name: "mmuuai.dynamic-segment-outputs.v001",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_TYPE) return;
    const originalCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function (...args) {
      const result = originalCreated?.apply(this, args);
      scheduleSync(this);
      return result;
    };
    const originalConnectionsChange = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function (...args) {
      const result = originalConnectionsChange?.apply(this, args);
      scheduleSync(this);
      return result;
    };
  },
  nodeCreated(node) {
    if (node.comfyClass === NODE_TYPE) scheduleSync(node);
  },
  loadedGraphNode(node) {
    if (node.comfyClass === NODE_TYPE) scheduleSync(node);
  },
});
