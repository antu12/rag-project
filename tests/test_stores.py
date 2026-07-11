import unittest
from types import SimpleNamespace

from rag_cli.stores import QdrantStore


class QdrantStoreTests(unittest.TestCase):
    def test_search_uses_query_points_and_reads_points(self):
        calls = []
        point = SimpleNamespace(
            id="vector-1",
            score=0.91,
            payload={
                "text": "Relevant text",
                "source_path": "notes.md",
                "chunk_index": 2,
                "page_number": None,
            },
        )

        class Client:
            def query_points(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(points=[point])

        store = object.__new__(QdrantStore)
        store.client = Client()
        hits = store.search("rag_workspace", [0.1, 0.2], 5)

        self.assertEqual("rag_workspace", calls[0]["collection_name"])
        self.assertEqual([0.1, 0.2], calls[0]["query"])
        self.assertTrue(calls[0]["with_payload"])
        self.assertEqual("notes.md", hits[0].source_path)
        self.assertEqual(0.91, hits[0].score)


if __name__ == "__main__":
    unittest.main()
