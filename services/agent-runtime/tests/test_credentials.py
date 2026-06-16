from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from queryclear_agent_runtime import (  # noqa: E402
    SecretCipher,
    SecretCipherError,
    WordPressCredentials,
)


class SecretCipherTest(unittest.TestCase):
    def test_encrypt_decrypt_wordpress_credentials(self) -> None:
        cipher = SecretCipher("test-secret-key-123")
        credentials = WordPressCredentials(
            base_url="https://wp.test",
            username="editor",
            app_password="secret-password",
        )

        encrypted = cipher.encrypt_wordpress(credentials)
        decrypted = cipher.decrypt_wordpress(encrypted)

        self.assertNotIn("secret-password", encrypted)
        self.assertEqual(decrypted, credentials)

    def test_tampered_payload_is_rejected(self) -> None:
        cipher = SecretCipher("test-secret-key-123")
        encrypted = cipher.encrypt_json({"x": "y"})
        tampered = encrypted[:-3] + ("A" if encrypted[-3] != "A" else "B") + encrypted[-2:]

        with self.assertRaises(SecretCipherError):
            cipher.decrypt_json(tampered)

    def test_short_key_rejected(self) -> None:
        with self.assertRaises(SecretCipherError):
            SecretCipher("short")


if __name__ == "__main__":
    unittest.main()
