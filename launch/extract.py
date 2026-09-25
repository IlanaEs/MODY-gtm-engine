"""Supplier page extraction: URL -> visible product facts -> products/<id>.yaml (schema v1.2), every value traceable
to the page (source key `product_page` + the evidence line it came from). Rules only, no model: a fact the page does
not state is not written. Unknown category / brand are reported, never guessed."""
import html as htmlmod, os, re, urllib.parse, urllib.request, glob, yaml
from html.parser import HTMLParser
from validate import ROOT

USER_AGENT = "MODY-launch/1.0 (+product intake)"
# label synonyms -> product schema field (technical.* unless noted)
LABELS = {
    "material": ["material", "materials", "body material", "חומר"],
    "finish": ["finish", "finishes", "surface finish", "colour finish", "color finish", "גימור"],
    "dimensions_mm": ["dimensions", "dimension", "size", "measurements", "height", "מידות"],
    "flow_rate_lpm": ["flow rate", "flow", "ספיקה"],
    "installation_type": ["installation", "installation type", "mounting", "mounting type", "התקנה", "סוג התקנה"],
    "features": ["features", "characteristics", "key features", "מאפיינים"],
    "technologies": ["technology", "technologies", "טכנולוגיה", "טכנולוגיות"],
    "technical_requirements": ["technical requirements", "requirements", "working pressure", "operating pressure", "max pressure", "דרישות טכניות"],
    "certifications": ["certification", "certifications", "certified", "standards", "standard", "approvals", "תקן", "תקנים"],
    "warranty": ["warranty", "guarantee", "אחריות"],
    "sku": ["sku", "article", "article number", "item number", "item no", "reference", "ref", "product code", "code", "part number", "מק\"ט", "מספר פריט"],
    "model_number": ["model", "model number", "model no", "דגם"],
    "collection": ["collection", "series", "range", "קולקציה", "סדרה"],
    "brand": ["brand", "manufacturer", "מותג", "יצרן"],
    "format_cm": ["format", "tile size", "פורמט"],
    "thickness_mm": ["thickness", "עובי"],
    "colour": ["colour", "color", "colours", "colors", "צבע"],
    "application": ["application", "applications", "suitable for", "use", "יישום"],
    "designer": ["designer", "design by", "designed by", "מעצב", "מעצבת"],
}
PRODUCT_FIELDS = {"model_number", "collection", "brand", "designer"}
LIST_FIELDS = {"features", "technologies", "certifications"}
CATEGORY_CUES = [           # first match wins; cues are matched on the page title + visible text
    ("kitchen_mixer", ["kitchen mixer", "kitchen tap", "kitchen faucet", "sink mixer", "ברז מטבח"]),
    ("shower_system", ["shower system", "shower set", "shower column", "shower head", "מערכת מקלחת", "ראש מקלחת"]),
    ("bath_mixer", ["bath mixer", "bath filler", "bath tap", "bath-shower mixer", "ברז אמבט", "ברז לאמבט"]),
    ("basin_mixer", ["basin mixer", "washbasin mixer", "washbasin tap", "basin tap", "basin faucet", "lavatory faucet", "ברז כיור", "ברז לכיור"]),
    ("tile", ["tiles", "tile", "porcelain stoneware", "ceramic", "אריח", "אריחים"]),
    ("flooring", ["flooring", "parquet", "ריצוף"]),
    ("sanitaryware", ["washbasin", "wc", "toilet", "bidet", "sanitaryware", "כיור", "אסלה"]),
    ("kitchen", ["kitchen furniture", "kitchen cabinet", "מטבח"]),
    ("accessory", ["accessory", "accessories", "towel rail", "אביזר", "אביזרים"]),
]


class _Parser(HTMLParser):
    """Visible text (script/style dropped), the title, table / definition-list rows, list items, images."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self._in_title, self._skip = "", False, 0
        self.text, self.rows, self.items, self.images = [], [], [], []
        self._cells, self._cell, self._in_cell, self._row = [], [], False, None
        self._dt, self._in_dt, self._in_dd, self._dd = None, False, False, []
        self._in_li, self._li = False, []
        self._block = {"p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd", "td", "th", "section", "article", "table"}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "tr":
            self._cells = []
        elif tag in ("td", "th"):
            self._in_cell, self._cell = True, []
        elif tag == "dt":
            self._in_dt, self._dt = True, []
        elif tag == "dd":
            self._in_dd, self._dd = True, []
        elif tag == "li":
            self._in_li, self._li = True, []
        elif tag == "img" and a.get("src"):
            self.images.append(a["src"])
        if tag in self._block:
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg"):
            self._skip = max(0, self._skip - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in ("td", "th"):
            self._in_cell = False
            self._cells.append(" ".join("".join(self._cell).split()))
        elif tag == "tr":
            if len(self._cells) >= 2:
                self.rows.append((self._cells[0], " ".join(self._cells[1:])))
        elif tag == "dt":
            self._in_dt = False
        elif tag == "dd":
            self._in_dd = False
            if self._dt is not None:
                self.rows.append((" ".join("".join(self._dt).split()), " ".join("".join(self._dd).split())))
        elif tag == "li":
            self._in_li = False
            t = " ".join("".join(self._li).split())
            if t:
                self.items.append(t)
        if tag in self._block:
            self.text.append("\n")

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
        if self._in_cell:
            self._cell.append(data)
        if self._in_dt:
            self._dt.append(data)
        if self._in_dd:
            self._dd.append(data)
        if self._in_li:
            self._li.append(data)
        self.text.append(data)


def fetch(url, timeout=20):
    """Returns the page HTML. http(s) via urllib; a local path or file:// URL is read from disk (fixtures, offline)."""
    if url.startswith("file://"):
        url = urllib.request.url2pathname(urllib.parse.urlparse(url).path)
    if os.path.exists(url):
        with open(url, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en,he;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse(html):
    p = _Parser()
    p.feed(html)
    text = re.sub(r"[ \t]+", " ", htmlmod.unescape("".join(p.text)))
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return {"title": " ".join(p.title.split()), "lines": lines, "rows": p.rows, "items": p.items, "images": p.images}


def _field_for(label):
    key = re.sub(r"[\s:：]+$", "", label.strip().lower())
    for field, names in LABELS.items():
        if key in names:
            return field
    return None


def _split_list(value):
    parts = [x.strip(" .") for x in re.split(r"\s*(?:[•·|;\n]|,\s)\s*", value) if x.strip(" .")]
    return parts if len(parts) > 1 else [value.strip()]


def extract(url, product_name, html=None, brands=None):
    """{"facts": {field: {value, evidence}}, "category": {value, evidence}|None, "brand": {value, evidence}|None,
        "line": {value, evidence}|None, "title", "images", "unmapped": [(label, value)]} – nothing inferred."""
    html = html if html is not None else fetch(url)
    page = parse(html)
    facts, unmapped = {}, []
    pairs = list(page["rows"])
    for l in page["lines"]:                                  # "Label: value" lines outside tables
        m = re.match(r"^([A-Za-zא-ת][\w\s\"/()-]{1,40}?)\s*[:：]\s*(.+)$", l)
        if m and len(m.group(2)) < 200:
            pairs.append((m.group(1), m.group(2)))
    for label, value in pairs:
        field = _field_for(label)
        if not field or not value.strip():
            unmapped.append((label, value)) if not field else None
            continue
        if field in facts:
            continue                                         # first statement wins; nothing merged from elsewhere
        val = _split_list(value) if field in LIST_FIELDS else value.strip()
        facts[field] = {"value": val, "evidence": f"{label}: {value}"[:200]}
    # features from a list under a "Features" heading, when no labelled row gave them
    if "features" not in facts:
        for i, l in enumerate(page["lines"]):
            if l.strip(": ").lower() in ("features", "key features", "characteristics", "מאפיינים"):
                items = [x for x in page["items"] if x in page["lines"][i + 1:i + 15]]
                if items:
                    facts["features"] = {"value": items[:12], "evidence": "Features list: " + " · ".join(items[:12])[:180]}
                break
    haystack = (page["title"] + "\n" + "\n".join(page["lines"])).lower()
    category = None
    for cat, cues in CATEGORY_CUES:
        hit = next((c for c in cues if c in haystack), None)
        if hit:
            line = next((l for l in [page["title"]] + page["lines"] if hit in l.lower()), hit)
            category = {"value": cat, "evidence": line[:160]}
            break
    brands = brands if brands is not None else known_brands()
    brand = None
    if "brand" in facts:
        b = str(facts["brand"]["value"]).strip().lower()
        if b in brands:
            brand = {"value": b, "evidence": facts["brand"]["evidence"]}
    if not brand:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        hit = next((b for b in sorted(brands) if b in host), None)
        if hit:
            brand = {"value": hit, "evidence": f"supplier host {host}"}
    line = None
    if brand:
        for key in manufacturer_lines(brand["value"]):
            pretty = key.replace("_", " ").lower()
            if pretty != "default" and pretty in haystack:
                src = next((l for l in [page["title"]] + page["lines"] if pretty in l.lower()), pretty)
                line = {"value": key, "evidence": src[:160]}
                break
    return {"facts": facts, "category": category, "brand": brand, "line": line, "title": page["title"],
            "images": page["images"][:10], "unmapped": unmapped[:40]}


def known_brands():
    return {os.path.basename(f).split(".v")[0] for f in glob.glob(os.path.join(ROOT, "brand", "*.v*.yaml"))} - {"mody_brand_dna"}


def manufacturer_lines(brand):
    files = sorted(glob.glob(os.path.join(ROOT, "brand", f"{brand}.v*.yaml")))
    if not files:
        return []
    with open(files[-1], encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    return list((cfg.get("lines") or {}).keys())


def claims_for(brand, line_key, collection):
    """The manufacturer's approved claim ids for the product's own collection block (F-02): those are the only
    claims_ref a product may carry. Empty when no block matches."""
    from validate import resolve_collection
    files = sorted(glob.glob(os.path.join(ROOT, "brand", f"{brand}.v*.yaml")))
    if not files or not collection:
        return []
    with open(files[-1], encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    block = resolve_collection(cfg, {"product": {"line": line_key, "collection": collection}})[2] or {}
    return [c["id"] for c in block.get("approved_claims") or [] if isinstance(c, dict) and "id" in c]


def product_file(pid, product_name, url, image, extracted, brand=None, category=None, price_ils=None, price_tier=None, approved=True):
    """The products/<id>.yaml document (schema v1.2) from the inputs + the extraction. Every technical value carries
    source: product_page + evidence. Unknown fields stay null (validator flags); nothing is invented."""
    f = extracted["facts"]
    tech = {}
    for field, item in f.items():
        if field in PRODUCT_FIELDS:
            continue
        val = item["value"]
        if field == "finish" and isinstance(val, str):
            val = {"name": val}
        tech[field] = {"value": val, "source": "product_page", "evidence": item["evidence"]}
    brand_id = brand or (extracted["brand"] or {}).get("value")
    line_key = (extracted["line"] or {}).get("value")
    collection = (f.get("collection") or {}).get("value")
    doc = {
        "product": {"id": pid, "name": product_name, "brand": brand_id, "collection": collection,
                    "line": line_key.replace("_", " ").title() if line_key else None,
                    "category": category or (extracted["category"] or {}).get("value"),
                    "model_number": (f.get("model_number") or {}).get("value") or (f.get("sku") or {}).get("value"),
                    "designer": (f.get("designer") or {}).get("value")},
        "technical": tech,
        "design": {"signature_material": None, "claims_ref": claims_for(brand_id, line_key, collection) if brand_id else []},
        "commercial": {"price_ils": {"value": price_ils, "source": "mody_internal"} if price_ils is not None else None,
                       "price_tier": price_tier},
        "sources": {"product_page": url, "technical_sheet": None, "image": image, "image_approved": bool(approved),
                    **({"mody_internal": "MODY internal commercial data (intake)"} if price_ils is not None else {})},
        "extraction": {"title": extracted["title"], "category_evidence": (extracted["category"] or {}).get("evidence"),
                       "brand_evidence": (extracted["brand"] or {}).get("evidence"), "line_evidence": (extracted["line"] or {}).get("evidence"),
                       "unmapped": [f"{l}: {v}"[:120] for l, v in extracted["unmapped"][:20]]},
    }
    return doc
