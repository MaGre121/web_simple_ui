import os
import unittest
from unittest.mock import patch

from maximo.oslc.session import load_environment


class TestSessionEnvironment(unittest.TestCase):
    def test_load_environment_uses_explicit_values(self):
        self.assertEqual(
            load_environment("https://company.example", "LtpaToken2-Value"),
            ("https://company.example", "LtpaToken2-Value"),
        )

    def test_load_environment_uses_process_environment(self):
        with patch.dict(
            os.environ,
            {
                "SERVER": "https://company.example",
                "MAXIMO_LTPA_TOKEN2": "LtpaToken2-Value",
            },
            clear=False,
        ):
            self.assertEqual(
                load_environment(),
                ("https://company.example", "LtpaToken2-Value"),
            )

    def test_load_environment_requires_both_values(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "SERVER oder MAXIMO_LTPA_TOKEN2 fehlt"):
                load_environment()


if __name__ == "__main__":
    unittest.main()
