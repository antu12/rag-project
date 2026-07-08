import unittest
from pathlib import Path

from rag_cli.config import effective_config
from rag_cli.inngest_payloads import (
    INGEST_EVENT_NAME,
    assert_secret_safe_event,
    build_ingest_event,
    build_ingest_event_payload,
    validate_ingest_event_data,
)


class InngestPayloadTests(unittest.TestCase):
    def test_build_ingest_event_payload_contains_required_fields(self):
        cfg = effective_config({"provider": "gemini", "store": "qdrant"})

        payload = build_ingest_event_payload(Path("data/raw"), "research", cfg, force=True)
        event = build_ingest_event(payload)

        self.assertEqual(event["name"], INGEST_EVENT_NAME)
        self.assertEqual(event["data"]["workspace"], "research")
        self.assertEqual(event["data"]["path"], "data/raw")
        self.assertEqual(event["data"]["provider"], "gemini")
        self.assertEqual(event["data"]["store"], "qdrant")
        self.assertEqual(event["data"]["embedding_model"], "gemini-embedding-2")
        self.assertEqual(event["data"]["generation_model"], "gemini-3.5-flash")
        self.assertTrue(event["data"]["force"])

    def test_validate_ingest_event_data_rejects_missing_fields(self):
        with self.assertRaises(ValueError):
            validate_ingest_event_data({"workspace": "research"})

    def test_event_payload_is_secret_safe(self):
        cfg = effective_config({"provider": "gemini", "store": "qdrant"})
        event = build_ingest_event(build_ingest_event_payload(Path("data/raw"), "research", cfg, force=False))

        assert_secret_safe_event(event)
        self.assertNotIn("API_KEY", repr(event))

    def test_secret_safe_event_rejects_secret_like_fields(self):
        with self.assertRaises(ValueError):
            assert_secret_safe_event({"name": "rag/ingest.requested", "data": {"api_key": "secret"}})


if __name__ == "__main__":
    unittest.main()
