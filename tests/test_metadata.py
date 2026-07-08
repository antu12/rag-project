import unittest

from rag_cli.errors import WorkspaceError
from rag_cli.metadata import MetadataStore


class MetadataTests(unittest.TestCase):
    def test_workspace_create_list_and_active(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            db = MetadataStore(Path(tmp) / "meta.sqlite3")

            db.create_workspace("research")
            db.create_workspace("company_docs")
            db.set_active_workspace("company_docs")

            self.assertEqual([workspace.name for workspace in db.list_workspaces()], ["company_docs", "research"])
            self.assertEqual(db.active_workspace(), "company_docs")
            self.assertEqual(db.resolve_workspace(None, no_interactive=True), "company_docs")
            db.close()

    def test_workspace_name_validation(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            db = MetadataStore(Path(tmp) / "meta.sqlite3")
            with self.assertRaises(WorkspaceError):
                db.create_workspace("../unsafe")
            db.close()

    def test_dimension_mismatch_fails(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            db = MetadataStore(Path(tmp) / "meta.sqlite3")
            db.create_workspace("research")
            db.set_namespace("research", "pgvector", "openai", "text-embedding-3-small", 1536, "research")

            with self.assertRaises(WorkspaceError):
                db.assert_dimensions("research", "pgvector", "other-model", 768)
            db.close()


if __name__ == "__main__":
    unittest.main()
