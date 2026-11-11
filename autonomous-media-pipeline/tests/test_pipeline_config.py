import unittest

from pipeline_config import has_youtube_credentials, resolve_privacy_status


class PipelineConfigTests(unittest.TestCase):
    def test_missing_oauth_credentials_are_not_publishable(self):
        self.assertFalse(has_youtube_credentials({}))

    def test_legacy_token_json_is_a_complete_credential_set(self):
        self.assertTrue(has_youtube_credentials({"YOUTUBE_TOKEN_JSON": "{\"refresh_token\":\"x\"}"}))

    def test_refresh_token_requires_both_oauth_client_values(self):
        base = {"YOUTUBE_REFRESH_TOKEN": "refresh"}
        self.assertFalse(has_youtube_credentials(base))
        self.assertFalse(has_youtube_credentials({**base, "YOUTUBE_CLIENT_ID": "id"}))
        self.assertTrue(has_youtube_credentials({**base, "YOUTUBE_CLIENT_ID": "id", "YOUTUBE_CLIENT_SECRET": "secret"}))

    def test_privacy_defaults_to_private(self):
        self.assertEqual(resolve_privacy_status({}), "private")

    def test_privacy_status_is_validated(self):
        self.assertEqual(resolve_privacy_status({"YOUTUBE_PRIVACY_STATUS": "unlisted"}), "unlisted")
        with self.assertRaises(ValueError):
            resolve_privacy_status({"YOUTUBE_PRIVACY_STATUS": "public-ish"})


if __name__ == "__main__":
    unittest.main()
