"""Run the whole portfolio: validate every product, run the launch package through QA and every renderer, QA the
rendered markdown, print one table.
Usage: python run_all.py   (from any directory; paths resolve from the project root)
Adding product #51 = adding products/<id>.yaml. This file does not change.
"""
import glob, os, sys, yaml
from validate import validate, ROOT
from qa import run as qa
try:
    from launch.pipeline import run as launch_run
except Exception:                                           # a copy without launch/ (or its deps): the markdown QA still runs
    launch_run = None

NONE = {"package": "—", "landing": "—", "deck": "—"}
rows = []
for path in sorted(glob.glob(os.path.join(ROOT, "products", "*.yaml"))):        # F-26: project root, not the caller's cwd
    try:
        v = validate(path)
    except Exception as e:                                  # F-12: one broken product never ends the portfolio run
        rows.append((os.path.basename(path), "—", "ERROR", "draft", 0, "—", "—", 0, "—", "—", [f"validate crashed: {type(e).__name__}: {e}"]))
        continue
    pid = os.path.basename(str(v["product"]))               # product.id, or the file name when the id is missing
    out = os.path.join(ROOT, "out", pid) + os.sep
    out_root = os.path.realpath(os.path.join(ROOT, "out"))
    d = dict(NONE)
    extra = []
    if v["status"] == "BLOCKED":
        q = {"status": "—", "checks": {}, "fails": []}
    elif not os.path.realpath(out).startswith(out_root + os.sep):       # F-31: never leave out/ (validator already blocks such ids)
        q = {"status": "ERROR", "checks": {}, "fails": [f"output path escapes out/: {out}"]}
    elif not os.path.isdir(out):
        q = {"status": "NOT GENERATED", "checks": {}, "fails": []}
    else:
        if launch_run is None:
            d["package"] = "n/a"
        else:
            # Single source of truth: package QA first, then the renderers (each isolated), then the 32 markdown checks
            try:
                rep = launch_run(path, out)
                d = {"package": (rep["qa"]["status"] if rep["qa"] else rep["package"]), "landing": rep["landing"], "deck": rep["deck"]}
                extra = [e for e in rep["errors"] if not e.startswith("markdown QA:")]
            except Exception as e:
                d = dict(NONE, package="ERROR")
                extra = [f"launch pipeline crashed: {type(e).__name__}: {e}"]
        try:
            q = qa(path, out)
        except Exception as e:
            q = {"status": "ERROR", "checks": {}, "fails": [f"qa crashed: {type(e).__name__}: {e}"]}
        # F-12: record the QA result in provenance only when QA itself could load it
        if q["checks"].get("files_present") == "PASS" and q["checks"].get("provenance_valid") == "PASS":
            prov_path = out + "provenance.yaml"
            try:
                prov = yaml.safe_load(open(prov_path, encoding="utf-8"))
                if isinstance(prov, dict):
                    # SKILL step 8: checks is a mapping (F-21i); fails kept for debugging, [] on PASS (F-22)
                    prov["qa"] = {"status": q["status"], "checks": q["checks"], "fails": q["fails"]}
                    if launch_run is not None:
                        prov["renders"] = dict(d)
                    yaml.safe_dump(prov, open(prov_path, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
            except Exception as e:
                q["fails"].append(f"provenance not updated: {type(e).__name__}: {e}")
    rows.append((pid, os.path.basename(v["brand_layers"]["manufacturer"] or "—"), v["status"],
                 "yes" if v["publishable"] else "draft", len(v["flags"]), d["package"], q["status"], len(q["checks"]),
                 d["landing"], d["deck"], q["fails"] + extra))

if not rows:                                                # F-32: an empty portfolio is a reportable condition
    print(f"no products found in {os.path.join(ROOT, 'products')}", file=sys.stderr)
    sys.exit(1)
w = "{:<28} {:<18} {:<17} {:<8} {:>5}  {:<21} {:<8} {:>6}  {:<10} {:<10}"
print(w.format("product", "manufacturer", "validation", "publish", "flags", "package", "QA", "checks", "landing", "deck"))
print("-" * 142)
for r in rows:
    print(w.format(*r[:10]))
    for f in r[10]:
        print("    ✗", f)
# F-05/F-12: CI exit code. A failed or missing package and a failing markdown QA fail the run; a renderer failure
# (landing / deck) is reported but never blocks the pipeline (the package and the other assets are kept).
OK_PACKAGE = ("passed", "passed_with_warnings", "not_ready", "n/a", "—")   # not_ready: content valid, final assets withheld until the approved image exists
sys.exit(0 if rows and all(r[2] not in ("BLOCKED", "ERROR") and r[6] == "PASS" and r[5] in OK_PACKAGE for r in rows) else 1)
