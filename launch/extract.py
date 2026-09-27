"""Supplier page extraction: URL -> visible product facts -> products/<id>.yaml (schema v1.2), every value traceable
to the page (source key `product_page` + the evidence line it came from). Rules only, no model: a fact the page does
not state is not written. Unknown category / brand are reported, never guessed.

Fetch: the static HTML first. When it yields no facts (a JavaScript-rendered page serves an empty app shell) and the
URL is remote, the page is rendered in a headless browser (Playwright driving the installed Chrome / Edge / Chromium)
and the rendered DOM goes through the same rules. The result records which fetch produced the facts (`fetch`:
static | browser) and keeps the HTML so the product file can point at a snapshot of what was read."""
import html as htmlmod, io, os, re, ssl, subprocess, sys, urllib.parse, urllib.request, glob, yaml
from datetime import date
from html.parser import HTMLParser
from validate import ROOT

USER_AGENT = "MODY-launch/1.0 (+product intake)"
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 MODY-launch/1.0"
# browsers to try, in order: MODY_BROWSER_CHANNEL, the installed Chrome, Edge, then Playwright's own Chromium (None)
BROWSER_CHANNELS = ([os.environ["MODY_BROWSER_CHANNEL"]] if os.environ.get("MODY_BROWSER_CHANNEL") else []) + ["chrome", "msedge", None]
RENDER_TIMEOUT_MS = int(os.environ.get("MODY_RENDER_TIMEOUT_MS", "60000"))
# label -> axis letter for a page that states each dimension on its own row (Height / Width / Depth …)
DIMENSION_PARTS = {"height": "H", "width": "W", "depth": "D", "length": "L", "diameter": "Ø", "גובה": "H", "רוחב": "W", "עומק": "D"}
IMAGE_SKIP = re.compile(r"(logo|icon|favicon|sprite|flag|badge|payment|pixel|\.svg(\?|$)|^data:)", re.I)
FILE_REF = re.compile(r"\b(download|pdf|dwg|dxf|zip|bim)\b|\(\s*pdf", re.I)      # a link to a file is never a fact value
TECH_SHEET_CUES = ("technical sheet", "technical data sheet", "data sheet", "datasheet", "spec sheet", "specification sheet",
                   "scheda tecnica", "דף טכני", "מפרט טכני")
HERO_MIN_PX = 400
# label synonyms -> product schema field (technical.* unless noted)
LABELS = {
    "material": ["material", "materials", "body material", "חומר"],
    "finish": ["finish", "finishes", "surface finish", "colour finish", "color finish", "גימור"],
    "dimensions_mm": ["dimensions", "dimension", "size", "measurements", "overall dimensions", "מידות"],
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
        self.text, self.rows, self.items, self.images, self.image_alts = [], [], [], [], {}
        self.h1, self._in_h1, self._h1 = "", False, []
        self.links, self._in_a, self._a, self._a_href, self._last_text = [], False, [], None, ""
        self.description, self._after_h1, self._in_p, self._p = "", False, False, []
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
            if a.get("alt"):
                self.image_alts[a["src"]] = a["alt"]
        elif tag == "a" and a.get("href"):
            self._in_a, self._a, self._a_href = True, [], a["href"]
        elif tag == "h1" and not self.h1:
            self._in_h1, self._h1 = True, []
        elif tag == "p" and self._after_h1 and not self.description:
            self._in_p, self._p = True, []
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
        elif tag == "a" and self._in_a:
            self._in_a = False
            self.links.append({"href": self._a_href, "text": " ".join("".join(self._a).split()), "before": self._last_text})
        elif tag == "h1" and self._in_h1:
            self._in_h1 = False
            self.h1 = " ".join("".join(self._h1).split())
            self._after_h1 = bool(self.h1)
        elif tag == "p" and self._in_p:
            self._in_p = False
            t = " ".join("".join(self._p).split())
            if t and not self.description:
                self.description = t
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
        if self._in_h1:
            self._h1.append(data)
        if self._in_p:
            self._p.append(data)
        if self._in_a:
            self._a.append(data)
        elif data.strip():
            self._last_text = " ".join(data.split())
        self.text.append(data)


def fetch(url, timeout=20):
    """Returns the page HTML. http(s) via urllib; a local path or file:// URL is read from disk (fixtures, offline)."""
    if url.startswith("file://"):
        url = urllib.request.url2pathname(urllib.parse.urlparse(url).path)
    if os.path.exists(url):
        with open(url, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    raw = fetch_bytes(url, timeout=timeout)[0]
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _ssl_context():
    """The system trust store, or certifi's bundle when the interpreter ships without CA certificates (python.org macOS builds)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch_bytes(url, timeout=20):
    """(bytes, content_type) for an http(s) URL, with the intake user agent."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en,he;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
        return resp.read(), resp.headers.get("Content-Type", "")


def render_page(url, timeout_ms=RENDER_TIMEOUT_MS):
    """The DOM of `url` after the page's JavaScript ran, as HTML: Playwright driving the installed Chrome / Edge, else its own
    Chromium (`playwright install chromium`). Returns (html, renderer). Raises RuntimeError with the reason when no
    browser is available, so the caller can report *why* the fallback was not possible."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("playwright is not installed (pip install playwright; it drives the installed Chrome, or run `playwright install chromium`)")
    reasons = []
    with sync_playwright() as p:
        for channel in BROWSER_CHANNELS:
            try:
                browser = p.chromium.launch(channel=channel, headless=True) if channel else p.chromium.launch(headless=True)
            except Exception as e:                       # that browser is not installed: try the next one
                reasons.append(f"{channel or 'chromium'}: {str(e).splitlines()[0][:120]}")
                continue
            try:
                page = browser.new_page(user_agent=BROWSER_UA, locale="en-US")
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                page.wait_for_timeout(1500)              # late template bindings after the last network response
                return page.content(), f"playwright:{channel or 'chromium'}"
            finally:
                browser.close()
    raise RuntimeError("no browser could be launched: " + "; ".join(reasons))


def parse(html):
    p = _Parser()
    p.feed(html)
    text = re.sub(r"[ \t]+", " ", htmlmod.unescape("".join(p.text)))
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return {"title": " ".join(p.title.split()), "lines": lines, "rows": p.rows, "items": p.items, "images": p.images,
            "image_alts": p.image_alts, "h1": p.h1, "description": htmlmod.unescape(p.description), "links": p.links}


def _field_for(label):
    key = re.sub(r"[\s:：]+$", "", label.strip().lower())
    for field, names in LABELS.items():
        if key in names:
            return field
    return None


def _split_list(value):
    parts = [x.strip(" .") for x in re.split(r"\s*(?:[•·|;\n]|,\s)\s*", value) if x.strip(" .")]
    return parts if len(parts) > 1 else [value.strip()]


def _is_label(text, pairable=False):
    """A known spec label. pairable: usable as the label of a sibling-element pair (list fields are not: a 'Features'
    heading is followed by its items, not by one value)."""
    key = re.sub(r"[\s:：]+$", "", text.strip().lower())
    field = _field_for(text)
    if pairable and field in LIST_FIELDS:
        return False
    return bool(field) or key in DIMENSION_PARTS


def _adjacent_pairs(lines):
    """A page that renders each spec as two sibling elements (<div>Height</div><div>275 mm</div>) yields a label line
    followed by its value line. Only lines that ARE a known label pair up; the value must be short and not a label."""
    out = []
    for i in range(len(lines) - 1):
        label, value = lines[i], lines[i + 1]
        if len(label) <= 40 and _is_label(label, pairable=True) and not _is_label(value) and 0 < len(value) < 120:
            out.append((label, value))
    return out


def _nice_case(name):
    """'warm bronze br. pvd' / 'WARM BRONZE BR. PVD' -> 'Warm Bronze Br. PVD': display form only (the evidence keeps the
    page's own text). Mixed-case words are left as written; a 3-letter word with no vowel is an acronym (PVD)."""
    out = []
    for w in name.split():
        if w.lower() != w and w.upper() != w:
            out.append(w); continue
        core = w.strip(".,")
        out.append(w.upper() if len(core) <= 3 and core.isalpha() and not re.search(r"[aeiou]", core, re.I) and not w.endswith(".") else w.capitalize())
    return " ".join(out)


def _finish_from_url_code(url, page):
    """Finish stated as '<code> - <name>' next to the finish selector, where <code> is also a query value of the product
    URL (…?finId=726). Nothing is read unless both agree."""
    codes = [v for _, v in urllib.parse.parse_qsl(urllib.parse.urlparse(url).query) if re.fullmatch(r"[A-Za-z0-9]{2,8}", v)]
    for code in codes:
        for l in page["lines"]:
            m = re.match(rf"^{re.escape(code)}\s*[-–:]\s*([^|]{{2,60}})$", l)
            if m:
                return {"value": {"code": code, "name": _nice_case(m.group(1).strip())}, "evidence": f"Finish selector: {l}"[:200]}
        for src, alt in page["image_alts"].items():
            m = re.match(rf"^(.{{2,60}}?)\s*[-–]\s*{re.escape(code)}$", alt.strip())
            if m:
                return {"value": {"code": code, "name": _nice_case(m.group(1).strip())}, "evidence": f"Finish image alt: {alt}"[:200]}
    return None


def _compose_dimensions(parts):
    """Height / Width / Depth rows -> one dimensions value, in the page's own units; evidence quotes every row."""
    order = ["H", "W", "D", "L", "Ø"]
    got = [(axis, v, ev) for axis in order for a, v, ev in parts if a == axis]
    if not got:
        return None
    return {"value": " × ".join(f"{axis} {v}" for axis, v, _ in got), "evidence": " · ".join(ev for _, _, ev in got)[:200]}


def _technical_sheet(url, page):
    """The supplier's technical sheet when the page links a PDF under a 'Technical Sheet' cue (the anchor's own text,
    the visible text just before it, or the file path). {url, evidence} or None."""
    for link in page["links"]:
        href = link["href"] or ""
        if not re.search(r"\.pdf(\?|$)", href, re.I):
            continue
        ctx = " ".join(x for x in (link["text"], link["before"]) if x).lower()
        if any(c in ctx for c in TECH_SHEET_CUES) or re.search(r"tech(nical)?[-_]?(sheet|data)|datasheet", href, re.I):
            return {"url": urllib.parse.urljoin(url, href), "evidence": f"{link['before']} → {link['text']}"[:200].strip(" →")}
    return None


def _features_from_description(description, category_cue):
    """The page's own product description split at its punctuation: every fragment is quoted, none is written.
    The category phrase itself ('Basin mixer') is not a feature."""
    frags = [f.strip(" ,;.") for f in re.split(r"[.;,]\s+|\.$", description) if f.strip(" ,;.")]
    frags = [f[0].upper() + f[1:] for f in frags if 2 <= len(f.split()) <= 8 and f.lower() != (category_cue or "").lower()]
    return frags[:8]


def extract(url, product_name, html=None, brands=None, render="auto", renderer=None):
    """{"facts": {field: {value, evidence}}, "category": {value, evidence}|None, "brand": {value, evidence}|None,
        "line": {value, evidence}|None, "collection_line", "title", "h1", "description", "images", "hero_candidates",
        "unmapped": [(label, value)], "fetch": static|browser, "renderer", "render_error", "html"} – nothing inferred.
    render: "auto" renders in a browser only when the static HTML gives no facts and the URL is remote; "never" / "always"."""
    given = html is not None
    html = html if given else fetch(url)
    result = _extract_html(url, product_name, html, brands)
    result.update({"fetch": "static", "renderer": None, "render_error": None})
    remote = url.startswith(("http://", "https://"))
    wants = render == "always" or (render == "auto" and not result["facts"] and remote and not given)
    if wants:
        try:
            rendered, name = (renderer or render_page)(url)
            r2 = _extract_html(url, product_name, rendered, brands)
            if len(r2["facts"]) > len(result["facts"]) or (r2["category"] and not result["category"]):
                r2.update({"fetch": "browser", "renderer": name, "render_error": None})
                result = r2
            else:
                result["render_error"] = f"rendered with {name}: still no facts on the page"
        except Exception as e:                                # the fallback itself is optional: report, never fail
            result["render_error"] = f"{type(e).__name__}: {e}"
    return result


def _extract_html(url, product_name, html, brands=None):
    page = parse(html)
    facts, unmapped = {}, []
    pairs = list(page["rows"])
    for l in page["lines"]:                                  # "Label: value" lines outside tables
        m = re.match(r"^([A-Za-zא-ת][\w\s\"/()-]{1,40}?)\s*[:：]\s*(.+)$", l)
        if m and len(m.group(2)) < 200:
            pairs.append((m.group(1), m.group(2)))
    pairs += _adjacent_pairs(page["lines"])                  # sibling-element rows (rendered SPAs)
    dims = []
    for label, value in pairs:
        if FILE_REF.search(value):                           # "Warranty" -> "Download (pdf - 0.26 MB)" is a link, not a fact
            continue
        axis = DIMENSION_PARTS.get(re.sub(r"[\s:：]+$", "", label.strip().lower()))
        if axis and value.strip():
            if axis not in [a for a, _, _ in dims]:
                dims.append((axis, value.strip(), f"{label}: {value}"))
            continue
        field = _field_for(label)
        if not field or not value.strip():
            if not field and label.strip() and value.strip() and not value.strip().startswith(label.strip()):
                unmapped.append((label, value))              # a real label/value the schema has no field for (provenance)
            continue
        if field in facts:
            continue                                         # first statement wins; nothing merged from elsewhere
        val = _split_list(value) if field in LIST_FIELDS else value.strip()
        facts[field] = {"value": val, "evidence": f"{label}: {value}"[:200]}
    if "dimensions_mm" not in facts and dims:
        facts["dimensions_mm"] = _compose_dimensions(dims)
    if "finish" not in facts:
        fin = _finish_from_url_code(url, page)
        if fin:
            facts["finish"] = fin
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
    if "features" not in facts and page["description"]:
        frags = _features_from_description(page["description"], next((c for _, cues in CATEGORY_CUES for c in cues if c in page["description"].lower()), None))
        if frags:
            facts["features"] = {"value": frags, "evidence": f"Description: {page['description']}"[:200]}
    # the model number as the page's own <h1> when it is a bare code and no labelled row gave one
    if "model_number" not in facts and "sku" not in facts and page["h1"]:
        h1 = page["h1"].strip()
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9./-]{2,14}", h1) and re.search(r"\d", h1):
            facts["model_number"] = {"value": h1, "evidence": f"h1: {h1}"}
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
    # the collection: a labelled row, else one of the manufacturer's own collection names stated on the page
    collection_line = None
    if brand and "collection" not in facts:
        for line_key, names in manufacturer_collections(brand["value"]).items():
            for name in names:
                pat = re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])", re.I)
                src = next((l for l in [page["title"], page["h1"]] + page["lines"] if l and pat.search(l)), None)
                if src:
                    facts["collection"] = {"value": pat.search(src).group(0), "evidence": src[:160]}
                    collection_line = line_key
                    break
            if "collection" in facts:
                break
        if not line and collection_line and collection_line != "default":
            line = {"value": collection_line, "evidence": f"collection {facts['collection']['value']} belongs to line {collection_line} (brand file)"}
    images = [urllib.parse.urljoin(url, i) for i in page["images"] if i and not IMAGE_SKIP.search(i)]
    return {"facts": facts, "category": category, "brand": brand, "line": line, "title": page["title"], "h1": page["h1"],
            "description": page["description"], "images": images[:10], "hero_candidates": images[:6],
            "technical_sheet": _technical_sheet(url, page), "unmapped": unmapped[:40], "html": html}


def manufacturer_collections(brand):
    """{line_key: [collection names]} from the manufacturer file: the only collection names a page can be matched to."""
    files = sorted(glob.glob(os.path.join(ROOT, "brand", f"{brand}.v*.yaml")))
    if not files:
        return {}
    with open(files[-1], encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    out = {}
    for key, line in (cfg.get("lines") or {}).items():
        names = [str(n) for n in ((line or {}).get("collections") or {}).keys()]
        if names:
            out[key] = names
    return out


def download_hero(candidates, dest_dir, basename, fetch=None, min_px=HERO_MIN_PX):
    """The first candidate image that is a real product photo (>= min_px on its short side), saved under dest_dir as
    PNG / JPG (a WebP is re-encoded, pixels unchanged). Returns {path, source_url, format, note} or None. Never
    invents an image: with no usable candidate the hero stays missing."""
    from PIL import Image
    fetch = fetch or fetch_bytes
    os.makedirs(dest_dir, exist_ok=True)
    tried = []
    for src in candidates:
        try:
            raw, _ = fetch(src)
            im = Image.open(io.BytesIO(raw)); im.load()
        except Exception as e:
            tried.append(f"{src}: {type(e).__name__}"); continue
        if min(im.size) < min_px:
            tried.append(f"{src}: {im.size[0]}x{im.size[1]} too small"); continue
        fmt = (im.format or "").lower()
        if fmt in ("png", "jpeg"):
            ext = "png" if fmt == "png" else "jpg"
            path = os.path.join(dest_dir, f"{basename}.{ext}")
            with open(path, "wb") as fh:
                fh.write(raw)
            note = f"downloaded from the product page ({fmt})"
        else:
            ext = "png" if im.mode in ("RGBA", "LA", "P") else "jpg"
            path = os.path.join(dest_dir, f"{basename}.{ext}")
            (im.convert("RGBA") if ext == "png" else im.convert("RGB")).save(path)
            note = f"downloaded from the product page ({fmt or 'unknown'}), re-encoded as {ext}"
        inside = os.path.abspath(path).startswith(os.path.abspath(ROOT) + os.sep)
        return {"path": os.path.relpath(path, ROOT) if inside else os.path.abspath(path), "source_url": src, "format": ext, "note": note, "size": list(im.size)}
    return None


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


def product_file(pid, product_name, url, image, extracted, brand=None, category=None, price_ils=None, price_tier=None, approved=True,
                 image_source=None, snapshot=None):
    """The products/<id>.yaml document (schema v1.2) from the inputs + the extraction. Every technical value carries
    source: product_page + evidence. Unknown fields stay null (validator flags); nothing is invented.
    image_source: the page image URL when the hero was downloaded from the page (sources.image_source, provenance);
    snapshot: path of the saved HTML the facts were read from (sources.product_page_snapshot)."""
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
        "sources": {"product_page": url, "technical_sheet": (extracted.get("technical_sheet") or {}).get("url"),
                    "image": image, "image_approved": bool(approved),
                    **({"image_source": image_source} if image_source else {}),
                    **({"product_page_snapshot": snapshot} if snapshot else {}),
                    **({"mody_internal": "MODY internal commercial data (intake)"} if price_ils is not None else {})},
        "extraction": {"fetch": extracted.get("fetch", "static"), "renderer": extracted.get("renderer"), "fetched_on": date.today().isoformat(),
                       "title": extracted["title"], "h1": extracted.get("h1") or None, "description": extracted.get("description") or None,
                       "category_evidence": (extracted["category"] or {}).get("evidence"),
                       "brand_evidence": (extracted["brand"] or {}).get("evidence"), "line_evidence": (extracted["line"] or {}).get("evidence"),
                       "collection_evidence": (f.get("collection") or {}).get("evidence"),
                       "technical_sheet_evidence": (extracted.get("technical_sheet") or {}).get("evidence"),
                       "unmapped": [f"{l}: {v}"[:120] for l, v in extracted["unmapped"][:20]],
                       **({"render_error": extracted["render_error"]} if extracted.get("render_error") else {})},
    }
    return doc
