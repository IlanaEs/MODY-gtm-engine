"""Regression tests for the final QA hardening round (findings F-28 .. F-32).
Run from the project root:  python -m unittest tests.test_round4 -v
"""
import os, shutil, subprocess, sys, tempfile, unittest, yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
from validate import validate, load_strict, DuplicateKeyError          # noqa: E402
from qa import constraint_phrases                                      # noqa: E402
from tests.test_round1 import Fixture, PID                             # noqa: E402

KITCHEN = "gessi-g60077"
TILE = "mutina-basrelief-patchwork"
ANCHOR = "הברז שלך לא חוזר על עצמו"


def validate_mutated(mutate=None, raw=None, pid=PID):
    d = tempfile.mkdtemp(prefix="mody_r4_", dir=ROOT)
    try:
        path = os.path.join(d, "p.yaml")
        if raw is None:
            p = yaml.safe_load(open(f"products/{pid}.yaml", encoding="utf-8")); mutate(p)
            with open(path, "w", encoding="utf-8") as f:
                yaml.safe_dump(p, f, allow_unicode=True)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(raw)
        return validate(path)
    finally:
        shutil.rmtree(d, ignore_errors=True)


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

    def rep(self, asset, old, new):
        self.assertIn(old, self.fx.files[asset]); self.fx.files[asset] = self.fx.files[asset].replace(old, new)


# ---------------------------------------------------------------- F-28
class TestF28PriceContract(unittest.TestCase):
    def test_scalar_price_blocked(self):                                          # P13
        v = validate_mutated(lambda p: p["commercial"].__setitem__("price_ils", 5000))
        self.assertEqual(v["status"], "BLOCKED"); self.assertTrue(any("value: <מספר>" in e for e in v["errors"]), v["errors"])

    def test_numeric_string_blocked(self):                                        # P14
        for bad in ("5,000", "5000", "5000 ₪", True, [5000]):
            v = validate_mutated(lambda p, bad=bad: p["commercial"]["price_ils"].__setitem__("value", bad))
            self.assertEqual(v["status"], "BLOCKED", repr(bad))
            self.assertTrue(any("price_ils.value" in e for e in v["errors"]), (bad, v["errors"]))

    def test_numbers_valid(self):
        for ok in (5000, 5000.0, 12345):
            v = validate_mutated(lambda p, ok=ok: p["commercial"]["price_ils"].__setitem__("value", ok))
            self.assertEqual(v["status"], "READY_WITH_FLAGS", ok)

    def test_malformed_price_never_reaches_qa(self):
        fx = Fixture()
        try:
            fx.prod["commercial"]["price_ils"] = 5000
            r = fx.qa(); self.assertEqual(r["status"], "FAIL"); self.assertEqual(r["checks"].get("validator"), "FAIL")
        finally:
            fx.close()

    def test_exact_house_rendering_still_enforced(self):
        fx = Fixture()
        try:
            fx.files["landing.md"] = fx.files["landing.md"].replace("5,000 ₪", "5000 ₪")
            self.assertEqual(fx.qa()["checks"]["price_exact"], "FAIL")
        finally:
            fx.close()


# ---------------------------------------------------------------- F-29
class TestF29ExclamationInUrls(Base):
    def test_bang_in_link_url_ignored(self):                                      # VO16
        self.rep("landing.md", ANCHOR, ANCHOR + " [מקור](https://example.com/a!b?x=!)"); self.assertPasses(self.fx.qa())

    def test_bang_in_image_url_ignored(self):
        self.fx.prod["sources"]["image"] = "assets/77201!bronze.png"
        self.rep("landing.md", "assets/77201_warm-bronze.png", "assets/77201!bronze.png")
        self.rep("deck.md", "assets/77201_warm-bronze.png", "assets/77201!bronze.png")
        self.assertPasses(self.fx.qa())

    def test_bang_in_visible_link_text_fails(self):
        self.rep("landing.md", ANCHOR, ANCHOR + " [ראו כאן!](https://example.com)"); self.assertFails(self.fx.qa(), "voice_landing.md")

    def test_banned_word_in_link_text_fails(self):
        self.rep("landing.md", ANCHOR, ANCHOR + " [מדהים](https://example.com)"); self.assertFails(self.fx.qa(), "voice_landing.md")

    def test_visible_bang_fails(self):
        self.rep("landing.md", ANCHOR, ANCHOR + "!"); self.assertFails(self.fx.qa(), "voice_landing.md")

    def test_fullwidth_bang_fails(self):
        self.rep("landing.md", ANCHOR, ANCHOR + "！"); self.assertFails(self.fx.qa(), "voice_landing.md")

    def test_bang_after_link_fails(self):
        self.rep("landing.md", ANCHOR, ANCHOR + " [מקור](https://example.com/a!b)!"); self.assertFails(self.fx.qa(), "voice_landing.md")


# ---------------------------------------------------------------- F-30
class TestF30ConfiguredConstraints(unittest.TestCase):
    def test_phrases_come_only_from_forbidding_sentences(self):
        mutina = yaml.safe_load(open("brand/mutina.v1.0.yaml", encoding="utf-8"))
        self.assertEqual(constraint_phrases(mutina), ["ידידותי לסביבה"])
        gessi = yaml.safe_load(open("brand/gessi.v1.1.yaml", encoding="utf-8"))
        self.assertEqual(constraint_phrases(gessi), [])
        self.assertEqual(constraint_phrases({"constraints": ['מותר לכתוב "ללא VOC". אסור לכתוב "ירוק" או "אקולוגי".']}), ["ירוק", "אקולוגי"])

    def test_constraint_phrase_in_copy_fails(self):                               # VO20
        fx = Fixture(TILE)
        try:
            fx.files["landing.md"] = fx.files["landing.md"].replace("## ב-MODY", "אריח ידידותי לסביבה.\n\n## ב-MODY")
            r = fx.qa(); self.assertEqual(r["status"], "FAIL"); self.assertEqual(r["checks"]["constraints_landing.md"], "FAIL")
        finally:
            fx.close()

    def test_constraint_phrase_allowed_in_dont_say_section(self):
        fx = Fixture(TILE)
        try:
            self.assertIn("ידידותי לסביבה", fx.files["sales.md"]); self.assertEqual(fx.qa()["status"], "PASS", fx.qa()["fails"])
        finally:
            fx.close()

    def test_g4_quoted_pattern_covered_by_voice_rule(self):
        fx = Fixture()
        try:
            fx.files["landing.md"] = fx.files["landing.md"].replace(ANCHOR, ANCHOR + ", הכי יוקרתי בישראל")
            self.assertEqual(fx.qa()["checks"]["voice_landing.md"], "FAIL")
        finally:
            fx.close()


# ---------------------------------------------------------------- F-31
class TestF31InputSafety(unittest.TestCase):
    def test_unsafe_ids_blocked(self):
        for bad in ("../escape", "a/b", "/abs", "..", ".", ".hidden", "-x", "a\\b", "a b", "", "gessi/../x", 5):
            v = validate_mutated(lambda p, bad=bad: p["product"].__setitem__("id", bad))
            self.assertEqual(v["status"], "BLOCKED", repr(bad)); self.assertTrue(any("product.id" in e for e in v["errors"]), (bad, v["errors"]))

    def test_shipped_ids_valid(self):
        for pid in (PID, KITCHEN, TILE):
            self.assertEqual(validate(f"products/{pid}.yaml")["status"], "READY_WITH_FLAGS", pid)

    def test_run_all_never_writes_outside_out(self):
        d = tempfile.mkdtemp(prefix="mody_r4_")
        try:
            for sub in ("brand", "products", "schema", "out"):
                shutil.copytree(os.path.join(ROOT, sub), os.path.join(d, sub))
            for f in ("validate.py", "qa.py", "run_all.py", "SKILL.md"):
                shutil.copy(os.path.join(ROOT, f), d)
            text = open(os.path.join(d, "products", PID + ".yaml"), encoding="utf-8").read().replace("id: gessi-77201", "id: ../escape")
            with open(os.path.join(d, "products", "zz-escape.yaml"), "w", encoding="utf-8") as f:
                f.write(text)
            r = subprocess.run([sys.executable, "run_all.py"], cwd=d, capture_output=True, text=True)
            self.assertEqual(r.returncode, 1); self.assertNotIn("Traceback", r.stderr); self.assertIn("BLOCKED", r.stdout)
            self.assertFalse(os.path.exists(os.path.join(d, "escape")))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_duplicate_keys_blocked(self):
        raw = open(f"products/{PID}.yaml", encoding="utf-8").read().replace("  id: gessi-77201\n", "  id: one\n  id: two\n")
        v = validate_mutated(raw=raw)
        self.assertEqual(v["status"], "BLOCKED"); self.assertTrue(any("DuplicateKeyError" in e and "'id'" in e for e in v["errors"]), v["errors"])

    def test_duplicate_top_level_key_blocked(self):
        raw = open(f"products/{PID}.yaml", encoding="utf-8").read() + "\ncommercial:\n  price_ils: {value: 999, source: mody_listing}\n"
        self.assertEqual(validate_mutated(raw=raw)["status"], "BLOCKED")

    def test_strict_loader_direct(self):
        with self.assertRaises(DuplicateKeyError):
            load_strict("a: 1\na: 2\n")
        self.assertEqual(load_strict("a: 1\nb: {c: 1}\n"), {"a": 1, "b": {"c": 1}})

    def test_duplicate_keys_in_provenance_fail_qa(self):
        fx = Fixture()
        try:
            ppath = fx.write()
            with open(fx.out + "provenance.yaml", "a", encoding="utf-8") as f:
                f.write("\nproduct: gessi-77201\n")
            from qa import run
            r = run(ppath, fx.out); self.assertEqual(r["status"], "FAIL"); self.assertEqual(r["checks"]["provenance_valid"], "FAIL")
        finally:
            fx.close()

    def test_unknown_field_does_not_count_toward_threshold(self):
        def only_unknown(p):
            for k in ("material", "features"):
                p["technical"][k] = {"value": None, "source": "product_page"}
            p["technical"]["warranty_years"] = {"value": 10, "source": "product_page"}
        v = validate_mutated(only_unknown)
        self.assertEqual(v["status"], "BLOCKED"); self.assertEqual(v["verified_specs"], 1)

    def test_unknown_field_kept_and_source_checked(self):
        v = validate_mutated(lambda p: p["technical"].__setitem__("warranty_years", {"value": 10, "source": "product_page"}))
        self.assertEqual(v["status"], "READY_WITH_FLAGS"); self.assertEqual(v["verified_specs"], 3)
        v = validate_mutated(lambda p: p["technical"].__setitem__("warranty_years", {"value": 10, "source": "ghost"}))
        self.assertEqual(v["status"], "BLOCKED")

    def test_known_non_profile_field_counts(self):
        # material is in schema structure.technical but not in the faucet profile: it still counts (gessi-77201 = 3)
        self.assertEqual(validate(f"products/{PID}.yaml")["verified_specs"], 3)


# ---------------------------------------------------------------- F-32
class TestF32CLI(unittest.TestCase):
    def _run(self, *args, cwd=ROOT):
        r = subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True)
        self.assertNotIn("Traceback", r.stderr, (args, r.stderr))
        return r.returncode, r.stdout, r.stderr

    def test_validate_no_args(self):
        rc, out, err = self._run("validate.py"); self.assertEqual(rc, 2); self.assertIn("usage", err)

    def test_qa_no_args_or_one_arg(self):
        for args in (("qa.py",), ("qa.py", f"products/{PID}.yaml")):
            rc, out, err = self._run(*args); self.assertEqual(rc, 2, args); self.assertIn("usage", err)

    def test_validate_missing_file(self):
        rc, out, err = self._run("validate.py", "products/nope.yaml"); self.assertEqual(rc, 1); self.assertIn("BLOCKED", out)

    def test_qa_missing_product(self):
        rc, out, err = self._run("qa.py", "products/nope.yaml", f"out/{PID}/"); self.assertEqual(rc, 1); self.assertIn("validator", out)

    def test_qa_missing_out_dir(self):
        rc, out, err = self._run("qa.py", f"products/{PID}.yaml", "out/nope/"); self.assertEqual(rc, 1); self.assertIn("files_present", out)

    def test_run_all_no_products(self):
        d = tempfile.mkdtemp(prefix="mody_r4_")
        try:
            for sub in ("brand", "schema", "out"):
                shutil.copytree(os.path.join(ROOT, sub), os.path.join(d, sub))
            os.makedirs(os.path.join(d, "products"))
            for f in ("validate.py", "qa.py", "run_all.py", "SKILL.md"):
                shutil.copy(os.path.join(ROOT, f), d)
            rc, out, err = self._run("run_all.py", cwd=d); self.assertEqual(rc, 1); self.assertIn("no products found", err)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_programming_errors_are_not_swallowed(self):
        src = open("qa.py", encoding="utf-8").read()
        self.assertNotIn("except Exception", src); self.assertNotIn("except:", src)


if __name__ == "__main__":
    unittest.main()
