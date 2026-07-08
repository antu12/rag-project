import unittest

from rag_cli.chunking import chunk_pages


class ChunkingTests(unittest.TestCase):
    def test_chunk_pages_skips_empty_text_and_overlaps(self):
        chunks = chunk_pages([("alpha beta gamma delta", None), ("   ", 2)], chunk_size=10, chunk_overlap=2)

        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0].text, "alpha beta")
        self.assertTrue(chunks[1].text.startswith("ta"))
        self.assertTrue(all(chunk.text.strip() for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
