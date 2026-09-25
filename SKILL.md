---
name: mody-product-launch
description: Turns one validated product input file into MODY launch assets (landing page, internal deck, sales talking points) in MODY's house voice plus the manufacturer's layer, with source tracking for every claim. Use when launching or refreshing any product from the MODY portfolio.
version: 1.1.0
---

# MODY Product Launch Skill

**One product file in, one launch package out, every asset rendered from it.** The Skill writes `out/<id>/launch_package.yaml` once; QA validates the package; deterministic renderers produce the landing page (`landing.md`, `landing.html`), the internal deck (`deck.md`, `launch.pptx`), the sales talking points (`sales.md`) and `provenance.yaml`. The skill never writes brand rules into the prompt. It reads them from versioned files, so changing the brand means changing one file, not 50 prompts.

```
products/<id>.yaml ──┐
brand/mody_brand_dna.v*.yaml ──┼──► this skill ──► out/<id>/launch_package.yaml ──► python -m launch run
brand/<manufacturer>.v*.yaml ──┘                    (single source of truth)         ├── launch.qa (schema · content · provenance · assets)
                                                                                     ├── landing.md · landing.html (MODY Product Page Template)
                                                                                     ├── deck.md · launch.pptx (assets/templates/presentation/)
                                                                                     ├── sales.md · provenance.yaml
                                                                                     └── qa.py (32 checks on the rendered markdown) ──► PASS / FAIL
```

**What stays constant:** house DNA, voice rules, output structure, guardrails, validation, and this workflow.
**What changes:** the product file, plus one manufacturer file per brand. A new brand is written once and reused.

---

## Pipeline: run every step in order, and never skip one

### 0. One command from the three GTM inputs
Inputs: product name, supplier / manufacturer product-page URL, approved product image. Run
`python -m launch generate --name "<name>" --url <url> --image <path> [--price-ils N --price-tier core|premium|signature]`.
It executes every step below without manual editing: fetch + extract the visible facts (`launch/extract.py`, each value
with `source: product_page` + the evidence line; unknown = null, never inferred) → `products/<id>.yaml` → validate →
content engine (`launch/content_engine.py`: Claude with these step-6 instructions when the API is available, else the
deterministic rules engine; either way QA-gated) → `out/<id>/launch_package.yaml` → package QA + readiness → `landing.html`
(MODY Product Page Template) + `launch.pptx` (`assets/templates/presentation/`) → `qa.py` → reports.
Steps 1-8 describe what that command does, and remain the procedure when a step is run by hand.
(`python -m launch intake` writes only the product file, for products whose facts are entered manually.)

### 1. Validate input
Run `python validate.py products/<id>.yaml`. The approved product image is a pipeline input: `sources.image` (path) and
`sources.image_approved: true` (MODY sign-off). Without both (and the file on disk), the launch package is still written and
QA'd, but `landing.html` and `launch.pptx` are withheld (`not_ready`). Never generate or substitute an image.
- `BLOCKED` → **stop.** Report the errors to the user and generate nothing.
- `READY_WITH_FLAGS` → continue. Keep the `flags` list, because every flag must appear in the outputs (step 8).
- `READY` → continue.
- `publishable: false` → generate a **draft**. Every asset opens with `> טיוטה – לא לפרסום. חסר: <publish_blockers>`.

Use the `brand_layers` paths the validator returns. Do not look up brand files yourself.

### 2. Load the MODY house DNA
Load the file from `brand_layers.house`. Take from it: `role`, `audiences`, `value_proposition`, `pillars`, `voice`, `format`, `guardrails`.

### 3. Load the manufacturer DNA
Load the file from `brand_layers.manufacturer`. Take from it: `identity`, `local_presence`, `voice_extension`, and the matching `lines.<line>.collections.<collection>` block.
- Collection keys are matched case-insensitively. If the product has no `line`, use `lines.default`.
- Vocabulary = the manufacturer's `voice_extension.vocabulary` + the matched line's `vocabulary`. **Never use a line's vocabulary for a product from another line.**
- If the product has no matching collection block, use the manufacturer-level identity only. Write **no story section**: describe the product only by its specs and the manufacturer identity.

### 4. Resolve approved claims
Build the **claim set**: the only statements you may make about the product.
| Type | Comes from | Example |
|---|---|---|
| `claim` | `approved_claims` entries listed in `design.claims_ref` | JQ-2: כל שורש נבחר ידנית |
| `spec` | `technical.*` or `design.signature_material` fields that have a `source` | finish: Warm Bronze Br. PVD |
| `commercial` | `commercial.price_ils` | 5,000 ₪ |
| `brand` | manufacturer `identity`, `local_presence`, `cross_sell` | Gessi Casa |
| `house` | MODY pillars, P5 service | ליווי עד ההתקנה |

If a statement is not in the claim set, it does not appear in the outputs.
You may *interpret* a claim, for example turning a spec into a benefit. You may not *add facts*.

### 5. Derive audience and positioning
This is the reasoning step. Write it into `provenance.yaml` under `positioning` **before** you generate any asset.

**Audience priority by `price_tier`** (use the audience IDs from the house DNA):
| price_tier | primary | secondary |
|---|---|---|
| signature | A (architects and designers) | B (high-end private clients) |
| premium | B | A |
| core | C (new-apartment upgrade) | B |
| missing | A | B, and add the flag `[חסר: price_tier – לבדיקה]` |

**Pillar selection:** choose 2–3 house pillars. Each one must be backed by at least one item in the claim set:
- a craft or material claim → P1 עיצוב מוקפד, P3 איכות וגימור
- a manufacturer with international origin → P2 השראה בינלאומית
- a functional feature (swivel, pull-out, flow, and so on) → P4 דקורטיבי + פרקטי
- P5 שירות מקצועי is always allowed, because it is a MODY fact and not a product fact

**Output of this step:**
```yaml
positioning:
  one_liner: "<≤ 12 words, Hebrew>"
  primary_audience: A
  secondary_audience: B
  pillars: [P1, P3, P4]
  spec_to_benefit:            # every row cites a claim-set item
    - { from: "technical.features: Swivel spout", benefit: "...", ref: spec:features }
    - { from: "JQ-3", benefit: "...", ref: claim:JQ-3 }
```

### 6. Write the launch package (once)
Run `python -m launch skeleton products/<id>.yaml > out/<id>/launch_package.yaml`, then complete it. This is the **only**
document you write. Every asset is rendered from it, so positioning, benefits, messaging, audiences and seller guidance
exist exactly once and can never disagree between the landing page and the deck.

The skeleton already holds every **fact** (`product.facts`, `product.specs` with flags, `product.assets.hero_image`, the house
audiences per `audience_rule`, `messaging.tone`, `deck.launch_plan`, `sources`, `meta`). **Do not change a fact**; QA
compares them with the sources (`FACT_MISMATCH`). Fill the derived and structural fields:

| Section | You write | Rendered into |
|---|---|---|
| `messaging` | `headline` (≤ 8 words), `one_liner` (= step 5, ≤ 12 words), `key_messages` (≤ 3) | landing H1 + sub-headline, deck cover, deck slide 04 |
| `strategy` | `positioning`, `value_proposition`, `customer_need`, `consumer_insight`, `differentiators`, `pillars` (step 5, with `support` text and `refs`), `spec_to_benefit` (step 5 table, with `display` text), `target_audiences[].needs_line` / `need` / `relevance`, `notes` | deck slides 02–03 + provenance.positioning |
| `story` | `value` (≤ 80 words, only when a collection block resolved; else `null`) + `claims` | landing הסיפור, deck slide 05 |
| `benefits` | exactly 3 × `{ title, text, fact, ref, claims }` | landing למה דווקא הוא, deck slide 05 |
| `sales` | `opening`, 3 `architect_points`, 3 `private_points`, `faq` (missing field → "נבדוק ונחזור אלייך" + flag), `dont_say`, `key_talking_points` (3), `seller_cheat_sheet`, `when_to_recommend` (3–5) | sales.md, deck slide 06 |
| `landing` | `product_details` rows `{ label, value, source, claims }` (every technical field: value or flag; price exactly as input), `mody_section` | landing פרטים / ב-MODY |
| `deck.cover.notes`, `deck.slides[].notes` | 8 speaker notes | deck.md `Notes:` lines and the PPTX notes pages |
| `product.summary` | 1–2 factual sentences | deck slide 01 |

Every derived field carries `derived_from: [ref, …]` and every quoted fact carries `claims: [{ text, ref }]`, in the
`claims_used` grammar (`claim:JQ-2`, `spec:finish`, `commercial:price_ils`, `house:B`, `brand:identity`). Source metadata
is internal: it never appears on the landing page or in the deck.

> You are generating the MODY launch package for an internal Go-To-Market. Use only the verified product data, MODY
> internal data, MODY Brand DNA, Manufacturer DNA and approved claims provided. Do not invent factual product information.
> You may derive positioning, benefits, messaging, audience framing, product story and seller guidance when they are
> clearly supported by the approved inputs. Write in MODY's premium brand language: elegant, precise, restrained,
> professional, design-led and confident. Avoid aggressive sales copy, generic luxury clichés and unsupported
> superlatives. Be concise and presentation-ready. Templates define design; make no layout decisions.

Write in Hebrew, RTL. Follow `voice` and `format` from the house DNA, and add the manufacturer's `voice_extension.vocabulary`.
The manufacturer is the hero of the product. MODY is the one that chose it and brought it here (`role.rule`).

The renderers produce the following formats deterministically from the package (these are what `qa.py` checks):

#### 6a. `landing.md`: internal landing page
```
# <Hero headline, up to 8 words>
<sub-headline = positioning.one_liner>
![<name>](<sources.image>)

## הסיפור
<up to 3 sentences, drawn from the collection story_line and the claims>

## למה דווקא הוא
- <benefit 1>   ← from spec_to_benefit
- <benefit 2>
- <benefit 3>

## פרטים
| | |
|---|---|
| מותג / סדרה | ... |
| מק"ט | ... |
| גימור | ... |
| <every technical field: value, or the missing flag> | |
| מחיר | <exactly as in the input, or the flag> |

## ב-MODY
<1–2 sentences: local_presence + P5>
```

#### 6b. `deck.md`: the internal GTM deck as text (cover + 7 slides = 8; `---` separates slides)
`deck.md` and `launch.pptx` are two renderings of the **same** canonical deck (`deck.cover` + `deck.slides`, adapted by
`launch/deck.py` onto the official `MODY_GTM_Product_Launch_Template.pptx` slots); neither can say something the other does not.
0. **Cover**: name / category, one_liner (image on slides 01 and 05, where the template has its frames)
1. **סקירת מוצר**: product · brand / collection · category · model lines, key facts (verified specs, price, tier), one_liner
2. **מיצוב**: `strategy.positioning`, הצעת ערך, בידול
3. **קהל יעד**: the template's three columns: לקוח פרטי (house B / C), אדריכל / מעצב (A), מכירות / אולם תצוגה (seller guidance)
4. **מסר מותג**: headline, tone, up to 3 key messages numbered, לומר / לא לומר
5. **סיפור מוצר ותועלות**: the story (only with a collection block), fact ← benefit lines, the 3 benefits numbered
6. **כלים למכירה**: מתי להמליץ, איך להציג (פתיח / ללקוח הפרטי / לאדריכלים ומעצבים), לזכור (the 3 `key_talking_points`, verbatim from sales.md)
7. **תוכנית השקה**: the template's 4 stages נכסים / הכשרה / ערוצים / מדידה and הצעד הבא (אחראי | סטטוס | תאריך השקה | החלטות פתוחות) — every open flag appears here

Each slide gets up to 16 lines of text, and every slide (cover included) has speaker notes under `Notes:` from
`deck.cover.notes` / `deck.slides[].notes`. Flags are never omitted: slide 7 lists every open flag.

#### 6c. `sales.md`: sales talking points
```
## פתיח (15 שניות)
## 3 נקודות לאדריכל/ית       ← audience A framing
## 3 נקודות ללקוח/ה הפרטי/ת  ← audience B or C framing
## שאלות צפויות ותשובות
   - an answer that depends on a missing field gets: "נבדוק ונחזור אלייך" + the flag
## מה לא להגיד
   - claims that are banned under guardrails G4 and the manufacturer's constraints
```

### 7. Run QA and render
Run `python -m launch run products/<id>.yaml`. It runs, in this order, and never invents data:
1. **Package QA** (`launch/qa.py`) on `launch_package.yaml`: schema, facts vs sources, sources (a technical fact without a
   source, a commercial fact without a MODY source), required GTM content, exactly 3 benefits, hero (headline + image entry,
   image file / approval / format: a missing or unapproved hero image makes the package `not_ready` and withholds the final
   assets), deck structure (cover + 7 content slides, each with content and notes), limits, house voice,
   manufacturer constraints, line isolation, invented numbers, price format, flags surfaced, placeholder text, provenance
   (`derived_from` on every derived field, every ref resolves, every `claims` fragment quotes its item). The verdict is written
   into the package's `qa` block (`passed` / `passed_with_warnings` / `failed`, `errors[{code, field, message}]`).
   `failed` → **nothing is rendered.** Fix the reported field and run again.
2. **Renderers**, each isolated: `landing.md` + `deck.md` + `sales.md` + `provenance.yaml` (6a–6c, step 8), `landing.html`,
   `landing.html` from the fixed MODY Product Page Template (`assets/templates/landing-page/`, photos embedded), `launch.pptx` from the
   fixed deck template. A renderer failure keeps the package and the other assets.
3. `qa.py` (the 32 landing checks) on the rendered markdown, as a regression guard on the renderer.
- `FAIL` in either QA → fix the specific field in `launch_package.yaml` and run again. You get up to 2 fix rounds. If it
  still fails, deliver the result marked FAIL together with the report (`generation_report.json`).
- **Never** fix a QA failure by inventing data. The only fixes allowed are removing the sentence or replacing it with a flag.

### 8. Provenance and flags (rendered from the package)
Every markdown asset ends with this block:
```
---
<!-- QA -->
**דגלים פתוחים:** <list, or "אין">
**גרסאות:** house <v> · <manufacturer> <v> · skill 1.1.0
```

`provenance.yaml` is rendered from the package (`positioning` from `strategy` + `messaging`, `claims_used` from every `claims` fragment, in rendering order) and holds:
```yaml
product: <id>
generated: <date>
brand_versions: { house: <file>, manufacturer: <file> }
validator_status: READY_WITH_FLAGS
flags: [...]
positioning: {...}            # from step 5
claims_used:                  # every factual sentence → source
  - { asset: landing, text: "...", ref: claim:JQ-2, source: <url> }
  - { asset: landing, text: "...", ref: spec:finish, source: product_page }
qa: { status: PASS, checks: {...} }
```

---

`launch_package.yaml` carries the same binding in its `meta` block (product, validator status, flags, brand versions).

## Hard rules (summary)
1. No invented data. A missing field becomes `[חסר: <field> – לבדיקה]`, in every asset where it would have appeared.
2. A factual sentence without an entry in `claims_used` is not allowed.
3. A price appears only exactly as written in the input.
4. No exclamation marks, no emoji, and no urgency or empty superlatives (`voice.dont`).
5. Brand, collection, and model names stay in their original language.
6. The skill does not edit brand files. Changing the brand means a new version of the file, not a change to the prompt.
7. The Skill writes one file, `launch_package.yaml`. No asset is written by hand: every asset is rendered from the package.

## When the brand changes
Publish a new brand file version, then run `run_all.py`. Every output generated against an older version fails the `versions_match` check until it is regenerated. **Changing the brand never goes unnoticed.**

## Adding a new product
1. Create `products/<id>.yaml` from the schema.
2. If the manufacturer is new, create `brand/<manufacturer>.v1.0.yaml` once.
3. Run the skill. Nothing else changes.
