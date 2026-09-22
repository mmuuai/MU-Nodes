import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

const MU_CATEGORY_PREFIX = "MU/";
const MU_CATEGORY_ORDER = ["接口", "文本", "加载", "媒体处理", "工具"];
const REMOVED_NODE_TYPES = new Set([
  "MmuuAISegmentPromptSplitterNodeV001",
  "MmuuAIH3PlanVideoBatchNodeV001",
  "MmuuAIH3SegmentCollectorNodeV001",
  "MmuuAIH3PromptAssemblerNodeV001",
  "MmuuAIRHWorkflowNodeV001",
]);
let nodeDefs = {};

function getNodeCategory(nodeType) {
  return nodeType?.category || nodeType?.prototype?.category || "";
}

function getNodeTitle(nodeType, typeName) {
  return nodeType?.title || nodeType?.prototype?.title || nodeType?.comfyClass || typeName;
}

function createNode(canvas, typeName) {
  const node = globalThis.LiteGraph?.createNode?.(typeName);
  if (!node) {
    console.warn(`[MU-Nodes] Unable to create node: ${typeName}`);
    return;
  }

  const graph = canvas.graph || app.graph;
  graph.add(node);
  node.pos = [canvas.graph_mouse[0], canvas.graph_mouse[1]];
  canvas.selectNode(node, false);
  canvas.setDirty?.(true, true);
  graph.change?.();
}

function getMuEntries() {
  return Object.entries(nodeDefs)
    .map(([typeName, definition]) => {
      if (REMOVED_NODE_TYPES.has(typeName)) return null;
      const nodeType = globalThis.LiteGraph?.registered_node_types?.[typeName];
      if (!nodeType) return null;
      const category = definition?.category || getNodeCategory(nodeType);
      if (!category.startsWith(MU_CATEGORY_PREFIX)) return null;
      return {
        typeName,
        category: category.slice(MU_CATEGORY_PREFIX.length) || "其他",
        title: definition?.display_name || getNodeTitle(nodeType, typeName),
      };
    })
    .filter(Boolean);
}

function getSortedCategories(entries) {
  return [...new Set(entries.map((entry) => entry.category))].sort((a, b) => {
    const aIndex = MU_CATEGORY_ORDER.indexOf(a);
    const bIndex = MU_CATEGORY_ORDER.indexOf(b);
    if (aIndex !== -1 || bIndex !== -1) {
      return (aIndex === -1 ? Number.MAX_SAFE_INTEGER : aIndex) -
        (bIndex === -1 ? Number.MAX_SAFE_INTEGER : bIndex);
    }
    return a.localeCompare(b, "zh-CN");
  });
}

function organizeAllMuNodes(canvas) {
  const graph = canvas.graph || app.graph;
  const entries = getMuEntries();
  const existing = new Map(
    (graph._nodes || [])
      .filter((node) => node.type && entries.some((entry) => entry.typeName === node.type))
      .map((node) => [node.type, node]),
  );

  for (const entry of entries) {
    if (!existing.has(entry.typeName)) {
      const node = globalThis.LiteGraph?.createNode?.(entry.typeName);
      if (node) {
        graph.add(node);
        existing.set(entry.typeName, node);
      }
    }
  }

  const Group = globalThis.LGraphGroup || globalThis.LiteGraph?.LGraphGroup;
  const origin = canvas.graph_mouse ? [...canvas.graph_mouse] : [0, 0];
  const categories = getSortedCategories(entries);
  const groupWidth = 430;
  const groupGap = 40;
  const rowHeight = 980;

  categories.forEach((category, categoryIndex) => {
    const categoryEntries = entries
      .filter((entry) => entry.category === category)
      .sort((a, b) => a.title.localeCompare(b.title, "zh-CN"));
    const column = categoryIndex % 3;
    const row = Math.floor(categoryIndex / 3);
    const groupPos = [
      origin[0] + column * (groupWidth + groupGap),
      origin[1] + row * rowHeight,
    ];
    const groupHeight = 110 + categoryEntries.length * 135;
    const group = Group ? new Group(`MU / ${category}`) : null;
    if (group) {
      group.pos = groupPos;
      group.size = [groupWidth, groupHeight];
      graph.add(group);
    }

    categoryEntries.forEach((entry, nodeIndex) => {
      const node = existing.get(entry.typeName);
      if (!node) return;
      node.pos = [groupPos[0] + 20, groupPos[1] + 60 + nodeIndex * 135];
      group?.add?.(node);
    });
  });

  canvas.setDirty?.(true, true);
  graph.change?.();
  canvas.draw?.(true, true);
}

function buildMenu(canvas) {
  const groups = new Map();

  for (const [typeName, definition] of Object.entries(nodeDefs)) {
    if (REMOVED_NODE_TYPES.has(typeName)) continue;
    const nodeType = globalThis.LiteGraph?.registered_node_types?.[typeName];
    if (!nodeType) continue;
    const category = definition?.category || getNodeCategory(nodeType);
    if (!category.startsWith(MU_CATEGORY_PREFIX)) continue;

    const groupName = category.slice(MU_CATEGORY_PREFIX.length) || "其他";
    if (!groups.has(groupName)) groups.set(groupName, []);
    groups.get(groupName).push({
      content: definition?.display_name || getNodeTitle(nodeType, typeName),
      callback: () => createNode(canvas, typeName),
    });
  }

  const sortedGroups = [...groups.entries()].sort(([a], [b]) => {
    const aIndex = MU_CATEGORY_ORDER.indexOf(a);
    const bIndex = MU_CATEGORY_ORDER.indexOf(b);
    if (aIndex !== -1 || bIndex !== -1) {
      return (aIndex === -1 ? Number.MAX_SAFE_INTEGER : aIndex) -
        (bIndex === -1 ? Number.MAX_SAFE_INTEGER : bIndex);
    }
    return a.localeCompare(b, "zh-CN");
  });

  return [
    {
      content: "全部 MU 节点（按类型整理）",
      callback: () => organizeAllMuNodes(canvas),
    },
    ...sortedGroups.map(([groupName, options]) => ({
    content: groupName,
    has_submenu: true,
    submenu: {
      options: options.sort((a, b) => String(a.content).localeCompare(String(b.content), "zh-CN")),
    },
    })),
  ];
}

app.registerExtension({
  name: "MU-Nodes.CanvasContextMenu",
  async setup() {
    try {
      nodeDefs = await api.getNodeDefs();
    } catch (error) {
      console.warn("[MU-Nodes] Unable to load node categories", error);
    }
  },
  getCanvasMenuItems(canvas) {
    const options = buildMenu(canvas);
    return [
      {
        content: "MU",
        has_submenu: true,
        submenu: { options },
      },
    ];
  },
});
