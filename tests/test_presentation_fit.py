"""The PPTX renderer applies the template's own shrink-on-overflow rule deterministically (presentation.render.shrink_to_fit)."""
import io, os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
try:
    from pptx import Presentation
    HAVE_PPTX = True
except ImportError:
    HAVE_PPTX = False
from presentation import config as cfg, render as R                      # noqa: E402


@unittest.skipUnless(HAVE_PPTX, "python-pptx not installed")
class TestShrinkToFit(unittest.TestCase):
    def shape(self, slide_no, name):
        with open(cfg.TEMPLATE_PATH, "rb") as fh:
            prs = Presentation(io.BytesIO(fh.read()))
        return next(sh for sh in list(prs.slides)[slide_no - 1].shapes if sh.name == name)

    def test_short_text_keeps_the_template_size(self):
        sh = self.shape(7, "Text 17")
        R.fill_text(sh, ["נקודה אחת", "נקודה שנייה"], bullets=True)
        orig, size, still = R.shrink_to_fit(sh, ["נקודה אחת", "נקודה שנייה"])
        self.assertEqual((orig, size, still), (16.0, 16.0, False))

    def test_long_text_is_reduced_until_it_fits_never_below_the_floor(self):
        sh = self.shape(7, "Text 17")
        items = ["זה Jacqueline 77201 של GESSI. הקולקציה הראשונה של Gessi שנוצרה משורשי במבוק אמיתי."] * 4
        R.fill_text(sh, items, bullets=True)
        orig, size, still = R.shrink_to_fit(sh, items)
        self.assertEqual(orig, 16.0); self.assertLess(size, orig); self.assertGreaterEqual(size, max(8.0, orig * 0.55))
        self.assertFalse(R.overflow_risk(sh, items, size)[0] if not still else False)
        sizes = {run.font.size.pt for p in sh.text_frame.paragraphs for run in p.runs}
        self.assertEqual(sizes, {size})                                                        # every run, one size
        impossible = ["א" * 400] * 12
        R.fill_text(sh, impossible, bullets=True)
        orig, size, still = R.shrink_to_fit(sh, impossible)
        self.assertEqual(size, max(8.0, round(orig * 0.55 * 2) / 2)); self.assertTrue(still)  # floor reached, still flagged


if __name__ == "__main__":
    unittest.main()
