import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "mu_nodes_client_test"
spec = importlib.util.spec_from_file_location(
    PACKAGE,
    ROOT / "__init__.py",
    submodule_search_locations=[str(ROOT)],
)
plugin = importlib.util.module_from_spec(spec)
sys.modules[PACKAGE] = plugin
spec.loader.exec_module(plugin)


class Response:
    def __init__(self, status, payload, headers=None):
        self.status_code = status
        self.payload = payload
        self.headers = headers or {}
        self.closed = False

    def iter_content(self, _size):
        yield json.dumps(self.payload).encode("utf-8")

    def close(self):
        self.closed = True


class Session:
    def __init__(self, routes):
        self.routes = list(routes)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        expected_method, suffix, response = self.routes.pop(0)
        if method != expected_method or not url.endswith(suffix):
            raise AssertionError(f"unexpected request: {method} {url}")
        return response


class MmuuAIClientTests(unittest.TestCase):
    def test_base_url_override_only_allows_https_or_loopback_http(self):
        client_module = plugin.model_nodes.mmuuai_client
        original = os.environ.get("MMUUAI_API_BASE_URL")
        try:
            os.environ["MMUUAI_API_BASE_URL"] = "http://127.0.0.1:3000"
            self.assertEqual(client_module._configured_base_url(), "http://127.0.0.1:3000")
            os.environ["MMUUAI_API_BASE_URL"] = "http://api.example.com"
            with self.assertRaisesRegex(RuntimeError, "只允许 HTTPS"):
                client_module._configured_base_url()
        finally:
            if original is None:
                os.environ.pop("MMUUAI_API_BASE_URL", None)
            else:
                os.environ["MMUUAI_API_BASE_URL"] = original

    def test_catalog_resolves_current_name_and_custom_public_id(self):
        resources = [
            {"id": "mdl_abcdefghijklmnop", "name": "GPT 5.6 Luna", "versionId": "mdl_abcdefghijklmnop:v1"}
        ]
        session = Session([
            ("GET", "v1/catalog/models", Response(200, {"data": resources, "nextCursor": None})),
            ("GET", "v1/catalog/models", Response(200, {"data": resources, "nextCursor": None})),
        ])
        client = plugin.model_nodes.mmuuai_client.MmuuAIClient("secret", 60, "https://api.test", session)

        by_label = client.resolve_model("OpenAI｜LLM｜GPT-5.6 Luna", "", {"OpenAI｜LLM｜GPT-5.6 Luna": "gpt-5.6-luna"})
        by_id = client.resolve_model("ignored", "mdl_abcdefghijklmnop", {})

        self.assertEqual(by_label["id"], "mdl_abcdefghijklmnop")
        self.assertEqual(by_id["name"], "GPT 5.6 Luna")

    def test_upload_uses_binary_contract_and_metadata_headers(self):
        session = Session([
            ("POST", "v1/uploads", Response(201, {"ref": "upl_payload.v1.signature"})),
        ])
        client = plugin.model_nodes.mmuuai_client.MmuuAIClient("secret", 60, "https://api.test", session)

        result = client.upload(b"png", "image", "人物 1.png", "image/png")

        self.assertEqual(result["ref"], "upl_payload.v1.signature")
        headers = session.calls[0][2]["headers"]
        self.assertEqual(headers["X-Mmuu-Media-Kind"], "image")
        self.assertEqual(headers["X-Mmuu-Mime-Type"], "image/png")
        self.assertEqual(headers["Content-Length"], "3")
        self.assertNotIn("人物", headers["X-Mmuu-File-Name"])

    def test_async_task_submits_once_then_polls_and_reads_result(self):
        task_id = "tsk_abcdefghijklmnop"
        session = Session([
            ("POST", "v1/tasks", Response(202, {"task": {"id": task_id}})),
            ("GET", f"v1/tasks/{task_id}", Response(200, {"executionStatus": "running"})),
            ("GET", f"v1/tasks/{task_id}", Response(200, {"executionStatus": "succeeded"})),
            ("GET", f"v1/tasks/{task_id}/result", Response(200, {"taskId": task_id, "result": {"text": "ok"}})),
        ])
        client = plugin.model_nodes.mmuuai_client.MmuuAIClient("secret", 60, "https://api.test", session)

        result = client.run_model(
            {"id": "mdl_abcdefghijklmnop", "versionId": "mdl_abcdefghijklmnop:v1"},
            {"prompt": "test"},
            poll_interval=0,
        )

        self.assertEqual(result["result"]["text"], "ok")
        self.assertEqual(sum(method == "POST" for method, _url, _kwargs in session.calls), 1)
        self.assertIn("Idempotency-Key", session.calls[0][2]["headers"])

    def test_parameter_mapping_only_sends_advertised_fields_and_clamps_range(self):
        resource = {
            "inputCapabilities": {
                "parameters": [
                    {"name": "temperature", "valueType": "number", "range": {"min": 0, "max": 1, "step": 0.1}, "options": []},
                    {"name": "reasoningEffort", "valueType": "enum", "options": [{"label": "高", "value": "high"}]},
                ]
            }
        }
        parameters = plugin.model_nodes.mmuuai_parameters.build_parameters(
            resource,
            [
                (("temperature",), 2, "number"),
                (("reasoning_effort", "reasoningEffort"), "高", "semantic"),
                (("max_tokens",), 128000, "number"),
            ],
        )

        self.assertEqual(parameters, {"temperature": 1, "reasoningEffort": "high"})


if __name__ == "__main__":
    unittest.main()
