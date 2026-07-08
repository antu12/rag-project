import unittest


class InngestAppTests(unittest.TestCase):
    def test_invalid_signing_key_is_detected(self):
        from rag_cli.inngest_payloads import is_valid_inngest_signing_key

        self.assertFalse(is_valid_inngest_signing_key("signkey-test-rag-cli-local"))
        self.assertTrue(is_valid_inngest_signing_key("signkey-test-00000000000000000000000000000000"))

    def test_inngest_endpoint_syncs_in_dev_mode(self):
        try:
            from fastapi.testclient import TestClient
        except ModuleNotFoundError:
            self.skipTest("FastAPI is not installed in this test environment.")
        from rag_cli.inngest_app import app

        response = TestClient(app).get("/api/inngest")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["function_count"], 1)
        self.assertEqual(response.json()["mode"], "dev")


if __name__ == "__main__":
    unittest.main()
