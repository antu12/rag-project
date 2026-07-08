import unittest

from rag_cli.providers import BaseProvider


class DummyProvider(BaseProvider):
    name = "dummy"

    def embed_texts(self, texts):
        return []

    def generate(self, question, context):
        raise NotImplementedError


class RetryDelayTests(unittest.TestCase):
    def test_retry_delay_parser_handles_gemini_error_text(self):
        provider = object.__new__(DummyProvider)
        exc = Exception("{'details': [{'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '52s'}]}")

        self.assertEqual(provider._retry_delay_seconds(exc), 52.0)


if __name__ == "__main__":
    unittest.main()
