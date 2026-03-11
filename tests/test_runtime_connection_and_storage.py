import importlib
import os
import tempfile
import unittest
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:
    TestClient = None


class RuntimeStorageTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.env_patch = patch.dict(
            os.environ,
            {"MAXIMO_APP_DATA_DIR": self.tempdir.name},
            clear=False,
        )
        self.env_patch.start()

        self.settings = importlib.import_module("maximo.config.settings")
        self.queue = importlib.import_module("maximo.model.queue")

        importlib.reload(self.settings)
        importlib.reload(self.queue)
        self.web_app = None
        if TestClient is not None:
            self.web_app = importlib.import_module("maximo.web.app")
            importlib.reload(self.web_app)

        self.addCleanup(self._cleanup_runtime_modules)

    def _cleanup_runtime_modules(self):
        self.env_patch.stop()
        importlib.reload(self.settings)
        importlib.reload(self.queue)
        if self.web_app is not None:
            importlib.reload(self.web_app)
        self.tempdir.cleanup()


class TestRuntimeStorage(RuntimeStorageTestCase):
    def test_persist_server_writes_only_non_secret_config(self):
        self.settings.persist_server(" https://company.example ")

        self.assertTrue(self.settings.RUNTIME_CONFIG_FILE.exists())
        content = self.settings.RUNTIME_CONFIG_FILE.read_text(encoding="utf-8")

        self.assertIn("https://company.example", content)
        self.assertNotIn("LtpaToken2", content)
        self.assertNotIn("secret-token", content)

    def test_queue_file_is_created_in_runtime_app_data(self):
        queue = self.queue.load_queue()

        self.assertEqual(queue, [])
        self.assertTrue(self.settings.CACHE_QUEUE_FILE.exists())
        self.assertTrue(
            str(self.settings.CACHE_QUEUE_FILE).startswith(self.tempdir.name)
        )

    def test_queue_preserves_blank_user_specs_when_saving(self):
        stored_entry = self.queue.add_to_queue(
            {
                "itemnum": "CISCO.CATALYST.9200L",
                "description": "Switch",
                "siteid": "BWS00001",
                "orgid": "BTRBZ",
                "location": "LOC-001",
                "serialnum": "SN-12345",
                "projekt": "PRJ-001",
                "cxprojekt": "PRJ-001",
                "projektcode": "PRJ-001",
                "cfglibgroup": "ConfigLibarianGroup",
                "fixed_specs": {"BAM.TYPENBEZEICHNUNG": "Cisco Catalyst 9200L"},
                "user_specs": {
                    "BAM.MACADRESSE": "",
                    "BAM.NOTIZ": " Rack 12 ",
                    "": "ignored",
                },
                "users": [],
            }
        )

        self.assertEqual(
            stored_entry["user_specs"],
            {"BAM.MACADRESSE": "", "BAM.NOTIZ": "Rack 12"},
        )

        queue = self.queue.load_queue()
        self.assertEqual(len(queue), 1)
        self.assertEqual(
            queue[0]["user_specs"],
            {"BAM.MACADRESSE": "", "BAM.NOTIZ": "Rack 12"},
        )

    def test_queue_reuses_existing_id_when_entry_is_overwritten(self):
        original_entry = self.queue.add_to_queue(
            {
                "itemnum": "CISCO.CATALYST.9200L",
                "description": "Switch",
                "siteid": "BWS00001",
                "orgid": "BTRBZ",
                "location": "LOC-001",
                "serialnum": "SN-12345",
                "projekt": "PRJ-001",
                "cxprojekt": "PRJ-001",
                "projektcode": "PRJ-001",
                "cfglibgroup": "ConfigLibarianGroup",
                "fixed_specs": {"BAM.TYPENBEZEICHNUNG": "Cisco Catalyst 9200L"},
                "user_specs": {"BAM.NOTIZ": "Rack 12"},
                "users": [],
            }
        )

        overwritten_entry = self.queue.add_to_queue(
            {
                "id": original_entry["id"],
                "itemnum": "CISCO.CATALYST.9200L",
                "description": "Switch",
                "siteid": "BWS00001",
                "orgid": "BTRBZ",
                "location": "LOC-001",
                "serialnum": "SN-99999",
                "projekt": "PRJ-001",
                "cxprojekt": "PRJ-001",
                "projektcode": "PRJ-001",
                "cfglibgroup": "ConfigLibarianGroup",
                "fixed_specs": {"BAM.TYPENBEZEICHNUNG": "Cisco Catalyst 9200L"},
                "user_specs": {"BAM.NOTIZ": "Rack 42"},
                "users": [],
                "status": "error",
                "assetnum": "ASSET-1",
                "error": "bad scan",
            }
        )

        self.assertEqual(overwritten_entry["id"], original_entry["id"])
        self.assertEqual(overwritten_entry["status"], "pending")
        self.assertNotIn("assetnum", overwritten_entry)
        self.assertNotIn("error", overwritten_entry)

        queue = self.queue.load_queue()
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["id"], original_entry["id"])
        self.assertEqual(queue[0]["serialnum"], "SN-99999")
        self.assertEqual(queue[0]["user_specs"], {"BAM.NOTIZ": "Rack 42"})
        self.assertEqual(queue[0]["status"], "pending")


@unittest.skipUnless(TestClient is not None, "fastapi is not installed in this test environment")
class TestRuntimeConnectionAPI(RuntimeStorageTestCase):
    def test_settings_api_persists_server_but_not_token_across_restart(self):
        with TestClient(self.web_app.app) as client:
            response = client.post(
                "/api/settings",
                json={
                    "server": "https://company.example",
                    "ltpa_token2": "secret-token",
                },
            )

            self.assertEqual(response.status_code, 200)
            data = response.json()

            self.assertEqual(data["server"], "https://company.example")
            self.assertEqual(data["ltpa_token2"], "")
            self.assertTrue(data["has_runtime_token"])
            self.assertTrue(data["session_ready"])

        with TestClient(self.web_app.app) as client:
            response = client.get("/api/settings")
            self.assertEqual(response.status_code, 200)
            data = response.json()

            self.assertEqual(data["server"], "https://company.example")
            self.assertEqual(data["ltpa_token2"], "")
            self.assertFalse(data["has_runtime_token"])
            self.assertFalse(data["session_ready"])

        config_text = self.settings.RUNTIME_CONFIG_FILE.read_text(encoding="utf-8")
        self.assertIn("https://company.example", config_text)
        self.assertNotIn("secret-token", config_text)

    def test_fetch_data_uses_runtime_session_without_persisting_token(self):
        summary = {
            "locations": 3,
            "assets": 0,
            "users": 2,
            "projects": 4,
            "templates": 5,
        }

        with patch.object(self.web_app, "refresh_master_data", return_value=summary) as mocked:
            with TestClient(self.web_app.app) as client:
                response = client.post(
                    "/api/fetch-data",
                    json={
                        "server": "https://company.example",
                        "ltpa_token2": "secret-token",
                    },
                )

                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertTrue(data["success"])
                self.assertEqual(data["summary"], summary)
                self.assertIn("Locations 3", data["message"])

        mocked.assert_called_once()
        args, _kwargs = mocked.call_args
        self.assertEqual(args[0], "https://company.example")
        self.assertEqual(args[1].cookies.get("LtpaToken2"), "secret-token")

        config_text = self.settings.RUNTIME_CONFIG_FILE.read_text(encoding="utf-8")
        self.assertIn("https://company.example", config_text)
        self.assertNotIn("secret-token", config_text)

    def test_queue_api_accepts_blank_user_specs_and_persists_them(self):
        with TestClient(self.web_app.app) as client:
            response = client.post(
                "/api/queue",
                json={
                    "itemnum": "CISCO.CATALYST.9200L",
                    "description": "Switch",
                    "siteid": "BWS00001",
                    "orgid": "BTRBZ",
                    "location": "LOC-001",
                    "serialnum": "SN-12345",
                    "projekt": "PRJ-001",
                    "cfglibgroup": "ConfigLibarianGroup",
                    "fixed_specs": {"BAM.TYPENBEZEICHNUNG": "Cisco Catalyst 9200L"},
                    "user_specs": {
                        "BAM.MACADRESSE": "",
                        "BAM.NOTIZ": " Rack 12 ",
                    },
                    "users": [],
                },
            )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(
            data[0]["user_specs"],
            {"BAM.MACADRESSE": "", "BAM.NOTIZ": "Rack 12"},
        )

    def test_queue_api_delete_removes_existing_entry(self):
        with TestClient(self.web_app.app) as client:
            create_response = client.post(
                "/api/queue",
                json={
                    "itemnum": "CISCO.CATALYST.9200L",
                    "description": "Switch",
                    "siteid": "BWS00001",
                    "orgid": "BTRBZ",
                    "location": "LOC-001",
                    "serialnum": "SN-12345",
                    "projekt": "PRJ-001",
                    "cfglibgroup": "ConfigLibarianGroup",
                    "fixed_specs": {"BAM.TYPENBEZEICHNUNG": "Cisco Catalyst 9200L"},
                    "user_specs": {"BAM.NOTIZ": "Rack 12"},
                    "users": [],
                },
            )

            self.assertEqual(create_response.status_code, 201)
            queue = create_response.json()
            self.assertEqual(len(queue), 1)

            delete_response = client.delete(f"/api/queue/{queue[0]['id']}")

        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json(), [])

    def test_queue_api_overwrites_existing_entry_when_id_is_reused(self):
        with TestClient(self.web_app.app) as client:
            create_response = client.post(
                "/api/queue",
                json={
                    "itemnum": "CISCO.CATALYST.9200L",
                    "description": "Switch",
                    "siteid": "BWS00001",
                    "orgid": "BTRBZ",
                    "location": "LOC-001",
                    "serialnum": "SN-12345",
                    "projekt": "PRJ-001",
                    "cfglibgroup": "ConfigLibarianGroup",
                    "fixed_specs": {"BAM.TYPENBEZEICHNUNG": "Cisco Catalyst 9200L"},
                    "user_specs": {"BAM.NOTIZ": "Rack 12"},
                    "users": [],
                },
            )

            self.assertEqual(create_response.status_code, 201)
            original_queue = create_response.json()
            self.assertEqual(len(original_queue), 1)

            update_response = client.post(
                "/api/queue",
                json={
                    "id": original_queue[0]["id"],
                    "itemnum": "CISCO.CATALYST.9200L",
                    "description": "Switch",
                    "siteid": "BWS00001",
                    "orgid": "BTRBZ",
                    "location": "LOC-001",
                    "serialnum": "SN-99999",
                    "projekt": "PRJ-001",
                    "cfglibgroup": "ConfigLibarianGroup",
                    "fixed_specs": {"BAM.TYPENBEZEICHNUNG": "Cisco Catalyst 9200L"},
                    "user_specs": {"BAM.NOTIZ": "Rack 42"},
                    "users": [],
                    "status": "error",
                    "assetnum": "ASSET-1",
                    "error": "bad scan",
                },
            )

        self.assertEqual(update_response.status_code, 201)
        updated_queue = update_response.json()
        self.assertEqual(len(updated_queue), 1)
        self.assertEqual(updated_queue[0]["id"], original_queue[0]["id"])
        self.assertEqual(updated_queue[0]["serialnum"], "SN-99999")
        self.assertEqual(updated_queue[0]["user_specs"], {"BAM.NOTIZ": "Rack 42"})
        self.assertEqual(updated_queue[0]["status"], "pending")
        self.assertNotIn("assetnum", updated_queue[0])
        self.assertNotIn("error", updated_queue[0])


if __name__ == "__main__":
    unittest.main()
