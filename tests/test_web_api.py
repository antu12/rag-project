import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from rag_cli.web_api import app, parse_progress, update_dotenv


class WebApiTests(unittest.TestCase):
    def test_health_and_inngest_are_served_by_one_app(self):
        client = TestClient(app)
        self.assertEqual(200, client.get("/api/v1/health").status_code)
        response = client.get("/api/inngest")
        self.assertEqual(200, response.status_code)

    def test_progress_parser_exposes_chunk_wait_and_retry(self):
        stage, status, fields = parse_progress("Embedding chunk 3/9 hit retryable error; waiting 4.5s before retry 2/20.")
        self.assertEqual("embedding", stage)
        self.assertEqual("retrying", status)
        self.assertEqual(3, fields["current"])
        self.assertEqual(9, fields["total"])
        self.assertEqual(4.5, fields["wait_seconds"])
        self.assertEqual(2, fields["retry_attempt"])
        self.assertEqual(20, fields["retry_limit"])

    def test_chunk_progress_fields_can_replace_file_progress(self):
        _stage, _status, fields = parse_progress("Embedding chunk 3/9 with Gemini.")
        current = fields.pop("current", 0)
        total = fields.pop("total", 1)

        self.assertEqual(3, current)
        self.assertEqual(9, total)
        self.assertNotIn("current", fields)
        self.assertNotIn("total", fields)

    def test_dotenv_update_preserves_comments_and_unrelated_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text("# keep me\nRAG_STORE=qdrant\nOPENAI_API_KEY=old\n", encoding="utf-8")
            with patch("rag_cli.web_api.PROJECT_DIR", Path(tmp)):
                update_dotenv({"OPENAI_API_KEY": "replacement"})
            content = env.read_text(encoding="utf-8")
            self.assertIn("# keep me", content)
            self.assertIn("RAG_STORE=qdrant", content)
            self.assertIn("OPENAI_API_KEY=replacement", content)
            self.assertNotIn("old", content)


if __name__ == "__main__":
    unittest.main()
