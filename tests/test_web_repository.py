import tempfile
import unittest
from pathlib import Path

from rag_cli.web_repository import WebRepository


class WebRepositoryTests(unittest.TestCase):
    def test_jobs_events_and_terminal_state_are_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = WebRepository(Path(tmp) / "metadata.sqlite3")
            job = repo.create_job("research", "ingestion", "synchronous", {"provider": "openai"})
            repo.update_job(job["id"], "running", current=1, total=2)
            event = repo.add_event(job["id"], "embedding", "running", "Embedding chunk 1/2", current=1, total=2)
            repo.update_job(job["id"], "succeeded", current=2, total=2, result={"added": 1})
            repo.update_job(job["id"], "failed", error={"message": "late update"})

            saved = repo.get_job(job["id"])
            self.assertEqual("succeeded", saved["status"])
            self.assertEqual({"added": 1}, saved["result"])
            self.assertEqual(2, event["sequence"])
            self.assertEqual(2, len(repo.list_events(job["id"])))
            repo.close()

    def test_chat_turns_are_independent_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = WebRepository(Path(tmp) / "metadata.sqlite3")
            session = repo.create_session("research")
            first = repo.create_turn(session["id"], "First question", {"top_k": 5})
            second = repo.create_turn(session["id"], "Independent question", {"top_k": 3})
            repo.finish_turn(first["id"], answer="Answer", citations=["notes.md chunk 0"])

            turns = repo.list_turns(session["id"])
            self.assertEqual(["First question", "Independent question"], [turn["question"] for turn in turns])
            self.assertNotIn("First question", turns[1]["question"])
            self.assertEqual("running", repo.get_turn(second["id"])["status"])
            repo.close()

    def test_upload_lookup_is_scoped_to_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = WebRepository(Path(tmp) / "metadata.sqlite3")
            upload = repo.add_upload("one", "notes.txt", "managed.txt", "txt", 4, "abcd")
            with self.assertRaises(KeyError):
                repo.get_upload("two", upload["id"])
            repo.close()


if __name__ == "__main__":
    unittest.main()
