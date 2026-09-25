"""Credentials in the runtime config file are encrypted at rest (config_crypto + backend_config)."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

import backend_config
import config_crypto


class ConfigEncryptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "config.json"
        self.key = Fernet.generate_key().decode()
        # Only read our temp file, not the developer's real config layers.
        patcher = patch.object(backend_config, "get_config_read_paths", lambda: [self.path])
        patcher.start()
        self.addCleanup(patcher.stop)
        shared = patch.object(backend_config, "CONFIGS_DIR", Path(self.tmp.name) / "no-configs")
        shared.start()
        self.addCleanup(shared.stop)

    def env(self, **values):
        return patch.dict(os.environ, {"APP_CONFIG_FILE": str(self.path), **values})

    def test_secrets_are_encrypted_on_disk_and_readable(self):
        with self.env(SECRETS_ENCRYPTION_KEY=self.key, APP_ENV="production"):
            returned = backend_config.write_config({"google_api_key": "AIza-plain-secret", "first_line": "Hello"})
            self.assertEqual(returned["google_api_key"], "AIza-plain-secret")
            raw = self.path.read_text(encoding="utf-8")
            self.assertNotIn("AIza-plain-secret", raw)
            self.assertTrue(json.loads(raw)["google_api_key"].startswith(config_crypto.PREFIX))
            self.assertEqual(json.loads(raw)["first_line"], "Hello")
            self.assertEqual(backend_config.read_config()["google_api_key"], "AIza-plain-secret")

            # Updating another field keeps the stored secret intact.
            backend_config.write_config({"first_line": "Hi again"})
            self.assertEqual(backend_config.read_config()["google_api_key"], "AIza-plain-secret")

    def test_missing_key_for_encrypted_file_fails_loudly(self):
        with self.env(SECRETS_ENCRYPTION_KEY=self.key, APP_ENV="production"):
            backend_config.write_config({"livekit_api_secret": "lk-secret"})
        with self.env(SECRETS_ENCRYPTION_KEY="", APP_ENV="local"):
            with self.assertRaises(config_crypto.SecretsKeyError):
                backend_config.read_config()
        with self.env(SECRETS_ENCRYPTION_KEY=Fernet.generate_key().decode(), APP_ENV="local"):
            with self.assertRaises(config_crypto.SecretsKeyError):
                backend_config.read_config()

    def test_plaintext_secrets_refused_outside_local(self):
        with self.env(SECRETS_ENCRYPTION_KEY="", APP_ENV="production"):
            with self.assertRaises(config_crypto.SecretsKeyError):
                backend_config.write_config({"google_api_key": "x"})
        with self.env(SECRETS_ENCRYPTION_KEY="", APP_ENV="local"):
            backend_config.write_config({"google_api_key": "local-plain"})
            self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["google_api_key"], "local-plain")

    def test_existing_plaintext_file_still_loads(self):
        self.path.write_text(json.dumps({"google_api_key": "legacy-plain"}), encoding="utf-8")
        with self.env(SECRETS_ENCRYPTION_KEY=self.key, APP_ENV="production"):
            self.assertEqual(backend_config.read_config()["google_api_key"], "legacy-plain")


if __name__ == "__main__":
    unittest.main()
