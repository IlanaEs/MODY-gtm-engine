"""The launch package: load, skeleton, and the display helpers every renderer shares."""
import datetime, os, re, yaml
from validate import validate, get, spec_status, project_path, load_strict, resolve_collection, MISSING, ROOT
import qa

SCHEMA_PATH = os.path.join(ROOT, "schema", "launch_package.schema.yaml")
with open(SCHEMA_PATH, encoding="utf-8") as _fh:
    SCHEMA = yaml.safe_load(_fh)
LIMITS = SCHEMA["limits"]
PACKAGE_FILE = "launch_package.yaml"
HEB = re.compile("[א-ת]")


# ---------------------------------------------------------------------------------------------------- context
def load_context(product_path, out_dir):
    """Validator result, product and the two brand layers (None when BLOCKED)."""
    v = validate(product_path)
    with open(product_path, encoding="utf-8") as fh:
        p = load_strict(fh)
    ctx = {"product_path": product_path, "out_dir": os.path.join(out_dir, ""), "v": v, "p": p, "house": None, "mfr": None}
    if v["status"] != "BLOCKED":
        with open(project_path(v["brand_layers"]["house"]), encoding="utf-8") as fh:
            ctx["house"] = yaml.safe_load(fh)
        with open(project_path(v["brand_layers"]["manufacturer"]), encoding="utf-8") as fh:
            ctx["mfr"] = yaml.safe_load(fh)
    return ctx


def load_package(out_dir):
    path = os.path.join(out_dir, PACKAGE_FILE)
    with open(path, encoding="utf-8") as fh:
        return load_strict(fh)


def skill_version():
    with open(project_path("SKILL.md"), encoding="utf-8") as fh:
        return re.search(r"^version:\s*(\S+)", fh.read(), re.M).group(1)


# ---------------------------------------------------------------------------------------------------- helpers
def getp(d, path):
    """Dotted path with list indexes ('benefits.0.fact'); None when anything is missing."""
    for k in str(path).split("."):
        if isinstance(d, list):
            if not k.isdigit() or int(k) >= len(d):
                return None
            d = d[int(k)]
        elif isinstance(d, dict):
            if k not in d:
                return None
            d = d[k]
        else:
            return None
    return d


def val(node):
    """The value of a { value, ... } field, or the node itself."""
    return node.get("value") if isinstance(node, dict) and "value" in node else node


def brand_display(p):
    b = get(p, "product.brand")
    return b.upper() if isinstance(b, str) else None


def title(pkg):
    """SKILL 6b slide 1 / landing image alt: 'GESSI Jacqueline 77201'; a Hebrew name gets the model first."""
    f = pkg["product"]["facts"]
    name, brand, model = val(f["name"]), val(f["brand"]), val(f.get("model"))
    if name and HEB.search(name) and model:
        return f"{brand} {model}: {name}"
    return f"{brand} {name}"


def _scalar(v):
    if isinstance(v, list):
        return " · ".join(str(x) for x in v)
    if isinstance(v, dict):
        if "code" in v or "name" in v:                       # finish: { code, name }
            return " – ".join(str(v[k]) for k in ("code", "name") if v.get(k) not in (None, ""))
        return " · ".join(f"{k}: {_scalar(x)}" for k, x in v.items())
    return str(v)


def spec_display(field):
    """Display text for a sourced field { value, source, variants?, options? }: value, then variants / options."""
    v = field.get("value") if isinstance(field, dict) else field
    parts = [_scalar(v)]
    for k in ("variants", "options"):
        extra = field.get(k) if isinstance(field, dict) else None
        if isinstance(extra, list):
            parts += [str(x) for x in extra if str(x) != parts[0]]
    return " · ".join(parts)


def draft_banner(v):
    return None if v["publishable"] else qa.DRAFT_BANNER[2:] + ", ".join(v["publish_blockers"])


def resolve_image(path, product_path):
    if not isinstance(path, str) or not path.strip():
        return ""
    if os.path.isabs(path):
        return path
    for base in (ROOT, os.path.dirname(os.path.abspath(product_path))):
        cand = os.path.join(base, path)
        if os.path.exists(cand):
            return cand
    return os.path.join(ROOT, path)


def ref_source(ctx, ref):
    """The `source` claims_used records for a ref (SKILL step 8): approved-claim URL, the product source key,
    or the layer file."""
    p, mfr, v = ctx["p"], ctx["mfr"], ctx["v"]
    kind, _, key = str(ref).partition(":")
    if kind == "claim":
        block = resolve_collection(mfr, p)[2] or {}
        for c in block.get("approved_claims") or []:
            if isinstance(c, dict) and c.get("id") == key:
                return c.get("source")
    if kind == "spec":
        field = get(p, "design.signature_material") if key == "signature_material" else (p.get("technical") or {}).get(key)
        return field.get("source") if isinstance(field, dict) else None
    if kind == "commercial":
        return get(p, "commercial.price_ils.source")
    if kind == "house":
        return v["brand_layers"]["house"]
    if kind == "brand":
        return v["brand_layers"]["manufacturer"]
    return None


# ---------------------------------------------------------------------------------------------------- skeleton
def facts(ctx):
    p, house = ctx["p"], ctx["house"]
    sources = p.get("sources") or {}
    f = {}
    for key, path in (("name", "product.name"), ("collection", "product.collection"), ("line", "product.line"),
                      ("model", "product.model_number"), ("designer", "product.designer")):
        v = get(p, path)
        f[key] = {"value": v if v not in ("",) else None, "source": "product_page" if v else None}
    f["brand"] = {"value": brand_display(p), "source": "product_page"}
    f["brand_id"] = {"value": get(p, "product.brand"), "source": "product_page"}
    cat = get(p, "product.category")
    f["category"] = {"value": cat, "source": "product_page"}
    f["category_label"] = {"value": SCHEMA["category_labels"].get(cat, cat), "source": "product_page"}
    price = get(p, "commercial.price_ils")
    pv = price.get("value") if isinstance(price, dict) else None
    ok = isinstance(pv, (int, float)) and not isinstance(pv, bool)
    f["price"] = {"value": pv if ok else None, "display": house["format"]["price"].format(value=pv) if ok else None,
                  "source": price.get("source") if isinstance(price, dict) and ok else None}
    f["price_tier"] = {"value": get(p, "commercial.price_tier") or None, "source": "mody_internal" if get(p, "commercial.price_tier") else None}
    f["availability"] = {"value": None, "source": None}          # no input field yet: never invented
    f["launch_status"] = {"value": None, "source": None}
    return f


def specs(ctx):
    """Every category-profile field + every entered technical field, SKILL order; missing -> flag; plus signature material."""
    p = ctx["p"]
    sources = p.get("sources") or {}
    tech = p.get("technical") or {}
    with open(project_path("schema/product_input.schema.yaml"), encoding="utf-8") as fh:
        pschema = yaml.safe_load(fh)
    profile = pschema["validation"].get("category_profiles", {}).get(get(p, "product.category"), [])
    labels = SCHEMA["field_labels"]
    rows = []
    sig = get(p, "design.signature_material")
    if spec_status(sig, sources) == "verified":
        rows.append({"field": "signature_material", "label": labels["signature_material"], "value": spec_display(sig),
                     "source": sig.get("source"), "ref": "spec:signature_material", "flag": None})
    for fld in list(dict.fromkeys(list(profile) + list(tech))):
        status = spec_status(tech.get(fld), sources)
        if status == "verified":
            rows.append({"field": fld, "label": labels.get(fld, fld), "value": spec_display(tech[fld]),
                         "source": tech[fld].get("source"), "ref": f"spec:{fld}", "flag": None,
                         **({"evidence": tech[fld]["evidence"]} if isinstance(tech[fld].get("evidence"), str) else {})})
        else:
            rows.append({"field": fld, "label": labels.get(fld, fld), "value": None, "source": None, "ref": None,
                         "flag": MISSING.format(f=f"technical.{fld}")})
    return rows


def audiences(ctx):
    house, p = ctx["house"], ctx["p"]
    by_id = {a.get("id"): a for a in house.get("audiences") or [] if isinstance(a, dict)}
    tier = get(p, "commercial.price_tier")
    ids = qa.AUDIENCE_BY_TIER.get(tier, ("A", "B"))
    rule = f"price_tier={tier} → {ids[0]}, {ids[1]}" if tier else f"price_tier missing → {ids[0]}, {ids[1]}"
    out = []
    for i in ids:
        a = by_id.get(i)
        if a:
            out.append({"id": i, "segment": a.get("name"),
                        "decision_driver": " · ".join(str(x) for x in a.get("cares_about") or []),
                        "needs_line": "צריכים " + " ו".join(str(x) for x in a.get("needs_from_us") or []),
                        "need": None, "relevance": None, "derived_from": [f"house:{i}"]})
    return rule, out


def tone_keywords(ctx):
    char = str(get(ctx["house"], "voice.character") or "")
    return [w.strip() for w in char.split(".")[0].split(",") if w.strip()][:LIMITS["messaging.tone"]["max_items"]]


def hero_asset(ctx):
    """The approved product image is a pipeline input: `sources.image` (path) + `sources.image_approved` (MODY sign-off).
    `approved` is true only when the file exists, the format is supported and MODY approved it. Nothing is ever generated."""
    p = ctx["p"]
    image = get(p, "sources.image") or None
    fmt = os.path.splitext(image)[1].lstrip(".").lower() if image else None
    exists = bool(image) and os.path.exists(resolve_image(image, ctx["product_path"]))
    signed = get(p, "sources.image_approved") is True
    return {"path": image, "source": "sources.image" if image else None, "exists": exists,
            "approved": exists and signed and fmt in SCHEMA["image_formats"], "format": fmt}


def readiness(pkg):
    """Final-asset readiness: the approved hero image is a hard requirement (schema image_missing_file: error)."""
    hero = (pkg.get("product") or {}).get("assets", {}).get("hero_image") or {}
    blockers = []
    if not hero.get("path"):
        blockers.append("MISSING_HERO_IMAGE: no product image in sources.image")
    elif not hero.get("exists"):
        blockers.append(f"MISSING_HERO_IMAGE: file not found: {hero['path']}")
    if hero.get("path") and hero.get("format") not in SCHEMA["image_formats"]:
        blockers.append(f"IMAGE_FORMAT: {hero.get('format')!r} not in {SCHEMA['image_formats']}")
    if hero.get("path") and hero.get("exists") and not hero.get("approved"):
        blockers.append("IMAGE_NOT_APPROVED: sources.image_approved is not true")
    return {"status": "ready" if not blockers else "not_ready", "blockers": blockers}


def launch_plan(ctx):
    """The template's four fixed stages (ASSETS / ENABLEMENT / CHANNELS / MEASURE). Pipeline facts only: what the
    renderers produce, what the sales team gets, image readiness. A stage with no source keeps the missing flag."""
    v = ctx["v"]
    stages = SCHEMA["launch_stages"]
    hero = hero_asset(ctx)
    return [
        {"stage": stages[0], "action": "דף מוצר פנימי · מצגת השקה פנימית · הנחיות מכירה · מפרט מאומת מהמקורות"
                                        + ("" if hero["approved"] else " · תמונת מוצר מאושרת: " + MISSING.format(f="sources.image")),
         "status": "מוכן להפצה פנימית" if hero["approved"] else "טיוטה עד לאישור תמונת מוצר", "owner": None},
        {"stage": stages[1], "action": "הנחיות המכירה ושקף כלים למכירה לצוות המכירות · מסרים מאושרים מחבילת ההשקה", "status": None, "owner": None},
        {"stage": stages[2], "action": "ערוצי ההשקה טרם הוגדרו: להחלטה עם צוות השיווק", "status": None, "owner": None},
        {"stage": stages[3], "action": "מדדי ההצלחה טרם הוגדרו: להחלטה לפני ההשקה", "status": None, "owner": None},
    ]


def next_step(ctx):
    """NEXT STEP line of the launch plan: owner | status | launch date | open decisions – facts only, flags otherwise."""
    v = ctx["v"]
    flags = list(v["flags"])
    return {"owner": SCHEMA["launch_stage_owner_default"] if flags else None,
            "status": "מאומת, ניתן לפרסום" if v["publishable"] else draft_banner(v),
            "launch_date": "להגדרה",
            "open_decisions": " · ".join(flags) if flags else "אין"}


def skeleton(ctx):
    """Every fact and every structural field prefilled; derived fields None. The Skill completes the rest ONCE."""
    v, p = ctx["v"], ctx["p"]
    if v["status"] == "BLOCKED":
        raise ValueError("BLOCKED product: " + "; ".join(v["errors"]))
    rule, aud = audiences(ctx)
    story_expected = resolve_collection(ctx["mfr"], p)[2] is not None
    d = lambda: {"value": None, "derived_from": []}
    return {
        "meta": {"product": get(p, "product.id"), "generated": str(datetime.date.today()), "skill_version": skill_version(),
                 "brand_versions": dict(v["brand_layers"]), "validator_status": v["status"], "publishable": v["publishable"],
                 "publish_blockers": list(v["publish_blockers"]), "flags": list(v["flags"]), "draft_banner": draft_banner(v)},
        "product": {"facts": facts(ctx), "specs": specs(ctx), "assets": {"hero_image": hero_asset(ctx)}, "summary": d()},
        "strategy": {"positioning": d(), "value_proposition": d(), "customer_need": d(), "consumer_insight": d(),
                     "differentiators": [], "audience_rule": rule, "target_audiences": aud, "pillars": [],
                     "spec_to_benefit": [], "notes": {}},
        "messaging": {"headline": d(), "one_liner": d(), "tone": tone_keywords(ctx), "key_messages": []},
        "story": {"value": None, "claims": [], "derived_from": [], "expected": story_expected},
        "benefits": [],
        "sales": {"opening": {"value": None, "ref": None}, "architect_points": [], "private_points": [], "faq": [],
                  "dont_say": [], "key_talking_points": [],
                  "seller_cheat_sheet": {"positioning": None, "private_customer": None, "professional_customer": None, "derived_from": []},
                  "when_to_recommend": []},
        "landing": {"hero": {"headline": "messaging.headline", "sub": "messaging.one_liner", "image": "product.assets.hero_image"},
                    "sections": ["story", "benefits", "details", "mody"], "product_details": [],
                    "mody_section": {"value": None, "claims": []}},
        "deck": {"cover": {"source_fields": list(SCHEMA["deck_cover_fields"]), "notes": None},
                 "slides": [dict(s, notes=None) for s in SCHEMA["deck_slides"]], "launch_plan": launch_plan(ctx), "next_step": next_step(ctx)},
        "sources": {"house": v["brand_layers"]["house"], "manufacturer": v["brand_layers"]["manufacturer"],
                    "product_sources": dict(p.get("sources") or {})},
        "qa": {"status": None, "errors": [], "warnings": []},
    }


def refresh_facts(pkg, ctx):
    """Re-derive every fact-owned field of an existing package from the sources (skeleton), keeping the authored
    content: meta, product facts/specs/assets, audiences' fact keys, tone, launch plan / next step, deck structure,
    sources. Used after a product file changes and by the content engine before QA."""
    sk = skeleton(ctx)
    pkg["meta"] = dict(sk["meta"], generated=pkg.get("meta", {}).get("generated") or sk["meta"]["generated"])
    for k in ("facts", "specs", "assets"):
        pkg["product"][k] = sk["product"][k]
    pkg["sources"] = sk["sources"]
    pkg["messaging"]["tone"] = sk["messaging"]["tone"]
    pkg["strategy"]["audience_rule"] = sk["strategy"]["audience_rule"]
    old_aud = {a.get("id"): a for a in pkg["strategy"].get("target_audiences") or [] if isinstance(a, dict)}
    pkg["strategy"]["target_audiences"] = [dict(a, need=old_aud.get(a["id"], {}).get("need"), relevance=old_aud.get(a["id"], {}).get("relevance"),
                                                needs_line=old_aud.get(a["id"], {}).get("needs_line") or a["needs_line"],
                                                derived_from=old_aud.get(a["id"], {}).get("derived_from") or a["derived_from"])
                                           for a in sk["strategy"]["target_audiences"]]
    pkg["story"]["expected"] = sk["story"]["expected"]
    deck = pkg.setdefault("deck", {})
    notes = [((deck.get("cover") or {}).get("notes"))] + [(s.get("notes") if isinstance(s, dict) else None) for s in deck.get("slides") or []]
    notes += [None] * (8 - len(notes))
    deck["cover"] = dict(sk["deck"]["cover"], notes=notes[0])
    deck["slides"] = [dict(s, notes=notes[i + 1]) for i, s in enumerate(sk["deck"]["slides"])]
    deck["launch_plan"], deck["next_step"] = sk["deck"]["launch_plan"], sk["deck"]["next_step"]
    return pkg


def dump(pkg, path):
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(pkg, fh, allow_unicode=True, sort_keys=False, width=110)
