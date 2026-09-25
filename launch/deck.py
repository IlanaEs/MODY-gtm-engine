"""Deck adapter: launch_package -> the deck content model (cover + 01..07) -> presentation.render on the official
MODY template. Every field is a canonical package value; this module only picks and shortens, it never reasons.
deck.md renders from exactly the same content (launch.render_md.deck_md)."""
from launch.package import val, getp
from presentation import render as R

DECK_FILE = "launch.pptx"
PRIVATE_IDS = ("B", "C")          # house audiences that are private customers; "A" = architects / designers


def content(pkg):
    f, s, msg, sales, story = pkg["product"]["facts"], pkg["strategy"], pkg["messaging"], pkg["sales"], pkg["story"]
    key_facts = [f"{r['label']}: {r['value']}" for r in pkg["product"]["specs"] if r.get("value")][:5]
    audiences = [{"id": a.get("id"), "segment": a["segment"], "need": a.get("need"), "decision_driver": a.get("decision_driver"),
                  "relevance": a.get("relevance")} for a in s["target_audiences"][:3]]
    sc = sales["seller_cheat_sheet"]
    return {
        "meta": {k: pkg["meta"].get(k) for k in ("product", "generated", "skill_version", "brand_versions", "validator_status", "publishable", "flags", "draft_banner")},
        "presentation": {
            "cover": {"product_name": val(f["name"]), "brand": val(f["brand"]), "collection": val(f.get("collection")),
                      "category": val(f["category_label"]), "launch_statement": val(msg["one_liner"]),
                      "hero_image": getp(pkg, "product.assets.hero_image.path") if getp(pkg, "product.assets.hero_image.approved") else None},
            "product_overview": {"product_name": val(f["name"]), "brand": val(f["brand"]), "collection": val(f.get("collection")),
                                 "model": val(f.get("model")), "category": val(f["category_label"]), "description": val(pkg["product"]["summary"]),
                                 "key_facts": key_facts, "price": f["price"].get("display"), "price_tier": val(f.get("price_tier")),
                                 "launch_status": val(f.get("launch_status")), "availability": val(f.get("availability"))},
            "positioning": {"positioning_statement": val(s["positioning"]), "value_proposition": val(s["value_proposition"]),
                            "customer_need": val(s["customer_need"]), "consumer_insight": val(s["consumer_insight"]),
                            "differentiator": " ".join(str(val(d)) for d in s["differentiators"][:1])},
            "target_audience": audiences,
            "brand_messaging": {"headline": val(msg["headline"]), "one_liner": val(msg["one_liner"]), "tone": list(msg.get("tone") or []),
                                "key_messages": [str(val(k)) for k in msg["key_messages"][:3]], "dont_say": list(sales.get("dont_say") or [])[:3]},
            "product_story": {"story": story.get("value"), "benefits": [{"fact": b["fact"], "benefit": b["title"].rstrip(".")} for b in pkg["benefits"][:3]]},
            "seller_cheat_sheet": {"positioning": sc["positioning"], "private_customer": sc["private_customer"],
                                   "professional_customer": sc["professional_customer"], "opening": sales["opening"]["value"],
                                   "remember": list(sales["key_talking_points"][:3]), "when_to_recommend": list(sales["when_to_recommend"][:5])},
            "launch_plan": [dict(st) for st in pkg["deck"]["launch_plan"]],
            "next_step": dict(pkg["deck"].get("next_step") or {}),
        },
        "notes": [pkg["deck"]["cover"].get("notes")] + [sl.get("notes") for sl in pkg["deck"]["slides"]],
        "provenance": {"derived_from": {}},
    }


def render(pkg, out_dir, product_path, template_path=None):
    """{"pptx": path | None, "warnings": [...], "errors": [...]} – never raises (presentation.render guarantees it)."""
    c = content(pkg)
    return R.render(c, out_dir, template_path=template_path, product_path=product_path, filename=DECK_FILE, notes=c["notes"])
