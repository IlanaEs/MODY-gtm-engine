"""Regression tests for QA fix round 3B (findings F-22 .. F-27).
Run from the project root:  python -m unittest tests.test_round3b -v
"""
import os, shutil, subprocess, sys, tempfile, unittest, yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
from validate import validate, resolve_layer                  # noqa: E402
from tests.test_round1 import Fixture, PID                    # noqa: E402

KITCHEN = "gessi-g60077"
TILE = "mutina-basrelief-patchwork"
ALL = (PID, KITCHEN, TILE)


class Base(unittest.TestCase):
    pid = PID

    def setUp(self):
        self.fx = Fixture(self.pid)

    def tearDown(self):
        self.fx.close()

    def assertFails(self, result, check):
        self.assertEqual(result["status"], "FAIL", result)
        self.assertEqual(result["checks"].get(check), "FAIL", f"{check} should FAIL: {result['fails']}")

    def assertPasses(self, result):
        self.assertEqual(result["status"], "PASS", result["fails"])


def project_copy():
    d = tempfile.mkdtemp(prefix="mody_r3b_")
    for sub in ("brand", "products", "schema", "out"):
        shutil.copytree(os.path.join(ROOT, sub), os.path.join(d, sub))
    for f in ("validate.py", "qa.py", "run_all.py", "SKILL.md"):
        shutil.copy(os.path.join(ROOT, f), d)
    return d


# ---------------------------------------------------------------- F-22
class TestF22ProvenanceQADetail(unittest.TestCase):
    def setUp(self):
        self.dir = project_copy()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _run(self):
        return subprocess.run([sys.executable, "run_all.py"], cwd=self.dir, capture_output=True, text=True)

    def _qa(self, pid=PID):
        return yaml.safe_load(open(os.path.join(self.dir, "out", pid, "provenance.yaml"), encoding="utf-8"))["qa"]

    def test_pass_provenance_has_mapping_and_empty_fails(self):
        self.assertEqual(self._run().returncode, 0)
        for pid in ALL:
            q = self._qa(pid)
            self.assertEqual(q["status"], "PASS")
            self.assertIsInstance(q["checks"], dict); self.assertTrue(all(s == "PASS" for s in q["checks"].values()))
            self.assertEqual(q["fails"], [])
            self.assertEqual(set(q), {"status", "checks", "fails"})

    def test_fail_provenance_keeps_details(self):
        shutil.copy(os.path.join(ROOT, "tests", "landing_with_planted_errors.md"), os.path.join(self.dir, "out", PID, "landing.md"))
        self.assertEqual(self._run().returncode, 1)
        q = self._qa()
        self.assertEqual(q["status"], "FAIL")
        self.assertEqual(q["checks"]["price_exact"], "FAIL"); self.assertEqual(q["checks"]["files_present"], "PASS")
        self.assertTrue(any(f.startswith("price_exact") for f in q["fails"]), q["fails"])
        self.assertTrue(any(f.startswith("no_invented_numbers") for f in q["fails"]), q["fails"])


# ---------------------------------------------------------------- F-23
class TestF23ClaimsUsedIntegrity(Base):
    def entry(self, **kw):
        e = {"asset": "landing", "text": "כל שורש נבחר ביד לפי הקוטר ולפי המרווח בין הפרקים", "ref": "claim:JQ-2",
             "source": "https://www.gessi.com/us/news-and-events/jacqueline"}
        e.update(kw); self.fx.prov["claims_used"].append(e); return e

    def test_golden_passes(self):
        self.assertPasses(self.fx.qa())

    def test_shipped_provenance_passes_for_all_products(self):
        for pid in ALL:
            fx = Fixture(pid)
            try:
                self.assertEqual(fx.qa()["checks"]["claims_used_integrity"], "PASS", (pid, fx.qa()["fails"]))
            finally:
                fx.close()

    def test_invalid_assets(self):
        for a in ("brochure", "unknown", "", None, "Landing", "landing.md"):
            fx = Fixture()
            try:
                fx.prov["claims_used"].append({"asset": a, "text": "5,000 ₪", "ref": "commercial:price_ils", "source": "mody_listing"})
                self.assertEqual(fx.qa()["checks"]["claims_used_integrity"], "FAIL", repr(a))
            finally:
                fx.close()

    def test_text_not_in_asset(self):
        self.entry(text="טקסט שלא מופיע בשום נכס"); self.assertFails(self.fx.qa(), "claims_used_integrity")

    def test_text_in_other_asset_only(self):
        self.entry(asset="sales"); self.assertFails(self.fx.qa(), "claims_used_integrity")

    def test_empty_text(self):
        self.entry(text="   "); self.assertFails(self.fx.qa(), "claims_used_integrity")

    def test_normalisation_tolerates_formatting(self):
        self.entry(text="  כל שורש   נבחר ביד\nלפי הקוטר ולפי המרווח בין הפרקים ")            # whitespace / newline
        self.entry(text="**פריט שאין לאף אחד אחר.**", ref="claim:JQ-3", source="https://www.gessi.com/us/haute-culture/jacqueline")   # bold
        self.entry(text="| מחיר | 5,000 ₪ |", ref="commercial:price_ils", source="mody_listing")       # table row
        self.entry(asset="sales", text="\"זה Jacqueline של Gessi.", ref="brand:identity", source="brand/gessi.v1.1.yaml")  # quote
        self.assertPasses(self.fx.qa())

    def test_claim_source_must_be_the_approved_source(self):
        self.entry(source="https://made-up.example/x"); self.assertFails(self.fx.qa(), "claims_used_integrity")
        self.fx.prov["claims_used"].pop()
        self.entry(source="https://www.gessi.com/en/bath/jacqueline"); self.assertFails(self.fx.qa(), "claims_used_integrity")  # JQ-1's, not JQ-2's

    def test_spec_source_key_or_resolved_url(self):
        self.entry(text="Warm Bronze Br. PVD", ref="spec:finish", source="product_page")
        self.entry(text="Warm Bronze Br. PVD", ref="spec:finish", source="https://areapro.gessi.com/en/haute-culture/collections/jacqueline")
        self.assertPasses(self.fx.qa())
        self.entry(text="Warm Bronze Br. PVD", ref="spec:finish", source="collection_page"); self.assertFails(self.fx.qa(), "claims_used_integrity")

    def test_spec_source_fake_url(self):
        self.entry(text="Warm Bronze Br. PVD", ref="spec:finish", source="https://fake.example/spec"); self.assertFails(self.fx.qa(), "claims_used_integrity")

    def test_house_and_brand_sources_are_the_layer_files(self):
        self.entry(text="מלווה אותך מהבחירה ועד ההתקנה", ref="house:P5", source="brand/gessi.v1.1.yaml"); self.assertFails(self.fx.qa(), "claims_used_integrity")
        self.fx.prov["claims_used"].pop()
        self.entry(text="Gessi Casa", ref="brand:local_presence", source="brand/mody_brand_dna.v1.0.yaml"); self.assertFails(self.fx.qa(), "claims_used_integrity")
        self.fx.prov["claims_used"].pop()
        self.entry(text="Gessi Casa", ref="brand:local_presence", source="https://www.gessi.com"); self.assertFails(self.fx.qa(), "claims_used_integrity")

    def test_commercial_source(self):
        self.entry(text="5,000 ₪", ref="commercial:price_ils", source="product_page"); self.assertFails(self.fx.qa(), "claims_used_integrity")
        self.fx.prov["claims_used"].pop()
        self.entry(text="5,000 ₪", ref="commercial:price_ils", source="assignment_brief"); self.assertPasses(self.fx.qa())   # resolved value of mody_listing

    def test_signature_material_source(self):
        self.entry(asset="deck", text="Real bamboo root, handcrafted", ref="spec:signature_material", source="collection_page"); self.assertPasses(self.fx.qa())
        self.entry(asset="deck", text="Real bamboo root, handcrafted", ref="spec:signature_material", source="product_page"); self.assertFails(self.fx.qa(), "claims_used_integrity")


# ---------------------------------------------------------------- F-24
class TestF24PinPrefix(unittest.TestCase):
    def _validate(self, mutate):
        p = yaml.safe_load(open(f"products/{PID}.yaml", encoding="utf-8")); mutate(p)
        d = tempfile.mkdtemp(prefix="mody_r3b_", dir=ROOT)
        try:
            path = os.path.join(d, "p.yaml")
            with open(path, "w", encoding="utf-8") as f:
                yaml.safe_dump(p, f, allow_unicode=True)
            return validate(path)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_other_brand_pin_blocked(self):
        v = self._validate(lambda p: p.__setitem__("brand_versions", {"manufacturer": "mutina@1.0"}))
        self.assertEqual(v["status"], "BLOCKED"); self.assertIsNone(v["brand_layers"]["manufacturer"])
        self.assertTrue(any("המזהה לפני @" in e for e in v["errors"]), v["errors"])

    def test_house_pin_prefix(self):
        v = self._validate(lambda p: p.__setitem__("brand_versions", {"house": "gessi@1.0"}))
        self.assertEqual(v["status"], "BLOCKED"); self.assertTrue(any("brand_versions.house" in e for e in v["errors"]))

    def test_case_must_match(self):
        self.assertEqual(self._validate(lambda p: p.__setitem__("brand_versions", {"manufacturer": "GESSI@1.0"}))["status"], "BLOCKED")

    def test_syntax(self):
        for pin in ("gessi", "gessi@", "gessi@1.x", "gessi@1.0@2", 1.0):
            self.assertEqual(self._validate(lambda p, pin=pin: p.__setitem__("brand_versions", {"manufacturer": pin}))["status"], "BLOCKED", pin)

    def test_requested_version_must_exist(self):
        v = self._validate(lambda p: p.__setitem__("brand_versions", {"manufacturer": "gessi@9.9"}))
        self.assertEqual(v["status"], "BLOCKED"); self.assertIsNone(v["brand_layers"]["manufacturer"])

    def test_valid_pins_work(self):
        v = self._validate(lambda p: p.__setitem__("brand_versions", {"manufacturer": "gessi@1.0", "house": "mody_brand_dna@1.0"}))
        self.assertNotEqual(v["status"], "BLOCKED")
        self.assertEqual(v["brand_layers"], {"house": "brand/mody_brand_dna.v1.0.yaml", "manufacturer": "brand/gessi.v1.0.yaml"})

    def test_latest_without_pin(self):
        v = self._validate(lambda p: p.pop("brand_versions", None))
        self.assertEqual(v["brand_layers"]["manufacturer"], "brand/gessi.v1.1.yaml")


# ---------------------------------------------------------------- F-25
class TestF25BrandIdentifier(unittest.TestCase):
    def _validate(self, brand):
        p = yaml.safe_load(open(f"products/{PID}.yaml", encoding="utf-8")); p["product"]["brand"] = brand
        d = tempfile.mkdtemp(prefix="mody_r3b_", dir=ROOT)
        try:
            path = os.path.join(d, "p.yaml")
            with open(path, "w", encoding="utf-8") as f:
                yaml.safe_dump(p, f, allow_unicode=True)
            return validate(path)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_glob_and_path_values_blocked(self):
        for brand in ("*", "g*", "?", "gessi?", "[a-z]*", "ges[s]i", "../products/gessi-77201", "brand/gessi", "gessi/../mutina",
                      "gessi.v1.1", "", " ", "gessi mutina", 5):
            v = self._validate(brand)
            self.assertEqual(v["status"], "BLOCKED", repr(brand)); self.assertIsNone(v["brand_layers"]["manufacturer"], repr(brand))

    def test_resolve_layer_never_globs(self):
        for bad in ("*", "g*", "?", "[gm]*", "../brand/gessi"):
            self.assertIsNone(resolve_layer(bad), bad)

    def test_legitimate_ids_still_resolve(self):
        self.assertEqual(resolve_layer("gessi"), "brand/gessi.v1.1.yaml")
        self.assertEqual(resolve_layer("mutina"), "brand/mutina.v1.0.yaml")
        self.assertEqual(resolve_layer("mody_brand_dna"), "brand/mody_brand_dna.v1.0.yaml")
        for pid in ALL:
            self.assertEqual(validate(f"products/{pid}.yaml")["status"], "READY_WITH_FLAGS", pid)

    def test_case_mismatch_is_blocked_not_resolved(self):
        v = self._validate("Gessi"); self.assertEqual(v["status"], "BLOCKED"); self.assertIsNone(v["brand_layers"]["manufacturer"])


# ---------------------------------------------------------------- F-26
class TestF26WorkingDirectory(unittest.TestCase):
    def _run(self, cwd, *args):
        r = subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr

    def test_scripts_behave_the_same_from_another_directory(self):
        other = tempfile.mkdtemp(prefix="mody_elsewhere_")
        try:
            for args in (("validate.py", "products/gessi-77201.yaml"), ("validate.py", "tests/broken_example.yaml"),
                         ("qa.py", "products/gessi-77201.yaml", "out/gessi-77201/"), ("run_all.py",)):
                here = self._run(ROOT, *args)
                there = self._run(other, *[os.path.join(ROOT, a) for a in args])
                self.assertNotIn("Traceback", there[2], (args, there[2]))
                self.assertEqual(here[0], there[0], args)
                self.assertEqual(here[1].replace(ROOT + os.sep, ""), there[1].replace(ROOT + os.sep, ""), args)
        finally:
            shutil.rmtree(other, ignore_errors=True)

    def test_run_all_from_elsewhere_sees_all_products(self):
        other = tempfile.mkdtemp(prefix="mody_elsewhere_")
        try:
            rc, out, err = self._run(other, os.path.join(ROOT, "run_all.py"))
            self.assertEqual(rc, 0, err)
            for pid in ALL:
                self.assertIn(pid, out)
        finally:
            shutil.rmtree(other, ignore_errors=True)

    def test_import_from_elsewhere(self):
        other = tempfile.mkdtemp(prefix="mody_elsewhere_")
        try:
            code = f"import sys; sys.path.insert(0, {ROOT!r}); from validate import validate; print(validate({os.path.join(ROOT, 'products', PID + '.yaml')!r})['status'])"
            rc, out, err = self._run(other, "-c", code)
            self.assertEqual((rc, out.strip()), (0, "READY_WITH_FLAGS"), err)
        finally:
            shutil.rmtree(other, ignore_errors=True)


# ---------------------------------------------------------------- F-27
class TestF27ShippedOutputsAudit(unittest.TestCase):
    def test_every_shipped_product_passes_every_check(self):
        from qa import run
        for pid in ALL:
            r = run(f"products/{pid}.yaml", f"out/{pid}/")
            self.assertEqual(r["status"], "PASS", (pid, r["fails"]))
            self.assertEqual(set(r["checks"].values()), {"PASS"}, pid)
            for c in ("landing_structure", "sales_structure", "deck_structure", "positioning", "claims_used_integrity",
                      "line_isolation_landing.md", "no_invented_numbers", "price_exact", "qa_footer_landing.md"):
                self.assertIn(c, r["checks"], (pid, c))

    def test_no_statement_from_line_description(self):
        mfr = yaml.safe_load(open("brand/gessi.v1.1.yaml", encoding="utf-8"))
        desc = mfr["lines"]["haute_culture"]["description"]
        for pid in (PID, KITCHEN):
            for a in ("landing.md", "deck.md", "sales.md"):
                self.assertNotIn("הניסיוני", open(f"out/{pid}/{a}", encoding="utf-8").read(), (pid, a, desc))


if __name__ == "__main__":
    unittest.main()
