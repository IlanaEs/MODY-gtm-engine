"""Landing Page renderer: launch_package -> landing.html, a single standalone file on the fixed MODY product
page template (assets/templates/landing-page/mody-landing-page-template.html). The template owns the design; this module only maps validated
package fields into its slots and embeds the approved photos as base64. No reasoning, no invented specs: a slot
without a source is left out, and short counts are reported as warnings."""
import base64, html, mimetypes, os
from validate import ROOT, get
from launch.package import val, title, resolve_image, SCHEMA

TEMPLATE_PATH = os.environ.get("MODY_PRODUCT_PAGE_TEMPLATE") or os.path.join(ROOT, "assets", "templates", "landing-page", "mody-landing-page-template.html")
PAGE_FILE = "landing.html"
CTA_TEXT = "בדיקת זמינות ומחיר"
STAT_ORDER = ["flow_rate_lpm", "dimensions_mm", "thickness_mm", "format_cm", "installation_type", "finish", "material", "features", "colour", "application"]
STEPS = ["המוצר", "מיצוב", "פרטים", "נתונים טכניים", "יתרונות", "מתי להמליץ", "דף עזר"]
COUNTS = {"advantages": 3, "technical_data": 3, "when_to_recommend": 4, "remember": 3}


def _data_uri(path):
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as fh:
        return f"data:{mime};base64," + base64.b64encode(fh.read()).decode("ascii")


def _url(v):
    return v if isinstance(v, str) and v.startswith(("http://", "https://")) else None


def fields(pkg, product_path=None):
    """The section-3 content model, filled from the canonical package. Returns (fields, warnings)."""
    f, s, msg, sales, w = pkg["product"]["facts"], pkg["strategy"], pkg["messaging"], pkg["sales"], []
    src = (pkg.get("sources") or {}).get("product_sources") or {}
    crumbs = [val(f.get("category_label")), val(f.get("collection")), val(f.get("brand")), val(f.get("collection")), val(f.get("model"))]
    details = [(r["label"], r["value"]) for r in pkg["landing"]["product_details"] if r.get("value") and "[חסר:" not in str(r["value"])]
    if not 8 <= len(details) <= 14:
        w.append(f"product_details: {len(details)} rows (layout balanced for 8–14); unknown values are left out, never guessed")
    verified = {r["field"]: r for r in pkg["product"]["specs"] if r.get("value")}
    stats = [{"label": verified[k]["label"], "value": verified[k]["value"]} for k in STAT_ORDER if k in verified][:COUNTS["technical_data"]]
    if len(stats) < COUNTS["technical_data"]:
        w.append(f"technical_data: only {len(stats)} verified stat(s) (template expects 3)")
    adv = [{"title": b["title"].rstrip("."), "text": b["text"]} for b in pkg["benefits"][:COUNTS["advantages"]]]
    rec = list(sales.get("when_to_recommend") or [])[:COUNTS["when_to_recommend"]]
    if len(rec) < COUNTS["when_to_recommend"]:
        w.append(f"when_to_recommend: only {len(rec)} bullet(s) (template expects 4)")
    hero = pkg["product"]["assets"]["hero_image"]
    hero_path = resolve_image(hero.get("path"), product_path or ROOT) if hero.get("approved") else None
    alts = [resolve_image(p, product_path or ROOT) for p in (src.get("images") or []) if isinstance(p, str)]
    alts = [p for p in alts if os.path.exists(p)][:3]
    cta_link = _url(src.get("mody_listing"))
    if not cta_link:
        w.append("cta_link: no MODY product URL in sources (mody_listing); the CTA has no target")
    return {
        "breadcrumb": [c for c in crumbs if c], "brand": val(f["brand"]), "product_name": val(f["name"]), "model": val(f.get("model")) or "",
        # main headline + supporting copy: the canonical messaging (the deck cover / slide 04 say the same)
        "short_description": " ".join(x for x in (str(val(msg["headline"]) or "").rstrip(".") + "." if val(msg["headline"]) else "", str(val(msg["one_liner"]) or "")) if x),
        "cta_text": CTA_TEXT, "cta_link": cta_link or "#",
        "pillars": {"core_value": val(s["value_proposition"]), "positioning": val(s["positioning"]),
                    "target_audience": " · ".join(a["segment"] for a in s["target_audiences"][:2])},
        "product_details": details, "technical_data": stats,
        "manufacturer_link": _url(src.get("technical_sheet")) or _url(src.get("product_page")),
        "advantages": adv, "product_story": pkg["story"].get("value") or val(pkg["product"]["summary"]) or "",
        "when_to_recommend": rec,
        "sales_cheat_sheet": {"remember": list(sales.get("key_talking_points") or [])[:COUNTS["remember"]],
                              "private_clients": sales["seller_cheat_sheet"]["private_customer"],
                              "architects": sales["seller_cheat_sheet"]["professional_customer"],
                              "opening_line": sales["opening"]["value"]},
        "images": {"hero": hero_path, "alts": alts},
    }, w


def render_html(pkg, product_path=None, template_path=None):
    """Returns (html, warnings). Every {{slot}} of the template is filled; nothing else is touched."""
    e = html.escape
    d, w = fields(pkg, product_path)
    with open(template_path or TEMPLATE_PATH, encoding="utf-8") as fh:
        tpl = fh.read()
    hero_src = _data_uri(d["images"]["hero"]) if d["images"]["hero"] else ""
    if not hero_src:
        w.append("images.hero: no approved product photo embedded")
    thumbs = ([f'<button class="active" data-src="{hero_src}"><img src="{hero_src}" alt=""></button>'] if hero_src else [])
    thumbs += [f'<button data-src="{_data_uri(p)}"><img src="{_data_uri(p)}" alt=""></button>' for p in d["images"]["alts"]]
    thumbs += ['<button class="empty" disabled></button>'] * (4 - len(thumbs))
    slots = {
        "page_title": e(title(pkg)),
        "breadcrumb": "".join(f"<span>{e(str(c))}</span>" for c in d["breadcrumb"]),
        "brand": e(str(d["brand"])), "product_name": e(str(d["product_name"])), "model": e(str(d["model"])),
        "short_description": e(d["short_description"]), "cta_text": e(d["cta_text"]), "cta_link": e(d["cta_link"]),
        "core_value": e(str(d["pillars"]["core_value"])), "positioning": e(str(d["pillars"]["positioning"])),
        "target_audience": e(d["pillars"]["target_audience"]),
        "details_rows": "".join(f"<tr><td>{e(l)}</td><td>{e(str(v))}</td></tr>" for l, v in d["product_details"]),
        "tech_stats": "".join(f'<div><span class="v">{e(str(t["value"]))}</span><span class="l">{e(t["label"])}</span></div>' for t in d["technical_data"]),
        "manufacturer_link": f'<a class="mlink" href="{e(d["manufacturer_link"])}" target="_blank" rel="noopener">למפרט המלא של היצרן</a>' if d["manufacturer_link"] else "",
        "advantages": "".join(f'<article><span class="n">0{i}</span><h3>{e(a["title"])}</h3><p>{e(a["text"])}</p></article>' for i, a in enumerate(d["advantages"], 1)),
        "product_story": e(d["product_story"]),
        "recommend_items": "".join(f"<li>{e(x)}</li>" for x in d["when_to_recommend"]),
        "remember_items": "".join(f"<li>{e(x)}</li>" for x in d["sales_cheat_sheet"]["remember"]),
        "private_clients": e(str(d["sales_cheat_sheet"]["private_clients"])), "architects": e(str(d["sales_cheat_sheet"]["architects"])),
        "opening_line": e(str(d["sales_cheat_sheet"]["opening_line"])),
        "hero_src": hero_src, "hero_alt": e(title(pkg)), "thumbs": "".join(thumbs),
        "steps": "".join(f'<a href="#s0{i}" title="{e(n)}">0{i}</a>' for i, n in enumerate(STEPS, 1)),
    }
    out = tpl
    for k, v in slots.items():
        out = out.replace("{{" + k + "}}", v)
    if "{{" in out:
        raise ValueError("unfilled template slot: " + out[out.index("{{"):out.index("{{") + 30])
    return out, w


def render(pkg, out_dir, product_path=None, template_path=None):
    """{"html": path | None, "warnings": [...], "errors": [...]} – never raises."""
    try:
        page, w = render_html(pkg, product_path, template_path)
        path = os.path.join(out_dir, PAGE_FILE)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(page)
        return {"html": path, "warnings": w, "errors": []}
    except Exception as ex:
        return {"html": None, "warnings": [], "errors": [f"PRODUCT_PAGE_RENDER_FAILED: {type(ex).__name__}: {ex}"]}
