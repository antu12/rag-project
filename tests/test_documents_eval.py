import tempfile
import unittest
from pathlib import Path

from rag_cli.documents import discover_supported, file_sha256, load_document
from rag_cli.operations import load_eval_file


class DocumentEvalTests(unittest.TestCase):
    def test_document_discovery_hash_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            docs.mkdir()
            note = docs / "note.md"
            note.write_text("# Hello\nworld", encoding="utf-8")
            ignored = docs / "image.png"
            ignored.write_bytes(b"not used")

            supported, skipped = discover_supported(docs)
            loaded = load_document(supported[0], docs)

            self.assertEqual(supported, [note])
            self.assertEqual(skipped[0].path, ignored)
            self.assertEqual(loaded.relative_path, "note.md")
            self.assertEqual(loaded.file_hash, file_sha256(note))

    def test_eval_file_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            eval_file = Path(tmp) / "eval.json"
            eval_file.write_text('{"tests":[{"question":"Q?","expected_sources":["note.md"]}]}', encoding="utf-8")

            tests = load_eval_file(eval_file)

            self.assertEqual(tests[0]["question"], "Q?")

    def test_eval_file_rejects_missing_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            eval_file = Path(tmp) / "bad.json"
            eval_file.write_text('{"nope":[]}', encoding="utf-8")

            with self.assertRaises(ValueError):
                load_eval_file(eval_file)


if __name__ == "__main__":
    unittest.main()
