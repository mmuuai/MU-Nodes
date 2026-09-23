import importlib
import unittest

from test_registry import plugin


class InterfaceProxyTests(unittest.TestCase):
    def test_all_api_nodes_expose_same_optional_proxy_controls(self):
        labels = ("代理地址（可选）", "代理用户名（可选）", "代理密码（可选）")
        api_categories = {"MU/接口"}
        nodes = [
            (node_id, node_type)
            for node_id, node_type in plugin.NODE_CLASS_MAPPINGS.items()
            if getattr(node_type, "CATEGORY", "") in api_categories
        ]
        rh_node = importlib.import_module(f"{plugin.__name__}.rh_workflow.node").MmuuAIRHWorkflowNode
        nodes.append(("MmuuAIRHWorkflowNodeV001", rh_node))

        self.assertGreater(len(nodes), 0)
        for node_id, node_type in nodes:
            with self.subTest(node=node_id):
                schema = node_type.INPUT_TYPES()
                fields = {**schema.get("required", {}), **schema.get("optional", {})}
                self.assertTrue(set(labels).issubset(fields))
                self.assertTrue(fields[labels[2]][1]["password"])

    def test_google_video_nodes_use_short_names_in_interface_category(self):
        node_ids = (
            "MmuuAIGeminiVideoUploadNodeV001",
            "MmuuAIGeminiVideoLLMNodeV001",
        )
        self.assertEqual(
            [plugin.NODE_DISPLAY_NAME_MAPPINGS[node_id] for node_id in node_ids],
            ["MU｜G视频上传", "MU｜G视频LLM模型"],
        )
        self.assertTrue(all(plugin.NODE_CLASS_MAPPINGS[node_id].CATEGORY == "MU/接口" for node_id in node_ids))

    def test_shared_clients_apply_proxy_and_keep_credentials_encoded(self):
        proxy = "https://proxy.example:8443"
        auth_proxy = "https://proxy%20user:p%40ss%3A%2Fword@proxy.example:8443"

        uk = plugin.model_nodes.client.UKClient(
            "api-key", 60, "https://api.test", proxy, "proxy user", "p@ss:/word",
        )
        self.addCleanup(uk.session.close)
        self.assertEqual(uk.session.proxies, {"http": auth_proxy, "https": auth_proxy})

        mmuu_session = plugin.model_nodes.mmuuai_client.requests.Session()
        self.addCleanup(mmuu_session.close)
        plugin.model_nodes.mmuuai_client.MmuuAIClient(
            "api-key", 60, "https://api.test", mmuu_session,
            proxy, "proxy user", "p@ss:/word",
        )
        self.assertEqual(mmuu_session.proxies, {"http": auth_proxy, "https": auth_proxy})

        rh_api = importlib.import_module(f"{plugin.__name__}.rh_workflow.api")
        rh = rh_api.RHClient(
            "api-key", 60, proxy, "proxy user", "p@ss:/word",
        )
        self.addCleanup(rh.session.close)
        self.assertEqual(rh.session.proxies, {"http": auth_proxy, "https": auth_proxy})

    def test_empty_proxy_is_direct_and_invalid_proxy_credentials_fail_closed(self):
        session = plugin.model_nodes.mmuuai_client.requests.Session()
        self.addCleanup(session.close)
        plugin.proxy.configure_proxy(session)
        self.assertEqual(session.proxies, {})

        for proxy, username, password in (
            ("socks5://proxy.example:1080", "", ""),
            ("http://proxy.example:3128", "proxy-user", ""),
            ("", "proxy-user", "secret"),
            ("http://proxy-user:secret@proxy.example:3128", "", ""),
        ):
            with self.subTest(proxy=proxy, username=bool(username), password=bool(password)):
                with self.assertRaises(ValueError):
                    plugin.proxy.configure_proxy(session, proxy, username, password)

    def test_proxy_auth_is_redacted_from_errors(self):
        error = "connection to https://proxy-user:p%40ss@proxy.example:8443 failed"
        safe = plugin.proxy.redact_proxy_credentials(error)
        self.assertNotIn("proxy-user", safe)
        self.assertNotIn("p%40ss", safe)
        self.assertIn("https://[REDACTED]@proxy.example:8443", safe)


if __name__ == "__main__":
    unittest.main()
