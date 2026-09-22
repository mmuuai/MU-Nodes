import { app } from "/scripts/app.js";

const NODE_TYPE = "MmuuAITextViewerNodeV001";
const MODES = ["TXT", "MD", "JSON"];

function hideWidget(widget) {
  if (!widget || widget._muHidden) return;
  widget._muHidden = true;
  Object.defineProperty(widget, "type", {
    configurable: true,
    get: () => "hidden",
    set: () => {},
  });
  widget.computeSize = () => [0, 0];
  const timer = setInterval(() => {
    const container = widget.element?.closest?.(".lg-node-widget") || widget.element;
    if (container) container.style.display = "none";
  }, 50);
  setTimeout(() => clearInterval(timer), 1000);
}

function moveWidget(node, widget, index) {
  const current = node.widgets?.indexOf(widget) ?? -1;
  if (current < 0 || current === index) return;
  node.widgets.splice(current, 1);
  node.widgets.splice(index, 0, widget);
}

function textValue(message, key, fallback = "") {
  const value = message?.ui?.[key] ?? message?.[key];
  if (Array.isArray(value)) return String(value[0] ?? fallback);
  return value == null ? fallback : String(value);
}

function renderMarkdown(container, source) {
  container.replaceChildren();
  const lines = String(source).replace(/\r\n?/g, "\n").split("\n");
  let code = null;
  for (const line of lines) {
    if (line.startsWith("```")) {
      if (code) {
        container.append(code);
        code = null;
      } else {
        code = document.createElement("pre");
      }
      continue;
    }
    if (code) {
      code.textContent += `${code.textContent ? "\n" : ""}${line}`;
      continue;
    }
    const heading = /^(#{1,6})\s+(.+)$/.exec(line);
    const list = /^\s*[-*+]\s+(.+)$/.exec(line);
    const element = document.createElement(heading ? `h${heading[1].length}` : list ? "li" : "p");
    element.textContent = heading?.[2] ?? list?.[1] ?? line;
    container.append(element);
  }
  if (code) container.append(code);
}

function prepareJson(source) {
  if (!String(source).trim()) return { text: "", status: "" };
  try {
    return { text: JSON.stringify(JSON.parse(source), null, 2), status: "JSON格式有效" };
  } catch (error) {
    return { text: String(source), status: `JSON格式错误：${error.message}` };
  }
}

function setWidgetVisible(widget, visible) {
  if (!widget) return;
  if (!widget._muTextOriginalType) widget._muTextOriginalType = widget.type;
  if (!widget._muTextOriginalComputeSize) {
    widget._muTextOriginalComputeSize = widget.computeSize?.bind(widget);
  }
  widget.type = visible ? widget._muTextOriginalType : "hidden";
  widget.computeSize = visible
    ? (widget._muTextOriginalComputeSize || (() => [0, 0]))
    : () => [0, 0];
  const element = widget.element?.closest?.(".lg-node-widget") || widget.element;
  if (element) element.style.display = visible ? "" : "none";
  if (widget.inputEl) widget.inputEl.style.display = visible ? "" : "none";
}

function createPanel(formatWidget, editorWidget) {
  const root = document.createElement("div");
  root.className = "mu-text-panel";
  root.innerHTML = `<div class="mu-text-toolbar"></div>`;
  const toolbar = root.querySelector(".mu-text-toolbar");
  const textarea = editorWidget.inputEl || editorWidget.element?.querySelector?.("textarea");
  const buttons = new Map();
  const state = { executedRaw: null };

  const update = () => {
    const mode = String(formatWidget.value || "TXT");
    const source = state.executedRaw ?? String(editorWidget.value || "");
    for (const [value, button] of buttons) button.classList.toggle("active", value === mode);
    if (textarea && textarea.value !== source) textarea.value = source;
  };

  for (const mode of MODES) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = mode;
    button.onclick = () => {
      formatWidget.value = mode;
      formatWidget.callback?.(mode);
      update();
    };
    buttons.set(mode, button);
    toolbar.append(button);
  }
  update();
  return {
    root,
    state,
    update,
    mode: () => String(formatWidget.value || "TXT"),
  };
}

function install(node) {
  if (node._muTextViewer) return;
  const formatWidget = node.widgets?.find((item) => item.name === "格式");
  const editorWidget = node.widgets?.find((item) => item.name === "文本");
  if (!formatWidget || !editorWidget) return;

  const textarea = editorWidget.inputEl || editorWidget.element?.querySelector?.("textarea");
  const panel = {
    state: { executedRaw: null },
    update() {
      const source = this.state.executedRaw ?? String(editorWidget.value || "");
      editorWidget.value = source;
      if (textarea && textarea.value !== source) textarea.value = source;
    },
  };
  node._muTextViewer = panel;
  const size = node.computeSize();
  node.setSize([Math.max(320, size[0]), Math.max(300, size[1])]);
  // Workflows saved with the broken height-sync version can contain a huge node.
  // Only normalize clearly corrupted heights; otherwise keep native widget sizing.
  setTimeout(() => {
    const restored = node.computeSize();
    if (Number(node.size?.[1]) > Number(restored?.[1] || 0) + 20) {
      node.setSize([Math.max(320, restored[0]), Math.max(300, restored[1])]);
      node.graph?.setDirtyCanvas(true, true);
    }
  }, 1200);
}

const style = document.createElement("style");
style.textContent = `
  .lg-node-widget:has(.mu-text-panel) { height: 28px !important; min-height: 28px !important; max-height: 28px !important; flex: 0 0 28px !important; overflow: hidden !important; }
  .mu-text-panel { box-sizing: border-box; width: 100%; height: 28px; max-height: 28px; min-height: 0; overflow: hidden; }
  .mu-text-toolbar { box-sizing: border-box; display: flex; align-items: center; gap: 4px; width: 100%; min-height: 0; height: 28px; margin: 0; color: var(--fg-color); }
  .mu-text-toolbar button { width: 48px; height: 24px; padding: 0; border: 1px solid color-mix(in srgb, var(--fg-color) 20%, transparent); border-radius: 4px; background: color-mix(in srgb, var(--comfy-menu-bg) 86%, transparent); color: var(--fg-color); font-size: 12px; cursor: pointer; }
  .mu-text-toolbar button.active { border-color: #52a8ff; background: #245b84; color: #fff; }
  .mu-text-render { box-sizing: border-box; width: 100%; min-height: 0; height: 100%; margin: 0; padding: 9px; border: 1px solid color-mix(in srgb, var(--fg-color) 24%, transparent); border-radius: 6px; background: var(--comfy-input-bg, #2a2d31); color: var(--fg-color); font: inherit; line-height: 1.5; overflow: auto; overflow-wrap: anywhere; }
  .mu-text-render { white-space: pre-wrap; user-select: text; }
  .mu-text-status { margin-top: 5px; color: #ffbd66; font-size: 12px; }
  .mu-text-render h1, .mu-text-render h2, .mu-text-render h3, .mu-text-render h4, .mu-text-render h5, .mu-text-render h6 { margin: 7px 0 4px; line-height: 1.25; }
  .mu-text-render p { min-height: 1em; margin: 2px 0; }
  .mu-text-render li { margin-left: 18px; }
  .mu-text-render pre { margin: 7px 0; padding: 8px; border-radius: 4px; background: #111; white-space: pre-wrap; }
`;
document.head.append(style);

function schedule(node) {
  for (const delay of [0, 100, 500]) setTimeout(() => install(node), delay);
}

app.registerExtension({
  name: "mmuuai.text-viewer.v001",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_TYPE) return;
    const originalCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function (...args) {
      const result = originalCreated?.apply(this, args);
      schedule(this);
      return result;
    };
    const originalExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (message) {
      originalExecuted?.apply(this, arguments);
      install(this);
      if (!this._muTextViewer) return;
      this._muTextViewer.state.executedRaw = textValue(message, "原始文本");
      this._muTextViewer.update();
    };
  },
  nodeCreated(node) {
    if (node.comfyClass === NODE_TYPE) schedule(node);
  },
  loadedGraphNode(node) {
    if (node.comfyClass === NODE_TYPE) schedule(node);
  },
});
