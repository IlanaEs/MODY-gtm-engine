"""Extraction from a JavaScript-rendered supplier page: the static HTML is an app shell, the browser-rendered DOM
carries the facts. Offline: the renderer is stubbed with tests/fixtures/supplier_page_rendered.html."""
import json, os, shutil, sys, tempfile, unittest, yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
from launch import extract, package as P, pipeline                        # noqa: E402
from tests.test_launch import write_png, HAVE_PPTX                         # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
SHELL = open(os.path.join(FIX, "supplier_page_spa.html"), encoding="utf-8").read()
RENDERED = open(os.path.join(FIX, "supplier_page_rendered.html"), encoding="utf-8").read()
URL = "https://areapro.gessi.example/en/product/77201?finId=726"


def stub_renderer(url):
    return RENDERED, "stub:chrome"


def failing_renderer(url):
    raise RuntimeError("no browser could be launched")


class TestRenderedExtraction(unittest.TestCase):
    def test_shell_alone_gives_no_facts(self):
        ex = extract.extract(URL, "Jacqueline 77201", html=SHELL)
        self.assertEqual(ex["facts"], {}); self.assertEqual(ex["fetch"], "static"); self.assertIsNone(ex["renderer"])

    def test_browser_fallback_reads_the_rendered_dom_with_evidence(self):
        with unittest.mock.patch.object(extract, "fetch", return_value=SHELL):
            ex = extract.extract(URL, "Jacqueline 77201", renderer=stub_renderer)
        self.assertEqual(ex["fetch"], "browser"); self.assertEqual(ex["renderer"], "stub:chrome"); self.assertIsNone(ex["render_error"])
        f = ex["facts"]
        self.assertEqual(f["finish"]["value"], {"code": "726", "name": "Warm Bronze Br. PVD"}); self.assertIn("726 - warm bronze br. pvd", f["finish"]["evidence"])
        self.assertEqual(f["dimensions_mm"]["value"], "H 275 mm × W 80 mm × D 220 mm"); self.assertEqual(f["dimensions_mm"]["evidence"], "Height: 275 mm · Width: 80 mm · Depth: 220 mm")
        self.assertEqual(f["model_number"], {"value": "77201", "evidence": "h1: 77201"})
        self.assertEqual(f["collection"]["value"], "Jacqueline"); self.assertIn("Collection Jacqueline", f["collection"]["evidence"])
        self.assertEqual(f["features"]["value"], ["Low spout without waste", "With connecting flexibles", "Horn-effect lever", "Swivel spout"])
        self.assertTrue(f["features"]["evidence"].startswith("Description: Basin mixer, low spout"))
        self.assertNotIn("warranty", f)                                                      # a download link is never a fact
        self.assertNotIn("certifications", f)                                                # footer links are not values
        self.assertNotIn("material", f)                                                      # "Handle material" is not the body material
        self.assertEqual(ex["category"]["value"], "basin_mixer"); self.assertEqual(ex["line"]["value"], "haute_culture")
        self.assertEqual(ex["technical_sheet"]["url"], "https://files.example.com/techsheets/GPF77201/GPF77201_EN_GB.pdf")
        self.assertEqual(ex["hero_candidates"][0], "https://cdn.example.com/zi4/thumb940/77201%23726.webp")
        self.assertFalse([1 for l, v in ex["unmapped"] if l.strip() == v.strip() or not l.strip()])   # provenance keeps no junk rows
        self.assertIn("Drive", ex["html"])                                                        # the rendered DOM itself is kept
        doc = extract.product_file("gessi-77201", "Jacqueline 77201", URL, "assets/x.png", ex, image_source="https://cdn.example.com/x.webp", snapshot="out/x/product_page.html")
        for field, spec in doc["technical"].items():
            self.assertEqual(spec["source"], "product_page"); self.assertTrue(spec["evidence"], field)
        self.assertEqual(doc["product"]["collection"], "Jacqueline"); self.assertEqual(doc["product"]["line"], "Haute Culture"); self.assertEqual(doc["product"]["model_number"], "77201")
        self.assertEqual(doc["design"]["claims_ref"], ["JQ-1", "JQ-2", "JQ-3", "JQ-4", "JQ-5"])
        self.assertEqual(doc["sources"]["technical_sheet"], "https://files.example.com/techsheets/GPF77201/GPF77201_EN_GB.pdf")
        self.assertEqual(doc["sources"]["image_source"], "https://cdn.example.com/x.webp"); self.assertEqual(doc["sources"]["product_page_snapshot"], "out/x/product_page.html")
        self.assertEqual((doc["extraction"]["fetch"], doc["extraction"]["renderer"]), ("browser", "stub:chrome"))
        self.assertIsNone(doc["design"]["signature_material"]); self.assertIsNone(doc["commercial"]["price_ils"])   # nothing inferred

    def test_static_page_with_facts_never_renders(self):
        page = "file://" + os.path.join(FIX, "supplier_page.html")
        ex = extract.extract(page, "Jacqueline 77201", renderer=failing_renderer)
        self.assertEqual(ex["fetch"], "static"); self.assertIn("material", ex["facts"]); self.assertIsNone(ex["render_error"])
        self.assertEqual(ex["facts"]["features"]["value"][:2], ["Low spout", "Swivel spout"])      # the list rule still wins

    def test_render_failure_is_reported_not_raised(self):
        with unittest.mock.patch.object(extract, "fetch", return_value=SHELL):
            ex = extract.extract(URL, "Jacqueline 77201", renderer=failing_renderer)
        self.assertEqual(ex["facts"], {}); self.assertEqual(ex["fetch"], "static"); self.assertIn("no browser could be launched", ex["render_error"])

    def test_render_never_skips_the_browser(self):
        with unittest.mock.patch.object(extract, "fetch", return_value=SHELL):
            ex = extract.extract(URL, "Jacqueline 77201", render="never", renderer=failing_renderer)
        self.assertEqual(ex["facts"], {}); self.assertIsNone(ex["render_error"])

    def test_helpers(self):
        self.assertEqual(extract._nice_case("warm bronze br. pvd"), "Warm Bronze Br. PVD")
        self.assertEqual(extract._nice_case("WARM BRONZE BR. PVD"), "Warm Bronze Br. PVD")
        self.assertEqual(extract._nice_case("Brushed Nickel"), "Brushed Nickel")
        self.assertEqual(extract._compose_dimensions([("D", "220 mm", "Depth: 220 mm"), ("H", "275 mm", "Height: 275 mm")]),
                         {"value": "H 275 mm × D 220 mm", "evidence": "Height: 275 mm · Depth: 220 mm"})
        self.assertEqual(extract.manufacturer_collections("gessi").get("haute_culture"), ["jacqueline"])


class TestHeroFromPage(unittest.TestCase):
    """generate without --image: the page's product photo is the hero, with its URL as provenance; MODY sign-off is a flag."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="mody_launch_", dir=ROOT)
        self.png = os.path.join(self.dir, "page.png"); write_png(self.png, 900, 900)
        self.small = os.path.join(self.dir, "thumb.png"); write_png(self.small, 40, 40)
        self.blobs = {"big": open(self.png, "rb").read(), "small": open(self.small, "rb").read()}

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def fake_fetch(self, url, timeout=20):
        return (self.blobs["small"] if "thumb" in url else self.blobs["big"]), "image/png"

    def test_download_hero_skips_small_images_and_keeps_provenance(self):
        hero = extract.download_hero(["https://cdn/thumb.png", "https://cdn/77201.png"], os.path.join(self.dir, "assets"), "hero", fetch=self.fake_fetch)
        self.assertEqual(hero["source_url"], "https://cdn/77201.png"); self.assertEqual(hero["format"], "png"); self.assertEqual(hero["size"], [900, 900])
        self.assertTrue(os.path.exists(hero["path"] if os.path.isabs(hero["path"]) else os.path.join(ROOT, hero["path"])))
        self.assertIsNone(extract.download_hero(["https://cdn/thumb.png"], os.path.join(self.dir, "assets"), "hero", fetch=self.fake_fetch))

    def _generate(self, *flags):
        from launch.__main__ import main
        products, out, assets = (os.path.join(self.dir, d) for d in ("products", "out", "assets"))
        page = "file://" + os.path.join(FIX, "supplier_page.html")
        with unittest.mock.patch.object(extract, "fetch_bytes", side_effect=self.fake_fetch):
            rc = main(["generate", "--name", "Jacqueline 77201", "--url", page, "--engine", "rules", "--render", "never",
                       "--products-root", products, "--out-root", out, "--assets-root", assets, *flags])
        o = os.path.join(out, "gessi-77201") + os.sep
        return rc, o, yaml.safe_load(open(os.path.join(products, "gessi-77201.yaml"), encoding="utf-8"))

    def test_page_image_without_sign_off_is_not_ready(self):
        rc, o, prod = self._generate()
        self.assertEqual(rc, 1)
        self.assertFalse(prod["sources"]["image_approved"]); self.assertTrue(prod["sources"]["image"].endswith("gessi-77201_hero.png"))
        self.assertEqual(prod["sources"]["image_source"], "file:///media/jacqueline-77201-warm-bronze.jpg")
        self.assertTrue(os.path.exists(o + "product_page.html")); self.assertTrue(prod["sources"]["product_page_snapshot"].endswith("product_page.html"))
        self.assertFalse(os.path.exists(o + "landing.html")); self.assertFalse(os.path.exists(o + "launch.pptx"))
        self.assertEqual(json.load(open(o + "generate_report.json", encoding="utf-8"))["result"], "not_ready")

    def test_page_image_with_sign_off_renders_both_final_assets(self):
        rc, o, prod = self._generate("--approve-page-image")
        self.assertEqual(rc, 0 if HAVE_PPTX else 1)
        self.assertTrue(prod["sources"]["image_approved"])
        self.assertTrue(os.path.exists(o + "landing.html")); self.assertTrue(os.path.exists(o + "provenance.yaml"))
        if HAVE_PPTX:
            self.assertTrue(os.path.exists(o + "launch.pptx"))
        report = json.load(open(o + pipeline.REPORT, encoding="utf-8"))
        self.assertEqual(report["readiness"]["status"], "ready"); self.assertEqual(report["markdown_qa"], "PASS")
        self.assertIn(P.load_package(o)["qa"]["status"], ("passed", "passed_with_warnings"))


import unittest.mock  # noqa: E402  (after the module-level imports above)

if __name__ == "__main__":
    unittest.main()
