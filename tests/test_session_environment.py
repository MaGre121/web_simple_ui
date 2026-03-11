import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import maximo.oslc.session as session


class TestSessionEnvironment(unittest.TestCase):
    def test_read_environment_returns_empty_values_when_file_is_missing(self):
        with TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            original_path = session.ENV_PATH
            session.ENV_PATH = env_path
            try:
                self.assertEqual(session.read_environment(), ("", ""))
            finally:
                session.ENV_PATH = original_path

    def test_save_environment_persists_values_for_later_load(self):
        with TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            original_path = session.ENV_PATH
            session.ENV_PATH = env_path
            try:
                session.save_environment(
                    "https://company.example",
                    "LtpaToken2-Value",
                )

                self.assertEqual(
                    session.read_environment(),
                    ("https://company.example", "LtpaToken2-Value"),
                )
                self.assertEqual(
                    session.load_environment(),
                    ("https://company.example", "LtpaToken2-Value"),
                )
            finally:
                session.ENV_PATH = original_path


if __name__ == "__main__":
    unittest.main()
