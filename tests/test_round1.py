"""Regression tests for QA fix round 1 (findings F-01 .. F-06).
Run from the project root:  python -m unittest tests.test_round1 -v
Fixtures are built from products/gessi-77201.yaml + out/gessi-77201/ and corrected to SKILL.md
(the 8-slide GTM deck with roles + Notes:, provenance refs typed per SKILL step 4) so a compliant output
is proven to PASS before every scenario proves its FAIL.
"""
import copy, os, re, shutil, subprocess, sys, tempfile, unittest, yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)                                   # validate/qa resolve brand/, schema/, SKILL.md relative to cwd
sys.path.insert(0, ROOT)
from validate import validate, allowed_claim_ids, spec_status   # noqa: E402
from qa import run as qa_run                                     # noqa: E402

PID = "gessi-77201"
FLAGS = ["[חסר: technical.dimensions_mm – לבדיקה]", "[חסר: technical.flow_rate_lpm – לבדיקה]",
         "[חסר: technical.installation_type – לבדיקה]", "[חסר: sources.technical_sheet – לבדיקה]"]
FOOTER = "\n---\n<!-- QA -->\n**דגלים פתוחים:** " + " · ".join(FLAGS) + "\n**גרסאות:** house mody_brand_dna.v1.0 · gessi.v1.1 · skill 1.1.0\n"
GOLDEN_SLIDES = [   # the rendered out/gessi-77201/deck.md: cover + the 7 GTM slides (SKILL 6b)
    '# GESSI Jacqueline 77201 / ברז לכיור\nhaute couture לכיור. שורש במבוק, יד אומן, אין שניים זהים.\nGESSI · Jacqueline\n![](assets/77201_warm-bronze.png)\n\nNotes: פתחו מהתמונה. הבמבוק הוא הסיפור כולו.\n',
    '# 01 סקירת מוצר\nמוצר: Jacqueline 77201\nמותג / קולקציה: GESSI / Jacqueline\nקטגוריה: ברז לכיור\nמק"ט: 77201\n- חומר חתימה: Real bamboo root, handcrafted\n- גימור: 726 – Warm Bronze Br. PVD\n- מאפיינים: Low spout · Swivel spout · Horn-effect lever · Connecting flexibles included · Without waste\n- חומר: Bamboo root + metal\n- מחיר: 5,000 ₪\n- דרגת מחיר: signature\nhaute couture לכיור. שורש במבוק, יד אומן, אין שניים זהים.\n\nNotes: עובדות מאומתות בלבד: מידות, ספיקה והתקנה עדיין פתוחות, ולכן אינן כאן.\n',
    '# 02 מיצוב\nפריט חתימה לחדר רחצה מעוצב, לא עוד ברז. שורש במבוק אמיתי בעבודת יד, שאין שני זהים לו.\n- **הצעת ערך**: חומר טבעי בעיבוד ידני, שהופך את הכיור לנקודת המוקד של החלל.\n- **בידול**: הקולקציה הראשונה של Gessi משורשי במבוק אמיתי. הגוון והפרקים משתנים מפריט לפריט.\n\nNotes: לא ברז אלא פריט חתימה. המיצוב נשען על טענה מאושרת (JQ-3) ועל חומר החתימה.\n',
    '# 03 קהל יעד\n**לקוח פרטי**\n- לקוחות פרטיים בבנייה או שיפוץ ברמה גבוהה\n- הצורך: פריט אחד שמגדיר את חדר הרחצה ומחזיק מעמד לאורך שנים.\n- מה מכריע: פריט שמגדיר את החלל · איכות לאורך זמן\n- עבודת יד איטלקית, עם ליווי של MODY מהבחירה ועד ההתקנה.\n**אדריכל / מעצב**\n- אדריכלים ומעצבי פנים\n- הצורך: סיפור חומר שאפשר להציג ללקוח, ונתונים מדויקים לתכנון.\n- מה מכריע: ייחודיות · סיפור להציג ללקוח · גימורים וזמינות\n- קו Haute Culture נותן למעצב פריט שמייחד את הפרויקט.\n**מכירות / אולם תצוגה**\n- למי להמליץ: חדר רחצה ראשי בפרויקט ברמה גבוהה\n- איך לפתוח: זה Jacqueline של Gessi.\n- מה להדגיש: זה הפריט שמגדיר את חדר הרחצה\n\nNotes: המחיר ממקם את המוצר ב-signature, ולכן המעצב הוא הערוץ הראשון.\n',
    '# 04 מסר מותג\n## שורש במבוק, יד אומן, אין שניים זהים\nטון: אלגנטי · בטוח · שקט · מדויק\n1. שורש במבוק אמיתי, נבחר ומעובד ביד.\n2. אין שני ברזים זהים. זה העיצוב, לא פגם.\n3. Haute couture לכיור: הידית בהשראת אביזרי אופנה.\n- לומר: שלושת מסרי המפתח, כלשונם  |  לא לומר: השוואות, סופרלטיבים וטענות ללא מקור\n\nNotes: הכותרת היא כותרת דף הנחיתה. להגיד בשקט, בלי סופרלטיבים.\n',
    '# 05 סיפור מוצר ותועלות\nJacqueline היא הקולקציה הראשונה של Gessi שנוצרה משורשי במבוק אמיתי. כל שורש נבחר ביד לפי הקוטר ולפי המרווח בין הפרקים, מעובד באדים ומשולב במתכת. כמו בגד שנתפר לפי מידה, התהליך ידני, ולכן כל פריט הוא יחיד.\n- **Real bamboo root, handcrafted** ← פריט שאין לאף אחד אחר\n- **הידיות בהשראת סוגרי תיקים ואביזרי אופנה** ← מגע של אביזר אופנה\n- **Swivel spout** ← יופי שעובד כל יום\n1. פריט שאין לאף אחד אחר\n2. מגע של אביזר אופנה\n3. יופי שעובד כל יום\n\nNotes: כל תועלת נשענת על עובדה מאומתת: חומר חתימה, JQ-4, פיה מסתובבת.\n',
    '# 06 כלים למכירה\n**מתי להמליץ**\n- חדר רחצה ראשי בפרויקט ברמה גבוהה\n- לקוח שמחפש פריט חתימה, לא פתרון סטנדרטי\n- מעצב/ת שמחפש/ת סיפור חומר לפרויקט\n- חלל בגוונים חמים, שהברונזה משלימה\n**איך להציג**\n- פתיח: זה Jacqueline של Gessi.\n- ללקוח הפרטי: זה הפריט שמגדיר את חדר הרחצה\n- לאדריכלים: אפשר להמשיך את אותה שפה לכל חדר הרחצה עם Total Look.\n**לזכור**\n- "זה Jacqueline של Gessi. הגוף עשוי משורש במבוק אמיתי שנבחר ועובד ביד, ולכן אין שני ברזים זהים."\n- "כל פריט יחיד. זה חלק מהעיצוב, לא פגם."\n- "הידית בהשראת סוגרי תיקים ואביזרי אופנה."\n\nNotes: שלוש השורות לזכור לקוחות מהנחיות המכירה. לא להבטיח תחזוקה או עמידות.\n',
    '# 07 תוכנית השקה\n| שלב | פעולה |\n|---|---|\n| 01 נכסים | דף מוצר פנימי · מצגת השקה פנימית · הנחיות מכירה · מפרט מאומת מהמקורות · תמונת מוצר מאושרת: [חסר: sources.image – לבדיקה] · סטטוס: טיוטה עד לאישור תמונת מוצר |\n| 02 הכשרה | הנחיות המכירה ושקף כלים למכירה לצוות המכירות · מסרים מאושרים מחבילת ההשקה |\n| 03 ערוצים | ערוצי ההשקה טרם הוגדרו: להחלטה עם צוות השיווק |\n| 04 מדידה | מדדי ההצלחה טרם הוגדרו: להחלטה לפני ההשקה |\n**הצעד הבא:** אחראי: מנהל/ת מוצר  |  סטטוס: מאומת, ניתן לפרסום  |  תאריך השקה: להגדרה  |  החלטות פתוחות: [חסר: technical.dimensions_mm – לבדיקה] · [חסר: technical.flow_rate_lpm – לבדיקה] · [חסר: technical.installation_type – לבדיקה] · [חסר: sources.technical_sheet – לבדיקה]\n\nNotes: עד שהדגלים ייסגרו, אין לפרסם מידות או ספיקה.\n',
]


def golden_deck(slides=None):
    return "\n---\n\n".join(slides or GOLDEN_SLIDES) + FOOTER


class Fixture:
    """A product + out dir in a temp directory, starting from a SKILL-compliant copy of gessi-77201."""

    def __init__(self, pid=PID):
        self.dir = tempfile.mkdtemp(prefix="mody_r1_", dir=ROOT)   # inside ROOT so relative paths keep working
        self.out = os.path.join(self.dir, "out") + os.sep
        os.makedirs(self.out)
        self.prod = yaml.safe_load(open(f"products/{pid}.yaml", encoding="utf-8"))
        self.files = {a: open(f"out/{pid}/{a}", encoding="utf-8").read() for a in ("landing.md", "deck.md", "sales.md")}
        if pid == PID:
            self.files["deck.md"] = golden_deck()
        self.prov = yaml.safe_load(open(f"out/{pid}/provenance.yaml", encoding="utf-8"))
        for c in self.prov["claims_used"]:                       # SKILL step 4: local_presence / cross_sell are `brand` facts
            if c["ref"] in ("house:local_presence", "house:cross_sell"):
                c["ref"] = c["ref"].replace("house:", "brand:")

    def write(self):
        ppath = os.path.join(self.dir, "product.yaml")
        with open(ppath, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.prod, f, allow_unicode=True, sort_keys=False)
        for a, t in self.files.items():
            with open(self.out + a, "w", encoding="utf-8") as f:
                f.write(t)
        with open(self.out + "provenance.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(self.prov, f, allow_unicode=True, sort_keys=False)
        return ppath

    def validate(self):
        return validate(self.write())

    def qa(self):
        return qa_run(self.write(), self.out)

    def add_ref(self, ref, text="x"):
        self.prov["claims_used"].append({"asset": "landing", "text": text, "ref": ref, "source": "product_page"})

    def add_banner(self):
        for a in self.files:
            self.files[a] = "> טיוטה – לא לפרסום. חסר: x\n\n" + self.files[a]

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()

    def tearDown(self):
        self.fx.close()

    def assertFails(self, result, check, msg=""):
        self.assertEqual(result["status"], "FAIL", msg or result)
        self.assertEqual(result["checks"].get(check), "FAIL", f"{check} should FAIL: {result['fails']}")


class TestGolden(Base):
    def test_compliant_output_passes(self):
        r = self.fx.qa()
        self.assertEqual(r["status"], "PASS", r["fails"])


class TestF01BlockedNeverPasses(Base):
    def _blocked(self):
        r = self.fx.qa()
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("validator", r["checks"])
        self.assertTrue(r["fails"][0].startswith("validator: BLOCKED"), r["fails"])

    def test_nonexistent_claim_with_banner(self):
        self.fx.prod["design"]["claims_ref"].append("JQ-9"); self.fx.add_ref("claim:JQ-9"); self.fx.add_banner(); self._blocked()

    def test_unresolved_spec_source_with_banner(self):
        self.fx.prod["technical"]["finish"]["source"] = "nowhere"; self.fx.add_banner(); self._blocked()

    def test_other_manufacturer_claim_with_banner(self):
        self.fx.prod["design"]["claims_ref"].append("MB-1"); self.fx.add_ref("claim:MB-1"); self.fx.add_banner(); self._blocked()

    def test_missing_required_field_with_banner(self):
        self.fx.prod["sources"]["product_page"] = None; self.fx.add_banner(); self._blocked()

    def test_missing_brand_file_does_not_crash(self):
        self.fx.prod["product"]["brand"] = "newbrand"; self._blocked()


TESTCO = """meta: {id: zz_testco, version: "1.0", layer: manufacturer}
identity: יצרן בדיקה
local_presence: אולם
voice_extension: {vocabulary: [בדיקה], angle: x, cross_sell: y}
lines:
  line_a:
    collections:
      col_a:
        approved_claims: [{id: TA-1, claim: א, source: https://a.example}]
      col_a2:
        approved_claims: [{id: TA2-1, claim: א2, source: https://a2.example}]
  line_b:
    collections:
      col_b:
        approved_claims: [{id: TB-1, claim: ב, source: https://b.example}]
"""


class TestF02ClaimIsolation(Base):
    BRAND = "brand/zz_testco.v1.0.yaml"

    def setUp(self):
        super().setUp()
        with open(self.BRAND, "w", encoding="utf-8") as f:
            f.write(TESTCO)
        self.fx.prod["product"].update({"brand": "zz_testco", "line": "Line A", "collection": "Col_A"})

    def tearDown(self):
        os.remove(self.BRAND); super().tearDown()

    def _claims(self, ids):
        self.fx.prod["design"]["claims_ref"] = ids
        return self.fx.validate()

    def test_own_collection_claim_ok(self):
        self.assertNotEqual(self._claims(["TA-1"])["status"], "BLOCKED")

    def test_other_line_claim_blocked(self):
        self.assertEqual(self._claims(["TB-1"])["status"], "BLOCKED")

    def test_sibling_collection_claim_blocked(self):
        self.assertEqual(self._claims(["TA2-1"])["status"], "BLOCKED")

    def test_no_collection_means_no_claims(self):
        self.fx.prod["product"]["collection"] = None
        self.assertEqual(self._claims(["TA-1"])["status"], "BLOCKED")

    def test_no_line_uses_default_only(self):
        self.fx.prod["product"]["line"] = None          # zz_testco has no lines.default
        self.assertEqual(self._claims(["TA-1"])["status"], "BLOCKED")


class TestF02ShippedProducts(unittest.TestCase):
    def test_gessi_line_and_collection_match_case_insensitively(self):
        self.assertEqual(validate("products/gessi-77201.yaml")["status"], "READY_WITH_FLAGS")

    def test_mutina_default_line(self):
        self.assertEqual(validate("products/mutina-basrelief-patchwork.yaml")["status"], "READY_WITH_FLAGS")

    def test_kitchen_tap_without_collection_cannot_use_jacqueline_claims(self):
        p = yaml.safe_load(open("products/gessi-g60077.yaml", encoding="utf-8"))
        p["design"]["claims_ref"] = ["JQ-1"]
        path = os.path.join(tempfile.mkdtemp(dir=ROOT), "p.yaml")
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(p, f, allow_unicode=True)
        try:
            self.assertEqual(validate(path)["status"], "BLOCKED")
        finally:
            shutil.rmtree(os.path.dirname(path))

    def test_gessi_77201_without_collection_blocked(self):
        p = yaml.safe_load(open("products/gessi-77201.yaml", encoding="utf-8"))
        p["product"]["collection"] = None; p["product"]["line"] = None
        self.assertEqual(allowed_claim_ids(yaml.safe_load(open("brand/gessi.v1.1.yaml", encoding="utf-8")), p), set())


class TestF03ProvenanceRefs(Base):
    def test_house_fake_claim(self):
        self.fx.add_ref("house:fake_claim"); self.assertFails(self.fx.qa(), "provenance_refs_resolve")

    def test_brand_fake_claim(self):
        self.fx.add_ref("brand:fake_claim"); self.assertFails(self.fx.qa(), "provenance_refs_resolve")

    def test_commercial_warranty(self):
        self.fx.add_ref("commercial:warranty"); self.assertFails(self.fx.qa(), "provenance_refs_resolve")

    def test_house_local_presence_is_mistyped(self):
        self.fx.add_ref("house:local_presence"); self.assertFails(self.fx.qa(), "provenance_refs_resolve")

    def test_valid_kinds_still_resolve(self):
        for ref in ("house:P5", "house:P1", "house:role", "house:A", "brand:identity", "brand:local_presence",
                    "brand:relationship", "brand:cross_sell", "commercial:price_ils", "spec:finish", "claim:JQ-1"):
            self.fx.add_ref(ref)
        r = self.fx.qa()
        self.assertEqual(r["checks"]["provenance_refs_resolve"], "PASS", r["fails"])   # text/source of these stubs is F-23's concern


class TestF04SpecVerification(Base):
    def _finish(self, val):
        self.fx.prod["technical"]["finish"] = val
        return self.fx.validate()

    def test_source_without_value_is_missing_not_verified(self):
        v = self._finish({"source": "product_page"})
        self.assertEqual(v["verified_specs"], 2)
        self.assertIn("[חסר: technical.finish – לבדיקה]", v["flags"])

    def test_null_value(self):
        v = self._finish({"value": None, "source": "product_page"}); self.assertEqual(v["verified_specs"], 2)

    def test_empty_string_value(self):
        v = self._finish({"value": "  ", "source": "product_page"}); self.assertEqual(v["verified_specs"], 2)

    def test_empty_list_value(self):
        v = self._finish({"value": [], "source": "product_page"}); self.assertEqual(v["verified_specs"], 2)

    def test_value_without_source_is_error(self):
        self.assertEqual(self._finish({"value": "Chrome"})["status"], "BLOCKED")

    def test_unknown_source_key_is_error(self):
        self.assertEqual(self._finish({"value": "Chrome", "source": "ghost"})["status"], "BLOCKED")

    def test_empty_source_is_error(self):
        self.assertEqual(self._finish({"value": "Chrome", "source": ""})["status"], "BLOCKED")

    def test_valid_value_and_source_verified(self):
        v = self._finish({"value": "Chrome", "source": "product_page"}); self.assertEqual(v["verified_specs"], 3)

    def test_all_specs_value_less_blocks(self):
        for k in ("material", "finish", "features"):
            self.fx.prod["technical"][k] = {"source": "product_page"}
        v = self.fx.validate()
        self.assertEqual(v["status"], "BLOCKED"); self.assertEqual(v["verified_specs"], 0)

    def test_qa_spec_ref_needs_real_value(self):
        # value-less finish -> flag, so the output must show the flag; spec:finish must not resolve
        self.fx.prod["technical"]["finish"] = {"source": "product_page"}
        for a in self.fx.files:
            self.fx.files[a] = self.fx.files[a].replace("Notes: עד שהדגלים ייסגרו", "[חסר: technical.finish – לבדיקה]\nNotes: עד שהדגלים ייסגרו")
        self.fx.files["landing.md"] = self.fx.files["landing.md"].replace("## ב-MODY", "[חסר: technical.finish – לבדיקה]\n\n## ב-MODY")
        self.assertFails(self.fx.qa(), "provenance_refs_resolve")

    def test_signature_material_needs_resolvable_source(self):
        self.fx.prod["design"]["signature_material"]["source"] = "ghost"
        self.assertEqual(spec_status(self.fx.prod["design"]["signature_material"], self.fx.prod["sources"]), "invalid")
        self.fx.add_ref("spec:signature_material")
        r = self.fx.qa()                      # since F-21e the validator BLOCKs an unresolved signature_material source
        self.assertEqual(r["status"], "FAIL")
        self.assertEqual(r["checks"].get("validator"), "FAIL", r["fails"])
        self.assertEqual(self.fx.validate()["status"], "BLOCKED")


class TestF05ExitCodes(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True).returncode

    def test_validate_blocked_exits_1(self):
        self.assertEqual(self._run("validate.py", "tests/broken_example.yaml"), 1)

    def test_validate_ready_exits_0(self):
        self.assertEqual(self._run("validate.py", f"products/{PID}.yaml"), 0)

    def test_qa_fail_exits_1(self):
        fx = Fixture()
        try:
            fx.files["landing.md"] = open("tests/landing_with_planted_errors.md", encoding="utf-8").read()
            self.assertEqual(self._run("qa.py", fx.write(), fx.out), 1)
        finally:
            fx.close()

    def test_qa_pass_exits_0(self):
        fx = Fixture()
        try:
            self.assertEqual(self._run("qa.py", fx.write(), fx.out), 0)
        finally:
            fx.close()

    def test_qa_missing_out_dir_exits_1(self):
        self.assertEqual(self._run("qa.py", f"products/{PID}.yaml", "/nonexistent/"), 1)


class TestF06DeckStructure(Base):
    def _deck(self, slides):
        self.fx.files["deck.md"] = golden_deck(slides)
        return self.fx.qa()

    def test_5_slides_with_flags_slide_fails(self):
        self.assertFails(self._deck(GOLDEN_SLIDES[:4] + [GOLDEN_SLIDES[7]]), "deck_structure")

    def test_6_slides_fails(self):
        self.assertFails(self._deck(GOLDEN_SLIDES[:6] + [GOLDEN_SLIDES[7]]), "deck_structure")

    def test_9_slides_fails(self):
        self.assertFails(self._deck(GOLDEN_SLIDES + [GOLDEN_SLIDES[2]]), "deck_structure")

    def test_12_slides_fails(self):
        self.assertFails(self._deck(GOLDEN_SLIDES + GOLDEN_SLIDES[:5]), "deck_structure")

    def test_missing_role_fails(self):
        s = list(GOLDEN_SLIDES); s[3] = s[3].replace("# 03 קהל יעד", "# 03 שונות")
        self.assertFails(self._deck(s), "deck_structure")

    def test_roles_out_of_order_fails(self):
        s = list(GOLDEN_SLIDES); s[2], s[3] = s[3], s[2]
        self.assertFails(self._deck(s), "deck_structure")

    def test_slide_over_16_lines_fails(self):
        s = list(GOLDEN_SLIDES); s[2] = s[2].replace("\nNotes:", "".join(f"\n- שורה {c}" for c in "אבגדהוזחטיכלמנסעפצקרשת"[:17]) + "\n\nNotes:")
        self.assertFails(self._deck(s), "deck_structure")

    def test_missing_notes_fails(self):
        s = list(GOLDEN_SLIDES); s[3] = s[3].replace("Notes:", "הערות:")
        self.assertFails(self._deck(s), "deck_structure")

    def test_slide1_without_image_fails(self):
        s = list(GOLDEN_SLIDES); s[0] = s[0].replace("![](assets/77201_warm-bronze.png)\n", "")
        self.assertFails(self._deck(s), "deck_structure")

    def test_slide1_without_product_name_fails(self):
        s = list(GOLDEN_SLIDES); s[0] = s[0].replace("# GESSI Jacqueline 77201", "# ברז")
        self.assertFails(self._deck(s), "deck_structure")

    def test_table_rule_and_draft_banner_do_not_count_as_text(self):
        s = list(GOLDEN_SLIDES); s[0] = "> טיוטה – לא לפרסום. חסר: x\n\n" + s[0]
        r = self._deck(s)
        self.assertEqual(r["checks"]["deck_structure"], "PASS", r["fails"])

    # --- slide 7 exception (SKILL 6b): flags take precedence over the 5-line limit ---
    def _slide8(self, flags_shown):
        """The launch-plan slide: every open flag must appear (in the stage-1 action cell)."""
        s = list(GOLDEN_SLIDES)
        s[7] = re.sub(r"החלטות פתוחות: .*", "החלטות פתוחות: " + " · ".join(flags_shown), s[7])
        return s

    def test_extra_flags_on_slide8_pass(self):
        r = self._deck(self._slide8(FLAGS + ["[חסר: care – לבדיקה]", "[חסר: warranty – לבדיקה]"]))
        self.assertEqual(r["checks"]["deck_structure"], "PASS", r["fails"])

    def test_omitted_flag_on_slide8_fails(self):
        self.assertFails(self._deck(self._slide8(FLAGS[1:])), "deck_structure")


if __name__ == "__main__":
    unittest.main()
