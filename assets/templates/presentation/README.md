# MODY GTM presentation template (`assets/templates/presentation/`)

This folder is the canonical location of the PowerPoint template. Generated content populates it; nothing is laid out
from scratch.

`MODY_GTM_Product_Launch_Template.pptx` is the fixed design for the internal GTM deck (8 slides). The generator
never changes it: `launch/deck.py` adapts the launch package and `presentation/render.py` opens an in-memory copy, fills the named slots listed in
`presentation/template_map.py`, and saves `out/<id>/launch.pptx`.

## Origin
The official MODY template (4:3, 8 slides: cover + 01 Product Overview · 02 Positioning · 03 Target Audience ·
04 Brand Messaging · 05 Product Story & Key Benefits · 06 Seller Cheat Sheet · 07 Launch Plan). Its text boxes carry
the template's own placeholder text; the renderer replaces exactly those and nothing else.

## Slot contract (`presentation/template_map.py`)
Shapes are addressed by the template's own shape names within each slide. Every shape not listed is decorative.

| Slide | Filled shapes | Content |
|---|---|---|
| 1 cover | Text 5, Text 6 | brand name / category, one-liner |
| 2 · 01 | Shape 6 (+ Text 7/8 captions removed), Text 10, Text 12, Text 15 | hero image, product lines, key facts, one-liner |
| 3 · 02 | Text 8, Text 11, Text 14 | positioning, value proposition, differentiator |
| 4 · 03 | Text 7, Text 9, Text 11 | private customer, architect / designer, sales / showroom bullets |
| 5 · 04 | Text 8, Text 11, Text 14, Text 17 | core message, tone, key messages, do / don't |
| 6 · 05 | Shape 6 (+ Text 7/8), Text 10, Text 13, Text 16 | hero image, story, fact ← benefit, 3 benefits |
| 7 · 06 | Text 9, Text 13, Text 17 | when to recommend, how to present, what to remember |
| 8 · 07 | Text 8, Text 11, Text 14, Text 17, Text 20 | assets / enablement / channels / measure, next step |

Speaker notes (cover + 7) come from `deck.cover.notes` / `deck.slides[].notes`. The image is fitted inside the two
frames with its aspect ratio preserved; without an approved image the deck is not rendered (`not_ready`).

Set `MODY_PRESENTATION_TEMPLATE=/path/to/file.pptx` to render against a different copy without editing code.
