"""Regression tests for QA fix round 3A (findings F-16 .. F-21).
Run from the project root:  python -m unittest tests.test_round3a -v
"""
import os, re, shutil, subprocess, sys, tempfile, unittest, yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
from validate import validate                                    # noqa: E402
from qa import EMOJI, EXCLAIM, banned_re, FINALS, run            # noqa: E402
from tests.test_round1 import Fixture, FLAGS, PID, GOLDEN_SLIDES, golden_deck   # noqa: E402

KITCHEN = "gessi-g60077"
TILE = "mutina-basrelief-patchwork"
ANCHOR = "הברז שלך לא חוזר על עצמו"   # a landing phrase that no claims_used entry quotes, so injecting after it keeps provenance intact


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

    def inject(self, text):
        self.rep("landing.md", ANCHOR, ANCHOR + " " + text)
        return self.fx.qa()


# ---------------------------------------------------------------- F-16
class TestF16BannedWords(Base):
    TRUE = ["הכי", "והכי", "שהכי", "מדהים", "ומדהים", "מדהימה", "מדהימים", "המדהימים", "מדהימות", "חובה", "החובה", "רק היום", "ורק היום"]
    COLLISION = ["הכיור", "בהכיור", "הכיוון", "חובבים", "מדהם"]

    def test_true_matches_by_regex(self):
        for term in ("הכי", "מדהים", "חובה", "רק היום"):
            rx = banned_re(term)
            for w in self.TRUE:
                if w.translate(FINALS).endswith(term.translate(FINALS)[:3]) or term in w or term.translate(FINALS)[:-1] in w.translate(FINALS):
                    pass
        hits = {w for w in self.TRUE if any(banned_re(t).search(w.translate(FINALS)) for t in ("הכי", "מדהים", "חובה", "רק היום"))}
        self.assertEqual(hits, set(self.TRUE))

    def test_collisions_by_regex(self):
        for w in self.COLLISION:
            self.assertFalse(any(banned_re(t).search(w.translate(FINALS)) for t in ("הכי", "מדהים", "חובה")), w)

    def test_true_matches_end_to_end(self):
        for w in ("והכי", "מדהימה", "המדהימים", "ומדהים"):
            fx = Fixture()
            try:
                fx.files["landing.md"] = fx.files["landing.md"].replace(ANCHOR, ANCHOR + " " + w)
                r = fx.qa()
                self.assertEqual(r["checks"]["voice_landing.md"], "FAIL", w)
            finally:
                fx.close()

    def test_collisions_end_to_end(self):
        self.assertPasses(self.inject("ליד הכיור, בהכיור ובכיוון הנכון"))

    def test_shipped_texts_unaffected(self):
        for pid in (PID, KITCHEN, TILE):
            fx = Fixture(pid)
            try:
                r = fx.qa()
                self.assertEqual(r["checks"]["voice_landing.md"], "PASS", (pid, r["fails"]))
            finally:
                fx.close()


# ---------------------------------------------------------------- F-17
class TestF17Emoji(Base):
    def test_symbols_detected(self):
        for sym in ("⭐", "‼", "！", "⁉", "🀄", "🎉", "✅", "❤", "⬆"):
            self.assertTrue(EMOJI.search(sym) or EXCLAIM.search(sym), sym)

    def test_ordinary_symbols_not_emoji(self):
        for sym in ("→", "·", "–", "×", "₪", "\"", "?", "…", "©"):
            self.assertFalse(EMOJI.search(sym) or EXCLAIM.search(sym), sym)

    def test_end_to_end(self):
        for sym in ("⭐", "‼", "！"):
            fx = Fixture()
            try:
                fx.files["landing.md"] = fx.files["landing.md"].replace(ANCHOR, ANCHOR + sym)
                self.assertEqual(fx.qa()["checks"]["voice_landing.md"], "FAIL", sym)
            finally:
                fx.close()

    def test_arrow_in_deck_heading_passes(self):
        self.rep("deck.md", "# 02 מיצוב", "# 02 מיצוב → Spec"); self.assertPasses(self.fx.qa())

    def test_image_syntax_not_flagged(self):
        self.assertIn("![", self.fx.files["landing.md"]); self.assertPasses(self.fx.qa())


# ---------------------------------------------------------------- F-18
class TestF18Numbers(Base):
    def test_small_int_facts_rejected(self):
        for txt in ("10 שנות אחריות", "5 שנות אחריות", "8 גימורים", "2 יחידות במלאי", "3 גוונים"):
            fx = Fixture()
            try:
                fx.files["landing.md"] = fx.files["landing.md"].replace(ANCHOR, ANCHOR + " " + txt)
                self.assertEqual(fx.qa()["checks"]["no_invented_numbers"], "FAIL", txt)
            finally:
                fx.close()

    def test_decimals_versions_dates_rejected(self):
        for txt in ("5.7 ליטר לדקה", "1.1 ליטר לדקה", "1.0 בר", "מאז 2024", "3.5 ק\"ג"):
            fx = Fixture()
            try:
                fx.files["landing.md"] = fx.files["landing.md"].replace(ANCHOR, ANCHOR + " " + txt)
                self.assertEqual(fx.qa()["checks"]["no_invented_numbers"], "FAIL", txt)
            finally:
                fx.close()

    def test_url_number_not_authorised(self):
        fx = Fixture(TILE)                                  # technical_sheet URL contains 2302 and 66
        try:
            fx.files["landing.md"] = fx.files["landing.md"].replace("## ב-MODY", "2302 יחידות במלאי, 66 בדרך.\n\n## ב-MODY")
            self.assertEqual(fx.qa()["checks"]["no_invented_numbers"], "FAIL")
        finally:
            fx.close()

    def test_structural_counts_allowed(self):
        self.assertIn("## 3 נקודות", self.fx.files["sales.md"]); self.assertIn("## פתיח (15 שניות)", self.fx.files["sales.md"])
        self.assertPasses(self.fx.qa())

    def test_factual_values_allowed(self):
        self.assertPasses(self.inject("גימור 726, דגם 77201"))

    def test_tile_values_allowed(self):
        fx = Fixture(TILE)
        try:
            self.assertIn("18×54", fx.files["landing.md"]); self.assertIn("9 מ\"מ", fx.files["landing.md"]); self.assertPasses(fx.qa())
        finally:
            fx.close()

    def test_claim_and_pillar_ids_not_numbers(self):
        self.assertIn("(JQ-3)", self.fx.files["deck.md"])
        self.rep("deck.md", "Notes: פתחו מהתמונה.", "Notes: P5 תמיד מותר. (JQ-5)"); self.assertPasses(self.fx.qa())

    def test_count_noun_does_not_launder_facts(self):
        self.assertEqual(self.inject("10 שנות אחריות ל-3 נקודות")["checks"]["no_invented_numbers"], "FAIL")


# ---------------------------------------------------------------- F-19
class TestF19Landing(Base):
    def _drop(self, head, until):
        t = self.fx.files["landing.md"]; i = t.index(head); j = t.index(until, i); self.fx.files["landing.md"] = t[:i] + t[j:]

    def test_golden_passes(self):
        self.assertPasses(self.fx.qa())

    def test_missing_story(self):
        self._drop("## הסיפור", "## למה דווקא הוא"); self.assertFails(self.fx.qa(), "landing_structure")

    def test_missing_why(self):
        self._drop("## למה דווקא הוא", "## פרטים"); self.assertFails(self.fx.qa(), "landing_structure")

    def test_missing_mody(self):
        self._drop("## ב-MODY", "---\n<!-- QA -->"); self.assertFails(self.fx.qa(), "landing_structure")

    def test_wrong_order(self):
        self.rep("landing.md", "## הסיפור", "## ב-MODY\nטקסט.\n\n## הסיפור"); self.assertFails(self.fx.qa(), "landing_structure")

    def test_renamed_section(self):
        self.rep("landing.md", "## פרטים", "## מפרט"); self.assertFails(self.fx.qa(), "landing_structure")

    def test_extra_section(self):
        self.rep("landing.md", "## ב-MODY", "## בונוס\nטקסט.\n\n## ב-MODY"); self.assertFails(self.fx.qa(), "landing_structure")

    def test_sub_headline_must_equal_one_liner(self):
        self.rep("landing.md", "haute couture לכיור. שורש במבוק, יד אומן, אין שניים זהים.", "ברז יפה מאוד.")
        self.assertFails(self.fx.qa(), "landing_structure")

    def test_missing_image(self):
        self.rep("landing.md", "![GESSI Jacqueline 77201](assets/77201_warm-bronze.png)\n", ""); self.assertFails(self.fx.qa(), "landing_structure")

    def test_wrong_image_path(self):
        self.rep("landing.md", "assets/77201_warm-bronze.png", "assets/other.png"); self.assertFails(self.fx.qa(), "landing_structure")

    def test_second_h1(self):
        self.rep("landing.md", "## הסיפור", "# כותרת שנייה\n\n## הסיפור"); self.assertFails(self.fx.qa(), "landing_structure")

    def test_four_benefits(self):
        self.rep("landing.md", "## פרטים", "- **עוד תועלת.** טקסט.\n\n## פרטים"); self.assertFails(self.fx.qa(), "landing_structure")

    def test_story_four_sentences(self):
        self.rep("landing.md", "ולכן כל פריט הוא יחיד.", "ולכן כל פריט הוא יחיד. משפט רביעי כאן."); self.assertFails(self.fx.qa(), "landing_structure")

    def test_mody_three_sentences(self):
        self.rep("landing.md", "מהבחירה ועד ההתקנה.", "מהבחירה ועד ההתקנה. משפט שלישי."); self.assertFails(self.fx.qa(), "landing_structure")

    def test_missing_details_rows(self):
        for row in ("| מותג / סדרה | GESSI · Jacqueline · Haute Culture |\n", "| מק\"ט | 77201 |\n", "| גימור | 726 – Warm Bronze Br. PVD |\n"):
            fx = Fixture()
            try:
                fx.files["landing.md"] = fx.files["landing.md"].replace(row, "")
                self.assertEqual(fx.qa()["checks"]["landing_structure"], "FAIL", row)
            finally:
                fx.close()


class TestF19LandingNoCollection(Base):
    pid = KITCHEN

    def test_kitchen_tap_passes_without_story(self):
        self.assertPasses(self.fx.qa())

    def test_story_forbidden_without_collection(self):
        self.rep("landing.md", "## למה דווקא הוא", "## הסיפור\nסיפור.\n\n## למה דווקא הוא"); self.assertFails(self.fx.qa(), "landing_structure")

    def test_image_flag_required_when_no_image(self):
        self.rep("landing.md", "[חסר: sources.image – לבדיקה]\n\n## למה", "\n## למה"); self.assertFails(self.fx.qa(), "landing_structure")

    def test_tile_without_finish_needs_no_finish_row(self):
        fx = Fixture(TILE)
        try:
            self.assertNotIn("| גימור |", fx.files["landing.md"]); self.assertPasses(fx.qa())
        finally:
            fx.close()


class TestF19Sales(Base):
    def _drop(self, head, until):
        t = self.fx.files["sales.md"]; i = t.index(head); j = t.index(until, i); self.fx.files["sales.md"] = t[:i] + t[j:]

    def test_missing_sections(self):
        for head, until in (("## 3 נקודות לאדריכל/ית", "## 3 נקודות ללקוח"), ("## שאלות צפויות ותשובות", "## מה לא להגיד"), ("## מה לא להגיד", "---\n<!-- QA -->")):
            fx = Fixture()
            try:
                t = fx.files["sales.md"]; i = t.index(head); j = t.index(until, i); fx.files["sales.md"] = t[:i] + t[j:]
                self.assertEqual(fx.qa()["checks"]["sales_structure"], "FAIL", head)
            finally:
                fx.close()

    def test_renamed_opening(self):
        self.rep("sales.md", "## פתיח (15 שניות)", "## פתיח קצר"); self.assertFails(self.fx.qa(), "sales_structure")

    def test_wrong_order(self):
        t = self.fx.files["sales.md"]; a = t.index("## 3 נקודות לאדריכל/ית"); b = t.index("## 3 נקודות ללקוח"); c = t.index("## שאלות")
        self.fx.files["sales.md"] = t[:a] + t[b:c] + t[a:b] + t[c:]
        self.assertFails(self.fx.qa(), "sales_structure")

    def test_two_points_only(self):
        self.rep("sales.md", "- פיה מסתובבת. יפה, ועובד כל יום.\n", ""); self.assertFails(self.fx.qa(), "sales_structure")

    def test_empty_qa_section(self):
        self._drop("- **מה המידות?**", "## מה לא להגיד")
        r = self.fx.qa(); self.assertEqual(r["checks"]["sales_structure"], "FAIL")


class TestF19DeckContent(Base):
    def _deck(self, slides):
        self.fx.files["deck.md"] = golden_deck(slides); return self.fx.qa()

    def test_one_liner_missing_on_slide1(self):
        s = list(GOLDEN_SLIDES); s[0] = s[0].replace("haute couture לכיור. שורש במבוק, יד אומן, אין שניים זהים.", "ברז.")
        self.assertFails(self._deck(s), "deck_structure")

    def test_audience_name_missing_on_slide3(self):
        s = list(GOLDEN_SLIDES); s[3] = s[3].replace("לקוחות פרטיים בבנייה או שיפוץ ברמה גבוהה", "לקוחות פרטיים")
        self.assertFails(self._deck(s), "deck_structure")

    def test_audience_need_missing_on_slide3(self):
        s = list(GOLDEN_SLIDES); s[3] = s[3].replace("ייחודיות · סיפור להציג ללקוח · גימורים וזמינות", "")
        self.assertFails(self._deck(s), "deck_structure")

    def test_pillar_name_missing_on_slide4(self):
        s = list(GOLDEN_SLIDES); s[5] = s[5].replace("- **Swivel spout** ← יופי שעובד כל יום\n", "").replace("3. יופי שעובד כל יום\n", "")
        self.assertFails(self._deck(s), "deck_structure")

    def test_benefit_missing_on_slide5(self):
        s = list(GOLDEN_SLIDES); s[5] = s[5].replace("פריט שאין לאף אחד אחר", "תועלת שלא בדף הנחיתה")
        self.assertFails(self._deck(s), "deck_structure")

    def test_slide6_line_not_from_sales(self):
        s = list(GOLDEN_SLIDES); s[6] = s[6].replace("כל פריט יחיד. זה חלק מהעיצוב, לא פגם.", "משפט שלא קיים במסמך המכירות.")
        self.assertFails(self._deck(s), "deck_structure")

    def test_slide6_two_lines(self):
        s = list(GOLDEN_SLIDES); s[6] = s[6].replace("- \"הידית בהשראת סוגרי תיקים ואביזרי אופנה.\"\n", "")
        self.assertFails(self._deck(s), "deck_structure")

    def test_slide7_flag_without_owner(self):
        s = list(GOLDEN_SLIDES); s[7] = s[7].replace("אחראי: מנהל/ת מוצר", "אחראי: ")
        self.assertFails(self._deck(s), "deck_structure")

    def test_shipped_decks_pass(self):
        for pid in (KITCHEN, TILE):
            fx = Fixture(pid)
            try:
                self.assertEqual(fx.qa()["checks"]["deck_structure"], "PASS", (pid, fx.qa()["fails"]))
            finally:
                fx.close()


# ---------------------------------------------------------------- F-20
class TestF20DraftBanner(Base):
    pid = KITCHEN
    BANNER = "> טיוטה – לא לפרסום. חסר: sources.image, commercial.price_ils"

    def _set(self, first_line, asset="landing.md"):
        body = self.fx.files[asset].split("\n", 1)[1]
        self.fx.files[asset] = (first_line + "\n" + body) if first_line is not None else body.lstrip("\n")

    def test_exact_banner_passes(self):
        self.assertTrue(all(f.startswith(self.BANNER + "\n") for f in self.fx.files.values())); self.assertPasses(self.fx.qa())

    def test_banner_missing(self):
        self._set(None); self.assertFails(self.fx.qa(), "draft_banner_landing.md")

    def test_banner_on_line_3(self):
        self._set(None); self.fx.files["landing.md"] = "\n\n" + self.BANNER + "\n" + self.fx.files["landing.md"]
        self.assertFails(self.fx.qa(), "draft_banner_landing.md")

    def test_wrong_blockers(self):
        for bad in ("> טיוטה – לא לפרסום. חסר: כלום", "> טיוטה – לא לפרסום. חסר: sources.image",
                    "> טיוטה – לא לפרסום. חסר: commercial.price_ils, sources.image",
                    "> טיוטה – לא לפרסום. חסר: sources.image, commercial.price_ils, product.model_number",
                    "> טיוטה – לא לפרסום", "טיוטה – לא לפרסום. חסר: sources.image, commercial.price_ils",
                    "> טיוטה - לא לפרסום. חסר: sources.image, commercial.price_ils"):
            fx = Fixture(KITCHEN)
            try:
                fx.files["landing.md"] = bad + "\n" + fx.files["landing.md"].split("\n", 1)[1]
                self.assertEqual(fx.qa()["checks"]["draft_banner_landing.md"], "FAIL", bad)
            finally:
                fx.close()

    def test_banner_only_in_two_assets(self):
        self._set(None, "sales.md"); self.assertFails(self.fx.qa(), "draft_banner_sales.md")


class TestF20PublishableHasNoBanner(Base):
    def test_publishable_with_banner_fails(self):
        self.fx.files["landing.md"] = "> טיוטה – לא לפרסום. חסר: x\n\n" + self.fx.files["landing.md"]
        self.assertFails(self.fx.qa(), "draft_banner_landing.md")

    def test_publishable_banner_later_in_body_fails(self):
        self.rep("landing.md", "## ב-MODY", "> טיוטה – לא לפרסום. חסר: x\n\n## ב-MODY"); self.assertFails(self.fx.qa(), "draft_banner_landing.md")


# ---------------------------------------------------------------- F-21
class TestF21CrossDocument(unittest.TestCase):
    def _validate(self, mutate, pid=PID):
        p = yaml.safe_load(open(f"products/{pid}.yaml", encoding="utf-8")); mutate(p)
        d = tempfile.mkdtemp(prefix="mody_r3_", dir=ROOT)
        try:
            path = os.path.join(d, "p.yaml")
            with open(path, "w", encoding="utf-8") as f:
                yaml.safe_dump(p, f, allow_unicode=True)
            return validate(path)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_21a_opening_heading_with_15_passes_number_check(self):
        fx = Fixture()
        try:
            self.assertIn("## פתיח (15 שניות)", fx.files["sales.md"])
            r = fx.qa(); self.assertEqual(r["checks"]["no_invented_numbers"], "PASS"); self.assertEqual(r["checks"]["sales_structure"], "PASS")
        finally:
            fx.close()

    def test_21b_skill_and_qa_agree_on_seven_slides(self):
        skill = open("SKILL.md", encoding="utf-8").read()
        self.assertIn("7 slides", skill)
        from qa import DECK_ROLES; self.assertEqual(len(DECK_ROLES), 8)

    def test_21c_missing_price_tier_flag(self):
        v = self._validate(lambda p: p["commercial"].pop("price_tier"))
        self.assertIn("[חסר: price_tier – לבדיקה]", v["flags"]); self.assertNotEqual(v["status"], "BLOCKED")
        v = self._validate(lambda p: p["commercial"].__setitem__("price_tier", None))
        self.assertIn("[חסר: price_tier – לבדיקה]", v["flags"])

    def test_21c_flag_enforced_in_outputs(self):
        fx = Fixture()
        try:
            del fx.prod["commercial"]["price_tier"]
            r = fx.qa()
            for c in ("flags_in_landing.md", "flags_in_deck.md", "flags_in_sales.md", "provenance_bound"):
                self.assertEqual(r["checks"][c], "FAIL", c)
        finally:
            fx.close()

    def test_21d_brand_versions_is_a_pin_and_resolved_versions_go_to_provenance(self):
        schema = open("schema/product_input.schema.yaml", encoding="utf-8").read()
        self.assertNotIn("נכתב אוטומטית בזמן הרצה", schema)
        self.assertIn("provenance.yaml", schema)
        for pid in (PID, KITCHEN, TILE):
            p = yaml.safe_load(open(f"products/{pid}.yaml", encoding="utf-8"))
            self.assertNotIn("brand_versions", p, "the pipeline must not write pins into product inputs")
            prov = yaml.safe_load(open(f"out/{pid}/provenance.yaml", encoding="utf-8"))
            self.assertEqual(prov["brand_versions"], validate(f"products/{pid}.yaml")["brand_layers"])

    def test_21e_price_source_must_resolve(self):
        v = self._validate(lambda p: p["commercial"]["price_ils"].__setitem__("source", "ghost"))
        self.assertEqual(v["status"], "BLOCKED"); self.assertTrue(any("commercial.price_ils" in e for e in v["errors"]))

    def test_21e_signature_material_source_must_resolve(self):
        v = self._validate(lambda p: p["design"]["signature_material"].__setitem__("source", "ghost"))
        self.assertEqual(v["status"], "BLOCKED"); self.assertTrue(any("design.signature_material" in e for e in v["errors"]))

    def test_21e_price_without_value_is_a_publish_blocker(self):
        v = self._validate(lambda p: p["commercial"].__setitem__("price_ils", {"value": None, "source": "mody_listing"}))
        self.assertIn("commercial.price_ils", v["publish_blockers"]); self.assertEqual(v["flags"].count("[חסר: commercial.price_ils – לבדיקה]"), 1)

    def test_21e_valid_sources_still_pass(self):
        for pid in (PID, KITCHEN, TILE):
            self.assertEqual(validate(f"products/{pid}.yaml")["status"], "READY_WITH_FLAGS", pid)

    def test_21f_price_tier_enum(self):
        for bad in ("luxury", "Core", 5, ["core"]):
            v = self._validate(lambda p, bad=bad: p["commercial"].__setitem__("price_tier", bad))
            self.assertEqual(v["status"], "BLOCKED", bad); self.assertTrue(any("price_tier" in e for e in v["errors"]), bad)
        for ok in ("core", "premium", "signature"):
            self.assertNotEqual(self._validate(lambda p, ok=ok: p["commercial"].__setitem__("price_tier", ok))["status"], "BLOCKED")

    def test_21g_planted_control_runnable_as_documented(self):
        r = subprocess.run([sys.executable, "-m", "unittest", "tests.test_planted"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        readme = open("README.md", encoding="utf-8").read()
        self.assertIn("tests.test_planted", readme); self.assertIn("tests/broken_example.yaml", readme)

    def test_21h_dependency_declared(self):
        req = open("requirements.txt", encoding="utf-8").read().lower()
        self.assertIn("pyyaml", req); self.assertIn("requirements.txt", open("README.md", encoding="utf-8").read())

    def test_21i_qa_checks_is_a_mapping_everywhere(self):
        skill = open("SKILL.md", encoding="utf-8").read()
        self.assertIn("checks: {...}", skill)
        d = tempfile.mkdtemp(prefix="mody_r3_")
        try:
            for sub in ("brand", "products", "schema", "out"):
                shutil.copytree(os.path.join(ROOT, sub), os.path.join(d, sub))
            for f in ("validate.py", "qa.py", "run_all.py", "SKILL.md"):
                shutil.copy(os.path.join(ROOT, f), d)
            r = subprocess.run([sys.executable, "run_all.py"], cwd=d, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            prov = yaml.safe_load(open(os.path.join(d, "out", PID, "provenance.yaml"), encoding="utf-8"))
            self.assertIsInstance(prov["qa"]["checks"], dict)
            self.assertEqual(prov["qa"]["status"], "PASS"); self.assertEqual(prov["qa"]["checks"]["price_exact"], "PASS")
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
