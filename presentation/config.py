"""Central configuration for presentation generation. Paths resolve from the project root (never the caller's cwd)."""
import os
from validate import ROOT

# The fixed MODY template. Override with MODY_PRESENTATION_TEMPLATE for a different (e.g. official) file.
TEMPLATE_PATH = os.environ.get("MODY_PRESENTATION_TEMPLATE") or os.path.join(ROOT, "templates", "MODY_GTM_Product_Launch_Template.pptx")

DECK_SUFFIX = "_MODY_GTM_Deck.pptx"              # fallback name when launch.deck does not pass one (launch.pptx)

# Error / warning codes
TEMPLATE_NOT_FOUND = "PRESENTATION_TEMPLATE_NOT_FOUND"
RENDER_FAILED = "PRESENTATION_RENDER_FAILED"
IMAGE_MISSING = "PRESENTATION_IMAGE_MISSING"
TEXT_OVERFLOW_RISK = "PRESENTATION_TEXT_OVERFLOW_RISK"
