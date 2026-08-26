from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from queryclear_agent_runtime.serve import _DemoProvider, build_service


class ServeConfigurationTest(unittest.TestCase):
    def test_missing_provider_fails_closed_when_demo_is_disabled(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "real model provider"):
                build_service(allow_demo=False)

    def test_local_demo_requires_explicit_opt_in(self) -> None:
        with patch.dict(os.environ, {"APP_ENV": "development"}, clear=True):
            service = build_service(allow_demo=True)
        self.assertIsInstance(service.provider, _DemoProvider)

    def test_production_cannot_enable_demo_through_environment(self) -> None:
        env = {"APP_ENV": "production", "QUERYCLEAR_ALLOW_DEMO": "true"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "real model provider"):
                build_service()


if __name__ == "__main__":
    unittest.main()
