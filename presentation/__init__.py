"""PPTX layer for the internal GTM deck. It never reasons about content: launch.deck adapts the validated launch
package into the 8-slide content model, template_map.py says which named shape of the fixed MODY template receives
which field, and render.py fills an in-memory copy of the template (the file on disk is never modified). A renderer
failure is returned, never raised, so the launch package and the other assets are untouched."""
