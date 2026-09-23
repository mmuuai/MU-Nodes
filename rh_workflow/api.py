import json
import time

import requests

from ..proxy import configure_proxy


BASE_URL = "https://www.runninghub.cn"


class RHClient:
    def __init__(self, api_key, timeout=600, proxy="", proxy_username="", proxy_password=""):
        self.api_key = api_key
        self.timeout = (30, None if timeout == 0 else timeout)
        self.session = requests.Session()
        configure_proxy(self.session, proxy, proxy_username, proxy_password)
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def get_workflow(self, workflow_id):
        result = self._post_json(
            "/api/openapi/getJsonApiFormat",
            {"apiKey": self.api_key, "workflowId": workflow_id},
        )
        prompt = (result.get("data") or {}).get("prompt")
        if not isinstance(prompt, str):
            raise RuntimeError("RH 获取工作流响应中没有 prompt")
        try:
            workflow = json.loads(prompt)
        except json.JSONDecodeError as exc:
            raise RuntimeError("RH 返回的工作流 JSON 无效") from exc
        if not isinstance(workflow, dict):
            raise RuntimeError("RH 返回的工作流结构无效")
        return workflow

    def upload(self, content, filename, mime_type):
        url = BASE_URL + "/openapi/v2/media/upload/binary"
        try:
            response = self.session.post(
                url, headers=self.headers,
                files={"file": (filename, content, mime_type)}, timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise RuntimeError("RH 文件上传连接失败") from exc
        result = self._decode(response, "文件上传")
        file_name = (result.get("data") or {}).get("fileName")
        if not isinstance(file_name, str) or not file_name:
            raise RuntimeError("RH 文件上传响应中没有 fileName")
        return file_name

    def create_task(self, workflow_id, node_info_list, access_password=""):
        payload = {
            "apiKey": self.api_key,
            "workflowId": workflow_id,
            "nodeInfoList": node_info_list,
        }
        if access_password:
            payload["accessPassword"] = access_password
        result = self._post_json("/task/openapi/create", payload)
        data = result.get("data") or {}
        task_id = data.get("taskId")
        if not isinstance(task_id, str) or not task_id:
            raise RuntimeError("RH 任务提交响应中没有 taskId")
        return task_id, result

    def wait(self, task_id, interval, max_wait):
        deadline = None if max_wait == 0 else time.monotonic() + max_wait
        while deadline is None or time.monotonic() < deadline:
            result = self._post_json("/openapi/v2/query", {"taskId": task_id})
            status = str(result.get("status", "")).upper()
            if status in ("SUCCESS", "COMPLETED"):
                return status, result
            if status in ("FAILED", "ERROR", "CANCELLED", "CANCELED"):
                message = result.get("errorMessage") or result.get("message") or status
                raise RuntimeError(f"RH 工作流执行失败：{message}")
            time.sleep(interval)
        raise RuntimeError("RH 工作流等待超时，任务仍可能在平台继续运行")

    def _post_json(self, path, payload):
        try:
            response = self.session.post(
                BASE_URL + path, headers=self.headers, json=payload, timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise RuntimeError("RH 请求连接失败；任务提交结果可能未知，节点不会自动重发") from exc
        return self._decode(response, "请求")

    @staticmethod
    def _decode(response, action):
        try:
            result = response.json()
        except ValueError as exc:
            raise RuntimeError(f"RH {action}返回的不是有效 JSON（HTTP {response.status_code}）") from exc
        if response.status_code >= 400:
            message = result.get("message") or result.get("msg") or "未知错误"
            raise RuntimeError(f"RH {action}返回 HTTP {response.status_code}：{message}")
        code = result.get("code")
        if code not in (None, 0):
            message = result.get("message") or result.get("msg") or f"错误码 {code}"
            raise RuntimeError(f"RH {action}失败：{message}")
        return result
