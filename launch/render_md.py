"""Markdown renderers: launch_package -> landing.md, deck.md (the 8-slide GTM deck as text), sales.md, provenance.yaml.
These are the SKILL 6a / 6b / 6c / 8 formats qa.py validates (32 checks). No reasoning here: every sentence
comes from the package; this module only decides where it goes."""
import datetime, os, yaml
from launch.package import val, title, ref_source, SCHEMA

IMG_FLAG = "[חסר: sources.image – לבדיקה]"
ROLES = SCHEMA["deck_roles"]                      # the 7 GTM slide names, shared with qa.py DECK_ROLES


def _footer(pkg):
    m = pkg["meta"]
    stems = {k: os.path.basename(f)[:-len(".yaml")] for k, f in m["brand_versions"].items()}
    flags = " · ".join(m["flags"]) if m["flags"] else "אין"
    return ("---\n<!-- QA -->\n**דגלים פתוחים:** " + flags +
            f"\n**גרסאות:** house {stems['house']} · {stems['manufacturer']} · skill {m['skill_version']}\n")


def _banner(pkg):
    return f"> {pkg['meta']['draft_banner']}\n\n" if pkg["meta"].get("draft_banner") else ""


def image_line(pkg, alt):
    hero = pkg["product"]["assets"]["hero_image"]
    return f"![{alt}]({hero['path']})" if hero.get("path") else IMG_FLAG


def landing_md(pkg):
    L = [f"# {val(pkg['messaging']['headline'])}", "", str(val(pkg["messaging"]["one_liner"])), "", image_line(pkg, title(pkg)), ""]
    story = pkg["story"].get("value")
    for section in pkg["landing"]["sections"]:
        if section == "story" and story:
            L += ["## הסיפור", story, ""]
        elif section == "benefits":
            L += ["## למה דווקא הוא"] + [f"- **{b['title']}** {b['text']}" for b in pkg["benefits"]] + [""]
        elif section == "details":
            L += ["## פרטים", "| | |", "|---|---|"] + [f"| {r['label']} | {r['value']} |" for r in pkg["landing"]["product_details"]] + [""]
        elif section == "mody":
            L += ["## ב-MODY", str(pkg["landing"]["mody_section"]["value"]), ""]
    return _banner(pkg) + "\n".join(L) + "\n" + _footer(pkg)


def deck_md(pkg):
    """deck.md = the SAME deck as launch.pptx (cover + 01..07 on the official template), rendered from the same
    adapter output (launch.deck.content + presentation.content.compose_slots), so the two can never diverge."""
    from launch.deck import content as deck_content
    from presentation.content import compose_slots
    c = deck_content(pkg)
    pres, notes = c["presentation"], c["notes"]
    comp = compose_slots(c)
    j = lambda item: "".join(item) if isinstance(item, (tuple, list)) else str(item)
    b = lambda items: [f"- {j(x)}" for x in items or []]
    cv, po, bm, ps, sc = (pres[k] for k in ("cover", "positioning", "brand_messaging", "product_story", "seller_cheat_sheet"))
    slides = [
        [f"# {comp['cover_title']}", str(cv["launch_statement"]), comp["brand_line"], image_line(pkg, "")],
        [f"# 01 {ROLES[0]}"] + [j(x) for x in comp["overview_lines"]] + b(comp["key_facts"]) + [str(bm["one_liner"])],
        [f"# 02 {ROLES[1]}", str(po["positioning_statement"]), f"- **הצעת ערך**: {po['value_proposition']}", f"- **בידול**: {po['differentiator']}"],
        [f"# 03 {ROLES[2]}", "**לקוח פרטי**"] + b(comp["audience_private"]) + ["**אדריכל / מעצב**"] + b(comp["audience_architect"]) + ["**מכירות / אולם תצוגה**"] + b(comp["audience_sales"]),
        [f"# 04 {ROLES[3]}", f"## {bm['headline']}", f"טון: {comp['tone_line']}"] + [j(x) for x in comp["key_messages_numbered"]] + b(comp["do_dont"]),
        [f"# 05 {ROLES[4]}"] + ([str(ps["story"])] if ps["story"] else []) + [f"- **{b_['fact']}** ← {b_['benefit']}" for b_ in ps["benefits"]] + [j(x) for x in comp["benefits_numbered"]],
        [f"# 06 {ROLES[5]}", "**מתי להמליץ**"] + b(sc["when_to_recommend"]) + ["**איך להציג**"] + b(comp["cheat_how"]) + ["**לזכור**"] + b(comp["cheat_remember"]),
        [f"# 07 {ROLES[6]}", "| שלב | פעולה |", "|---|---|"]
        + [f"| {i + 1:02d} {st['stage']} | {' · '.join(j(x) for x in comp[f'launch_text.{i}'] or ['—'])} |" for i, st in enumerate(pres["launch_plan"])]
        + [f"**הצעד הבא:** {comp['next_step']}"],
    ]
    body = "\n\n---\n\n".join("\n".join(lines) + f"\n\nNotes: {notes[i]}" for i, lines in enumerate(slides))
    return _banner(pkg) + body + "\n\n" + _footer(pkg)


def sales_md(pkg):
    s = pkg["sales"]
    L = ["## פתיח (15 שניות)", f'"{s["opening"]["value"]}"', "",
         "## 3 נקודות לאדריכל/ית"] + [f"- {x['text']}" for x in s["architect_points"]] + ["",
         "## 3 נקודות ללקוח/ה הפרטי/ת"] + [f"- {x['text']}" for x in s["private_points"]] + ["",
         "## שאלות צפויות ותשובות"] + [f"- **{x['q']}** {x['a']}" for x in s["faq"]] + ["",
         "## מה לא להגיד"] + [f"- {x}" for x in s["dont_say"]] + [""]
    return _banner(pkg) + "\n".join(L) + "\n" + _footer(pkg)


def claims_used(pkg, ctx):
    """SKILL step 8: every factual sentence -> source, collected from the package items that cite the claim set,
    in rendering order (landing: story, benefits, details, MODY; sales: points)."""
    out = []

    def add(asset, items):
        for it in items or []:
            for c in (it.get("claims") if isinstance(it, dict) else None) or []:
                out.append({"asset": asset, "text": c["text"], "ref": c["ref"], "source": ref_source(ctx, c["ref"])})

    add("landing", [pkg["story"]])
    add("landing", pkg["benefits"])
    add("landing", pkg["landing"]["product_details"])
    add("landing", [pkg["landing"]["mody_section"]])
    s = pkg["sales"]
    add("sales", [s["opening"]] + s["architect_points"] + s["private_points"] + s["faq"])
    return out


def provenance(pkg, ctx, qa_block=None):
    m, s = pkg["meta"], pkg["strategy"]
    aud = s["target_audiences"]
    positioning = {"one_liner": val(pkg["messaging"]["one_liner"]),
                   "primary_audience": aud[0]["id"] if aud else None,
                   "secondary_audience": aud[1]["id"] if len(aud) > 1 else None,
                   "audience_rule": s["audience_rule"], "pillars": [p["id"] for p in s["pillars"]]}
    positioning.update(s.get("notes") or {})
    positioning["spec_to_benefit"] = [{"from": r["from"], "benefit": r["benefit"], "ref": r["ref"]} for r in s["spec_to_benefit"]]
    generated = m["generated"]
    try:
        generated = datetime.date.fromisoformat(str(generated))
    except ValueError:
        pass
    prov = {"product": m["product"], "generated": generated, "skill_version": m["skill_version"],
            "brand_versions": dict(m["brand_versions"]), "validator_status": m["validator_status"],
            "publishable": m["publishable"]}
    if m.get("publish_blockers"):
        prov["publish_blockers"] = list(m["publish_blockers"])
    prov.update({"flags": list(m["flags"]), "positioning": positioning, "claims_used": claims_used(pkg, ctx)})
    if qa_block:
        prov["qa"] = qa_block
    return prov


def render(pkg, ctx, out_dir):
    """Write the four SKILL assets. Returns the list of files written."""
    written = []
    for name, text in (("landing.md", landing_md(pkg)), ("deck.md", deck_md(pkg)), ("sales.md", sales_md(pkg))):
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
            fh.write(text)
        written.append(name)
    prov_path = os.path.join(out_dir, "provenance.yaml")
    old_qa = None
    if os.path.exists(prov_path):                            # keep the last QA record (run_all refreshes it)
        with open(prov_path, encoding="utf-8") as fh:
            old = yaml.safe_load(fh)
        old_qa = old.get("qa") if isinstance(old, dict) else None
    with open(prov_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(provenance(pkg, ctx, old_qa), fh, allow_unicode=True, sort_keys=False)
    written.append("provenance.yaml")
    return written
