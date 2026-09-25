"""One product, end to end, never raising:

    launch_package.yaml ──► launch.qa ──(passed)──► render_md · render_product_page (landing.html) · deck (launch.pptx)   (independent; one failing never
                                 │                                                     touches the package or the others)
                                 └──(failed)──► nothing is rendered
    then qa.py (the 32 landing checks) on the rendered markdown, and generation_report.json.

run() -> {"product", "package": generated|missing|invalid|blocked, "qa": <package qa>, "readiness": {status, blockers},
          "landing": generated|render_failed|not_ready|skipped, "markdown": ..., "deck": ..., "markdown_qa": PASS|FAIL|skipped,
          "files": {...}, "errors": [...], "warnings": [...]}
A package whose content is valid but whose approved hero image is missing is `not_ready`: the working markdown assets
are rendered (drafts), the final assets (landing.html, launch.pptx) are withheld and stale copies removed.
"""
import datetime, json, os, traceback, yaml
import qa as mdqa
from launch import package as P
from launch import qa as pkgqa
from launch import render_md, render_product_page, deck

REPORT = "generation_report.json"


def run(product_path, out_dir, template_path=None):
    out_dir = os.path.join(out_dir, "")
    rep = {"product": None, "generated": str(datetime.date.today()), "package": "missing", "qa": None, "readiness": None,
           "landing": "skipped", "markdown": "skipped", "deck": "skipped", "markdown_qa": "skipped",
           "files": {}, "errors": [], "warnings": [], "report": os.path.join(out_dir, REPORT)}
    try:
        ctx = P.load_context(product_path, out_dir)
        rep["product"] = P.get(ctx["p"], "product.id")
        if ctx["v"]["status"] == "BLOCKED":
            rep.update(package="blocked", errors=["validator BLOCKED – " + "; ".join(ctx["v"]["errors"])])
            return _write(rep)
        pkg_path = os.path.join(out_dir, P.PACKAGE_FILE)
        if not os.path.exists(pkg_path):
            rep["errors"].append(f"LAUNCH_PACKAGE_MISSING: {pkg_path} (SKILL step 6)")
            return _write(rep)
        try:
            pkg = P.load_package(out_dir)
        except yaml.YAMLError as e:
            rep.update(package="invalid", errors=[f"LAUNCH_PACKAGE_INVALID: not valid YAML ({type(e).__name__})"])
            return _write(rep)
        # QA on the package, before any renderer; the verdict is written back into the single source of truth
        result = pkgqa.run(pkg, ctx)
        rep["qa"] = result
        if isinstance(pkg, dict):
            pkg["qa"] = {"status": result["status"], "errors": result["errors"], "warnings": result["warnings"]}
            P.dump(pkg, pkg_path)
        rep["warnings"] += [f"{w['code']} {w['field']}: {w['message']}" for w in result["warnings"]]
        if result["status"] == "failed":
            rep.update(package="invalid", errors=[f"{e['code']} {e['field']}: {e['message']}" for e in result["errors"]])
            return _write(rep)
        rep["package"] = "generated"
        ready = result["status"] != "not_ready"
        rep["readiness"] = P.readiness(pkg)
        if not ready:                                       # final assets are withheld, and stale ones never pose as complete
            rep["errors"] += [f"{e['code']} {e['field']}: {e['message']}" for e in result["errors"]]
            for stale in (render_product_page.PAGE_FILE, deck.DECK_FILE):
                if os.path.exists(out_dir + stale):
                    os.remove(out_dir + stale)
        # Renderers: independent, isolated
        try:
            rep["files"]["markdown"] = render_md.render(pkg, ctx, out_dir)
            rep["markdown"] = "generated"
        except Exception as e:
            rep["markdown"] = "render_failed"; rep["errors"].append(f"MARKDOWN_RENDER_FAILED: {type(e).__name__}: {e}")
        if not ready:
            rep["landing"] = rep["deck"] = "not_ready"
        else:
            try:
                pg = render_product_page.render(pkg, out_dir, product_path=product_path)  # landing.html on the MODY Product Page Template
            except Exception as e:
                pg = {"html": None, "warnings": [], "errors": [f"LANDING_RENDER_FAILED: {type(e).__name__}: {e}"]}
            rep["warnings"] += [f"landing {w}" for w in pg["warnings"]]; rep["errors"] += pg["errors"]
            rep["landing"] = "generated" if pg["html"] else "render_failed"
            rep["files"]["landing"] = os.path.basename(pg["html"]) if pg["html"] else None
            try:
                r = deck.render(pkg, out_dir, product_path, template_path=template_path)
            except Exception as e:
                r = {"pptx": None, "warnings": [], "errors": [f"PRESENTATION_RENDER_FAILED: {type(e).__name__}: {e}"]}
            rep["warnings"] += r["warnings"]; rep["errors"] += r["errors"]
            rep["deck"] = "generated" if r["pptx"] else "render_failed"
            rep["files"]["deck"] = os.path.basename(r["pptx"]) if r["pptx"] else None

        # Second gate: the existing 32 checks on the rendered markdown (regression guard for the renderer)
        if rep["markdown"] == "generated":
            try:
                q = mdqa.run(product_path, out_dir)
                rep["markdown_qa"] = q["status"]
                rep["markdown_qa_detail"] = q
                if q["status"] != "PASS":
                    rep["errors"] += [f"markdown QA: {f}" for f in q["fails"]]
            except Exception as e:
                rep["markdown_qa"] = "ERROR"; rep["errors"].append(f"markdown QA crashed: {type(e).__name__}: {e}")
        return _write(rep)
    except Exception as e:
        rep["errors"].append(f"PIPELINE_CRASHED: {type(e).__name__}: {e}")
        rep["trace"] = traceback.format_exc()
        return _write(rep)


def _write(rep):
    try:
        os.makedirs(os.path.dirname(rep["report"]), exist_ok=True)
        with open(rep["report"], "w", encoding="utf-8") as fh:
            json.dump({k: v for k, v in rep.items() if k != "trace"}, fh, ensure_ascii=False, indent=2)
    except Exception as e:
        rep["warnings"].append(f"report not written: {type(e).__name__}: {e}")
    return rep
