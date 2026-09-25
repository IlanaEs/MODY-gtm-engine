"""Product input validator – runs before the Skill generates anything.
Usage: python validate.py products/gessi-77201.yaml
"""
import glob, os, re, sys, yaml

MISSING = "[חסר: {f} – לבדיקה]"
ROOT = os.path.dirname(os.path.abspath(__file__))      # F-26: project paths resolve from here, never from the caller's cwd
BRAND_RE = re.compile(r"^[A-Za-z0-9_-]+$")              # F-25: a brand id is a plain slug (no glob chars, dots or separators)
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")       # F-31: product.id becomes the out/<id>/ directory name


def project_path(rel):
    return os.path.join(ROOT, rel)


class DuplicateKeyError(yaml.YAMLError):
    pass


class StrictLoader(yaml.SafeLoader):
    """F-31: PyYAML silently keeps the last of duplicate mapping keys; for inputs a duplicate is an error."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if isinstance(key, (list, dict)):
                continue                                # SafeLoader raises its own error for unhashable keys
            if key in seen:
                raise DuplicateKeyError(f"duplicate key {key!r} (line {key_node.start_mark.line + 1})")
            seen.add(key)
        return super().construct_mapping(node, deep)


def load_strict(fh):
    return yaml.load(fh, Loader=StrictLoader)


def get(d, path):
    for k in path.split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


VERSION_RE = re.compile(r"\.v(\d+(?:\.\d+)*)\.yaml$")


def parse_version(path):
    m = VERSION_RE.search(path)
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


PIN_RE = re.compile(r"^[A-Za-z0-9_-]+@\d+(?:\.\d+)*$")     # "gessi@1.0"


def resolve_layer(layer_id, pin=None):
    """Return brand/<id>.v<ver>.yaml (relative to the project root).
    pin="gessi@1.0" -> that exact version; otherwise highest semantic version.
    F-25: the id must be a slug and is glob-escaped, so "*" or "g*" can never match a file."""
    if not isinstance(layer_id, str) or not BRAND_RE.match(layer_id):
        return None
    names = [os.path.basename(f) for f in glob.glob(os.path.join(ROOT, "brand", f"{glob.escape(layer_id)}.v*.yaml"))]
    files = [f"brand/{n}" for n in names if n.startswith(layer_id + ".v") and parse_version(n)]
    if pin:
        want = tuple(int(x) for x in pin.split("@", 1)[1].split("."))
        files = [f for f in files if parse_version(f) == want]
    return max(files, key=parse_version) if files else None


def _mapping(container, key, errors):
    """F-11: a section that must be a mapping. Wrong type -> error + empty mapping, never a crash."""
    val = container.get(key)
    if val is None:
        return {}
    if not isinstance(val, dict):
        errors.append(f"{key}: חייב להיות מבנה מפתח-ערך (mapping), התקבל {type(val).__name__}")
        return {}
    return val


def _pin(pins, key, errors, layer_id=None):
    """F-11: a version pin is either absent or '<id>@<major>.<minor>'; anything else is an error, not a crash.
    F-24: the id before '@' must be the layer being resolved (a gessi product cannot pin 'mutina@1.0').
    Returns (pin, ok); ok is False when a pin was given but rejected, so nothing gets resolved in its place."""
    pin = pins.get(key)
    if pin is None:
        return None, True
    if not isinstance(pin, str) or not PIN_RE.match(pin):
        errors.append(f"brand_versions.{key}: פורמט גרסה לא תקין '{pin}' (נדרש <id>@<major>.<minor>)")
        return None, False
    if layer_id is not None and pin.split("@", 1)[0] != layer_id:
        errors.append(f"brand_versions.{key}: המזהה לפני @ חייב להיות '{layer_id}', התקבל '{pin}'")
        return None, False
    return pin, True


def _norm(key):
    """Case-insensitive key match (SKILL step 3). Space, hyphen and underscore are equivalent,
    so product `line: Haute Culture` matches brand key `haute_culture`."""
    return re.sub(r"[\s_-]+", "_", str(key).strip().lower())


def resolve_line(brand_cfg, p):
    """(line key, line block) for the product's `line`, or lines.default when it has none; (None, None) if no match."""
    lines = (brand_cfg or {}).get("lines") or {}
    line_key = get(p, "product.line")
    want = _norm(line_key) if line_key else "default"
    return next(((k, v) for k, v in lines.items() if isinstance(v, dict) and _norm(k) == want), (None, None))


def resolve_collection(brand_cfg, p):
    """(line key, collection key, collection block) per SKILL step 3, or (line key, None, None) when there is no match.
    No `line` -> lines.default. No `collection` or no matching block -> None (manufacturer identity only)."""
    line_key, line = resolve_line(brand_cfg, p)
    col_key = get(p, "product.collection")
    if line is None or not col_key:
        return line_key, None, None
    cols = line.get("collections") or {}
    return line_key, *next(((k, v) for k, v in cols.items() if isinstance(v, dict) and _norm(k) == _norm(col_key)), (None, None))


def collection_block(brand_cfg, p):
    return resolve_collection(brand_cfg, p)[2]


def allowed_claim_ids(brand_cfg, p):
    """F-02: the only claim ids this product may reference = its own collection's approved_claims."""
    block = collection_block(brand_cfg, p) or {}
    return {c["id"] for c in block.get("approved_claims") or [] if isinstance(c, dict) and "id" in c}


def _empty(v):
    return v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, (list, dict, tuple)) and not v)


def spec_status(val, sources):
    """F-04: 'verified' only with a real value AND a source key that resolves to a non-empty entry.
    'missing' = no value (becomes a flag). 'invalid' = value without a usable source (error)."""
    if val is None or (isinstance(val, dict) and _empty(val.get("value"))):
        return "missing"
    src = val.get("source") if isinstance(val, dict) else None
    if isinstance(src, str) and isinstance(sources, dict) and sources.get(src):
        return "verified"
    return "invalid"


def validate(path):
    schema = yaml.safe_load(open(project_path("schema/product_input.schema.yaml"), encoding="utf-8"))
    rules = schema["validation"]
    errors, flags = [], []

    # 0. load (F-11: unreadable, invalid or wrong-shaped YAML is a controlled BLOCKED, never a crash)
    try:
        with open(path, encoding="utf-8") as fh:
            p = load_strict(fh)
    except (OSError, yaml.YAMLError) as e:
        p = None
        errors.append(f"קובץ המוצר לא נטען: {type(e).__name__}" + (f": {e}" if isinstance(e, DuplicateKeyError) else ""))
    if not isinstance(p, dict):
        if not errors:
            errors.append(f"קובץ המוצר חייב להיות מבנה מפתח-ערך (mapping), התקבל {type(p).__name__}")
        p = {}
    product = _mapping(p, "product", errors)
    design = _mapping(p, "design", errors)
    commercial = _mapping(p, "commercial", errors)
    pins = _mapping(p, "brand_versions", errors)
    tech = _mapping(p, "technical", errors)
    sources = _mapping(p, "sources", errors)

    # 1. required fields
    for f in rules["required_fields"]:
        if not get(p, f):
            errors.append(f"שדה חובה חסר: {f}")
    pid = product.get("id")
    if pid is not None and (not isinstance(pid, str) or not ID_RE.match(pid)):        # F-31: no traversal / separators
        errors.append(f"product.id: מזהה לא תקין '{pid}' (אותיות, ספרות, קו תחתון או מקף, ללא / או ..)")

    # 2. category enum
    cats = schema["structure"]["product"]["category"]["values"]
    category = product.get("category")
    if not isinstance(category, str) or category not in cats:
        errors.append(f"קטגוריה לא מוכרת: {category}")
        category = None

    # 3. manufacturer layer
    brand = product.get("brand")
    brand_ok = isinstance(brand, str) and bool(BRAND_RE.match(brand))
    if brand is not None and not brand_ok:
        errors.append(f"product.brand: מזהה לא תקין '{brand}' (אותיות, ספרות, קו תחתון או מקף בלבד)")
    mfr_pin, mfr_ok = _pin(pins, "manufacturer", errors, brand if brand_ok else None)
    house_pin, house_ok = _pin(pins, "house", errors, "mody_brand_dna")
    brand_file = resolve_layer(brand, mfr_pin) if brand_ok and mfr_ok else None
    house_file = resolve_layer("mody_brand_dna", house_pin) if house_ok else None
    if not brand_file and mfr_ok:
        errors.append(f"אין קובץ יצרן עבור '{brand}'" + (f" בגרסה {mfr_pin}" if mfr_pin else ""))
    if not house_file and house_ok:
        errors.append("אין קובץ House DNA")

    # 4. verified specs + source resolution
    #    fields to check = category profile ∪ whatever the author entered
    expected = rules.get("category_profiles", {}).get(category, [])
    known = set(expected) | set((get(schema, "structure.technical") or {}).keys())
    verified = 0
    for field in list(dict.fromkeys(list(expected) + list(tech))):
        status = spec_status(tech.get(field), sources)
        if status == "missing":
            flags.append(MISSING.format(f=f"technical.{field}"))
        elif status == "verified":
            verified += field in known     # F-31: extension fields keep their source contract but do not satisfy min_verified_specs
        else:
            errors.append(f"technical.{field}: אין source תקין")
    if verified < rules["min_verified_specs"]:
        errors.append(f"רק {verified} specs מאומתים (נדרש {rules['min_verified_specs']})")
    # 4a. F-28: the one price contract is { value: <number>, source: <key> } (schema, house format "{value:,} ₪")
    price = commercial.get("price_ils")
    if price is not None:
        if not isinstance(price, dict):
            errors.append(f"commercial.price_ils: חייב להיות {{ value: <מספר>, source: <מקור> }}, התקבל {price!r}")
        elif price.get("value") is not None and (isinstance(price["value"], bool) or not isinstance(price["value"], (int, float))):
            errors.append(f"commercial.price_ils.value: חייב להיות מספר, התקבל {price['value']!r}")
    # 4b. F-21e: the same source contract (schema source_must_resolve, SKILL step 4) for the other sourced fields
    for f in ("design.signature_material", "commercial.price_ils"):
        val = get(p, f)
        if val is not None:
            status = spec_status(val, sources)
            if status == "invalid":
                errors.append(f"{f}: אין source תקין")
            elif status == "missing":
                flags.append(MISSING.format(f=f))
    # 4c. F-21c/f: price_tier drives audience priority (SKILL step 5). Missing -> flag; outside the enum -> error.
    tier = commercial.get("price_tier")
    tiers = get(schema, "structure.commercial.price_tier.values") or []
    if tier is None or tier == "":
        flags.append("[חסר: price_tier – לבדיקה]")
    elif not isinstance(tier, str) or tier not in tiers:
        errors.append(f"commercial.price_tier לא בערכים המותרים {tiers}: {tier}")

    # 5. claims belong to the product's own collection block (F-02: no leakage between lines / collections)
    claims_ref = design.get("claims_ref")
    if claims_ref is None:
        claims_ref = []
    elif not isinstance(claims_ref, list):
        errors.append(f"design.claims_ref: חייב להיות רשימה, התקבל {type(claims_ref).__name__}")
        claims_ref = []
    bad_items = [c for c in claims_ref if not isinstance(c, str)]
    if bad_items:
        errors.append(f"design.claims_ref: פריטים שאינם מזהי טענה: {bad_items}")
        claims_ref = [c for c in claims_ref if isinstance(c, str)]
    if brand_file:
        brand_cfg = yaml.safe_load(open(project_path(brand_file), encoding="utf-8"))
        allowed = allowed_claim_ids(brand_cfg, p)
        where = f"{get(p, 'product.line') or 'default'}/{get(p, 'product.collection')}"
        for c in claims_ref:
            if c not in allowed:
                errors.append(f"טענה {c} לא שייכת לקולקציית המוצר ({where}) ב-{brand_file}"
                              + ("" if allowed else " – אין בלוק קולקציה תואם, claims_ref חייב להיות ריק"))

    # 6. publish gates (draft allowed, publish not) + optional sources
    publish_blockers = []
    for f in rules.get("publish_required", []):
        val = get(p, f)
        if isinstance(val, dict) and _empty(val.get("value")):      # {value: null, source: x} has no value either
            val = None
        if not val:
            if MISSING.format(f=f) not in flags:
                flags.append(MISSING.format(f=f))
            publish_blockers.append(f)
    if not get(p, "sources.technical_sheet"):
        flags.append(MISSING.format(f="sources.technical_sheet"))

    status = "BLOCKED" if errors else ("READY_WITH_FLAGS" if flags else "READY")
    return {
        "product": get(p, "product.id") or path,
        "status": status,
        "publishable": not errors and not publish_blockers,
        "publish_blockers": publish_blockers,
        "verified_specs": verified,
        "brand_layers": {"house": house_file, "manufacturer": brand_file},
        "errors": errors,
        "flags": flags,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:                                   # F-32: routine misuse gets a usage line, not a silent exit 0
        print("usage: python validate.py products/<id>.yaml [more.yaml ...]", file=sys.stderr)
        sys.exit(2)
    results = [validate(path) for path in sys.argv[1:]]
    for r in results:
        print(yaml.safe_dump(r, allow_unicode=True, sort_keys=False))
    sys.exit(1 if any(r["status"] == "BLOCKED" for r in results) else 0)   # F-05: CI-usable exit code
