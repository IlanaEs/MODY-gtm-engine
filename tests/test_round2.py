"""Regression tests for QA fix round 2 (findings F-07 .. F-15).
Run from the project root:  python -m unittest tests.test_round2 -v
"""
import os, re, shutil, subprocess, sys, tempfile, unittest, yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
from validate import validate                                    # noqa: E402
from tests.test_round1 import Fixture, FLAGS, PID                # noqa: E402

KITCHEN = "gessi-g60077"
MARKER = "<!-- QA -->"


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
        self.assertIn(old, self.fx.files[asset], f"fixture has no '{old}' in {asset}")
        self.fx.files[asset] = self.fx.files[asset].replace(old, new)


# ---------------------------------------------------------------- F-07
class TestF07ProvenanceBinding(Base):
    def test_golden_passes(self):
        self.assertPasses(self.fx.qa())

    def test_other_products_provenance_rejected(self):
        self.fx.prov = yaml.safe_load(open(f"out/{KITCHEN}/provenance.yaml", encoding="utf-8"))
        self.assertFails(self.fx.qa(), "provenance_bound")

    def test_product_id_mismatch(self):
        self.fx.prov["product"] = "other"; self.assertFails(self.fx.qa(), "provenance_bound")

    def test_validator_status_mismatch(self):
        self.fx.prov["validator_status"] = "READY"; self.assertFails(self.fx.qa(), "provenance_bound")

    def test_flags_mismatch(self):
        self.fx.prov["flags"] = FLAGS[:2]; self.assertFails(self.fx.qa(), "provenance_bound")

    def test_publishable_mismatch(self):
        self.fx.prov["publishable"] = False; self.assertFails(self.fx.qa(), "provenance_bound")

    def test_publishable_absent_is_not_required(self):
        del self.fx.prov["publishable"]; self.assertPasses(self.fx.qa())

    def test_positioning_missing(self):
        del self.fx.prov["positioning"]; self.assertFails(self.fx.qa(), "positioning")

    def test_wrong_audience_for_tier(self):
        self.fx.prov["positioning"]["primary_audience"] = "C"; self.assertFails(self.fx.qa(), "positioning")

    def test_audience_follows_price_tier(self):
        self.fx.prod["commercial"]["price_tier"] = "core"
        self.fx.prov["positioning"].update(primary_audience="C", secondary_audience="B")
        self.assertEqual(self.fx.qa()["checks"]["positioning"], "PASS")   # slide 3 still names A, so deck_structure fails (F-19)

    def test_missing_tier_expects_A_B(self):
        del self.fx.prod["commercial"]["price_tier"]                    # validator now also emits the price_tier flag (F-21c)
        self.assertEqual(self.fx.qa()["checks"]["positioning"], "PASS")   # golden is A / B
        self.fx.prov["positioning"]["primary_audience"] = "B"; self.assertFails(self.fx.qa(), "positioning")

    def test_unknown_pillar(self):
        self.fx.prov["positioning"]["pillars"] = ["P1", "P9"]; self.assertFails(self.fx.qa(), "positioning")

    def test_pillar_count_2_to_3(self):
        self.fx.prov["positioning"]["pillars"] = ["P1"]; self.assertFails(self.fx.qa(), "positioning")
        self.fx.prov["positioning"]["pillars"] = ["P1", "P2", "P3", "P4"]; self.assertFails(self.fx.qa(), "positioning")

    def test_one_liner_too_long(self):
        self.fx.prov["positioning"]["one_liner"] = " ".join(["מילה"] * 13); self.assertFails(self.fx.qa(), "positioning")

    def test_spec_to_benefit_must_cite_claim_set(self):
        self.fx.prov["positioning"]["spec_to_benefit"].append({"from": "x", "benefit": "y", "ref": "spec:dimensions_mm"})
        self.assertFails(self.fx.qa(), "positioning")

    def test_spec_to_benefit_missing(self):
        self.fx.prov["positioning"]["spec_to_benefit"] = []; self.assertFails(self.fx.qa(), "positioning")


# ---------------------------------------------------------------- F-08
class TestF08Price(Base):
    def test_hidden_price(self):
        self.rep("landing.md", "| מחיר | 5,000 ₪ |", "| מחיר | לפי בקשה |"); self.rep("sales.md", "5,000 ₪.", "לפי בקשה.")
        self.assertFails(self.fx.qa(), "price_exact")

    def test_altered_price(self):
        self.rep("landing.md", "5,000 ₪", "5,001 ₪"); self.assertFails(self.fx.qa(), "price_exact")

    def test_alternate_currency_notation(self):
        for alt in ("5,000 ש\"ח", "5,000 ש״ח", "5,000 שקלים", "5,000 NIS", "5000 ₪", "₪5,000"):
            fx = Fixture()
            try:
                fx.files["landing.md"] = fx.files["landing.md"].replace("5,000 ₪", alt)
                r = fx.qa()
                self.assertEqual(r["checks"]["price_exact"], "FAIL", alt)
            finally:
                fx.close()

    def test_wrong_amount_in_other_notation(self):
        self.rep("landing.md", "5,000 ₪", "726 ש\"ח"); self.assertFails(self.fx.qa(), "price_exact")

    def test_extra_amount_other_currency(self):
        self.rep("sales.md", "5,000 ₪.", "5,000 ₪. באירופה 1,200 €."); self.assertFails(self.fx.qa(), "price_exact")

    def test_extra_amount_small_int(self):
        self.rep("sales.md", "5,000 ₪.", "5,000 ₪. משלוח 9 ₪."); self.assertFails(self.fx.qa(), "price_exact")

    def test_no_price_but_amount_shown(self):
        self.fx.prod["commercial"]["price_ils"] = None; self.assertFails(self.fx.qa(), "price_exact")

    def test_exact_house_format_passes(self):
        self.assertPasses(self.fx.qa())


# ---------------------------------------------------------------- F-09
class TestF09VoiceBypass(Base):
    def test_dont_say_section_first_in_sales(self):
        self.rep("sales.md", "## פתיח (15 שניות)", "## מה לא להגיד\n- כלום\n\n## פתיח (15 שניות)")
        self.rep("sales.md", "זה Jacqueline של Gessi.", "זה Jacqueline של Gessi. מדהים, רק היום.")
        self.assertFails(self.fx.qa(), "voice_sales.md")

    def test_dont_say_heading_in_landing_has_no_effect(self):
        self.rep("landing.md", "## הסיפור", "## מה לא להגיד\n\n## הסיפור")
        self.rep("landing.md", "התהליך ידני", "התהליך ידני, מדהים")
        self.assertFails(self.fx.qa(), "voice_landing.md")

    def test_dont_say_exemption_ends_at_next_heading(self):
        self.rep("sales.md", "- \"הכי יוקרתי בישראל\"\n", "- \"הכי יוקרתי בישראל\"\n\n## עוד\nמדהים\n")
        self.assertFails(self.fx.qa(), "voice_sales.md")

    def test_legit_dont_say_section_is_exempt(self):
        self.assertIn("הכי יוקרתי", self.fx.files["sales.md"]); self.assertPasses(self.fx.qa())

    def test_marker_at_top_of_asset(self):
        self.fx.files["sales.md"] = MARKER + "\n" + self.fx.files["sales.md"].replace("זה Jacqueline של Gessi.", "זה Jacqueline של Gessi. מדהים")
        r = self.fx.qa()
        self.assertFails(r, "qa_footer_sales.md"); self.assertEqual(r["checks"]["voice_sales.md"], "FAIL")

    def test_marker_twice(self):
        self.rep("landing.md", "## הסיפור", MARKER + "\n## הסיפור"); self.assertFails(self.fx.qa(), "qa_footer_landing.md")

    def test_content_after_footer(self):
        self.fx.files["landing.md"] += "\nמדהים\n"; self.assertFails(self.fx.qa(), "qa_footer_landing.md")


# ---------------------------------------------------------------- F-10
class TestF10LineIsolation(Base):
    pid = KITCHEN

    def test_kitchen_tap_passes(self):
        self.assertPasses(self.fx.qa())

    def test_other_line_vocabulary(self):
        self.rep("landing.md", "## למה דווקא הוא", "מלאכת יד מהקו Haute Culture.\n\n## למה דווקא הוא")
        r = self.fx.qa(); self.assertFails(r, "line_isolation_landing.md")
        self.assertIn("Haute Culture", r["fails"][0]); self.assertIn("מלאכת יד", r["fails"][0])

    def test_other_collection_claim_text(self):
        self.rep("landing.md", "## למה דווקא הוא", "הקולקציה הראשונה של Gessi שנוצרה משורשי במבוק אמיתי.\n\n## למה דווקא הוא")
        self.assertFails(self.fx.qa(), "line_isolation_landing.md")

    def test_other_collection_story_line(self):
        self.rep("deck.md", "Notes: מוצר פונקציונלי.", "Notes: חומר טבעי, יד אומן, ואין שניים זהים.")
        self.assertFails(self.fx.qa(), "line_isolation_deck.md")

    def test_vocabulary_inside_word_is_not_flagged(self):
        self.rep("landing.md", "## למה דווקא הוא", "החומרים נבחרו.\n\n## למה דווקא הוא")     # 'חומר' inside 'החומרים'
        self.assertPasses(self.fx.qa())

    def test_dont_say_section_may_name_the_other_line(self):
        self.assertIn("Haute Culture", self.fx.files["sales.md"]); self.assertPasses(self.fx.qa())


class TestF10OwnLineVocabularyAllowed(Base):
    def test_signature_product_uses_its_own_line_vocabulary(self):
        self.assertIn("Haute Culture", self.fx.files["landing.md"]); self.assertPasses(self.fx.qa())

    def test_manufacturer_level_vocabulary_allowed_everywhere(self):
        self.rep("landing.md", "הברז שלך לא חוזר על עצמו", "הברז שלך לא חוזר על עצמו, Made in Italy"); self.assertPasses(self.fx.qa())


# ---------------------------------------------------------------- F-11
class TestF11MalformedInput(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="mody_r2_", dir=ROOT)
        self.base = yaml.safe_load(open(f"products/{PID}.yaml", encoding="utf-8"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _raw(self, text):
        path = os.path.join(self.dir, "p.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return validate(path)

    def _obj(self, mutate):
        mutate(self.base)
        return self._raw(yaml.safe_dump(self.base, allow_unicode=True))

    def test_raw_shapes(self):
        for name, text in [("empty", ""), ("list", "- a\n"), ("scalar", "hello\n"), ("invalid", "product:\n  id: [x\n")]:
            v = self._raw(text)
            self.assertEqual(v["status"], "BLOCKED", name); self.assertTrue(v["errors"], name)

    def test_missing_file(self):
        v = validate(os.path.join(self.dir, "nope.yaml")); self.assertEqual(v["status"], "BLOCKED")

    def test_wrong_section_types(self):
        for name, mutate in [
            ("technical list", lambda p: p.__setitem__("technical", ["x"])),
            ("technical str", lambda p: p.__setitem__("technical", "x")),
            ("sources list", lambda p: p.__setitem__("sources", ["x"])),
            ("sources str", lambda p: p.__setitem__("sources", "x")),
            ("design str", lambda p: p.__setitem__("design", "x")),
            ("product str", lambda p: p.__setitem__("product", "x")),
            ("commercial str", lambda p: p.__setitem__("commercial", "x")),
            ("claims_ref str", lambda p: p["design"].__setitem__("claims_ref", "JQ-1")),
            ("claims_ref dict item", lambda p: p["design"].__setitem__("claims_ref", [{"id": "JQ-1"}])),
            ("claims_ref list item", lambda p: p["design"].__setitem__("claims_ref", [["JQ-1"]])),
            ("category list", lambda p: p["product"].__setitem__("category", ["basin_mixer"])),
            ("category dict", lambda p: p["product"].__setitem__("category", {"a": 1})),
            ("spec source dict", lambda p: p["technical"].__setitem__("finish", {"value": "x", "source": {"a": 1}})),
            ("spec source list", lambda p: p["technical"].__setitem__("finish", {"value": "x", "source": ["product_page"]})),
            ("brand_versions str", lambda p: p.__setitem__("brand_versions", "gessi@1.0")),
            ("brand_versions list", lambda p: p.__setitem__("brand_versions", ["gessi@1.0"])),
        ]:
            self.base = yaml.safe_load(open(f"products/{PID}.yaml", encoding="utf-8"))
            v = self._obj(mutate)
            self.assertEqual(v["status"], "BLOCKED", name)

    def test_malformed_pins(self):
        for pin in ({"manufacturer": "gessi"}, {"manufacturer": "gessi@"}, {"manufacturer": "gessi@1.x"},
                    {"manufacturer": 1.0}, {"house": "latest"}, {"house": ["mody_brand_dna@1.0"]}, {"manufacturer": "gessi@1.0@2"}):
            self.base = yaml.safe_load(open(f"products/{PID}.yaml", encoding="utf-8"))
            v = self._obj(lambda p, pin=pin: p.__setitem__("brand_versions", pin))
            self.assertEqual(v["status"], "BLOCKED", pin)
            self.assertTrue(any("פורמט גרסה" in e for e in v["errors"]), v["errors"])

    def test_valid_pin_still_resolves(self):
        v = self._obj(lambda p: p.__setitem__("brand_versions", {"manufacturer": "gessi@1.0"}))
        self.assertEqual(v["brand_layers"]["manufacturer"], "brand/gessi.v1.0.yaml")


# ---------------------------------------------------------------- F-12
class TestF12RunAllRobustness(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="mody_r2_")
        for d in ("brand", "products", "schema", "out"):
            shutil.copytree(os.path.join(ROOT, d), os.path.join(self.dir, d))
        for f in ("validate.py", "qa.py", "run_all.py", "SKILL.md"):
            shutil.copy(os.path.join(ROOT, f), self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _run(self):
        r = subprocess.run([sys.executable, "run_all.py"], cwd=self.dir, capture_output=True, text=True)
        self.assertNotIn("Traceback", r.stderr, r.stderr)
        for pid in (PID, KITCHEN, "mutina-basrelief-patchwork"):
            self.assertIn(pid, r.stdout, "table row missing for " + pid)
        return r

    def test_green_baseline_exit_0(self):
        self.assertEqual(self._run().returncode, 0)

    def test_provenance_missing(self):
        os.remove(os.path.join(self.dir, "out", PID, "provenance.yaml"))
        r = self._run(); self.assertEqual(r.returncode, 1); self.assertIn("files_present", r.stdout)

    def test_provenance_empty_not_rewritten(self):
        pp = os.path.join(self.dir, "out", PID, "provenance.yaml")
        open(pp, "w").close()
        r = self._run(); self.assertEqual(r.returncode, 1); self.assertIn("provenance_valid", r.stdout)
        self.assertEqual(os.path.getsize(pp), 0, "run_all must not write provenance it could not load")

    def test_provenance_invalid_yaml(self):
        with open(os.path.join(self.dir, "out", PID, "provenance.yaml"), "w") as f:
            f.write("a: [\n")
        self.assertEqual(self._run().returncode, 1)

    def test_out_dir_empty(self):
        d = os.path.join(self.dir, "out", PID)
        for f in os.listdir(d):
            os.remove(os.path.join(d, f))
        self.assertEqual(self._run().returncode, 1)

    def test_malformed_product_does_not_stop_the_run(self):
        with open(os.path.join(self.dir, "products", "zz-bad.yaml"), "w") as f:
            f.write("product:\n  id: [x\n")
        open(os.path.join(self.dir, "products", "zz-empty.yaml"), "w").close()
        r = self._run(); self.assertEqual(r.returncode, 1); self.assertIn("BLOCKED", r.stdout)

    def test_blocked_product_exit_1(self):
        shutil.copy(os.path.join(ROOT, "tests", "broken_example.yaml"), os.path.join(self.dir, "products", "zz-broken.yaml"))
        self.assertEqual(self._run().returncode, 1)


# ---------------------------------------------------------------- F-13
class TestF13MalformedProvenance(Base):
    def _raw(self, text, check="provenance_valid"):
        self.fx.raw_prov = text
        with open(self.fx.out + "provenance.yaml", "w", encoding="utf-8") as f:
            f.write(text)
        ppath = self.fx.write()
        with open(self.fx.out + "provenance.yaml", "w", encoding="utf-8") as f:   # write() re-dumped prov; overwrite again
            f.write(text)
        from qa import run
        r = run(ppath, self.fx.out)
        self.assertFails(r, check)

    def test_invalid_yaml(self):
        self._raw("a: [\n")

    def test_null(self):
        self._raw("")

    def test_scalar(self):
        self._raw("hello\n")

    def test_list(self):
        self._raw("- a\n")

    def test_claims_used_wrong_types(self):
        for cu in ("x", {"a": 1}, 5, ["claim:JQ-1"], [5], [None]):
            fx = Fixture()
            try:
                fx.prov["claims_used"] = cu
                self.assertEqual(fx.qa()["checks"]["provenance_shape"], "FAIL", repr(cu))
            finally:
                fx.close()

    def test_non_string_ref(self):
        self.fx.prov["claims_used"][0]["ref"] = 5; self.assertFails(self.fx.qa(), "provenance_shape")
        self.fx.prov["claims_used"][0]["ref"] = ["claim:JQ-1"]; self.assertFails(self.fx.qa(), "provenance_shape")

    def test_flags_wrong_type(self):
        self.fx.prov["flags"] = "x"; self.assertFails(self.fx.qa(), "provenance_shape")

    def test_brand_versions_wrong_type(self):
        self.fx.prov["brand_versions"] = "brand/gessi.v1.1.yaml"; self.assertFails(self.fx.qa(), "provenance_shape")

    def test_positioning_wrong_type(self):
        self.fx.prov["positioning"] = "x"; self.assertFails(self.fx.qa(), "positioning")


# ---------------------------------------------------------------- F-14
class TestF14FlagsInAllAssets(Base):
    def test_flag_removed_from_sales_body(self):
        self.rep("sales.md", " [חסר: technical.installation_type – לבדיקה]", ""); self.assertFails(self.fx.qa(), "flags_in_sales.md")

    def test_flag_only_in_sales_footer(self):
        self.rep("sales.md", "- **יש דף טכני לשלוח?** נבדוק ונחזור אלייך. [חסר: sources.technical_sheet – לבדיקה]\n", "")
        r = self.fx.qa(); self.assertFails(r, "flags_in_sales.md"); self.assertEqual(r["checks"]["qa_footer_sales.md"], "PASS")

    def test_flag_removed_from_landing_body(self):
        self.rep("landing.md", "| מידות | [חסר: technical.dimensions_mm – לבדיקה] |", "| מידות | לפי דרישה |")
        self.assertFails(self.fx.qa(), "flags_in_landing.md")

    def test_all_flags_present_passes(self):
        self.assertPasses(self.fx.qa())


# ---------------------------------------------------------------- F-15
class TestF15Footer(Base):
    def _footer(self, asset, flags_line=None, vers_line=None):
        body = self.fx.files[asset].split(MARKER)[0]
        fl = flags_line if flags_line is not None else "**דגלים פתוחים:** " + " · ".join(FLAGS)
        vl = vers_line if vers_line is not None else "**גרסאות:** house mody_brand_dna.v1.0 · gessi.v1.1 · skill 1.1.0"
        self.fx.files[asset] = body + MARKER + "\n" + fl + "\n" + vl + "\n"

    def test_marker_only(self):
        self.fx.files["landing.md"] = self.fx.files["landing.md"].split(MARKER)[0] + MARKER + "\n"
        self.assertFails(self.fx.qa(), "qa_footer_landing.md")

    def test_marker_missing(self):
        self.fx.files["landing.md"] = self.fx.files["landing.md"].split(MARKER)[0]
        self.assertFails(self.fx.qa(), "qa_footer_landing.md")

    def test_versions_line_missing(self):
        self._footer("landing.md", vers_line=""); self.assertFails(self.fx.qa(), "qa_footer_landing.md")

    def test_false_ein_with_open_flags(self):
        self._footer("landing.md", flags_line="**דגלים פתוחים:** אין"); self.assertFails(self.fx.qa(), "qa_footer_landing.md")

    def test_flag_missing_from_footer_list(self):
        self._footer("landing.md", flags_line="**דגלים פתוחים:** " + " · ".join(FLAGS[:3])); self.assertFails(self.fx.qa(), "qa_footer_landing.md")

    def test_count_instead_of_list(self):
        self._footer("deck.md", flags_line="**דגלים פתוחים:** 4 (שקף אחרון)"); self.assertFails(self.fx.qa(), "qa_footer_deck.md")

    def test_stale_manufacturer_version(self):
        self._footer("sales.md", vers_line="**גרסאות:** house mody_brand_dna.v1.0 · gessi.v1.0 · skill 1.1.0"); self.assertFails(self.fx.qa(), "qa_footer_sales.md")

    def test_stale_house_version(self):
        self._footer("sales.md", vers_line="**גרסאות:** house mody_brand_dna.v1.1 · gessi.v1.1 · skill 1.1.0"); self.assertFails(self.fx.qa(), "qa_footer_sales.md")

    def test_wrong_skill_version(self):
        self._footer("sales.md", vers_line="**גרסאות:** house mody_brand_dna.v1.0 · gessi.v1.1 · skill 1.0"); self.assertFails(self.fx.qa(), "qa_footer_sales.md")

    def test_marker_not_after_rule(self):
        self.rep("landing.md", "---\n" + MARKER, MARKER); self.assertFails(self.fx.qa(), "qa_footer_landing.md")

    def test_pinned_version_footer_passes(self):
        self.fx.prod["brand_versions"] = {"manufacturer": "gessi@1.0"}
        self.fx.prov["brand_versions"]["manufacturer"] = "brand/gessi.v1.0.yaml"
        for c in self.fx.prov["claims_used"]:                       # brand facts are then sourced from the v1.0 file (F-23)
            if c["source"] == "brand/gessi.v1.1.yaml":
                c["source"] = "brand/gessi.v1.0.yaml"
        for a in self.fx.files:
            self.rep(a, "gessi.v1.1 · skill", "gessi.v1.0 · skill")
        self.assertPasses(self.fx.qa())

    def _no_flags(self):
        t = self.fx.prod["technical"]
        t["dimensions_mm"] = {"value": "200×150", "source": "product_page"}
        t["flow_rate_lpm"] = {"value": 5, "source": "product_page"}
        t["installation_type"] = {"value": "Deck mounted", "source": "product_page"}
        self.fx.prod["sources"]["technical_sheet"] = "https://example.com/sheet.pdf"
        self.fx.prov["flags"] = []; self.fx.prov["validator_status"] = "READY"

    def test_no_flags_requires_ein(self):
        self._no_flags()
        for a in self.fx.files:
            self._footer(a, flags_line="**דגלים פתוחים:** אין")
        self.assertPasses(self.fx.qa())

    def test_no_flags_but_stale_list(self):
        self._no_flags()
        for a in self.fx.files:
            self._footer(a, flags_line="**דגלים פתוחים:** " + FLAGS[0])
        self.assertFails(self.fx.qa(), "qa_footer_landing.md")


if __name__ == "__main__":
    unittest.main()
