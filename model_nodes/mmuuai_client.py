import json
import os
import re
import time
import uuid
from urllib.parse import quote, urljoin, urlsplit

import requests

from .client import MAX_IMAGE_BYTES, MAX_RESPONSE_BYTES, sanitize
from ..proxy import configure_proxy


BASE_URL = "https://api.mmuu.ai"
CONNECT_TIMEOUT_SECONDS = 30


class MmuuAIHTTPError(RuntimeError):
    def __init__(self, status_code, message, code=""):
        self.status_code = status_code
        self.code = sanitize(code)
        self.upstream_message = sanitize(message)
        detail = f"{self.code}：" if self.code else ""
        super().__init__(f"mmuuai 返回 HTTP {status_code}：{detail}{self.upstream_message}")


class MmuuAIClient:
    def __init__(self, api_key, timeout, base_url=None, session=None, proxy="", proxy_username="", proxy_password=""):
        base_url = base_url or _configured_base_url()
        self.base_url = base_url.rstrip("/") + "/"
        self.wait_timeout = None if timeout == 0 else timeout
        self.timeout = (CONNECT_TIMEOUT_SECONDS, None if timeout == 0 else timeout)
        self.session = session or requests.Session()
        configure_proxy(self.session, proxy, proxy_username, proxy_password)
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def list_models(self):
        models = []
        cursor = None
        for _page in range(50):
            params = {"limit": 100}
            if cursor:
                params["cursor"] = cursor
            payload = self.get_json("v1/catalog/models", params=params)
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list):
                raise RuntimeError("mmuuai 模型目录格式无效")
            models.extend(item for item in data if isinstance(item, dict))
            cursor = payload.get("nextCursor")
            if not cursor:
                return models
        raise RuntimeError("mmuuai 模型目录分页超过安全上限")

    def resolve_model(self, model_label, model_name, aliases):
        custom = str(model_name or "").strip()
        requested = custom or aliases.get(model_label, model_label)
        models = self.list_models()
        exact_id = [item for item in models if item.get("id") == requested]
        if exact_id:
            return exact_id[0]
        candidates = [requested]
        if not custom:
            label_name = str(model_label).rsplit("｜", 1)[-1].strip()
            candidates.append(label_name)
            candidates.append(re.sub(r"（[^）]*）|\([^)]*\)", "", label_name).strip())
        for candidate in candidates:
            target = _normalized(candidate)
            exact_name = [item for item in models if _normalized(item.get("name")) == target]
            if len(exact_name) == 1:
                return exact_name[0]
            if len(exact_name) > 1:
                raise ValueError(f"mmuuai 模型名称不唯一，请填写 mdl_ 模型ID：{candidate}")
        raise ValueError(f"当前 mmuuai Key 无权使用或找不到模型：{requested}")

    def upload(self, data, media_kind, file_name, mime_type):
        headers = {
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(data)),
            "X-Mmuu-Media-Kind": media_kind,
            "X-Mmuu-File-Name": quote(file_name, safe=""),
            "X-Mmuu-Mime-Type": mime_type,
        }
        return self._request_json("POST", "v1/uploads", data=data, extra_headers=headers)

    def run_model(self, resource, task_input, poll_interval=2):
        payload = {
            "resourceId": resource["id"],
            "versionId": resource.get("versionId"),
            "input": task_input,
        }
        response = self._request_json(
            "POST",
            "v1/tasks",
            json=payload,
            extra_headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        if isinstance(response, dict) and "result" in response:
            return response
        task = response.get("task") if isinstance(response, dict) else None
        task_id = task.get("id") if isinstance(task, dict) else None
        if not isinstance(task_id, str) or not task_id:
            raise RuntimeError("mmuuai 未返回任务ID")
        return self._wait_for_result(task_id, poll_interval)

    def _wait_for_result(self, task_id, poll_interval):
        deadline = None if self.wait_timeout is None else time.monotonic() + self.wait_timeout
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                raise RuntimeError(f"等待 mmuuai 任务 {sanitize(task_id)} 超时")
            task = self.get_json(f"v1/tasks/{task_id}")
            status = str(task.get("executionStatus", "")).lower()
            if status == "succeeded":
                return self.get_json(f"v1/tasks/{task_id}/result")
            if status in ("failed", "cancelled"):
                error = task.get("error")
                if isinstance(error, dict):
                    message = error.get("message") or error.get("code")
                else:
                    message = error
                raise RuntimeError(f"mmuuai 任务失败：{sanitize(message or status)}")
            if status not in ("queued", "running", "reconciling"):
                raise RuntimeError(f"mmuuai 返回未知任务状态：{sanitize(status)}")
            time.sleep(max(1, poll_interval))

    def get_json(self, endpoint, params=None):
        return self._request_json("GET", endpoint, params=params)

    def download_image(self, value):
        current = urljoin(self.base_url, value)
        for _redirect in range(4):
            parts = urlsplit(current)
            if parts.scheme != "https" or not parts.hostname:
                raise RuntimeError("mmuuai 图片地址不是 HTTPS")
            same_origin = parts.netloc == urlsplit(self.base_url).netloc
            headers = self.headers if same_origin else {}
            response = self.session.get(
                current,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=False,
                stream=True,
            )
            if 300 <= response.status_code < 400:
                location = response.headers.get("location")
                response.close()
                if not location:
                    raise RuntimeError("图片重定向缺少地址")
                current = urljoin(current, location)
                continue
            if response.status_code >= 400:
                response.close()
                raise RuntimeError(f"图片下载返回 HTTP {response.status_code}")
            return _read_bytes(response, MAX_IMAGE_BYTES, "单张图片超过 100 MB")
        raise RuntimeError("图片下载重定向次数超过 3 次")

    def _request_json(self, method, endpoint, extra_headers=None, **kwargs):
        headers = {**self.headers, **(extra_headers or {})}
        try:
            response = self.session.request(
                method,
                urljoin(self.base_url, endpoint.lstrip("/")),
                headers=headers,
                timeout=self.timeout,
                allow_redirects=False,
                stream=True,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise RuntimeError("连接 mmuuai API 失败，提交结果未知") from exc
        if 300 <= response.status_code < 400:
            response.close()
            raise RuntimeError("mmuuai API 返回重定向，已拒绝携带密钥继续请求")
        raw = _read_bytes(response, MAX_RESPONSE_BYTES, "mmuuai 响应超过 128 MB")
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("mmuuai 返回的不是有效 JSON") from exc
        if response.status_code >= 400:
            message, code = _error_details(payload)
            raise MmuuAIHTTPError(response.status_code, message, code)
        return payload


def _read_bytes(response, maximum, too_large_message):
    chunks = []
    total = 0
    try:
        for chunk in response.iter_content(64 * 1024):
            total += len(chunk)
            if total > maximum:
                raise RuntimeError(too_large_message)
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        response.close()


def _error_details(payload):
    error = payload.get("error", payload) if isinstance(payload, dict) else payload
    if isinstance(error, dict):
        return str(error.get("message") or error.get("detail") or "请求失败"), str(
            error.get("code") or ""
        )
    return str(error), ""


def _normalized(value):
    return re.sub(r"[^\w]+", "", str(value or "").strip().casefold(), flags=re.UNICODE)


def _configured_base_url():
    value = os.environ.get("MMUUAI_API_BASE_URL", BASE_URL).strip()
    parsed = urlsplit(value)
    loopback = parsed.hostname in ("127.0.0.1", "localhost", "::1")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise RuntimeError("MMUUAI_API_BASE_URL 只允许 HTTPS 或本机回环 HTTP")
    if not parsed.hostname or parsed.username or parsed.password:
        raise RuntimeError("MMUUAI_API_BASE_URL 格式无效")
    return value
