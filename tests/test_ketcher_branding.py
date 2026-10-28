import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class KetcherBrandingTests(unittest.TestCase):
    def test_built_sketcher_uses_xinpilot_branding(self):
        index_text = (ROOT / "ketcher_bridge" / "dist" / "index.html").read_text(encoding="utf-8")
        asset_path = next((ROOT / "ketcher_bridge" / "dist" / "assets").glob("index-*.js"))
        asset_text = asset_path.read_text(encoding="utf-8")

        self.assertIn("XinPilot Reaction Sketcher", index_text)
        self.assertIn("XinPilot Reaction Sketcher", asset_text)
        self.assertIn("Send RXN to XinPilot", asset_text)
        self.assertNotIn("OneClick Reaction Sketcher", index_text + asset_text)
        self.assertNotIn("Send RXN to OneClick", asset_text)


if __name__ == "__main__":
    unittest.main()
