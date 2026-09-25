"""Negative control: tests/landing_with_planted_errors.md must FAIL QA (README: "landing_with_planted_errors.md (QA FAIL)").
Run from the project root:  python -m unittest tests.test_planted
"""
import os, shutil, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
from qa import run   # noqa: E402

PID = "gessi-77201"


class TestPlantedErrors(unittest.TestCase):
    def test_planted_landing_fails(self):
        out = tempfile.mkdtemp(prefix="mody_planted_", dir=ROOT) + os.sep
        try:
            for a in ("deck.md", "sales.md", "provenance.yaml"):
                shutil.copy(f"out/{PID}/{a}", out + a)
            shutil.copy("tests/landing_with_planted_errors.md", out + "landing.md")
            r = run(f"products/{PID}.yaml", out)
            self.assertEqual(r["status"], "FAIL")
            for c in ("voice_landing.md", "flags_in_landing.md", "price_exact", "no_invented_numbers"):
                self.assertEqual(r["checks"].get(c), "FAIL", f"{c} should catch a planted error: {r['fails']}")
        finally:
            shutil.rmtree(out, ignore_errors=True)

    def test_broken_example_is_blocked(self):
        from validate import validate
        self.assertEqual(validate("tests/broken_example.yaml")["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
