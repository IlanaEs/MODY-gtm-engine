"""Canonical launch package: ONE structured GTM content model per product, generated once, validated once,
rendered into every asset.

    products/<id>.yaml + brand layers + image  ──►  Skill (AI + rules)  ──►  out/<id>/launch_package.yaml
                                                                                   │
                                                                              launch.qa (schema · content · provenance · assets)
                                                                                   │ passed
                    ┌──────────────────────────────┬───────────────────────────────┴──────────────────────┐
             launch.render_md                 launch.render_html                                  launch.deck
     landing.md · deck.md · sales.md            landing.html                     presentation.render → launch.pptx
     provenance.yaml  (SKILL 6a-6c / 8)

package.py   context, skeleton (every fact prefilled), helpers          qa.py   validation → package["qa"]
pipeline.py  QA then independent renderers; a renderer failure never touches the package
"""
