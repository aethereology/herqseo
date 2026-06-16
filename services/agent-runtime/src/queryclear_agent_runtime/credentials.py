from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
from dataclasses import asdict, dataclass


class SecretCipherError(RuntimeError):
    pass


@dataclass(frozen=True)
class WordPressCredentials:
    base_url: str
    username: str
    app_password: str


class SecretCipher:
    """Small authenticated at-rest encryption helper.

    This keeps CMS credentials out of plain database rows without introducing a
    heavyweight secret manager into the local/runtime slice. The key must come
    from environment/config and should be rotated into a real KMS-backed envelope
    scheme before enterprise production.
    """

    _VERSION = "qcsec1"

    def __init__(self, key: str) -> None:
        if not key or len(key.encode("utf-8")) < 16:
            raise SecretCipherError("QUERYCLEAR_SECRET_KEY must be at least 16 bytes")
        self._enc_key = hashlib.sha256(f"enc:{key}".encode("utf-8")).digest()
        self._mac_key = hashlib.sha256(f"mac:{key}".encode("utf-8")).digest()

    @classmethod
    def from_env(cls, env: dict[str, str] | os._Environ[str]) -> SecretCipher:
        return cls(env.get("QUERYCLEAR_SECRET_KEY", "queryclear-dev-secret-key"))

    def encrypt_json(self, payload: dict[str, object]) -> str:
        plaintext = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        nonce = os.urandom(16)
        ciphertext = _xor_bytes(plaintext, _keystream(self._enc_key, nonce, len(plaintext)))
        tag = hmac.new(self._mac_key, nonce + ciphertext, hashlib.sha256).digest()
        blob = {
            "v": self._VERSION,
            "n": _b64(nonce),
            "c": _b64(ciphertext),
            "t": _b64(tag),
        }
        return json.dumps(blob, sort_keys=True, separators=(",", ":"))

    def decrypt_json(self, encrypted: str) -> dict[str, object]:
        try:
            blob = json.loads(encrypted)
            if blob.get("v") != self._VERSION:
                raise SecretCipherError("unsupported secret payload version")
            nonce = _unb64(str(blob["n"]))
            ciphertext = _unb64(str(blob["c"]))
            expected = _unb64(str(blob["t"]))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, binascii.Error) as exc:
            raise SecretCipherError("invalid encrypted secret payload") from exc

        actual = hmac.new(self._mac_key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(actual, expected):
            raise SecretCipherError("encrypted secret payload failed authentication")
        plaintext = _xor_bytes(ciphertext, _keystream(self._enc_key, nonce, len(ciphertext)))
        data = json.loads(plaintext.decode("utf-8"))
        if not isinstance(data, dict):
            raise SecretCipherError("decrypted secret payload is not an object")
        return data

    def encrypt_wordpress(self, credentials: WordPressCredentials) -> str:
        return self.encrypt_json(asdict(credentials))

    def decrypt_wordpress(self, encrypted: str) -> WordPressCredentials:
        data = self.decrypt_json(encrypted)
        return WordPressCredentials(
            base_url=str(data["base_url"]),
            username=str(data["username"]),
            app_password=str(data["app_password"]),
        )


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    blocks: list[bytes] = []
    counter = 0
    while sum(len(block) for block in blocks) < length:
        blocks.append(
            hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        )
        counter += 1
    return b"".join(blocks)[:length]


def _xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right))


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))
