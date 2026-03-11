import unittest

from maximo.oslc import post_asset


class TestPostAssetPayloads(unittest.TestCase):
    def test_build_spec_payload_keeps_blank_user_specs(self):
        payload = post_asset._build_spec_payload(
            {
                "fixed_specs": {"BAM.TYPENBEZEICHNUNG": "Cisco Catalyst 9200L"},
                "user_specs": {
                    "BAM.MACADRESSE": "",
                    "BAM.NOTIZ": "Rack 12",
                },
            }
        )

        self.assertEqual(
            payload,
            [
                {
                    "assetattrid": "BAM.TYPENBEZEICHNUNG",
                    "alnvalue": "Cisco Catalyst 9200L",
                },
                {
                    "assetattrid": "BAM.MACADRESSE",
                    "alnvalue": "",
                },
                {
                    "assetattrid": "BAM.NOTIZ",
                    "alnvalue": "Rack 12",
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
