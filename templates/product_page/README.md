# MODY Product Page Template

Fixed design for the single-file landing page (`out/<id>/landing.html`). The renderer
(`launch/render_product_page.py`) fills the `{{slots}}` of `template.html` from the validated launch package and
embeds the approved photos as base64, so the file works standalone. It never changes the design: 100% of the layout,
CSS, fonts, colours, responsive behaviour and interactions come from `template.html`.

## 1. Design system (fixed, never changes between products)

| Token | Value | Use |
|---|---|---|
| Background | `#0a0a0a` | Page |
| Text | `#f2efe9` | Body, values |
| Muted | `#bdb8b0` | Secondary text, labels |
| Lines | `#2a2a2a` | 1px dividers, box borders |
| Accent red | `#e3202a` | Section titles, CTA, active states, short underline |

Typography: Cormorant Garamond (serif) for the product name (60px), model number (32px) and the advantage numbers
01/02/03; Heebo (300–600) for all Hebrew text; Oswald Light for the brand wordmark above the product name;
Montserrat Black for the MODY logo (the O is a red/white ring).

Style rules: RTL layout, Latin names and numbers stay LTR. No rounded corners; structure comes only from thin lines
and dividers. Section titles are red, 17–18px, weight 500. A short red line (34×2px) sits under the model number.
Exactly one red CTA button. Photos have a dark, moody background with the product in warm light.

## 2. Layout (top to bottom, reading right to left)

Header: breadcrumb on the right, MODY logo on the left, 1px bottom line. Main area, three columns: content (right,
flexible), gallery (~600px, sticky, divider + fade on the text-facing edge, 4 thumbnails), step navigation 01–07
(left, narrow, thin red vertical line). Content column: title row (CTA right; brand, name, model, red line, short
description left) → three pillars with dividers (core value, positioning, target audience) → two columns (right:
product details table, technical data (3 stats), manufacturer link; left: 3 numbered advantages, product story) →
bottom row (right: when to recommend, 4 bullets; left: sales cheat sheet, 4 columns).
Responsive: ≤1180px the advantages become a vertical list; ≤900px everything stacks, gallery on top, step nav hidden.

## 3. Content fields → launch package

| Field | Source in `launch_package.yaml` | Rule |
|---|---|---|
| breadcrumb | category_label · collection · brand · collection · model | facts only |
| brand / product_name / model | `product.facts` | as in the input |
| short_description | `messaging.headline` + `messaging.one_liner` (main headline + supporting copy) | 1–2 sentences |
| cta_text / cta_link | fixed "בדיקת זמינות ומחיר" / `sources.product_sources.mody_listing` when it is a URL | exactly one CTA |
| pillars.core_value / positioning / target_audience | `strategy.value_proposition` / `strategy.positioning` / audience segments | 3 pillars |
| product_details | `landing.product_details` rows with a value (flagged rows are left out, never guessed) | 8–14 rows |
| technical_data | first 3 verified `product.specs` in stat order (flow, dimensions, thickness, format, installation, finish, material) | ≤ 3 |
| manufacturer_link | `sources.product_sources.technical_sheet`, else `product_page` | URL |
| advantages | `benefits` (title, text) | exactly 3 |
| product_story | `story.value`, else `product.summary` | 2–3 sentences |
| when_to_recommend | `sales.when_to_recommend[:4]` | exactly 4 |
| sales_cheat_sheet | `sales.key_talking_points` (remember), `seller_cheat_sheet.private_customer`, `.professional_customer`, `sales.opening` | 4 columns |
| images | `product.assets.hero_image` (hero) + optional `sources.images` (alt views) | approved assets only, base64 |

The page is a FINAL asset: it is rendered only when the package is `ready` (approved hero image on disk).
Counts that fall short (fewer than 3 stats, fewer than 4 bullets) are rendered as they are and reported as warnings;
nothing is invented to fill a slot.

## 4. Prompt to reuse for each new product (when authoring by hand instead of the renderer)

> Create a single-file HTML product landing page using `templates/product_page/template.html` as the exact template.
> Keep 100% of the design, layout, CSS, fonts, colors, responsive behavior and interactions unchanged. Replace ONLY the
> content and images with the data below. Respect the word limits and fixed item counts. Embed images as base64 so the
> file works standalone. Do not invent any specification that is not provided.
