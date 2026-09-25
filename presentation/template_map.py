"""Deterministic mapping: deck content -> slide -> named shape in templates/MODY_GTM_Product_Launch_Template.pptx
(the official MODY template, 8 slides: cover + 01..07).

The template owns the design; this module only says WHICH shape receives WHICH field. Shapes are addressed by the
template's own shape names within each slide (`shape`), nothing is moved or restyled, and every shape not listed
here is decorative and never touched. `source` is a dotted path into the deck content dict built by launch.deck
("presentation.cover.product_name") or "compose:<name>" for text composed by presentation.content.compose_slots.

Slot kinds: text (one string, paragraph per line) · lines (list -> one paragraph each) · bullets (list -> "• " lines,
the template's own bullet style) · image (file fitted inside the shape's box, aspect ratio preserved) · caption
(a template label inside an image frame; removed once the picture is inserted or the image is missing).
`placeholder` is the template's own placeholder text in that slot; the post-render check asserts none survives.
"""

SLIDE_COUNT = 8
SLIDES = {1: "cover", 2: "product_overview", 3: "positioning", 4: "target_audience", 5: "brand_messaging",
          6: "product_story", 7: "seller_cheat_sheet", 8: "launch_plan"}

MAP = {
    # ---------------------------------------------------------------- slide 1 · cover
    "cover.product_name":       {"slide": 1, "shape": "Text 5",  "kind": "text",    "source": "compose:cover_title",                    "placeholder": "[Product name / Category]"},
    "cover.launch_statement":   {"slide": 1, "shape": "Text 6",  "kind": "text",    "source": "presentation.cover.launch_statement",    "placeholder": "[One sentence launch definition]"},
    # ---------------------------------------------------------------- slide 2 · 01 product overview
    "overview.image":           {"slide": 2, "shape": "Shape 6", "kind": "image",   "source": "presentation.cover.hero_image",          "placeholder": None},
    "overview.image_caption":   {"slide": 2, "shape": "Text 7",  "kind": "caption", "source": "presentation.cover.hero_image",          "placeholder": "PRODUCT IMAGE"},
    "overview.image_caption2":  {"slide": 2, "shape": "Text 8",  "kind": "caption", "source": "presentation.cover.hero_image",          "placeholder": "Hero / Lifestyle"},
    "overview.lines":           {"slide": 2, "shape": "Text 10", "kind": "lines",   "source": "compose:overview_lines",                 "placeholder": "Product name: [ ]"},
    "overview.key_facts":       {"slide": 2, "shape": "Text 12", "kind": "bullets", "source": "compose:key_facts",                      "placeholder": "• Verified fact #1"},
    "overview.one_liner":       {"slide": 2, "shape": "Text 15", "kind": "text",    "source": "presentation.brand_messaging.one_liner", "placeholder": "[Short sentence that explains what the product is and why it matters for launch]"},
    # ---------------------------------------------------------------- slide 3 · 02 positioning
    "positioning.statement":    {"slide": 3, "shape": "Text 8",  "kind": "text",    "source": "presentation.positioning.positioning_statement", "placeholder": "[How the product is positioned within MODY’s premium world]"},
    "positioning.value_proposition": {"slide": 3, "shape": "Text 11", "kind": "text", "source": "presentation.positioning.value_proposition", "placeholder": "[The added value beyond basic function for the customer / designer]"},
    "positioning.differentiator": {"slide": 3, "shape": "Text 14", "kind": "text",  "source": "presentation.positioning.differentiator", "placeholder": "[What makes it different from similar products and why now]"},
    # ---------------------------------------------------------------- slide 4 · 03 target audience (fixed columns)
    "audience.private":         {"slide": 4, "shape": "Text 7",  "kind": "bullets", "source": "compose:audience_private",               "placeholder": "• Building or renovating"},
    "audience.architect":       {"slide": 4, "shape": "Text 9",  "kind": "bullets", "source": "compose:audience_architect",             "placeholder": "• Completes a design concept"},
    "audience.sales":           {"slide": 4, "shape": "Text 11", "kind": "bullets", "source": "compose:audience_sales",                 "placeholder": "• Who to recommend it to"},
    # ---------------------------------------------------------------- slide 5 · 04 brand messaging
    "messaging.headline":       {"slide": 5, "shape": "Text 8",  "kind": "text",    "source": "presentation.brand_messaging.headline",  "placeholder": "[The product’s core message in one sentence]"},
    "messaging.tone":           {"slide": 5, "shape": "Text 11", "kind": "text",    "source": "compose:tone_line",                      "placeholder": "[Elegant / precise / clean / professional / premium / confident]"},
    "messaging.key_messages":   {"slide": 5, "shape": "Text 14", "kind": "lines",   "source": "compose:key_messages_numbered",          "placeholder": "1. [Benefit #1]"},
    "messaging.do_dont":        {"slide": 5, "shape": "Text 17", "kind": "lines",   "source": "compose:do_dont",                        "placeholder": "[What to say]  |  [What not to say / forbidden claims]"},
    # ---------------------------------------------------------------- slide 6 · 05 product story & key benefits
    "story.image":              {"slide": 6, "shape": "Shape 6", "kind": "image",   "source": "presentation.cover.hero_image",          "placeholder": None},
    "story.image_caption":      {"slide": 6, "shape": "Text 7",  "kind": "caption", "source": "presentation.cover.hero_image",          "placeholder": "VISUAL"},
    "story.image_caption2":     {"slide": 6, "shape": "Text 8",  "kind": "caption", "source": "presentation.cover.hero_image",          "placeholder": "Product / detail"},
    "story.text":               {"slide": 6, "shape": "Text 10", "kind": "text",    "source": "presentation.product_story.story",       "placeholder": "[The story of the product / collection. Why it exists and what feeling it creates]"},
    "story.fact_benefit":       {"slide": 6, "shape": "Text 13", "kind": "lines",   "source": "compose:fact_benefit_lines",             "placeholder": "[Technical fact / material / finish]"},
    "story.benefits":           {"slide": 6, "shape": "Text 16", "kind": "lines",   "source": "compose:benefits_numbered",              "placeholder": "1. [Benefit #1]"},
    # ---------------------------------------------------------------- slide 7 · 06 seller cheat sheet
    "cheat.when":               {"slide": 7, "shape": "Text 9",  "kind": "bullets", "source": "presentation.seller_cheat_sheet.when_to_recommend", "placeholder": "• Project style"},
    "cheat.how":                {"slide": 7, "shape": "Text 13", "kind": "bullets", "source": "compose:cheat_how",                      "placeholder": "• Suggested opener"},
    "cheat.remember":           {"slide": 7, "shape": "Text 17", "kind": "bullets", "source": "compose:cheat_remember",                 "placeholder": "• 3 must-remember points"},
    # ---------------------------------------------------------------- slide 8 · 07 launch plan (fixed stages)
    **{f"launch.{i}.text":     {"slide": 8, "shape": s,          "kind": "lines",   "source": f"compose:launch_text.{i-1}",             "placeholder": p}
       for i, (s, p) in enumerate((("Text 8", "Product page / landing page / images / verified spec sheet"),
                                   ("Text 11", "Seller cheat sheet / team briefing / approved messages"),
                                   ("Text 14", "Showroom / website / catalog / architect materials"),
                                   ("Text 17", "Post-launch check: usage, inquiries, team questions")), 1)},
    "launch.next_step":         {"slide": 8, "shape": "Text 20", "kind": "text",    "source": "compose:next_step",                      "placeholder": "[Owner]  |  [Status]  |  [Launch Date]  |  [Open Decisions]"},
}

GROUP_DECOR = {}
PLACEHOLDERS = sorted({s["placeholder"] for s in MAP.values() if s["placeholder"]})
# every mapped (slide, shape); anything else in the template is decorative
MAPPED = {(s["slide"], s["shape"]) for s in MAP.values()}


def slots_for(slide_no):
    return {name: spec for name, spec in MAP.items() if spec["slide"] == slide_no}
