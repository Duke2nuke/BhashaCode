"""Tests for BhashaCode. No API key or network needed.

Run:  python -m unittest discover -s tests -v
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bharatcode_client import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    BharatCodeError,
    explain_code,
    language_name,
    mock_explain,
)

SAMPLE = (
    "def total(prices):\n"
    "    total = 0\n"
    "    for price in prices:\n"
    "        total = total + price\n"
    "    return total\n"
)


def fake_live_transport(url, headers, body):
    """Stand-in for the BharatCode API: asserts the request shape, then
    returns a canned Chat Completions response."""
    assert url == f"{DEFAULT_BASE_URL}/chat/completions", url
    assert headers["Authorization"] == "Bearer fake-test-key"
    assert body["model"] == DEFAULT_MODEL
    assert body["messages"][0]["role"] == "system"
    assert "Hindi" in body["messages"][0]["content"]
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "summary": "Test summary in Hindi.",
                            "breakdown": [
                                {
                                    "line": "def total(prices):",
                                    "explanation": "Defines a function.",
                                }
                            ],
                        }
                    )
                }
            }
        ]
    }


class TestMockExplain(unittest.TestCase):
    def test_mock_explain_returns_summary_and_breakdown(self):
        result = mock_explain(SAMPLE, "hi")
        self.assertEqual(result["mode"], "mock")
        self.assertEqual(result["language"], "hi")
        self.assertEqual(result["language_name"], "Hindi")
        self.assertIn("MOCK", result["summary"])
        self.assertTrue(result["breakdown"])
        # One entry per non-empty line.
        self.assertEqual(len(result["breakdown"]), 5)
        lines = [item["line"] for item in result["breakdown"]]
        self.assertIn("def total(prices):", lines)
        self.assertIn("return total", lines)

    def test_mock_explain_labels_no_key_honestly(self):
        result = explain_code(SAMPLE, "ta")
        self.assertEqual(result["mode"], "mock")
        self.assertIn("no BharatCode key set", result["summary"])


class TestLanguages(unittest.TestCase):
    def test_all_ten_languages_accepted(self):
        for code in ("en", "hi", "ta", "te", "bn", "mr", "kn", "ml", "gu", "pa"):
            self.assertTrue(language_name(code))
            self.assertEqual(explain_code("x = 1", code)["language"], code)

    def test_unknown_language_rejected(self):
        with self.assertRaises(ValueError):
            language_name("xx")
        with self.assertRaises(ValueError):
            mock_explain("x = 1", "xx")


class TestValidation(unittest.TestCase):
    def test_empty_code_rejected(self):
        for bad in ("", "   ", "\n\n"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                mock_explain(bad, "en")
            with self.assertRaises(ValueError, msg=repr(bad)):
                explain_code(bad, "en")

    def test_oversized_code_rejected(self):
        with self.assertRaises(ValueError):
            mock_explain("x = 1\n" * 500, "en")


class TestLiveClientPath(unittest.TestCase):
    def test_client_uses_fake_transport_and_parses_json(self):
        result = explain_code(
            SAMPLE, "hi", api_key="fake-test-key", transport=fake_live_transport
        )
        self.assertEqual(result["mode"], "live")
        self.assertEqual(result["model"], DEFAULT_MODEL)
        self.assertEqual(result["summary"], "Test summary in Hindi.")
        self.assertEqual(len(result["breakdown"]), 1)
        self.assertEqual(result["breakdown"][0]["line"], "def total(prices):")

    def test_client_error_surfaces_as_bharatcode_error(self):
        def failing_transport(url, headers, body):
            err = BharatCodeError("BharatCode API returned HTTP 401: bad key")
            err.status = 401
            raise err

        with self.assertRaises(BharatCodeError):
            explain_code(SAMPLE, "en", api_key="bad-key", transport=failing_transport)


class TestFlaskApp(unittest.TestCase):
    def setUp(self):
        os.environ.pop("BHARATCODE_API_KEY", None)
        from app import app

        app.testing = True
        self.client = app.test_client()

    def test_home_page_loads_with_form(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("BhashaCode", html)
        self.assertIn('name="code"', html)
        self.assertIn('name="language"', html)
        self.assertIn("MOCK", html)

    def test_health_endpoint(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok", "mode": "mock"})

    def test_explain_json_mock(self):
        resp = self.client.post(
            "/explain", json={"code": SAMPLE, "language": "hi"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["mode"], "mock")
        self.assertEqual(data["language"], "hi")
        self.assertTrue(data["breakdown"])

    def test_explain_empty_code_is_400(self):
        resp = self.client.post("/explain", json={"code": "  ", "language": "en"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())


if __name__ == "__main__":
    unittest.main()
