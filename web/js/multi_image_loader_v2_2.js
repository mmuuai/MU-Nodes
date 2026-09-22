import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

const NODE_TYPE = "MmuuAIMultiImageLoaderNodeV002";
const PATHS_FIELD = "图片路径";
const MAX_IMAGES = 50;
const FIXED_OUTPUTS = 6;

function pathsFromWidget(widget) {
  return String(widget?.value || "")
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter(Boolean)
    .slice(0, MAX_IMAGES);
}

function outputNumber(output) {
  for (const value of [output?.name, output?.label, output?.localized_name]) {
    const match = /^图片(\d+)$/.exec(String(value || ""));
    const number = Number(match?.[1]);
    if (number >= 1 && number <= MAX_IMAGES) return number;
  }
  return 0;
}

function linkedDynamicOutput(node) {
  let highest = 0;
  for (let index = FIXED_OUTPUTS; index < (node.outputs || []).length; index += 1) {
    const output = node.outputs[index];
    if (output?.links?.length) highest = Math.max(highest, outputNumber(output));
  }
  for (const link of Object.values(node.graph?.links || {})) {
    if (link?.origin_id !== node.id) continue;
    highest = Math.max(highest, outputNumber(node.outputs?.[link.origin_slot]));
  }
  return highest;
}

function syncOutputs(node, imageCount) {
  if (!Array.isArray(node.outputs) || node.outputs.length < FIXED_OUTPUTS) return;
  const visibleCount = Math.min(
    MAX_IMAGES,
    Math.max(FIXED_OUTPUTS, imageCount, linkedDynamicOutput(node)),
  );
  const oldOutputs = [...node.outputs];
  const byNumber = new Map(oldOutputs.map((output) => [outputNumber(output), output]));
  const linkNumbers = new Map();
  for (const [id, link] of Object.entries(node.graph?.links || {})) {
    if (link?.origin_id === node.id) {
      linkNumbers.set(id, outputNumber(oldOutputs[link.origin_slot]));
    }
  }

  const next = oldOutputs.slice(0, FIXED_OUTPUTS);
  for (let number = FIXED_OUTPUTS + 1; number <= visibleCount; number += 1) {
    let output = byNumber.get(number);
    if (!output) {
      node.addOutput(`图片${number}`, "IMAGE");
      output = node.outputs.pop();
    }
    output.name = `图片${number}`;
    next.push(output);
  }
  node.outputs = next;

  const slots = new Map(node.outputs.map((output, index) => [outputNumber(output), index]));
  for (const [id, number] of linkNumbers) {
    const link = node.graph?.links?.[id];
    if (link && slots.has(number)) link.origin_slot = slots.get(number);
  }
  const computed = node.computeSize();
  node.setSize([Math.max(Number(node.size?.[0]) || 0, 420, computed[0]), computed[1]]);
  node.graph?.setDirtyCanvas?.(true, true);
}

function setPaths(node, widget, paths, render) {
  widget.value = paths.slice(0, MAX_IMAGES).join("\n");
  widget.callback?.(widget.value);
  render();
  syncOutputs(node, paths.length);
}

function imageUrl(path) {
  const query = new URLSearchParams({ filename: path, type: "input" });
  return `/api/view?${query.toString()}`;
}

async function uploadFile(file) {
  const body = new FormData();
  body.append("image", file);
  const response = await api.fetchApi("/upload/image", { method: "POST", body });
  if (!response.ok) throw new Error(`上传失败：HTTP ${response.status}`);
  const result = await response.json();
  return result.subfolder ? `${result.subfolder}/${result.name}` : result.name;
}

function createGallery(node, widget) {
  const root = document.createElement("div");
  root.className = "mu-multi-image-loader-v2";
  root.innerHTML = `
    <div class="mu-image-toolbar">
      <button type="button" class="mu-upload">上传图片</button>
      <button type="button" class="mu-clear">全部移除</button>
      <span class="mu-count"></span>
      <input class="mu-file-input" type="file" accept="image/*" multiple hidden>
    </div>
    <div class="mu-image-grid"></div>
  `;
  const input = root.querySelector(".mu-file-input");
  const grid = root.querySelector(".mu-image-grid");
  const count = root.querySelector(".mu-count");

  const render = () => {
    const paths = pathsFromWidget(widget);
    count.textContent = `${paths.length}/${MAX_IMAGES}`;
    grid.replaceChildren();
    paths.forEach((path, index) => {
      const item = document.createElement("div");
      item.className = "mu-image-item";
      item.draggable = true;
      item.dataset.index = String(index);
      item.innerHTML = `
        <img alt="图片${index + 1}">
        <span>${index + 1}</span>
        <button type="button" title="移除图片">×</button>
      `;
      item.querySelector("img").src = imageUrl(path);
      item.querySelector("button").onclick = () => {
        const next = pathsFromWidget(widget);
        next.splice(index, 1);
        setPaths(node, widget, next, render);
      };
      item.ondragstart = (event) => event.dataTransfer.setData("text/plain", String(index));
      item.ondragover = (event) => event.preventDefault();
      item.ondrop = (event) => {
        event.preventDefault();
        const from = Number(event.dataTransfer.getData("text/plain"));
        if (!Number.isInteger(from) || from === index) return;
        const next = pathsFromWidget(widget);
        const [moved] = next.splice(from, 1);
        next.splice(index, 0, moved);
        setPaths(node, widget, next, render);
      };
      grid.append(item);
    });
  };

  root.querySelector(".mu-upload").onclick = () => input.click();
  root.querySelector(".mu-clear").onclick = () => setPaths(node, widget, [], render);
  input.onchange = async () => {
    const paths = pathsFromWidget(widget);
    const files = [...input.files].slice(0, MAX_IMAGES - paths.length);
    input.value = "";
    try {
      for (const file of files) paths.push(await uploadFile(file));
      setPaths(node, widget, paths, render);
    } catch (error) {
      alert(error.message || String(error));
    }
  };
  render();
  return { root, render };
}

function installGallery(node) {
  if (node._muImageGalleryV2) return;
  const widget = node.widgets?.find((item) => item.name === PATHS_FIELD);
  if (!widget) return;
  Object.defineProperty(widget, "hidden", {
    configurable: true,
    get: () => true,
    set: () => {},
  });
  Object.defineProperty(widget, "type", {
    configurable: true,
    get: () => "hidden",
    set: () => {},
  });
  widget.computeSize = () => [0, 0];
  const hideTimer = setInterval(() => {
    const container = widget.element?.closest?.(".lg-node-widget") || widget.element;
    if (container) container.style.display = "none";
  }, 50);
  setTimeout(() => clearInterval(hideTimer), 1000);
  const gallery = createGallery(node, widget);
  node.addDOMWidget("图片列表", "mu-image-gallery", gallery.root, {
    serialize: false,
    getValue: () => undefined,
    setValue: () => {},
  });
  node._muImageGalleryV2 = gallery;
  syncOutputs(node, pathsFromWidget(widget).length);
}

const style = document.createElement("style");
style.textContent = `
  .lg-node-widgets:has(.mu-multi-image-loader-v2) .lg-node-widget:has(textarea[placeholder="图片路径"]) { display: none !important; }
  .mu-multi-image-loader-v2 {
    box-sizing: border-box;
    min-height: 132px;
    padding: 10px;
    border: 1px solid color-mix(in srgb, var(--fg-color) 28%, transparent);
    border-radius: 6px;
    background: color-mix(in srgb, var(--comfy-menu-bg) 78%, transparent);
    color: var(--fg-color);
  }
  .mu-multi-image-loader-v2 .mu-image-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
  .mu-multi-image-loader-v2 .mu-image-toolbar button { border: 0; border-radius: 4px; padding: 5px 10px; cursor: pointer; }
  .mu-multi-image-loader-v2 .mu-image-toolbar .mu-clear { background: #b93838; color: #fff; }
  .mu-multi-image-loader-v2 .mu-count { margin-left: auto; opacity: .75; }
  .mu-multi-image-loader-v2 .mu-image-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); align-content: start; gap: 6px; min-height: 78px; padding: 6px; border: 1px dashed color-mix(in srgb, var(--fg-color) 22%, transparent); border-radius: 4px; }
  .mu-multi-image-loader-v2 .mu-image-item { position: relative; aspect-ratio: 1; overflow: hidden; border: 1px solid #555; border-radius: 4px; cursor: grab; }
  .mu-multi-image-loader-v2 .mu-image-item img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .mu-multi-image-loader-v2 .mu-image-item span { position: absolute; left: 3px; bottom: 3px; padding: 1px 4px; border-radius: 3px; background: #000b; color: #fff; font-size: 11px; }
  .mu-multi-image-loader-v2 .mu-image-item button { position: absolute; top: 2px; right: 2px; width: 20px; height: 20px; border: 0; border-radius: 50%; background: #000b; color: #fff; cursor: pointer; }
`;
document.head.append(style);

function scheduleInstall(node) {
  for (const delay of [0, 100, 500]) setTimeout(() => installGallery(node), delay);
}

app.registerExtension({
  name: "mmuuai.multi-image-loader.v002.2",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_TYPE) return;
    const originalCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function (...args) {
      const result = originalCreated?.apply(this, args);
      scheduleInstall(this);
      return result;
    };
    const originalConnectionsChange = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function (...args) {
      const result = originalConnectionsChange?.apply(this, args);
      const widget = this.widgets?.find((item) => item.name === PATHS_FIELD);
      setTimeout(() => syncOutputs(this, pathsFromWidget(widget).length));
      return result;
    };
  },
  nodeCreated(node) {
    if (node.comfyClass === NODE_TYPE) scheduleInstall(node);
  },
  loadedGraphNode(node) {
    if (node.comfyClass === NODE_TYPE) scheduleInstall(node);
  },
});
