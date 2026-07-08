import unittest

from rag_cli.config import ConfigError, effective_config


class ConfigTests(unittest.TestCase):
    def test_option_overrides_env_and_defaults(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"RAG_PROVIDER": "gemini"}), patch(
            "rag_cli.config.CONFIG_PATH", Path(tmp) / "missing.json"
        ):
            cfg = effective_config({"provider": "openai", "top_k": 3})

        self.assertEqual(cfg.provider, "openai")
        self.assertEqual(cfg.get("top_k"), 3)

    def test_chunk_overlap_must_be_smaller_than_chunk_size(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp, patch("rag_cli.config.CONFIG_PATH", Path(tmp) / "missing.json"):
            with self.assertRaises(ConfigError):
                effective_config({"chunk_size": 100, "chunk_overlap": 100})

    def test_gemini_embedding_delay_accepts_float(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp, patch("rag_cli.config.CONFIG_PATH", Path(tmp) / "missing.json"):
            cfg = effective_config({"gemini_embedding_delay_seconds": "1.25"})

        self.assertEqual(cfg.get("gemini_embedding_delay_seconds"), 1.25)

    def test_gemini_embedding_retries_must_be_positive(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp, patch("rag_cli.config.CONFIG_PATH", Path(tmp) / "missing.json"):
            with self.assertRaises(ConfigError):
                effective_config({"gemini_embedding_retries": 0})

    def test_dotenv_is_loaded_without_overwriting_shell_env(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"RAG_PROVIDER": "openai"}, clear=True):
            project_dir = Path(tmp)
            (project_dir / ".env").write_text("RAG_PROVIDER=gemini\nGOOGLE_API_KEY=from-file\n", encoding="utf-8")
            with patch("rag_cli.config.PROJECT_DIR", project_dir), patch(
                "rag_cli.config.CONFIG_PATH", project_dir / ".rag" / "config.json"
            ):
                cfg = effective_config()

            self.assertEqual(cfg.provider, "openai")
            import os

            self.assertEqual(os.environ["GOOGLE_API_KEY"], "from-file")


if __name__ == "__main__":
    unittest.main()
