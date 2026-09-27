"""Render-time helpers for the deck: slot composition, JSON export and a markdown preview of the 8-slide content
model that launch.deck builds from the launch package. Facts and validation live in launch/ (package.py, qa.py)."""
import json, os, re
from launch.package import SCHEMA, resolve_image   # noqa: F401  (resolve_image re-exported for render.py)

HEB = re.compile("[א-ת]")
DONT_LINE = "השוואות, סופרלטיבים וטענות ללא מקור"              # house guardrail G4; the product's own list: sales guidance › מה לא להגיד
DO_LINE = "שלושת מסרי המפתח, כלשונם"                              # the key messages listed right above on slide 04
FLAG_RE = re.compile(r"\[חסר: (.+?) – לבדיקה\]")
FINAL_FLAG_TEXT = {"launch_plan.launch_date": "להגדרה", "launch_plan.channels": "להגדרה", "launch_plan.measure": "להגדרה",
                   "sources.image": "תמונת מוצר מאושרת", "sources.technical_sheet": "דף טכני של היצרן", "price_tier": "דרגת מחיר",
                   "commercial.price_ils": "מחיר", "product.model_number": 'מק"ט'}


def flag_label(flag):
    """A validator flag as an internal open item, for the final deck: '[חסר: technical.flow_rate_lpm – לבדיקה]' -> 'ספיקה (ל/דק)'.
    The field is named by its house label; nothing about its value is stated."""
    m = FLAG_RE.fullmatch(str(flag).strip())
    field = m.group(1) if m else str(flag)
    return FINAL_FLAG_TEXT.get(field) or SCHEMA["field_labels"].get(field.split(".")[-1]) or SCHEMA["detail_labels"].get(field.split(".")[-1]) or field.split(".")[-1]


def finalize(text):
    """Final-deck wording for a string that may carry raw flags: each flag becomes its label, marked as open."""
    if text is None or not FLAG_RE.search(str(text)):
        return text
    flags = FLAG_RE.findall(str(text))
    if re.fullmatch(r"\s*(\[חסר: .+? – לבדיקה\]\s*(·\s*)?)+\s*", str(text)):        # a pure list of flags
        return " · ".join(flag_label(f"[חסר: {f} – לבדיקה]") for f in flags) + " – להשלמה"
    return FLAG_RE.sub(lambda m: (FINAL_FLAG_TEXT.get(m.group(1)) if m.group(1) in FINAL_FLAG_TEXT and m.group(1).startswith("launch_plan")
                                  else flag_label(m.group(0)) + " – להשלמה"), str(text))


def _first_sentence(s):
    parts = re.split(r"(?<=[.!?])\s+", str(s or "").strip())
    return parts[0] if parts and parts[0] else str(s or "")


def _titles(s, n=None):
    """'תועלת א. תועלת ב.' -> 'תועלת א · תועלת ב' (the seller's emphasis line, without the sentence rhythm); n = first n."""
    parts = [x.strip().rstrip(".") for x in re.split(r"(?<=\.)\s+", str(s or "").strip()) if x.strip(" .")]
    return " · ".join(parts[:n] if n else parts)


def _short_fact(fact, max_chars=60):
    """A list fact (items joined by ' · ') longer than max_chars keeps its first two items + 'ועוד'; the full list is on
    slide 01 and in the sales guidance. A scalar fact is never cut."""
    text = str(fact or "")
    if len(text) <= max_chars or " · " not in text:
        return text
    return " · ".join(text.split(" · ")[:2]) + " ועוד"


def _last_sentence(s):
    parts = [x for x in re.split(r"(?<=[.!?])\s+", str(s or "").strip()) if x]
    return parts[-1] if parts else ""


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


def compose_slots(content, final=False):
    """Text composed deterministically for slots that hold more than one field (template_map 'compose:' sources).
    Returns {name: str | list | None}. Items may be (bold, rest) pairs. Same output feeds launch.pptx and deck.md.
    final=True (the .pptx): validator flags read as open items by their house label instead of the raw QA flag syntax;
    deck.md keeps the raw flags, which the QA rules match verbatim."""
    pres, meta = content.get("presentation") or {}, content.get("meta") or {}
    cv, ov, po = pres.get("cover") or {}, pres.get("product_overview") or {}, pres.get("positioning") or {}
    bm, ps, sc = pres.get("brand_messaging") or {}, pres.get("product_story") or {}, pres.get("seller_cheat_sheet") or {}
    labels = SCHEMA["detail_labels"]
    flags = meta.get("flags") or []
    fin = finalize if final else (lambda t: t)
    flag_for = lambda field: fin(next((f for f in flags if f"[חסר: {field} " in f), None))
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
        # DO / DON'T: one line, as the template frames it; the product-specific forbidden phrases live in the sales guidance
        "do_dont": [("לומר: ", f"{DO_LINE}  |  לא לומר: {DONT_LINE}")],
        "fact_benefit_lines": [(_short_fact(b.get("fact")) + " ", "← " + str(b.get("benefit"))) for b in ps.get("benefits") or [] if isinstance(b, dict)],
        "benefits_numbered": [f"{i}. {b.get('benefit')}" for i, b in enumerate(ps.get("benefits") or [], 1) if isinstance(b, dict)],
        "audience_private": [l for a in privates for l in column(a)],
        "audience_architect": column(architect),
        # seller columns: the opener's first sentence, the benefit titles, the first sentence for professionals (the full
        # sentences are in the sales guidance); לזכור = the 3 talking points, verbatim
        "audience_sales": [("למי להמליץ: ", when[0]) if when else "—", ("איך לפתוח: ", _first_sentence(sc.get("opening")) or "—"),
                           ("מה להדגיש: ", _titles(sc.get("private_customer"), 1) or "—")],
        "cheat_how": [("פתיח: ", _first_sentence(sc.get("opening")) or "—"), ("ללקוח הפרטי: ", _titles(sc.get("private_customer"), 1) or "—"),
                      ("לאדריכלים: ", _last_sentence(sc.get("professional_customer")) or "—")],
        "cheat_remember": [f'"{t}"' for t in (sc.get("remember") or [])],
        "versions_line": " · ".join(x for x in (
            "house " + os.path.basename(str((meta.get("brand_versions") or {}).get("house", "")))[:-5] if (meta.get("brand_versions") or {}).get("house") else None,
            os.path.basename(str((meta.get("brand_versions") or {}).get("manufacturer", "")))[:-5] if (meta.get("brand_versions") or {}).get("manufacturer") else None,
            f"skill {meta.get('skill_version')}" if meta.get("skill_version") else None,
            f"נוצר {meta.get('generated')}" if meta.get("generated") else None) if x),
    }
    out.update({f"launch_text.{i}": None for i in range(4)})
    for i, st in enumerate(pres.get("launch_plan") or []):
        if isinstance(st, dict):
            lines = [fin(str(st["action"]))] if st.get("action") else []
            if st.get("status"):
                lines.append(("סטטוס: ", fin(str(st["status"]))))
            if st.get("owner"):
                lines.append(("אחראי: ", str(st["owner"])))
            out[f"launch_text.{i}"] = lines
    ns = pres.get("next_step") or {}
    out["next_step"] = "  |  ".join(f"{k}: {fin(dash(ns.get(key)))}" for k, key in (("אחראי", "owner"), ("סטטוס", "status"), ("תאריך השקה", "launch_date"), ("החלטות פתוחות", "open_decisions")))
    return out


def slot_value(content, source, composed=None):
    if source.startswith("compose:"):
        return (composed if composed is not None else compose_slots(content)).get(source[8:])
    return _get(content, source)


# ---------------------------------------------------------------------------------------------------- export
def to_json(content):
    return json.dumps(content, ensure_ascii=False, indent=2)


