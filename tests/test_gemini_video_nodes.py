import io
import unittest
from unittest.mock import Mock, patch

from test_registry import plugin


class VideoSource:
    def __init__(self):
        self.stream = io.BytesIO(b"small video bytes")

    def get_stream_source(self):
        return self.stream

    def get_container_format(self):
        return "mp4"


class GeminiVideoNodeTests(unittest.TestCase):
    def test_upload_uses_resumable_google_api_with_optional_proxy_and_waits_active(self):
        module = plugin.model_nodes.gemini_video_file
        session = Mock()
        session.proxies = {}
        session.post.side_effect = [
            Mock(ok=True, headers={"x-goog-upload-url": "https://upload.google.test/session"}),
            Mock(ok=True, json=lambda: {"file": {
                "uri": "https://generativelanguage.googleapis.com/v1beta/files/1",
                "name": "files/1", "mimeType": "video/mp4", "state": "PROCESSING",
            }}),
        ]
        session.get.return_value = Mock(ok=True, json=lambda: {
            "uri": "https://generativelanguage.googleapis.com/v1beta/files/1",
            "name": "files/1", "mimeType": "video/mp4", "state": "ACTIVE",
        })
        video = VideoSource()
        with patch.object(module.time, "sleep"):
            result = module.upload_gemini_video(video, "google-key", "http://127.0.0.1:7890", 20, session)

        self.assertEqual((result.uri, result.mime_type, result.name), (
            "https://generativelanguage.googleapis.com/v1beta/files/1", "video/mp4", "files/1",
        ))
        self.assertEqual(session.proxies, {
            "http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890",
        })
        self.assertEqual(session.post.call_args_list[0].kwargs["headers"]["x-goog-api-key"], "google-key")
        self.assertEqual(session.post.call_args_list[1].kwargs["headers"]["X-Goog-Upload-Command"], "upload, finalize")
        self.assertEqual(session.get.call_args.kwargs["headers"]["x-goog-api-key"], "google-key")
        self.assertEqual(video.stream.tell(), 0)

    def test_upload_rejects_bad_proxy_and_empty_key(self):
        module = plugin.model_nodes.gemini_video_file
        with self.assertRaisesRegex(ValueError, "Google Gemini API Key"):
            module.upload_gemini_video(VideoSource(), "")
        with self.assertRaisesRegex(ValueError, "代理地址"):
            module.upload_gemini_video(VideoSource(), "google-key", "socks5://localhost:1080")
        with self.assertRaisesRegex(ValueError, "同时填写"):
            module.upload_gemini_video(
                VideoSource(), "google-key", "http://localhost:3128", proxy_username="proxy-user",
            )
        with self.assertRaisesRegex(ValueError, "也需要填写代理地址"):
            module.upload_gemini_video(
                VideoSource(), "google-key", proxy_username="proxy-user", proxy_password="secret",
            )

    def test_upload_applies_basic_proxy_auth_and_masks_the_password_widget(self):
        module = plugin.model_nodes.gemini_video_file
        session = Mock()
        session.proxies = {}
        session.post.side_effect = [
            Mock(ok=True, headers={"x-goog-upload-url": "https://upload.google.test/session"}),
            Mock(ok=True, json=lambda: {"file": {
                "uri": "https://generativelanguage.googleapis.com/v1beta/files/1",
                "name": "files/1", "mimeType": "video/mp4", "state": "ACTIVE",
            }}),
        ]

        module.upload_gemini_video(
            VideoSource(), "google-key", "https://proxy.example:8443", 20, session,
            proxy_username="proxy user", proxy_password="p@ss:/word",
        )

        self.assertEqual(session.proxies, {
            "http": "https://proxy%20user:p%40ss%3A%2Fword@proxy.example:8443",
            "https": "https://proxy%20user:p%40ss%3A%2Fword@proxy.example:8443",
        })
        session.mount.assert_called_once()
        self.assertEqual(session.mount.call_args.args[0], "https://")
        self.assertIsInstance(session.mount.call_args.args[1], module._SystemTrustProxyAdapter)
        schema = plugin.NODE_CLASS_MAPPINGS["MmuuAIGeminiVideoUploadNodeV001"].INPUT_TYPES()["required"]
        self.assertTrue(schema["代理密码（可选）"][1]["password"])

    def test_https_proxy_certificate_uses_validating_system_trust(self):
        module = plugin.model_nodes.gemini_video_file
        with patch.object(module.HTTPAdapter, "proxy_manager_for", return_value="manager") as parent:
            adapter = module._SystemTrustProxyAdapter()
            self.assertEqual(adapter.proxy_manager_for("https://proxy.example:8443"), "manager")

        context = parent.call_args.kwargs["proxy_ssl_context"]
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, module.ssl.CERT_REQUIRED)

    def test_proxy_connection_error_does_not_reveal_credentials(self):
        module = plugin.model_nodes.gemini_video_file
        session = Mock()
        session.proxies = {}
        session.post.side_effect = module.requests.ConnectionError("https://proxy-user:secret@proxy.example")

        with self.assertRaises(RuntimeError) as error:
            module.upload_gemini_video(
                VideoSource(), "google-key", "https://proxy.example:8443", session=session,
                proxy_username="proxy-user", proxy_password="secret",
            )

        self.assertNotIn("secret", str(error.exception))

    def test_new_google_video_llm_sends_file_reference_to_selected_upstream(self):
        node_type = plugin.NODE_CLASS_MAPPINGS["MmuuAIGeminiVideoLLMNodeV001"]
        node = node_type()
        values = {
            "Google文件": plugin.model_nodes.gemini_video_file.GeminiFile(
                "google-file-uri", "video/mp4", "files/1",
            ),
            "URL": "https://api.mmuu.uk", "自定义URL": "", "模型名称": "gemini-test",
            "key": "upstream-key", "系统提示词": "", "提示词": "总结视频",
            "温度": 0.3, "思考强度": "自动（模型默认）", "最大令牌数": 4096,
            "超时时间（秒，0不限）": 30,
        }
        client = Mock()
        client.post_sse.return_value = [{"candidates": [{"content": {"parts": [{"text": "总结"}]}}]}]
        with patch.object(plugin.model_nodes.gemini_video_llm_node, "UKClient", return_value=client):
            text, _raw = node.execute(**values)

        self.assertEqual(text, "总结")
        endpoint, payload = client.post_sse.call_args.args
        self.assertEqual(endpoint, "v1beta/models/gemini-test:streamGenerateContent?alt=sse")
        self.assertEqual(payload["contents"][0]["parts"][0]["fileData"], {
            "mimeType": "video/mp4", "fileUri": "google-file-uri",
        })
        self.assertEqual(payload["contents"][0]["parts"][1]["text"], "总结视频")


if __name__ == "__main__":
    unittest.main()
