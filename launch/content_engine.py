"""AI / content engine: verified facts + MODY Brand DNA + Manufacturer DNA + GTM rules -> the completed canonical
launch package (schema/launch_package.schema.yaml). One stage, one output; both renderers consume it.

Two backends behind one interface:
  RulesEngine   deterministic, offline. Derives every marketing field from the claim set and the DNA files with
                fixed house-voice templates (facts are quoted, never rephrased into new facts). Always available.
  ClaudeEngine  the Claude API (anthropic SDK) with the SKILL step-6 instructions; its output is QA'd and, when a
                check fails, the errors are fed back for up to 2 repair rounds; a still-failing or unavailable
                model falls back to RulesEngine so the pipeline never blocks on the content stage.
Neither backend may invent a fact: package QA compares every fact with the sources (FACT_MISMATCH) and every
derived field must trace to the claim set (MISSING_DERIVATION / UNSUPPORTED_CLAIM)."""
import os, re, yaml
from validate import get, resolve_collection, project_path, MISSING
from launch import package as P
from launch import qa as pkgqa

MODEL = os.environ.get("MODY_CONTENT_MODEL", "claude-opus-5")
FIELD_Q = {"price_tier": "מה דרגת המחיר?", "dimensions_mm": "מה המידות?", "flow_rate_lpm": "מה הספיקה?", "installation_type": "איך הוא מותקן?",
           "sources.technical_sheet": "יש דף טכני לשלוח?", "commercial.price_ils": "מה המחיר?", "sources.image": "יש תמונה לשלוח ללקוח?",
           "product.model_number": 'מה המק"ט להזמנה?', "application": "מתאים לרצפה או לאזור רטוב?", "material": "מאיזה חומר הוא עשוי?",
           "finish": "אילו גימורים קיימים?", "format_cm": "מה הפורמט?", "thickness_mm": "מה העובי?", "colour": "אילו גוונים קיימים?"}
BENEFIT = {"finish": "גימור שמשלים את שפת החלל", "material": "חומר שמורגש במגע ולאורך זמן", "features": "נוחות בשימוש היומיומי",
           "dimensions_mm": "התאמה מדויקת לחלל", "flow_rate_lpm": "ספיקה ידועה לתכנון מדויק", "installation_type": "התקנה מוגדרת מראש",
           "certifications": "תקנים מאושרים לפרויקט", "warranty": "אחריות יצרן לאורך זמן", "technical_requirements": "דרישות טכניות ברורות לתכנון",
           "format_cm": "גמישות בהתאמה לחלל", "thickness_mm": "עובי ידוע לתכנון", "colour": "גוון לבחירה לפי החלל", "technologies": "טכנולוגיה שעובדת כל יום",
           "application": "יישום ברור", "signature_material": "חומר חתימה שמייחד את הפריט", "sku": "זיהוי מדויק להזמנה"}
STAT_ORDER = ["signature_material", "finish", "material", "features", "installation_type", "dimensions_mm", "flow_rate_lpm",
              "format_cm", "thickness_mm", "colour", "technical_requirements", "certifications", "warranty", "technologies", "application"]


def _first_sentence(s):
    return re.split(r"(?<=[.!?])\s+", str(s or "").strip())[0].rstrip(".")


def _words(s):
    return len(str(s).split())


class RulesEngine:
    name = "rules"

    def fill(self, pkg, ctx):
        p, house, mfr = ctx["p"], ctx["house"], ctx["mfr"]
        f, specs = pkg["product"]["facts"], [r for r in pkg["product"]["specs"] if r.get("value")]
        by_field = {r["field"]: r for r in specs}
        brand, name, cat, collection = P.val(f["brand"]), P.val(f["name"]), P.val(f["category_label"]), P.val(f.get("collection"))
        block = resolve_collection(mfr, p)[2] or {}
        allowed = {c["id"]: c for c in block.get("approved_claims") or [] if isinstance(c, dict) and "id" in c}
        claims = [(cid, allowed[cid]["claim"]) for cid in (get(p, "design.claims_ref") or []) if cid in allowed]
        identity = _first_sentence(mfr.get("identity"))
        relationship = get(mfr, "meta.relationship")
        pillars_by_id = {pl["id"]: pl for pl in house["pillars"]}
        auds = pkg["strategy"]["target_audiences"]
        house_aud = {a["id"]: a for a in house["audiences"]}
        primary = house_aud.get(auds[0]["id"]) if auds else None
        # -- pillars (SKILL step 5): each backed by the claim set
        pillars = []
        if claims:
            pillars.append({"id": "P1", "support": f"{claims[0][1]} ({claims[0][0]})", "refs": [f"claim:{claims[0][0]}"]})
        for fld, pid in (("finish", "P3"), ("material", "P3"), ("features", "P4"), ("signature_material", "P3")):
            if fld in by_field and pid not in {x["id"] for x in pillars}:
                pillars.append({"id": pid, "support": f"{by_field[fld]['label']}: {by_field[fld]['value']}", "refs": [by_field[fld]["ref"]]})
        pillars.append({"id": "P2", "support": identity, "refs": ["brand:identity"]})
        pillars.append({"id": "P5", "support": pillars_by_id["P5"]["line"], "refs": ["house:P5"]})
        pillars = [dict(x, name=pillars_by_id[x["id"]]["name"]) for x in pillars[:3]]
        # -- spec -> benefit rows and the 3 primary benefits
        rows = [{"from": f"claim {cid}", "display": f"{text} ({cid})", "benefit": "סיפור מותג להציג ללקוח", "ref": f"claim:{cid}", "fact": text}
                for cid, text in claims[:1]]
        for fld in STAT_ORDER:
            if fld in by_field and fld != "sku":
                r = by_field[fld]
                src = "design.signature_material" if fld == "signature_material" else f"technical.{fld}"
                rows.append({"from": src, "display": r["value"], "benefit": BENEFIT[fld], "ref": r["ref"], "fact": r["value"], "label": r["label"]})
        rows = rows[:5]
        extra = [{"from": "brand.identity", "display": identity, "benefit": "מותג בינלאומי שנבחר ל-MODY", "ref": "brand:identity", "fact": identity},
                 {"from": "house.P5", "display": str(pillars_by_id["P5"]["line"]), "benefit": "שירות מקצועי", "ref": "house:P5", "fact": str(pillars_by_id["P5"]["line"])}]
        while len(rows) < 3 and extra:
            rows.append(extra.pop(0))
        benefits = []
        for r in rows[:3]:
            text = (f"{r['label']}: {r['fact']}." if r.get("label") else f"{r['fact']}.")
            benefits.append({"title": r["benefit"] + ".", "text": text, "fact": r["fact"], "ref": r["ref"],
                             "claims": [{"text": r["fact"], "ref": r["ref"]}], "derived_from": [r["ref"]]})
        short = [by_field[k] for k in ("finish", "material", "installation_type", "dimensions_mm", "format_cm") if k in by_field][:2]
        spec_refs = [r["ref"] for r in short] or [r["ref"] for r in specs[:1]]
        pk = pkg["strategy"]
        pk["pillars"], pk["spec_to_benefit"] = pillars, [{k: r[k] for k in ("from", "display", "benefit", "ref")} for r in rows]
        pk["positioning"] = {"value": f"{cat} מבית {brand}, שנבחר ל-MODY בזכות {' ו'.join(x['name'] for x in pillars[:2])}. {identity}.",
                             "derived_from": [f"house:{x['id']}" for x in pillars[:2]] + ["brand:identity"]}
        pk["value_proposition"] = {"value": str(house["value_proposition"]), "derived_from": ["house:value_proposition"]}
        cares = list(primary.get("cares_about") or []) if primary else []
        needs = list(primary.get("needs_from_us") or []) if primary else []
        pk["customer_need"] = {"value": (" ו".join(cares[:2]) if cares else "פריט שמגדיר את החלל") + ".", "derived_from": [f"house:{primary['id']}" if primary else "house:audiences"]}
        pk["consumer_insight"] = {"value": f"ל{primary['name']} חשוב {cares[0]}." if primary and cares else "ללקוח חשוב פריט שמגדיר את החלל.",
                                  "derived_from": [f"house:{primary['id']}" if primary else "house:audiences"]}
        pk["differentiators"] = [{"value": (f"{claims[0][1]}." if claims else f"{short[0]['label']}: {short[0]['value']}."),
                                  "derived_from": [f"claim:{claims[0][0]}" if claims else short[0]["ref"]]}]
        for a in auds:
            h = house_aud.get(a["id"], {})
            n = list(h.get("needs_from_us") or [])
            a["need"] = (" ו".join(n[:2]) if n else "ביטחון ברכישה") + "."
            a["relevance"] = None
            a["derived_from"] = [f"house:{a['id']}"]
        # -- messaging
        msg = pkg["messaging"]
        msg["headline"] = {"value": f"{brand} {name}: {cat}", "derived_from": spec_refs + ["brand:identity"]}
        prefix = f"{cat} של {brand}."
        fits = [(x["id"], str(pillars_by_id[x["id"]]["line"])) for x in pillars if _words(prefix) + _words(pillars_by_id[x["id"]]["line"]) <= 12]
        pid_, line_ = max(fits, key=lambda t: _words(t[1])) if fits else (pillars[0]["id"], "")
        msg["one_liner"] = {"value": f"{prefix} {line_}." if line_ else prefix, "derived_from": [f"house:{pid_}", "brand:identity"]}
        kms = [(text, f"claim:{cid}") for cid, text in claims if _words(text) <= 15]
        kms += [(f"{by_field[k]['label']}: {by_field[k]['value']}", by_field[k]["ref"]) for k in STAT_ORDER if k in by_field and _words(by_field[k]["value"]) <= 12]
        msg["key_messages"] = [{"value": t if t.endswith(".") else t + ".", "derived_from": [r]} for t, r in kms[:3]]
        # -- story: only with a collection block
        if pkg["story"].get("expected") and block:
            parts, refs, frags = [str(block.get("story_line") or "").strip()], [], []
            for cid, text in claims:
                cand = " ".join(parts + [text + "."])
                if _words(cand) <= 80 and pkgqa._sentences(cand) <= int(house["format"].get("paragraph_max_sentences") or 3):
                    parts.append(text + "."); refs.append(f"claim:{cid}"); frags.append({"text": text, "ref": f"claim:{cid}"})
            pkg["story"].update(value=" ".join(x for x in parts if x), claims=frags, derived_from=refs or [f"claim:{c[0]}" for c in claims[:1]])
        else:
            pkg["story"].update(value=None, claims=[], derived_from=[])
        pkg["product"]["summary"] = {"value": f"{cat} של {brand}" + (f" מקולקציית {collection}" if collection else "") + ": "
                                              + ", ".join(f"{r['label']} {r['value']}" for r in short) + ".",
                                     "derived_from": spec_refs + ["brand:identity"]}
        pkg["benefits"] = benefits
        # -- sales
        p5_line = str(pillars_by_id["P5"]["line"])
        first_km = msg["key_messages"][0]["value"] if msg["key_messages"] else f"{cat} של {brand}."
        opening = f"זה {name} של {brand}. {first_km}"
        km_ref = msg["key_messages"][0]["derived_from"][0] if msg["key_messages"] else "brand:identity"
        km_text = first_km.rstrip(".")
        s = pkg["sales"]
        s["opening"] = {"value": opening, "ref": km_ref, "claims": [{"text": km_text, "ref": km_ref}] if km_ref.startswith(("claim:", "spec:")) else []}
        arch = [{"text": f"{by_field[k]['label']}: {by_field[k]['value']}.", "ref": by_field[k]["ref"], "claims": [{"text": by_field[k]["value"], "ref": by_field[k]["ref"]}]}
                for k in ("dimensions_mm", "installation_type", "finish", "material", "certifications", "format_cm", "thickness_mm") if k in by_field]
        if relationship:
            arch.append({"text": f"{relationship}.", "ref": "brand:relationship", "claims": [{"text": relationship, "ref": "brand:relationship"}]})
        arch.append({"text": f"{identity}.", "ref": "brand:identity", "claims": [{"text": identity, "ref": "brand:identity"}]})
        s["architect_points"] = arch[:3]
        s["private_points"] = [{"text": f"{b['title']} {b['text']}", "ref": b["ref"], "claims": [{"text": b["fact"], "ref": b["ref"]}]} for b in benefits][:3]
        faq = []
        for flag in pkg["meta"]["flags"]:
            field = re.search(r"\[חסר: (.+?) –", flag).group(1)
            q = FIELD_Q.get(field) or FIELD_Q.get(field.split(".")[-1]) or f"מה לגבי {field}?"
            faq.append({"q": q, "a": f"נבדוק ונחזור אלייך. {flag}", "flag": flag})
        if f["price"].get("display"):
            faq.append({"q": "מה המחיר?", "a": f"{f['price']['display']}.", "flag": None, "claims": [{"text": f["price"]["display"], "ref": "commercial:price_ils"}]})
        s["faq"] = faq or [{"q": "מה זמן האספקה?", "a": "נבדוק ונחזור אלייך.", "flag": None}]
        s["dont_say"] = [f'"{ph}"' for ph in pkgqa.mdqa.constraint_phrases(mfr)] + ["השוואה למותגים אחרים", "סופרלטיבים והבטחות שאי אפשר לאמת"]
        s["key_talking_points"] = [opening] + [x["text"] for x in s["private_points"][:2]]
        s["seller_cheat_sheet"] = {"positioning": opening, "private_customer": " ".join(b["title"] for b in benefits[:2]),
                                   "professional_customer": f"{identity}. " + (f"{relationship}." if relationship else f"{p5_line}."),
                                   "derived_from": sorted({km_ref} | {x["ref"] for x in s["private_points"][:2]} | {"brand:identity", "brand:relationship" if relationship else "house:P5"})}
        s["when_to_recommend"] = [f"פרויקט ברמה גבוהה שמחפש {cat} עם {pillars[0]['name']}", f"{primary['name']}" if primary else "לקוח פרטי בשיפוץ",
                                  f"חלל שבו {cat} הוא פריט שמגדיר", f"לקוח שמבקש {brand}"]
        s["when_to_recommend_derived_from"] = [f"house:{pillars[0]['id']}", f"house:{primary['id']}" if primary else "house:audiences", "brand:identity"]
        # -- landing: details table (SKILL 6a) + MODY section
        line = P.val(f.get("line"))
        rows_l = [{"label": "מותג / סדרה", "value": " · ".join(x for x in (brand, collection, line) if x), "ref": None, "source": "product_page"}]
        rows_l.append({"label": 'מק"ט', "value": P.val(f.get("model")) or next((fl for fl in pkg["meta"]["flags"] if "product.model_number" in fl), "—"), "ref": None, "source": "product_page"})
        rows_l.append({"label": "סוג", "value": cat, "ref": None, "source": "product_page"})
        for r in pkg["product"]["specs"]:
            if r.get("value"):
                rows_l.append({"label": r["label"], "value": r["value"], "ref": r["ref"], "source": r["source"], "claims": [{"text": r["value"], "ref": r["ref"]}]})
            else:
                rows_l.append({"label": r["label"], "value": r["flag"], "ref": None, "source": None})
        ts = next((fl for fl in pkg["meta"]["flags"] if "sources.technical_sheet" in fl), None)
        if ts:
            rows_l.append({"label": "דף טכני", "value": ts, "ref": None, "source": None})
        price_flag = next((fl for fl in pkg["meta"]["flags"] if "commercial.price_ils" in fl), None)
        rows_l.append({"label": "מחיר", "value": f["price"].get("display") or price_flag or "—", "ref": "commercial:price_ils" if f["price"].get("display") else None,
                       "source": f["price"].get("source"), "claims": [{"text": f["price"]["display"], "ref": "commercial:price_ils"}] if f["price"].get("display") else []})
        tier_flag = next((fl for fl in pkg["meta"]["flags"] if "price_tier" in fl), None)
        if tier_flag:
            rows_l.append({"label": "דרגת מחיר", "value": tier_flag, "ref": None, "source": None})
        pkg["landing"]["product_details"] = rows_l
        p5 = pillars_by_id["P5"]["line"]
        mody = f"{identity}. " + (f"{relationship}, {p5}." if relationship else f"{p5}.")
        pkg["landing"]["mody_section"] = {"value": mody, "claims": [{"text": identity, "ref": "brand:identity"}] + ([{"text": relationship, "ref": "brand:relationship"}] if relationship else []) + [{"text": p5, "ref": "house:P5"}]}
        # -- deck notes (cover + 7)
        notes = [f"פתחו מהתמונה. {cat} של {brand}.", "עובדות מאומתות בלבד. שדה חסר נשאר דגל.",
                 f"המיצוב נשען על {' ו'.join(x['name'] for x in pillars)}.", f"קהל ראשי: {primary['name'] if primary else 'לקוח פרטי'}.",
                 "לומר בשקט, בלי סופרלטיבים.", "כל תועלת נשענת על עובדה מאומתת.", "שלוש השורות לזכור מתוך sales.md.",
                 "עד שהדגלים ייסגרו, לא לפרסם נתונים חסרים."]
        pkg["deck"]["cover"]["notes"] = notes[0]
        for i, sl in enumerate(pkg["deck"]["slides"]):
            sl["notes"] = notes[i + 1]
        return pkg


class ClaudeEngine:
    name = "claude"

    def __init__(self, model=MODEL, rounds=2):
        self.model, self.rounds, self.usage = model, rounds, []

    def available(self):
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                    or os.path.isdir(os.path.expanduser("~/.config/anthropic")))

    def _prompt(self, pkg, ctx):
        with open(project_path("SKILL.md"), encoding="utf-8") as fh:
            skill = fh.read()
        rules = skill[skill.index("### 6."):skill.index("### 7.")]
        with open(P.SCHEMA_PATH, encoding="utf-8") as fh:
            schema = fh.read()
        with open(project_path(ctx["v"]["brand_layers"]["house"]), encoding="utf-8") as fh:
            house = fh.read()
        with open(project_path(ctx["v"]["brand_layers"]["manufacturer"]), encoding="utf-8") as fh:
            mfr = fh.read()
        product = yaml.safe_dump(ctx["p"], allow_unicode=True, sort_keys=False)
        skeleton = yaml.safe_dump(pkg, allow_unicode=True, sort_keys=False, width=110)
        system = ("You are generating the MODY launch package for an internal Go-To-Market. Use only the verified product data, "
                  "MODY internal data, MODY Brand DNA, Manufacturer DNA and approved claims provided. Do not invent factual product "
                  "information. You may derive positioning, benefits, messaging, audience framing, product story and seller guidance "
                  "when they are clearly supported by the approved inputs. Write in MODY's premium brand language: elegant, precise, "
                  "restrained, professional, design-led and confident, in Hebrew. Avoid aggressive sales copy, generic luxury clichés "
                  "and unsupported superlatives. Be concise and presentation-ready. Templates define design; make no layout decisions.\n\n"
                  "Return ONLY the completed launch_package.yaml: the skeleton below with every derived field filled, every fact "
                  "unchanged, derived_from and claims on every derived item, no code fences, no commentary.\n\n" + rules)
        user = (f"## schema/launch_package.schema.yaml\n{schema}\n\n## MODY house DNA\n{house}\n\n## Manufacturer DNA\n{mfr}\n\n"
                f"## Product file (facts, each with its source)\n{product}\n\n## Skeleton to complete\n{skeleton}")
        return system, user

    def fill(self, pkg, ctx):
        import anthropic
        client = anthropic.Anthropic()
        system, user = self._prompt(pkg, ctx)
        messages = [{"role": "user", "content": user}]
        last, errors = None, None
        for attempt in range(self.rounds + 1):
            if errors:
                messages.append({"role": "user", "content": "Package QA failed. Fix ONLY these fields and return the full YAML again:\n"
                                 + "\n".join(f"- {e['code']} {e['field']}: {e['message']}" for e in errors)})
            resp = client.beta.messages.create(model=self.model, max_tokens=16000, system=system, messages=messages,
                                               betas=["server-side-fallback-2026-06-01"], fallbacks=[{"model": "claude-opus-4-8"}],
                                               output_config={"effort": "high"})
            self.usage.append({"input": resp.usage.input_tokens, "output": resp.usage.output_tokens, "model": resp.model})
            if resp.stop_reason == "refusal":
                raise RuntimeError("model refused the request")
            text = "".join(b.text for b in resp.content if b.type == "text")
            messages.append({"role": "assistant", "content": text})
            text = re.sub(r"^```[a-z]*\n|\n```$", "", text.strip())
            cand = yaml.safe_load(text)
            if not isinstance(cand, dict):
                errors = [{"code": "SCHEMA_SHAPE", "field": "", "message": "output is not a YAML mapping"}]
                continue
            P.refresh_facts(cand, ctx)
            result = pkgqa.run(cand, ctx)
            last = cand
            errors = [e for e in result["errors"] if e["code"] not in pkgqa.READINESS_CODES]
            if not errors:
                return cand
        raise RuntimeError("package still fails QA after repair rounds: " + "; ".join(f"{e['code']} {e['field']}" for e in errors[:5]))


def generate(ctx, engine="auto"):
    """The content stage. Returns (package, report) where report = {"engine", "fallback", "warnings", "usage"}."""
    report = {"engine": None, "fallback": None, "warnings": [], "usage": []}
    pkg = P.skeleton(ctx)
    use_claude = engine == "claude" or (engine == "auto" and ClaudeEngine().available())
    if use_claude:
        eng = ClaudeEngine()
        try:
            pkg = eng.fill(P.skeleton(ctx), ctx)
            report.update(engine=eng.name, usage=eng.usage)
            return pkg, report
        except Exception as e:                              # the content stage never blocks the pipeline
            report["fallback"] = f"claude engine unavailable or failed ({type(e).__name__}: {str(e)[:120]}); rules engine used"
            report["usage"] = eng.usage
            pkg = P.skeleton(ctx)
    pkg = RulesEngine().fill(pkg, ctx)
    P.refresh_facts(pkg, ctx)
    report["engine"] = "rules"
    return pkg, report
