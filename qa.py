"""Deterministic QA for skill outputs (pipeline step 7).
Usage: python qa.py products/<id>.yaml out/<id>/
Checks what code can check reliably. Tone and quality stay with human review.
"""
import os, re, sys, yaml
from validate import validate, get, spec_status, allowed_claim_ids, resolve_collection, project_path, load_strict

ASSETS = ["landing.md", "deck.md", "sales.md"]
# F-17: pictographs and symbols. Ranges: playing cards / enclosed / misc pictographs / emoticons / supplemental symbols
# (U+1F000–1FAFF), misc symbols + dingbats (U+2600–27BF), misc symbols and arrows (U+2B00–2BFF), a few CJK symbols.
# Plain arrows (U+2190–21FF, e.g. "→" in "Spec → Benefit") and ordinary punctuation are not emoji.
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿〰〽㊗㊙]")
EXCLAIM = re.compile("[!！‼⁉]")      # ASCII, full-width, double and question-exclamation
NUM = re.compile(r"\d[\d,\.]*")
# F-18: a number is allowed only when it comes from a factual value field of the product, or when it is a structural
# count: an integer directly followed by one of these count nouns (SKILL headings such as "3 נקודות", "פתיח (15 שניות)").
COUNT_NOUNS = ("נקודות", "עמודי", "שניות", "שקפים", "שלבים", "דגלים")
COUNT_RE = re.compile(r"\b\d+\s+(?:" + "|".join(COUNT_NOUNS) + r")")
ORDINAL_RE = re.compile(r"(?<![\d.,])0[1-9](?![\d.,])")      # SKILL 6b slide / launch-stage numbering "01".."07"
LIST_NUM_RE = re.compile(r"(?m)^\s*\d\.\s")                  # numbered list items "1. " (deck slides 04 / 05)
# F-16: Hebrew banned words match with the common one/two-letter prefixes (ו ב ש ל מ כ ה) and inflection suffixes
# (ה ים ות י ת), after final-letter normalisation ("מדהים" -> "מדהימ" so "מדהימה"/"מדהימים" match). The letter boundary
# outside the prefix/suffix keeps "הכי" from matching "הכיור" (ו is not an inflection suffix).
FINALS = str.maketrans("ךםןףץ", "כמנפצ")
HEB_PREFIX, HEB_SUFFIX = "[ובשלמכה]{0,2}", "(?:ה|ימ|ות|י|ת)?"      # suffixes in final-letter-normalised form (ים -> ימ)
# F-19: mandatory sections (SKILL 6a / 6c), in order
LANDING_SECTIONS = ["הסיפור", "למה דווקא הוא", "פרטים", "ב-MODY"]
SALES_SECTIONS = ["פתיח (15 שניות)", "3 נקודות לאדריכל/ית", "3 נקודות ללקוח/ה הפרטי/ת", "שאלות צפויות ותשובות", "מה לא להגיד"]
DRAFT_BANNER = "> טיוטה – לא לפרסום. חסר: "
# F-06: SKILL 6b. Slide 1 = the cover (name + one_liner + image); slides 2-8 = the 7 GTM content slides, whose headings
# carry these role names in this order (the same structure launch.pptx renders from the launch package).
DECK_ROLES = [None, ("סקירת מוצר",), ("מיצוב",), ("קהל יעד",), ("מסר מותג",), ("סיפור מוצר",), ("כלים למכירה",), ("תוכנית השקה",)]
SLIDE_MAX_LINES = 16
TABLE_SEP = re.compile(r"^\|[\s:|-]+\|$")
MARKER = "<!-- QA -->"
FOOTER_FLAGS = re.compile(r"^\*\*דגלים פתוחים:\*\*\s*(.*?)\s*$")
FOOTER_VERS = re.compile(r"^\*\*גרסאות:\*\*\s*house (\S+) · (\S+) · skill (\S+)\s*$")
# F-08: any amount attached to a currency token, symbol before or after
CURRENCY = r"₪|ש\"ח|ש״ח|שקלים|שקל|NIS|ILS|EUR|USD|€|\$|£"
AMOUNT_AFTER = re.compile(rf"(\d[\d,\.]*)\s*(?:{CURRENCY})")
AMOUNT_BEFORE = re.compile(r"(?:₪|€|\$|£|NIS|ILS|EUR|USD)\s*(\d[\d,\.]*)")
# SKILL step 5: audience priority by price_tier (missing tier -> A, B)
AUDIENCE_BY_TIER = {"signature": ("A", "B"), "premium": ("B", "A"), "core": ("C", "B")}
ONE_LINER_MAX_WORDS = 12
DONT_SAY = "## מה לא להגיד"


def factual_numbers(p):
    """F-18: numeric tokens from the product's factual value fields only (technical.* minus `source`,
    design.signature_material, commercial.price_ils, product.name, product.model_number). Never from sources / URLs,
    ids, versions or metadata."""
    vals = []

    def walk(x):
        if isinstance(x, dict):
            for k, val in x.items():
                if k != "source":
                    walk(val)
        elif isinstance(x, list):
            for i in x:
                walk(i)
        elif x is not None and not isinstance(x, bool):
            vals.append(str(x))

    for node in (p.get("technical"), get(p, "design.signature_material"), get(p, "commercial.price_ils"),
                 get(p, "product.name"), get(p, "product.model_number")):
        walk(node)
    return {n.replace(",", "").rstrip(".") for v in vals for n in NUM.findall(v)}


def scan_text(t, ids):
    """Text for the number scan: no גרסאות footer line (validated by F-15), no markdown image targets, no claim / pillar
    ids such as JQ-3 or P5, and no structural counts ("3 נקודות")."""
    t = "\n".join(l for l in t.splitlines() if not l.startswith("**גרסאות:**"))
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    for i in sorted(ids, key=len, reverse=True):
        t = t.replace(i, " ")
    return LIST_NUM_RE.sub(" ", ORDINAL_RE.sub(" ", COUNT_RE.sub(" ", t)))


def banned_re(term):
    """F-16: see HEB_PREFIX / HEB_SUFFIX. Latin terms match as whole words, case-insensitively."""
    if re.search(r"[א-ת]", term):
        return re.compile(rf"(?<![א-ת]){HEB_PREFIX}{re.escape(term.translate(FINALS))}{HEB_SUFFIX}(?![א-ת])")
    return re.compile(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", re.I)


def count_sentences(text):
    return len(re.findall(r"[.!?](?:\s|$)", text))


def sections(body):
    """{heading: section text} for '## ' headings, in order."""
    out, heads = {}, re.findall(r"^## (.*?)\s*$", body, flags=re.M)
    parts = re.split(r"^## .*?\s*$", body, flags=re.M)[1:]
    for h, txt in zip(heads, parts):
        out[h] = txt
    return heads, out


def bullets(text):
    return [l[2:].strip() for l in text.splitlines() if l.startswith("- ")]


def landing_problems(body, p, pos, story_expected):
    """F-19: SKILL 6a. H1, sub-headline = positioning.one_liner, the image (or its flag), the mandatory sections in
    order, their size rules and the mandatory פרטים rows."""
    probs = []
    lines = [l for l in body.splitlines() if l.strip() and not l.startswith(DRAFT_BANNER.strip())]
    if len([l for l in lines if l.startswith("# ")]) != 1 or not lines or not lines[0].startswith("# "):
        probs.append("must open with exactly one H1 headline")
    one_liner = pos.get("one_liner") if isinstance(pos, dict) else None
    sub = lines[1] if len(lines) > 1 else ""
    if isinstance(one_liner, str) and sub.strip() != one_liner.strip():
        probs.append(f"sub-headline '{sub[:40]}' must equal positioning.one_liner")
    img_line, image = lines[2] if len(lines) > 2 else "", get(p, "sources.image")
    if image:
        if not (img_line.startswith("![") and img_line.rstrip().endswith(f"]({image})")):
            probs.append(f"third line must be the image ![..]({image})")
    elif "[חסר: sources.image" not in img_line:
        probs.append("no image in input: third line must be the image flag")
    heads, secs = sections(body)
    expected = LANDING_SECTIONS if story_expected else LANDING_SECTIONS[1:]
    if heads != expected:
        probs.append(f"sections {heads} != {expected}")
        return probs
    if story_expected and not 1 <= count_sentences(secs["הסיפור"]) <= 3:
        probs.append("הסיפור must have 1-3 sentences")
    if len(bullets(secs["למה דווקא הוא"])) != 3:
        probs.append("למה דווקא הוא must have exactly 3 benefit bullets")
    rows = [l.split("|")[1].strip() for l in secs["פרטים"].splitlines() if l.startswith("|") and not TABLE_SEP.match(l.strip())]
    need = ["מותג", 'מק"ט', "מחיר"] + (["גימור"] if "finish" in (p.get("technical") or {}) else [])
    for label in need:
        if not any(r == label or (label == "מותג" and r.startswith("מותג")) for r in rows):
            probs.append(f"פרטים table has no '{label}' row")
    if not 1 <= count_sentences(secs["ב-MODY"]) <= 2:
        probs.append("ב-MODY must have 1-2 sentences")
    return probs


def sales_problems(body):
    """F-19: SKILL 6c. The five sections, in order, with 3 bullets in each '3 נקודות' section."""
    heads, secs = sections(body)
    if heads != SALES_SECTIONS:
        return [f"sections {heads} != {SALES_SECTIONS}"]
    probs = []
    if not secs[SALES_SECTIONS[0]].strip():
        probs.append("פתיח is empty")
    for h in SALES_SECTIONS[1:3]:
        if len(bullets(secs[h])) != 3:
            probs.append(f"'{h}' must have exactly 3 bullets")
    for h in SALES_SECTIONS[3:]:
        if not bullets(secs[h]):
            probs.append(f"'{h}' has no bullets")
    return probs


def deck_problems(slides, product_name, flags=(), ctx=None):
    """F-06: exactly 8 slides (cover + the 7 GTM slides), the SKILL roles in order, <= SLIDE_MAX_LINES lines of text,
    and Notes: on every slide. Slide 8 (launch plan) shows every open flag.
    F-19 (ctx given): slide content SKILL 6b defines: one_liner on the cover, audience names + what they care about on
    slide 4, every landing benefit on slide 6, 3 verbatim sales.md lines on slide 7, an owner in the הצעד הבא line of slide 8."""
    problems = []
    if ctx and len(slides) >= 8:
        pos, house, sales_body = ctx["positioning"], ctx["house"], ctx["sales_body"]
        if isinstance(pos, dict):
            if isinstance(pos.get("one_liner"), str) and pos["one_liner"].strip() not in slides[0]:
                problems.append("slide 1: positioning.one_liner missing")
            auds = {a.get("id"): a for a in house.get("audiences") or [] if isinstance(a, dict)}
            for role in ("primary_audience", "secondary_audience"):
                a = auds.get(pos.get(role))
                if a and (a.get("name") not in slides[3] or not any(c in slides[3] for c in a.get("cares_about") or [])):
                    problems.append(f"slide 4: audience {a.get('id')} name and what it cares about required")
        for b in re.findall(r"^- \*\*(.+?)\*\* ", ctx.get("landing_body") or "", flags=re.M):      # landing למה דווקא הוא
            if b.rstrip(".") not in slides[5]:
                problems.append(f"slide 6: landing benefit '{b[:30]}' missing")
        lines7 = [b.strip('"״“”') for b in bullets(slides[6]) if b.startswith(('"', '״', '“'))]
        if len(lines7) != 3 or not all(l and l in sales_body for l in lines7):
            problems.append("slide 7: לזכור must be exactly 3 lines taken verbatim from sales.md")
        nxt = next((l for l in slides[7].splitlines() if l.startswith("**הצעד הבא:**")), "")
        if not re.search(r"אחראי: \S", nxt):
            problems.append("slide 8: הצעד הבא line with an owner (אחראי) required")
    if len(slides) != 8:
        problems.append(f"{len(slides)} slides (SKILL 6b: cover + 7 = exactly 8)")
    for i, s in enumerate(slides[:8]):
        lines = [l.rstrip() for l in s.strip("\n").splitlines()]
        head = next((l[2:].strip() for l in lines if l.startswith("# ")), "")
        if i == 0:
            if product_name and product_name not in s:
                problems.append(f"slide 1: product name '{product_name}' missing")
            if not ("![" in s or "[חסר: sources.image" in s):
                problems.append("slide 1: no image and no image flag")
        elif not any(r in head for r in DECK_ROLES[i]):
            problems.append(f"slide {i + 1}: heading '{head}' is not '{' / '.join(DECK_ROLES[i])}'")
        if not any(l.startswith("Notes:") for l in lines):
            problems.append(f"slide {i + 1}: no Notes:")
        text = []
        for l in lines:
            if l.startswith("Notes:"):
                break                                   # speaker notes are not slide text
            if not l.strip() or l.startswith("# ") or l.startswith("![") or l.startswith("> טיוטה") or TABLE_SEP.match(l):
                continue                                # heading, image, draft banner, table rule
            text.append(l)
        if len(text) > SLIDE_MAX_LINES:
            problems.append(f"slide {i + 1}: {len(text)} lines of text (max {SLIDE_MAX_LINES})")
        if i == 7:
            not_shown = [f for f in flags if f not in s]
            if not_shown:
                problems.append(f"slide 8: flags not shown: {not_shown}")
    return problems


def split_footer(t):
    """F-09/F-15: (body, footer lines, problems). The marker appears exactly once, after a '---' line,
    and only the two footer lines follow it, so nothing can hide behind it."""
    parts = t.split(MARKER)
    if len(parts) != 2:
        return parts[0], [], [f"marker appears {len(parts) - 1} times (need exactly 1)"]
    body, footer = parts
    problems = []
    body_lines = body.rstrip("\n").splitlines()
    if not body_lines or body_lines[-1].strip() != "---":
        problems.append("marker must directly follow a '---' line")
    flines = [l.strip() for l in footer.splitlines() if l.strip()]
    if len(flines) != 2 or not FOOTER_FLAGS.match(flines[0]) or not flines[1].startswith("**גרסאות:**"):
        problems.append("footer must be exactly the דגלים פתוחים line and the גרסאות line")
    return body, flines, problems


def checkable_body(asset, body):
    """Text subject to voice / leakage rules: images removed; in sales.md only, the body of the single
    'מה לא להגיד' section is exempt because it quotes banned phrases by design (SKILL 6c)."""
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)                    # images: not visible copy
    body = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", body)                # F-29: links: keep the visible text, drop the URL
    problems = []
    n = len(re.findall(rf"^{re.escape(DONT_SAY)}", body, flags=re.M))
    if asset == "sales.md":
        if n > 1:
            problems.append(f"'{DONT_SAY}' appears {n} times")
        body = re.sub(rf"^{re.escape(DONT_SAY)}\s*$.*?(?=^## |\Z)", "", body, flags=re.M | re.S)
    return body, problems


def constraint_phrases(mfr):
    """F-30: what the manufacturer file forbids deterministically: quoted phrases in a `constraints` sentence that
    contains 'אסור' (e.g. mutina: אסור לכתוב "ידידותי לסביבה"). Competitor names and unverifiable promises (house G4)
    have no list in any configuration file and stay with human review."""
    phrases = []
    for c in mfr.get("constraints") or []:
        if isinstance(c, str):
            for sentence in re.split(r"(?<=[.!?])\s+", c):
                if "אסור" in sentence:
                    phrases += re.findall(r'"([^"]+)"', sentence)
    return phrases


def word_re(term):
    """Whole-word match with Hebrew/Latin letter boundaries (line vocabulary, F-10)."""
    return re.compile(rf"(?<![A-Za-zא-ת]){re.escape(term)}(?![A-Za-zא-ת])")


def sentences(text):
    return [s.strip() for s in re.split(r"[.!?]", text or "") if len(s.split()) >= 3]


def leakage_terms(mfr, p):
    """F-10: what belongs to OTHER lines / collections of this manufacturer and may not appear in this product's copy:
    other lines' vocabulary (unless also in the product's own vocabulary), other collections' story_line sentences
    and approved-claim texts. Boundary = the line / collection resolved by the validator (SKILL step 3)."""
    own_line, own_col, _ = resolve_collection(mfr, p)
    lines = mfr.get("lines") or {}
    own_vocab = set(get(mfr, "voice_extension.vocabulary") or []) | set((lines.get(own_line) or {}).get("vocabulary") or [])
    terms = []
    for lk, line in lines.items():
        if not isinstance(line, dict):
            continue
        if lk != own_line:
            terms += [("vocabulary", lk, w) for w in line.get("vocabulary") or [] if isinstance(w, str) and w not in own_vocab]
        for ck, col in (line.get("collections") or {}).items():
            if (lk, ck) == (own_line, own_col) or not isinstance(col, dict):
                continue
            terms += [("story_line", f"{lk}/{ck}", s) for s in sentences(col.get("story_line"))]
            for c in col.get("approved_claims") or []:
                if isinstance(c, dict) and c.get("claim"):
                    terms += [("claim", f"{lk}/{ck}/{c.get('id')}", s) for s in sentences(c["claim"])]
    return terms


def ref_resolver(p, house, mfr):
    """The SKILL step 4 claim set as a predicate. ref_ok("claim:JQ-2") is True only when the ref resolves to a fact of
    THIS product: an approved claim of its own collection (F-02), a verified spec (F-04), its price, or a house / brand
    fact that exists in the layer files (F-03). Shared by qa.run and presentation.content, so there is one grammar."""
    approved = set(get(p, "design.claims_ref") or []) & allowed_claim_ids(mfr, p)          # F-02
    sources = p.get("sources") or {}
    verified = {k for k, val in (p.get("technical") or {}).items() if spec_status(val, sources) == "verified"}   # F-04
    if spec_status(get(p, "design.signature_material"), sources) == "verified":
        verified.add("signature_material")
    price = get(p, "commercial.price_ils.value")
    # F-03: house / brand / commercial refs resolve only to facts that exist in the layer files (SKILL step 4 table)
    house_keys = {pl.get("id") for pl in house.get("pillars") or [] if isinstance(pl, dict)} \
                 | {a.get("id") for a in house.get("audiences") or [] if isinstance(a, dict)} \
                 | {k for k in ("role", "audiences", "value_proposition") if house.get(k)}
    brand_keys = {k for k in ("identity", "local_presence") if mfr.get(k)} \
                 | ({"relationship"} if get(mfr, "meta.relationship") else set()) \
                 | ({"cross_sell"} if get(mfr, "voice_extension.cross_sell") else set())

    def ref_ok(ref):
        if not isinstance(ref, str):
            return False
        kind, _, key = ref.partition(":")
        return (kind == "claim" and key in approved) or (kind == "spec" and key in verified) \
            or (kind == "commercial" and key == "price_ils" and bool(price)) \
            or (kind == "house" and key in house_keys) or (kind == "brand" and key in brand_keys)

    return ref_ok


def run(product_path, out_dir):
    v = validate(product_path)
    if v["status"] == "BLOCKED":                        # F-01: a BLOCKED product is never QA'd, let alone PASSed
        return {"status": "FAIL", "checks": {"validator": "FAIL"},
                "fails": ["validator: BLOCKED – " + "; ".join(v["errors"])]}
    p = yaml.safe_load(open(product_path, encoding="utf-8"))
    house = yaml.safe_load(open(project_path(v["brand_layers"]["house"]), encoding="utf-8"))
    mfr = yaml.safe_load(open(project_path(v["brand_layers"]["manufacturer"]), encoding="utf-8"))
    checks, fails = {}, []

    def check(name, ok, detail=""):
        checks[name] = "PASS" if ok else "FAIL"
        if not ok:
            fails.append(f"{name}: {detail}")

    # 0. files
    missing = [a for a in ASSETS + ["provenance.yaml"] if not os.path.exists(os.path.join(out_dir, a))]
    check("files_present", not missing, missing)
    if missing:
        return {"status": "FAIL", "checks": checks, "fails": fails}
    text = {a: open(os.path.join(out_dir, a), encoding="utf-8").read() for a in ASSETS}

    # 0b. provenance loads and has the SKILL step 8 shape (F-13: malformed provenance is a FAIL, never a crash)
    try:
        with open(os.path.join(out_dir, "provenance.yaml"), encoding="utf-8") as fh:
            prov = load_strict(fh)                       # F-31: duplicate keys are an error here too
        prov_err = "" if isinstance(prov, dict) else f"not a mapping ({type(prov).__name__})"
    except yaml.YAMLError as e:
        prov, prov_err = None, f"invalid YAML ({type(e).__name__}: {str(e)[:60]})"
    check("provenance_valid", not prov_err, prov_err)
    if prov_err:
        return {"status": "FAIL", "checks": checks, "fails": fails}
    shape = []
    claims_used = prov.get("claims_used")
    if not isinstance(claims_used, list):
        shape.append(f"claims_used is not a list ({type(claims_used).__name__})")
        claims_used = []
    entries = [c for c in claims_used if isinstance(c, dict) and isinstance(c.get("ref"), str)]
    shape += [f"malformed claims_used entry: {c!r:.80}" for c in claims_used if c not in entries]
    if not isinstance(prov.get("flags", []), list):
        shape.append("flags is not a list")
    if not isinstance(prov.get("brand_versions", {}), dict):
        shape.append("brand_versions is not a mapping")
    check("provenance_shape", not shape, shape)

    # bodies: everything before the QA marker (footer validated in 8). F-09: when the footer is not in its valid
    # final position, nothing is trusted as "footer", so the whole asset is validated as body.
    footer = {a: split_footer(t) for a, t in text.items()}
    body = {a: footer[a][0] if not footer[a][2] else t for a, t in text.items()}

    # 1. voice: no "!", no emoji, no banned words  (F-09: exemption only for the one 'מה לא להגיד' section of sales.md)
    banned = re.findall(r'"([^"]+)"', " ".join(house["voice"]["dont"]))
    voice_body = {}
    for a in ASSETS:
        voice_body[a], probs = checkable_body(a, body[a])
        norm = voice_body[a].translate(FINALS)
        bad = [w for w in banned if banned_re(w).search(norm)]                     # F-16
        excl, emo = len(EXCLAIM.findall(voice_body[a])), bool(EMOJI.search(voice_body[a]))   # F-17
        check(f"voice_{a}", not excl and not emo and not bad and not probs,
              f"'!'={excl} emoji={emo} banned={bad} {probs}")

    # 1a. F-30: phrases the manufacturer's constraints explicitly forbid
    forbidden = constraint_phrases(mfr)
    for a in ASSETS:
        hit = [ph for ph in forbidden if ph in voice_body[a]]
        check(f"constraints_{a}", not hit, hit)

    # 1b. F-10: no vocabulary / story / claims from another line or collection of the same manufacturer
    terms = leakage_terms(mfr, p)
    for a in ASSETS:
        leaked = [f"{kind} {where}: '{t}'" for kind, where, t in terms
                  if (word_re(t).search(voice_body[a]) if kind == "vocabulary" else t in voice_body[a])]
        check(f"line_isolation_{a}", not leaked, leaked)

    # 2. structure
    h1 = next((l[2:].strip() for l in text["landing.md"].splitlines() if l.startswith("# ")), "")
    check("headline_length", 0 < len(h1.split()) <= house["format"]["headline_max_words"], f"'{h1}'")
    slides = [s for s in re.split(r"^---\s*$", body["deck.md"], flags=re.M) if s.strip()]
    ctx = {"positioning": prov.get("positioning"), "house": house, "sales_body": body["sales.md"], "landing_body": body["landing.md"]}
    deck_bad = deck_problems(slides, get(p, "product.name"), v["flags"], ctx)
    check("deck_structure", not deck_bad, deck_bad)
    # F-19: landing.md / sales.md structure per SKILL 6a / 6c. A story section exists iff a collection block resolved.
    story_expected = resolve_collection(mfr, p)[2] is not None
    check("landing_structure", not (lp := landing_problems(body["landing.md"], p, prov.get("positioning"), story_expected)), lp)
    check("sales_structure", not (sp := sales_problems(body["sales.md"])), sp)

    # 3. every validator flag surfaces in the body of every asset (hard rule 1; F-14 adds sales.md)
    for a in ASSETS:
        lost = [f for f in v["flags"] if f not in body[a]]                       # body, not just footer
        check(f"flags_in_{a}", not lost, lost)

    # 4. price: exactly the house format in the landing פרטים row, and no other monetary amount anywhere (F-08)
    price = get(p, "commercial.price_ils.value")
    expected = house["format"]["price"].format(value=price) if isinstance(price, (int, float)) and not isinstance(price, bool) else (str(price) if price else None)
    amounts = {m.replace(",", "").rstrip(".") for t in text.values() for m in AMOUNT_AFTER.findall(t) + AMOUNT_BEFORE.findall(t)}
    if price:
        row_ok = bool(re.search(rf"^\|\s*מחיר\s*\|\s*{re.escape(expected)}\s*\|", body["landing.md"], flags=re.M))
        check("price_exact", row_ok and amounts <= {str(price).replace(",", "")},
              f"expected row '| מחיר | {expected} |' in landing.md: {row_ok}; amounts shown={sorted(amounts)}")
    else:
        check("price_exact", not amounts, f"no price in input but amounts shown={sorted(amounts)}")

    # 5. no invented numbers (F-18: factual value fields only; structural counts, ids and the versions line excluded)
    skill_v = re.search(r"^version:\s*(\S+)", open(project_path("SKILL.md"), encoding="utf-8").read(), re.M).group(1)
    allowed = factual_numbers(p)
    ids = set(get(p, "design.claims_ref") or []) | {pl.get("id") for pl in house.get("pillars") or [] if isinstance(pl, dict)}
    invented = set()
    for t in text.values():
        for n in NUM.findall(scan_text(t, {i for i in ids if isinstance(i, str)})):
            n = n.replace(",", "").rstrip(".")
            if n not in allowed:
                invented.add(n)
    check("no_invented_numbers", not invented, sorted(invented))

    # 6. provenance: every ref resolves to the claim set (ref_resolver is shared with the presentation asset)
    sources = p.get("sources") or {}
    ref_ok = ref_resolver(p, house, mfr)
    bad_refs = [c["ref"] for c in entries if not ref_ok(c["ref"])]
    check("provenance_refs_resolve", not bad_refs and entries, bad_refs or "empty")

    # 6d. F-23: every claims_used entry names a generated asset, quotes text that really appears in it (after the
    #     normalisation below), and records the source of the fact its ref points at.
    def norm(s):
        return re.sub(r"\s+", " ", re.sub(r"[*`\"״“”|>]", "", s)).strip()       # markdown emphasis/quotes/table bars, whitespace

    norm_body = {a[:-3]: norm(body[a]) for a in ASSETS}
    approved_src = {c.get("id"): c.get("source") for c in (resolve_collection(mfr, p)[2] or {}).get("approved_claims") or []
                    if isinstance(c, dict)}

    def expected_sources(ref):
        kind, _, key = ref.partition(":")
        if kind == "claim":
            return {approved_src.get(key)}
        if kind in ("spec", "commercial"):
            field = get(p, "design.signature_material") if key == "signature_material" else \
                get(p, "commercial.price_ils") if kind == "commercial" else (p.get("technical") or {}).get(key)
            k = field.get("source") if isinstance(field, dict) else None
            return {k, sources.get(k) if isinstance(k, str) else None}           # the source key, or the URL it resolves to
        if kind == "house":
            return {v["brand_layers"]["house"]}
        if kind == "brand":
            return {v["brand_layers"]["manufacturer"]}
        return set()

    integrity = []
    for c in entries:
        a, t, s = c.get("asset"), c.get("text"), c.get("source")
        if a not in norm_body:
            integrity.append(f"asset {a!r} is not one of landing/deck/sales")
        elif not isinstance(t, str) or not t.strip() or norm(t) not in norm_body[a]:
            integrity.append(f"text not found in {a}: {str(t)[:40]!r}")
        if ref_ok(c["ref"]) and s not in (expected_sources(c["ref"]) - {None}):
            integrity.append(f"source {str(s)[:40]!r} is not the source of {c['ref']}")
    check("claims_used_integrity", not integrity, integrity)

    # 6b. F-07: provenance is bound to THIS product and THIS validator result (SKILL step 8)
    bound = []
    if prov.get("product") != get(p, "product.id"):
        bound.append(f"product {prov.get('product')!r} != {get(p, 'product.id')!r}")
    if prov.get("validator_status") != v["status"]:
        bound.append(f"validator_status {prov.get('validator_status')!r} != {v['status']!r}")
    if not isinstance(prov.get("flags"), list) or set(prov["flags"]) != set(v["flags"]):
        bound.append(f"flags {prov.get('flags')!r} != validator flags")
    if "publishable" in prov and prov["publishable"] != v["publishable"]:
        bound.append(f"publishable {prov['publishable']!r} != {v['publishable']!r}")
    check("provenance_bound", not bound, bound)

    # 6c. F-07: positioning has the SKILL step 5 shape and follows its rules
    pos, pp = prov.get("positioning"), []
    if not isinstance(pos, dict):
        pp.append("positioning missing or not a mapping")
    else:
        ol = pos.get("one_liner")
        if not isinstance(ol, str) or not ol.strip() or len(ol.split()) > ONE_LINER_MAX_WORDS:
            pp.append(f"one_liner missing or > {ONE_LINER_MAX_WORDS} words")
        tier = get(p, "commercial.price_tier")
        exp = AUDIENCE_BY_TIER.get(tier, ("A", "B"))
        got = (pos.get("primary_audience"), pos.get("secondary_audience"))
        if got != exp:
            pp.append(f"audience {got} != {exp} for price_tier={tier}")
        pillar_ids = {pl.get("id") for pl in house.get("pillars") or [] if isinstance(pl, dict)}
        pillars = pos.get("pillars")
        if not isinstance(pillars, list) or not 2 <= len(pillars) <= 3 or not all(isinstance(x, str) and x in pillar_ids for x in pillars):
            pp.append(f"pillars {pillars!r}: need 2-3 of {sorted(pillar_ids)}")
        s2b = pos.get("spec_to_benefit")
        if not isinstance(s2b, list) or not s2b:
            pp.append("spec_to_benefit missing or empty")
        else:
            for row in s2b:
                if not isinstance(row, dict) or not all(isinstance(row.get(k), str) and row[k].strip() for k in ("from", "benefit", "ref")) or not ref_ok(row["ref"]):
                    pp.append(f"spec_to_benefit row does not cite the claim set: {row!r:.80}")
    check("positioning", not pp, pp)

    # 7. versions recorded match what validator resolved
    check("versions_match", prov.get("brand_versions") == v["brand_layers"],
          f"{prov.get('brand_versions')} vs {v['brand_layers']}")

    # 8a. draft banner (F-20): a draft opens with exactly `> טיוטה – לא לפרסום. חסר: <publish_blockers>` (SKILL step 1);
    #     a publishable asset carries no draft banner at all
    banner = DRAFT_BANNER + ", ".join(v["publish_blockers"])
    for a, tx in text.items():
        first = tx.splitlines()[0].rstrip() if tx.strip() else ""
        if not v["publishable"]:
            check(f"draft_banner_{a}", first == banner, f"line 1 must be exactly '{banner}', got '{first[:60]}'")
        else:
            check(f"draft_banner_{a}", "טיוטה – לא לפרסום" not in tx, "publishable product must not carry a draft banner")

    # 8. QA footer: present, in its final position, and its content matches the validator and the resolved layers (F-15)
    stems = {k: os.path.basename(f)[:-len(".yaml")] for k, f in v["brand_layers"].items()}
    for a in ASSETS:
        _, flines, probs = footer[a]
        probs = list(probs)
        if not probs:
            listed = FOOTER_FLAGS.match(flines[0]).group(1)
            if v["flags"]:
                lost = [f for f in v["flags"] if f not in listed]
                if lost:
                    probs.append(f"דגלים פתוחים does not list {lost}")
                if listed == "אין":
                    probs.append("דגלים פתוחים says אין while flags exist")
            elif listed != "אין":
                probs.append(f"no flags, so דגלים פתוחים must be אין, got '{listed}'")
            m = FOOTER_VERS.match(flines[1])
            if not m:
                probs.append("גרסאות line must be 'house <v> · <manufacturer> <v> · skill <v>'")
            elif m.groups() != (stems["house"], stems["manufacturer"], skill_v):
                probs.append(f"גרסאות {m.groups()} != {(stems['house'], stems['manufacturer'], skill_v)}")
        check(f"qa_footer_{a}", not probs, probs)

    return {"status": "FAIL" if fails else "PASS", "checks": checks, "fails": fails}


if __name__ == "__main__":
    if len(sys.argv) != 3:                                  # F-32: routine misuse gets a usage line, not a traceback
        print("usage: python qa.py products/<id>.yaml out/<id>/", file=sys.stderr)
        sys.exit(2)
    result = run(sys.argv[1], sys.argv[2])
    print(yaml.safe_dump(result, allow_unicode=True, sort_keys=False))
    sys.exit(0 if result["status"] == "PASS" else 1)   # F-05: CI-usable exit code
