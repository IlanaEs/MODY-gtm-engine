"""Render-time helpers for the deck: slot composition, JSON export and a markdown preview of the 8-slide content
model that launch.deck builds from the launch package. Facts and validation live in launch/ (package.py, qa.py)."""
import json, os, re
from launch.package import SCHEMA, resolve_image   # noqa: F401  (resolve_image re-exported for render.py)

HEB = re.compile("[א-ת]")
DONT_LINE = "טענות ללא מקור, השוואה למתחרים והבטחות שאי אפשר לאמת (הרשימה המלאה ב-sales.md)"   # house guardrail G4


# ---------------------------------------------------------------------------------------------------- composition
def _get(d, path):
    """Dotted path with list indexes: 'target_audience.1.need'. None when anything is missing."""
    for k in path.split("."):
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


def compose_slots(content):
    """Text composed deterministically for slots that hold more than one field (template_map 'compose:' sources).
    Returns {name: str | list | None}. Items may be (bold, rest) pairs. Same output feeds launch.pptx and deck.md."""
    pres, meta = content.get("presentation") or {}, content.get("meta") or {}
    cv, ov, po = pres.get("cover") or {}, pres.get("product_overview") or {}, pres.get("positioning") or {}
    bm, ps, sc = pres.get("brand_messaging") or {}, pres.get("product_story") or {}, pres.get("seller_cheat_sheet") or {}
    labels = SCHEMA["detail_labels"]
    flags = meta.get("flags") or []
    flag_for = lambda field: next((f for f in flags if f"[חסר: {field} " in f), None)
    dash = lambda v: v if v not in (None, "") else "—"
    brand_col = " / ".join(x for x in (ov.get("brand"), ov.get("collection")) if x)
    overview_lines = [("מוצר: ", str(dash(ov.get("product_name")))), ("מותג / קולקציה: ", str(dash(brand_col))),
                      ("קטגוריה: ", str(dash(ov.get("category")))), ('מק"ט: ', str(ov.get("model") or flag_for("product.model_number") or "—"))]
    key_facts = list(ov.get("key_facts") or [])
    if ov.get("price") or flag_for("commercial.price_ils"):
        key_facts.append(f"{labels['price']}: {ov.get('price') or flag_for('commercial.price_ils')}")
    if ov.get("price_tier"):
        key_facts.append(f"{labels['price_tier']}: {ov['price_tier']}")
    auds = pres.get("target_audience") or []
    def column(a):
        if not a:
            return []
        lines = [str(a["segment"])]
        if a.get("need"):
            lines.append(("הצורך: ", str(a["need"])))
        if a.get("decision_driver"):
            lines.append(("מה מכריע: ", str(a["decision_driver"])))
        if a.get("relevance"):
            lines.append(str(a["relevance"]))
        return lines
    privates = [a for a in auds if a.get("id") in ("B", "C")]           # every private-type house audience (C, B)
    architect = next((a for a in auds if a.get("id") == "A"), None)
    when = list(sc.get("when_to_recommend") or [])
    out = {
        "cover_title": " / ".join(x for x in (" ".join(y for y in (cv.get("brand"), cv.get("product_name")) if y), cv.get("category")) if x),
        "brand_line": " · ".join(x for x in (cv.get("brand"), cv.get("collection")) if x),
        "overview_lines": overview_lines,
        "key_facts": key_facts,
        "tone_line": " · ".join(bm.get("tone") or []) or None,
        "key_messages_numbered": [f"{i}. {m}" for i, m in enumerate(bm.get("key_messages") or [], 1)],
        # DON'T: the house guardrail (G4); the product-specific forbidden phrases live only in sales.md › מה לא להגיד
        "do_dont": [("לומר: ", str(m)) for m in (bm.get("key_messages") or [])[:1]] + [("לא לומר: ", DONT_LINE)],
        "fact_benefit_lines": [(str(b.get("fact")) + " ", "← " + str(b.get("benefit"))) for b in ps.get("benefits") or [] if isinstance(b, dict)],
        "benefits_numbered": [f"{i}. {b.get('benefit')}" for i, b in enumerate(ps.get("benefits") or [], 1) if isinstance(b, dict)],
        "audience_private": [l for a in privates for l in column(a)],
        "audience_architect": column(architect),
        "audience_sales": [("למי להמליץ: ", when[0]) if when else "—", ("איך לפתוח: ", str(sc.get("opening") or "—")), ("מה להדגיש: ", str(sc.get("private_customer") or "—"))],
        "cheat_how": [("פתיח: ", str(sc.get("opening") or "—")), ("ללקוח הפרטי: ", str(sc.get("private_customer") or "—")), ("לאדריכלים ומעצבים: ", str(sc.get("professional_customer") or "—"))],
        "cheat_remember": [f'"{t}"' for t in (sc.get("remember") or [])] + [("לא להמציא: ", DONT_LINE)],
        "versions_line": " · ".join(x for x in (
            "house " + os.path.basename(str((meta.get("brand_versions") or {}).get("house", "")))[:-5] if (meta.get("brand_versions") or {}).get("house") else None,
            os.path.basename(str((meta.get("brand_versions") or {}).get("manufacturer", "")))[:-5] if (meta.get("brand_versions") or {}).get("manufacturer") else None,
            f"skill {meta.get('skill_version')}" if meta.get("skill_version") else None,
            f"נוצר {meta.get('generated')}" if meta.get("generated") else None) if x),
    }
    out.update({f"launch_text.{i}": None for i in range(4)})
    for i, st in enumerate(pres.get("launch_plan") or []):
        if isinstance(st, dict):
            lines = [str(st["action"])] if st.get("action") else []
            if st.get("status"):
                lines.append(("סטטוס: ", str(st["status"])))
            if st.get("owner"):
                lines.append(("אחראי: ", str(st["owner"])))
            out[f"launch_text.{i}"] = lines
    ns = pres.get("next_step") or {}
    out["next_step"] = "  |  ".join(f"{k}: {dash(ns.get(key))}" for k, key in (("אחראי", "owner"), ("סטטוס", "status"), ("תאריך השקה", "launch_date"), ("החלטות פתוחות", "open_decisions")))
    return out


def slot_value(content, source, composed=None):
    if source.startswith("compose:"):
        return (composed if composed is not None else compose_slots(content)).get(source[8:])
    return _get(content, source)


# ---------------------------------------------------------------------------------------------------- export
def to_json(content):
    return json.dumps(content, ensure_ascii=False, indent=2)


