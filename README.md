# MODY Product Launch Engine

One product file in → one canonical launch package (`launch_package.yaml`) → landing page (md + html), internal deck (md + pptx), sales talking points and provenance, all rendered from that single source of truth. Every claim is traceable to its source.

## Run
```
pip install -r requirements.txt             # PyYAML + python-pptx (use a venv)
python validate.py products/<id>.yaml      # check the input
# run the Skill (SKILL.md) on the product      → out/<id>/
python -m launch generate --name "…" --url <supplier page> --image <approved image>   # SKILL step 0: everything, no manual editing
python -m launch generate --name "…" --url <supplier page> --approve-page-image        # no image file: the page's product photo, signed off by the flag
python -m launch skeleton products/<id>.yaml > out/<id>/launch_package.yaml   # SKILL step 6: the Skill completes this ONE file
python -m launch qa products/<id>.yaml        # package QA only
python -m launch run products/<id>.yaml       # package QA → landing.md/html · deck.md · sales.md · provenance.yaml · launch.pptx → qa.py
python run_all.py                           # validate + package QA + render + markdown QA for the whole portfolio
python -m unittest discover -s tests -t .   # QA regression tests + the two negative controls below
```
All commands run from the project root. Exit code is 0 only when nothing is BLOCKED / FAIL / NOT GENERATED, so all three scripts can gate CI.

Negative controls: `python validate.py tests/broken_example.yaml` must print BLOCKED and exit 1;
`python -m unittest tests.test_planted` runs `tests/landing_with_planted_errors.md` through qa.py next to a real deck, sales file and provenance, and asserts FAIL.

## Supplier pages: static or browser-rendered
`launch/extract.py` reads the static HTML first. When it yields no facts and the URL is remote (a JavaScript app that serves
an empty shell, e.g. `areapro.gessi.com`), the page is rendered in a headless browser (Playwright driving the installed Chrome
or Edge, else `playwright install chromium`) and the rendered DOM goes through the same rules: table / definition-list rows,
`Label: value` lines, sibling-element rows (`Height` / `275 mm` → `dimensions_mm`), the finish stated as `<code> - <name>` where
the code is also in the URL (`?finId=726`), the model number as a bare `<h1>` code, the collection as one of the manufacturer
file's own collection names, features from the page's own description sentence, and the technical-sheet PDF link. A link to a
file is never a value. The product file records `extraction.fetch` (static | browser), the renderer, the evidence line of every
fact, `sources.product_page_snapshot` (the HTML that was read, saved in `out/<id>/product_page.html`) and, without `--image`,
`sources.image_source` (the page photo's URL; `--approve-page-image` is MODY's sign-off, otherwise the final assets stay withheld).
`--render never|always` overrides the automatic choice. Without a browser the fallback reports why and the run continues
with what the static page gave (usually BLOCKED by the validator).

## Structure
```
brand/      mody_brand_dna.v1.0.yaml   ← House layer. Constant for every product
            gessi.v1.1.yaml, mutina.v1.0.yaml  ← one file per manufacturer, versioned
schema/     product_input.schema.yaml  ← v1.1: required fields, publish gates, category profiles
products/   <id>.yaml                  ← facts only. Each value has a source
out/<id>/   launch_package.yaml  ← single source of truth (Skill writes it once; QA verdict inside)
            landing.md · landing.html (MODY Product Page Template) · deck.md · sales.md · provenance.yaml · launch.pptx · generation_report.json  ← all rendered
launch/     extract.py (supplier page → facts + evidence) · content_engine.py (rules | Claude → launch_package) · package.py · qa.py
            render_md.py · render_product_page.py (landing.html) · deck.py (adapter) · pipeline.py
presentation/  template_map.py (field → slide → shape) · render.py (PPTX layer) · content.py (slot composition)
assets/templates/landing-page/  mody-landing-page-template.html + README.md  ← canonical landing-page template (landing.html)
assets/templates/presentation/  MODY_GTM_Product_Launch_Template.pptx + README.md  ← canonical PowerPoint template (launch.pptx)
schema/     launch_package.schema.yaml ← package model, limits, labels, QA settings
SKILL.md    8-step pipeline (6 = launch package, 7 = QA + render)
validate.py · qa.py · run_all.py
```

## Templates (`assets/templates/`)
- `assets/templates/landing-page/` holds the canonical landing-page template. `launch/render_product_page.py` fills its
  `{{slots}}` to produce `out/<id>/landing.html`.
- `assets/templates/presentation/` holds the canonical PowerPoint template. `presentation/render.py` opens an in-memory copy
  and fills the named shapes listed in `presentation/template_map.py` to produce `out/<id>/launch.pptx`.
- Generated content populates these templates; the renderers never create a layout from scratch, and the template files
  on disk are never modified. Override a template for one run with `MODY_PRODUCT_PAGE_TEMPLATE` / `MODY_PRESENTATION_TEMPLATE`.
- `launch.pptx` is the final internal deck: open items appear by label (`ספיקה (ל/דק) – להשלמה`), never as raw QA flags,
  assets are named in business terms, and text is shrunk to fit each box (template autofit, real font metrics, floor 9 pt).
  `deck.md` keeps the raw flags the QA rules match.

## Demo: three levels of proof
| # | Product | What it proves |
|---|---|---|
| 1 | GESSI Jacqueline 77201 | Signature product with a rich story. Publishable |
| 2 | GESSI G60077 (kitchen) | Same manufacturer, no collection story. The skill does not invent one |
| 3 | MUTINA Bas-Relief Patchwork | Different manufacturer and category. The house layer does not change |
| 4 | GESSI Jacqueline 77201 from its supplier URL (`gessi-jacqueline-77201`) | The same product, generated end to end by `launch generate` from `areapro.gessi.com` (a JavaScript page: browser-rendered fetch), its own product photo, the technical-sheet link and a snapshot of the page as provenance. Product 1 stays the hand-curated golden the test suite is built on |

## What products 2–3 exposed (and the fix)
- schema v1.0 → v1.1: `image` and `model_number` block publishing, not generation. Missing fields are detected by category profile.
- gessi v1.0 → v1.1: Haute Culture vocabulary moved to line level (it had leaked into the kitchen tap).
- After the Gessi update, QA flagged product 1 as stale until it was regenerated.

## Adding product #51
1. `products/<id>.yaml`
2. New manufacturer only: `brand/<name>.v1.0.yaml`, written once
3. Run the skill, then `run_all.py`

## Single source of truth
```
name + supplier URL + approved image ──► extract (static, else browser-rendered: facts + evidence) ──► products/<id>.yaml ──► validate
   ──► content engine (rules | Claude) + brand DNA ──► launch_package.yaml ──► launch.qa ──► render_md (landing.md, deck.md, sales.md, provenance.yaml)
                                                                    ├─► render_product_page (landing.html, MODY Product Page Template)
                                                                    └─► deck adapter → presentation.render (launch.pptx)
                                                          then qa.py (32 checks) on the rendered markdown
```
Stages are independent: a failed package QA renders nothing; a valid package without an approved product image
(`sources.image` + `sources.image_approved: true`, file on disk, png/jpg) is `not_ready`: the markdown drafts are rendered, `landing.html`
and `launch.pptx` are withheld; a failed renderer keeps the package and the other assets. `deck.md` and `launch.pptx` are two
renderings of the same 8-slide deck (cover + 7). `generation_report.json` records `package / qa / readiness / landing / markdown / deck / markdown_qa`. Tests:
`python -m unittest tests.test_launch -v` (deck rendering tests skip without python-pptx).
