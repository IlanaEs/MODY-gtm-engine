"""Package QA – runs on launch_package.yaml BEFORE any renderer: schema, content, provenance, assets.
Result shape (also written into the package's `qa` block):
    {"status": passed | failed | passed_with_warnings, "errors": [{code, field, message}], "warnings": [...], "checks": {...}}
Content rules (voice, banned words, numbers, price, leakage, constraints) are qa.py's own functions, so both QA
layers share one implementation; refs resolve through qa.ref_resolver (one provenance grammar)."""
import json, os, re
import qa as mdqa
from validate import get
from launch.package import SCHEMA, LIMITS, getp, val, skeleton, readiness
from presentation.template_map import PLACEHOLDERS

SKIP_KEYS = {"derived_from", "ref", "refs", "source", "source_fields", "id", "field", "flag", "format", "path",
             "expected", "when_to_recommend_derived_from", "from", "approved", "exists", "evidence"}
READINESS_CODES = ("MISSING_HERO_IMAGE", "IMAGE_NOT_APPROVED", "IMAGE_FORMAT")
FACT_PATHS = ["product.facts", "product.specs", "product.assets", "strategy.audience_rule", "messaging.tone",
              "deck.launch_plan", "deck.next_step", "deck.cover.source_fields", "sources", "story.expected"]    # deck.slides: structure checked in 7
META_KEYS = ("product", "skill_version", "brand_versions", "validator_status", "publishable", "publish_blockers", "flags", "draft_banner")
AUDIENCE_FACTS = ("id", "segment", "decision_driver")


def texts(node, path="", skip_paths=()):
    """(path, text) for every visible string; internal metadata keys and the given sub-trees are skipped."""
    if path in skip_paths:
        return []
    if isinstance(node, str):
        return [(path, node)]
    if isinstance(node, dict):
        return [t for k, v in node.items() if k not in SKIP_KEYS for t in texts(v, f"{path}.{k}" if path else k, skip_paths)]
    if isinstance(node, list):
        return [t for i, v in enumerate(node) for t in texts(v, f"{path}.{i}", skip_paths)]
    return []


def _paths(pattern, pkg):
    if ".*" not in pattern:
        return [pattern]
    head, _, tail = pattern.partition(".*")
    items = getp(pkg, head) or []
    return [f"{head}.{i}{tail}" for i in range(len(items))] if isinstance(items, list) else []


def _words(s):
    return len(str(s).split())


def _sentences(s):
    return max(1, mdqa.count_sentences(str(s)))


def run(pkg, ctx):
    errors, warnings, checks = [], [], {}
    v, p, house, mfr = ctx["v"], ctx["p"], ctx["house"], ctx["mfr"]

    def err(code, field, message):
        errors.append({"code": code, "field": field, "message": message})

    def warn(code, field, message):
        warnings.append({"code": code, "field": field, "message": message})

    def check(name, ok):
        checks[name] = "PASS" if ok else "FAIL"

    # 1. schema: sections and shapes
    n0 = len(errors)
    if not isinstance(pkg, dict):
        err("SCHEMA_SHAPE", "", "package is not a mapping")
        return _result(errors, warnings, {"schema": "FAIL"})
    for s in SCHEMA["sections"]:
        if s not in pkg:
            err("MISSING_SECTION", s, f"required section '{s}' is missing")
    for path, typ in (("benefits", list), ("strategy.target_audiences", list), ("strategy.pillars", list),
                      ("strategy.spec_to_benefit", list), ("deck.slides", list), ("deck.launch_plan", list),
                      ("landing.product_details", list), ("product.facts", dict), ("product.specs", list),
                      ("messaging.key_messages", list), ("sales.faq", list)):
        if getp(pkg, path) is not None and not isinstance(getp(pkg, path), typ):
            err("SCHEMA_SHAPE", path, f"must be a {typ.__name__}")
    check("schema", len(errors) == n0)
    if errors:
        return _result(errors, warnings, checks)

    # 2. facts match their sources (a changed or added fact has no source)
    n0 = len(errors)
    sk = skeleton(ctx)
    for path in FACT_PATHS:
        if getp(pkg, path) != getp(sk, path):
            err("FACT_MISMATCH", path, f"differs from the source-derived value: {json.dumps(getp(pkg, path), ensure_ascii=False)[:80]}")
    for k in META_KEYS:
        if getp(pkg, f"meta.{k}") != getp(sk, f"meta.{k}"):
            err("META_MISMATCH", f"meta.{k}", f"{getp(pkg, f'meta.{k}')!r} != validator {getp(sk, f'meta.{k}')!r}")
    aud, sk_aud = pkg["strategy"].get("target_audiences") or [], sk["strategy"]["target_audiences"]
    for i, a in enumerate(aud):
        if not isinstance(a, dict):
            err("SCHEMA_SHAPE", f"strategy.target_audiences.{i}", "not a mapping"); continue
        if i < len(sk_aud):
            for k in AUDIENCE_FACTS:
                if a.get(k) != sk_aud[i].get(k):
                    err("FACT_MISMATCH", f"strategy.target_audiences.{i}.{k}", f"{a.get(k)!r} != house DNA {sk_aud[i].get(k)!r}")
        elif not any(a.get("segment") == h.get("name") for h in house.get("audiences") or [] if isinstance(h, dict)):
            err("FACT_MISMATCH", f"strategy.target_audiences.{i}.segment", f"{a.get('segment')!r} is not a house audience")
    check("facts_match_sources", len(errors) == n0)

    # 3. sources: every factual value has a source; commercial facts need a MODY source
    n0 = len(errors)
    for k, f in (pkg["product"].get("facts") or {}).items():
        if isinstance(f, dict) and f.get("value") not in (None, "") and not f.get("source"):
            err("MISSING_PRODUCT_SOURCE", f"product.facts.{k}", f"'{k}' has a value but no verified source")
    for i, row in enumerate(pkg["product"].get("specs") or []):
        if row.get("value") not in (None, "") and not row.get("source"):
            err("MISSING_PRODUCT_SOURCE", f"product.specs.{i}", f"spec '{row.get('field')}' has a value but no source")
    price = getp(pkg, "product.facts.price") or {}
    if price.get("value") is not None and not any(str(price.get("source", "")).startswith(pfx) for pfx in SCHEMA["mody_source_prefixes"]):
        err("MISSING_MODY_SOURCE", "product.facts.price", f"commercial fact needs a MODY source key, got {price.get('source')!r}")
    for i, row in enumerate(pkg["landing"].get("product_details") or []):
        if not all(row.get(k) for k in ("label", "value")):
            err("DETAIL_INCOMPLETE", f"landing.product_details.{i}", "needs label and value")
        elif "[חסר:" not in str(row["value"]) and not row.get("source"):
            err("MISSING_PRODUCT_SOURCE", f"landing.product_details.{i}", f"detail '{row.get('label')}' has no source")
    check("sources", len(errors) == n0)

    # 4. required GTM content
    n0 = len(errors)
    for path, label in (("messaging.headline", "headline"), ("messaging.one_liner", "one-liner"), ("strategy.positioning", "positioning"),
                        ("strategy.value_proposition", "value proposition"), ("strategy.customer_need", "customer need"),
                        ("strategy.consumer_insight", "consumer insight"), ("product.summary", "product summary"),
                        ("landing.mody_section", "MODY section"), ("sales.opening", "sales opening")):
        if not (isinstance(val(getp(pkg, path)), str) and val(getp(pkg, path)).strip()):
            err("MISSING_REQUIRED", path, f"{label} is missing")
    if not aud:
        err("MISSING_REQUIRED", "strategy.target_audiences", "target audience is missing")
    for i, a in enumerate(aud):
        if isinstance(a, dict) and not (isinstance(a.get("need"), str) and a["need"].strip()):
            err("MISSING_REQUIRED", f"strategy.target_audiences.{i}.need", "audience need is missing")
        if isinstance(a, dict) and not (isinstance(a.get("needs_line"), str) and a["needs_line"].strip()):
            err("MISSING_REQUIRED", f"strategy.target_audiences.{i}.needs_line", "audience needs line (deck slide 3) is missing")
    if not (pkg["strategy"].get("differentiators") or []):
        err("MISSING_REQUIRED", "strategy.differentiators", "differentiator is missing")
    if not (pkg["messaging"].get("key_messages") or []):
        err("MISSING_REQUIRED", "messaging.key_messages", "key messages are missing")
    sc = pkg["sales"].get("seller_cheat_sheet") or {}
    for k in ("positioning", "private_customer", "professional_customer"):
        if not (isinstance(sc.get(k), str) and sc[k].strip()):
            err("MISSING_REQUIRED", f"sales.seller_cheat_sheet.{k}", "seller guidance is missing")
    for k, n in (("architect_points", 3), ("private_points", 3), ("key_talking_points", 1), ("faq", 1), ("dont_say", 1)):
        if len(pkg["sales"].get(k) or []) < n:
            err("MISSING_REQUIRED", f"sales.{k}", f"needs at least {n} item(s)")
    for k in ("pillars", "spec_to_benefit"):
        if not (pkg["strategy"].get(k) or []):
            err("MISSING_REQUIRED", f"strategy.{k}", f"{k} is missing")
    story = pkg.get("story") or {}
    if story.get("expected") and not (isinstance(story.get("value"), str) and story["value"].strip()):
        err("MISSING_REQUIRED", "story", "collection block exists, so a product story is required (SKILL step 3)")
    if not story.get("expected") and story.get("value"):
        err("UNSUPPORTED_CLAIM", "story", "no collection block for this product, so no story may be written (SKILL step 3)")
    notes = [getp(pkg, "deck.cover.notes")] + [s.get("notes") if isinstance(s, dict) else None for s in pkg["deck"].get("slides") or []]
    if len(notes) != 8 or not all(isinstance(n, str) and n.strip() for n in notes):
        err("MISSING_REQUIRED", "deck.slides.*.notes", "speaker notes are required on the cover and on all 7 slides (SKILL 6b)")
    check("required_content", len(errors) == n0)

    # 5. benefits: exactly 3, each complete and traced
    n0 = len(errors)
    ben = pkg.get("benefits") or []
    if len(ben) != 3:
        err("BENEFIT_COUNT", "benefits", f"exactly 3 primary benefits required, got {len(ben)}")
    ref_ok = mdqa.ref_resolver(p, house, mfr)
    for i, b in enumerate(ben):
        if not isinstance(b, dict) or not all(isinstance(b.get(k), str) and b[k].strip() for k in ("title", "text", "fact", "ref")):
            err("BENEFIT_INCOMPLETE", f"benefits.{i}", "needs title, text, fact and ref")
        elif not ref_ok(b["ref"]):
            err("UNSUPPORTED_CLAIM", f"benefits.{i}.ref", f"ref {b['ref']!r} does not resolve to the claim set")
    check("benefits", len(errors) == n0)

    # 6. hero + image asset: a real pipeline input. Missing / unapproved / wrong format blocks FINAL rendering
    #    (schema image_missing_file: error -> status not_ready); the package itself may still be created.
    n0 = len(errors)
    hero = getp(pkg, "product.assets.hero_image") or {}
    severity = err if SCHEMA.get("image_missing_file") == "error" else warn
    for b in readiness(pkg)["blockers"]:
        code, _, msg = b.partition(": ")
        severity(code, "product.assets.hero_image", msg)
    for k, ref in (("headline", "messaging.headline"), ("sub", "messaging.one_liner"), ("image", "product.assets.hero_image")):
        if getp(pkg, f"landing.hero.{k}") != ref:
            err("HERO_INCOMPLETE", f"landing.hero.{k}", f"must reference {ref}")
    check("hero", not [e for e in errors[n0:] if e["code"] not in READINESS_CODES])
    check("readiness", not [e for e in errors[n0:] if e["code"] in READINESS_CODES])

    # 7. deck structure: cover + 7 slides, fixed order, every slide has its content
    n0 = len(errors)
    want = SCHEMA["deck_slides"]
    slides = pkg["deck"].get("slides") or []
    if [(s.get("id"), s.get("type"), s.get("source_fields")) for s in slides if isinstance(s, dict)] != [(s["id"], s["type"], s["source_fields"]) for s in want]:
        err("DECK_STRUCTURE", "deck.slides", f"7 content slides in fixed order with their source_fields required: {[s['type'] for s in want]}")
    if getp(pkg, "deck.cover.source_fields") != SCHEMA["deck_cover_fields"]:
        err("DECK_STRUCTURE", "deck.cover", "cover must reference the fixed cover fields")
    for s in want:
        for f in s["source_fields"]:
            node = getp(pkg, f)
            empty = node in (None, "", []) or (isinstance(node, dict) and "value" in node and node["value"] in (None, ""))
            if empty and not (f == "story" and not story.get("expected")):
                err("SLIDE_CONTENT_MISSING", f"deck.slides.{s['id']}", f"slide {s['id']} ({s['type']}) has no content for {f}")
    lp = pkg["deck"].get("launch_plan") or []
    if [st.get("stage") for st in lp if isinstance(st, dict)] != SCHEMA["launch_stages"]:
        err("DECK_STRUCTURE", "deck.launch_plan", f"4 fixed launch stages required: {SCHEMA['launch_stages']}")
    check("deck_structure", len(errors) == n0)

    # 8. limits
    n0, w0 = len(errors), len(warnings)
    for pattern, lim in LIMITS.items():
        for path in _paths(pattern, pkg):
            node = getp(pkg, path)
            v_ = val(node)
            if v_ is None:
                continue
            if isinstance(v_, list):
                if "min_items" in lim and len(v_) < lim["min_items"]:
                    err("LIMIT", path, f"{len(v_)} items < {lim['min_items']}")
                if "max_items" in lim and len(v_) > lim["max_items"]:
                    err("LIMIT", path, f"{len(v_)} items > {lim['max_items']}")
                if "item_max_words" in lim:
                    for i, item in enumerate(v_):
                        t = val(item) if isinstance(item, dict) else item
                        t = " ".join(str(x) for x in t.values()) if isinstance(t, dict) else str(t)
                        if _words(t) > lim["item_max_words"]:
                            err("LIMIT", f"{path}.{i}", f"{_words(t)} words > {lim['item_max_words']}")
            elif isinstance(v_, str):
                if "max_words" in lim and _words(v_) > lim["max_words"]:
                    err("LIMIT", path, f"{_words(v_)} words > {lim['max_words']}")
                if "max_sentences" in lim and _sentences(v_) > lim["max_sentences"]:
                    err("LIMIT", path, f"{_sentences(v_)} sentences > {lim['max_sentences']}")
                if "warn_min_words" in lim and _words(v_) < lim["warn_min_words"]:
                    warn("LIMIT", path, f"{_words(v_)} words (recommended ≥ {lim['warn_min_words']})")
    check("limits", len(errors) == n0)

    # 9. voice / constraints / line isolation / numbers / price / flags / placeholders (qa.py rules)
    skip = ("meta", "sources", "qa", "strategy.notes", "deck.slides", "deck.cover", "sales.dont_say", "landing.hero", "landing.sections")   # metadata, not copy
    tx = texts(pkg, skip_paths=skip)
    joined = "\n".join(t for _, t in tx)
    n0 = len(errors)
    banned = re.findall(r'"([^"]+)"', " ".join(house["voice"]["dont"]))
    norm = joined.translate(mdqa.FINALS)
    for w in banned:
        if mdqa.banned_re(w).search(norm):
            err("VOICE", "", f"banned word '{w}' (house voice.dont)")
    if mdqa.EXCLAIM.search(joined):
        err("VOICE", "", "exclamation mark")
    if mdqa.EMOJI.search(joined):
        err("VOICE", "", "emoji")
    for ph in mdqa.constraint_phrases(mfr):
        if ph in joined:
            err("CONSTRAINT", "", f"manufacturer forbids the phrase '{ph}'")
    for kind, where, t in mdqa.leakage_terms(mfr, p):
        if (mdqa.word_re(t).search(joined) if kind == "vocabulary" else t in joined):
            err("LINE_LEAKAGE", "", f"{kind} of {where} used: '{t}'")
    ids = set(get(p, "design.claims_ref") or []) | {pl.get("id") for pl in house.get("pillars") or [] if isinstance(pl, dict)}
    allowed = mdqa.factual_numbers(p)
    for n in sorted({n.replace(",", "").rstrip(".") for n in mdqa.NUM.findall(mdqa.scan_text(joined, {i for i in ids if isinstance(i, str)}))} - allowed):
        err("INVENTED_NUMBER", "", f"number {n} is not a factual value of the product")
    expected = (getp(pkg, "product.facts.price") or {}).get("display")
    amounts = {m.replace(",", "").rstrip(".") for m in mdqa.AMOUNT_AFTER.findall(joined) + mdqa.AMOUNT_BEFORE.findall(joined)}
    if expected:
        if not amounts <= {str(price.get("value"))}:
            err("PRICE", "", f"amounts other than the input price appear: {sorted(amounts)}")
        if expected not in joined:
            err("PRICE", "landing.product_details", f"price must appear exactly as {expected!r}")
    elif amounts:
        err("PRICE", "", f"no price in the input but amounts appear: {sorted(amounts)}")
    for f in v["flags"]:
        if f not in joined:
            err("FLAG_MISSING", "", f"validator flag not surfaced: {f}")
    pats = [re.compile(x, re.I) for x in SCHEMA["placeholder_patterns"]]
    for path, t in tx:
        if t.strip() in PLACEHOLDERS or any(x.search(t) for x in pats):
            err("PLACEHOLDER_TEXT", path, f"placeholder / filler text: {t[:40]!r}")
    check("content_rules", len(errors) == n0)

    # 10. provenance: derived fields traced, every ref resolves, every claim fragment quotes its item
    n0 = len(errors)
    for pattern in SCHEMA["derived_fields"]:
        for path in _paths(pattern, pkg):
            node = getp(pkg, path)
            if node in (None, "", []) or (isinstance(node, dict) and "value" in node and node["value"] in (None, "")):
                continue
            refs = node.get("derived_from") if isinstance(node, dict) else None
            if not isinstance(refs, list) or not refs:
                err("MISSING_DERIVATION", path, "derived field has no derived_from")
            else:
                for r in refs:
                    if not ref_ok(r):
                        err("UNSUPPORTED_CLAIM", path, f"derived_from ref {r!r} does not resolve to the claim set")
    if not isinstance(getp(pkg, "sales.when_to_recommend_derived_from"), list) or not getp(pkg, "sales.when_to_recommend_derived_from"):
        err("MISSING_DERIVATION", "sales.when_to_recommend", "no derived_from")

    def walk_claims(node, path=""):
        if isinstance(node, dict):
            if isinstance(node.get("claims"), list):
                host = " ".join(str(x) for k, x in node.items() if isinstance(x, str) and k not in SKIP_KEYS)
                for j, c in enumerate(node["claims"]):
                    if not isinstance(c, dict) or not ref_ok(c.get("ref")):
                        err("UNSUPPORTED_CLAIM", f"{path}.claims.{j}", f"ref {c.get('ref') if isinstance(c, dict) else c!r} does not resolve")
                    elif str(c.get("text", "")) not in host:
                        err("CLAIM_TEXT", f"{path}.claims.{j}", f"quoted text not in the item: {str(c.get('text'))[:40]!r}")
            for k, x in node.items():
                if k != "claims":
                    walk_claims(x, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, x in enumerate(node):
                walk_claims(x, f"{path}.{i}")

    walk_claims({k: pkg[k] for k in ("story", "benefits", "landing", "sales")})
    for i, pl in enumerate(pkg["strategy"].get("pillars") or []):
        for r in pl.get("refs") or []:
            if not ref_ok(r):
                err("UNSUPPORTED_CLAIM", f"strategy.pillars.{i}", f"ref {r!r} does not resolve")
    for i, row in enumerate(pkg["strategy"].get("spec_to_benefit") or []):
        if not ref_ok(row.get("ref")):
            err("UNSUPPORTED_CLAIM", f"strategy.spec_to_benefit.{i}", f"ref {row.get('ref')!r} does not resolve")
    check("provenance", len(errors) == n0)

    return _result(errors, warnings, checks)


def _result(errors, warnings, checks):
    """failed = content invalid (nothing renders); not_ready = content valid but the final assets are blocked (only
    readiness errors: hero image); passed / passed_with_warnings = ready."""
    content_errors = [e for e in errors if e["code"] not in READINESS_CODES]
    status = "failed" if content_errors else ("not_ready" if errors else ("passed_with_warnings" if warnings else "passed"))
    return {"status": status, "errors": errors, "warnings": warnings, "checks": checks}
