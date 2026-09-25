"""CLI for the launch package.
  python -m launch generate --name "<product name>" --url <supplier product page> --image <approved image>
                            [--id <id>] [--brand <id>] [--category <category>] [--price-ils N --price-tier core|premium|signature]
                            [--engine auto|rules|claude] [--force]
      the whole pipeline from the three GTM inputs: fetch + extract facts -> products/<id>.yaml -> validate ->
      content engine -> out/<id>/launch_package.yaml -> package QA + readiness -> landing.html + launch.pptx -> generation_report.json
  python -m launch intake <id> --name "<product name>" --url <supplier product page> --image <approved image path>
                          [--brand <brand id>] [--category <category>]     # writes products/<id>.yaml (inputs only, no facts invented)
  python -m launch skeleton products/<id>.yaml            # facts + structure prefilled -> the Skill fills the derived fields
  python -m launch qa products/<id>.yaml [out/<id>/]      # validate out/<id>/launch_package.yaml only
  python -m launch run products/<id>.yaml [out/<id>/]     # QA, then render landing.md/html, deck.md, sales.md, provenance.yaml, launch.pptx
"""
import os, sys, yaml
from validate import ROOT
from launch import package as P
from launch import qa as pkgqa
from launch import pipeline


def intake(argv):
    """The GTM inputs (product name, supplier URL, approved product image) -> products/<id>.yaml. Nothing else is
    written: every technical field starts null (a validator flag), so no fact exists before it is extracted from the
    supplier page and sourced (SKILL step 0). The brand is taken from --brand or the supplier host when a brand file
    exists; the category must be given (validator BLOCKED otherwise)."""
    import argparse, glob, urllib.parse
    ap = argparse.ArgumentParser(prog="python -m launch intake")
    ap.add_argument("id"); ap.add_argument("--name", required=True); ap.add_argument("--url", required=True)
    ap.add_argument("--image", required=True); ap.add_argument("--brand"); ap.add_argument("--category")
    ap.add_argument("--approved", action="store_true", help="MODY has approved the image (sources.image_approved)")
    a = ap.parse_args(argv)
    brands = {os.path.basename(f).split(".v")[0] for f in glob.glob(os.path.join(ROOT, "brand", "*.v*.yaml"))} - {"mody_brand_dna"}
    host = urllib.parse.urlparse(a.url).hostname or ""
    brand = a.brand or next((b for b in sorted(brands) if b in host), None)
    path = os.path.join(ROOT, "products", f"{a.id}.yaml")
    if os.path.exists(path):
        print(f"exists: {path}", file=sys.stderr)
        return 1
    doc = {"product": {"id": a.id, "name": a.name, "brand": brand, "collection": None, "line": None, "category": a.category, "model_number": None},
           "technical": {}, "design": {"signature_material": None, "claims_ref": []},
           "commercial": {"price_ils": None, "price_tier": None},
           "sources": {"product_page": a.url, "technical_sheet": None, "image": a.image, "image_approved": bool(a.approved)}}
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# intake: inputs only. SKILL step 0 extracts the facts from sources.product_page; every value needs a source.\n")
        yaml.safe_dump(doc, fh, allow_unicode=True, sort_keys=False)
    print(path)
    print("next: SKILL step 0 (extract + source the facts), then python validate.py " + os.path.relpath(path, ROOT))
    if not brand:
        print(f"note: no brand file matched {host!r}; set product.brand (brand/<brand>.v*.yaml must exist)", file=sys.stderr)
    if not a.category:
        print("note: product.category is required by the validator", file=sys.stderr)
    return 0


def generate(argv):
    """Product name + supplier URL + approved image -> every asset, no intermediate editing."""
    import argparse, json, re
    from validate import validate
    from launch import extract as X, content_engine as CE, qa as pkgqa
    ap = argparse.ArgumentParser(prog="python -m launch generate")
    ap.add_argument("--name", required=True); ap.add_argument("--url", required=True); ap.add_argument("--image", required=True)
    ap.add_argument("--id"); ap.add_argument("--brand"); ap.add_argument("--category")
    ap.add_argument("--price-ils", type=float); ap.add_argument("--price-tier", choices=["core", "premium", "signature"])
    ap.add_argument("--engine", choices=["auto", "rules", "claude"], default="auto")
    ap.add_argument("--force", action="store_true", help="overwrite an existing products/<id>.yaml and out/<id>/")
    ap.add_argument("--out-root", default=os.path.join(ROOT, "out"), help=argparse.SUPPRESS)
    ap.add_argument("--products-root", default=os.path.join(ROOT, "products"), help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    report = {"inputs": {"name": a.name, "url": a.url, "image": a.image}, "stages": {}}
    # 1-4. fetch, extract, normalise, provenance
    try:
        ex = X.extract(a.url, a.name)
    except Exception as e:
        report["stages"]["extraction"] = f"failed: {type(e).__name__}: {e}"
        print(json.dumps(report, ensure_ascii=False, indent=2)); return 1
    brand = a.brand or (ex["brand"] or {}).get("value")
    pid = a.id or re.sub(r"[^a-z0-9]+", "-", f"{brand or 'product'}-{(ex['facts'].get('model_number') or ex['facts'].get('sku') or {}).get('value') or a.name}".lower()).strip("-")
    ppath = os.path.join(a.products_root, f"{pid}.yaml")
    out_dir = os.path.join(a.out_root, pid) + os.sep
    if os.path.exists(ppath) and not a.force:
        print(f"exists: {ppath} (use --force to regenerate)", file=sys.stderr); return 1
    doc = X.product_file(pid, a.name, a.url, a.image, ex, brand=brand, category=a.category, price_ils=a.price_ils, price_tier=a.price_tier)
    os.makedirs(os.path.dirname(ppath), exist_ok=True)
    with open(ppath, "w", encoding="utf-8") as fh:
        fh.write("# generated by `python -m launch generate`: facts extracted from sources.product_page (evidence per field); no value without a source\n")
        yaml.safe_dump(doc, fh, allow_unicode=True, sort_keys=False)
    report["stages"]["extraction"] = {"product_file": ppath, "facts": sorted(ex["facts"]), "category": ex["category"], "brand": ex["brand"], "line": ex["line"], "unmapped": ex["unmapped"][:10]}
    v = validate(ppath)
    report["stages"]["validation"] = {"status": v["status"], "errors": v["errors"], "flags": v["flags"], "publishable": v["publishable"]}
    os.makedirs(out_dir, exist_ok=True)
    if v["status"] == "BLOCKED":
        report["result"] = "blocked"
        _write_report(out_dir, report); print(yaml.safe_dump(report, allow_unicode=True, sort_keys=False)); return 1
    # 5-6. content engine -> canonical package
    ctx = P.load_context(ppath, out_dir)
    pkg, crep = CE.generate(ctx, engine=a.engine)
    P.dump(pkg, os.path.join(out_dir, P.PACKAGE_FILE))
    report["stages"]["content"] = crep
    # 7-12. package QA, readiness, renderers, final QA, report (launch.pipeline)
    r = pipeline.run(ppath, out_dir)
    report["stages"]["pipeline"] = {k: r[k] for k in ("package", "readiness", "landing", "markdown", "deck", "markdown_qa", "files", "errors", "warnings")}
    report["stages"]["pipeline"]["qa"] = r["qa"]["status"] if r["qa"] else None
    ok = r["package"] == "generated" and r["landing"] == "generated" and r["deck"] == "generated" and r["markdown_qa"] == "PASS"
    report["result"] = "generated" if ok else ("not_ready" if (r.get("readiness") or {}).get("status") == "not_ready" else "failed")
    _write_report(out_dir, report)
    print(yaml.safe_dump({"product": pid, "result": report["result"], "engine": crep["engine"], "fallback": crep["fallback"],
                          "package_qa": report["stages"]["pipeline"]["qa"], "files": r["files"], "errors": r["errors"]}, allow_unicode=True, sort_keys=False, width=120))
    return 0 if ok else 1


def _write_report(out_dir, report):
    """generate_report.json next to generation_report.json: the intake-to-package stages (the pipeline writes its own)."""
    import json
    with open(os.path.join(out_dir, "generate_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, default=str)


def main(argv):
    if argv and argv[0] == "generate":
        return generate(argv[1:])
    if argv and argv[0] == "intake":
        return intake(argv[1:])
    if len(argv) < 2 or argv[0] not in ("skeleton", "qa", "run"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    cmd, product_path = argv[0], argv[1]
    pid = os.path.basename(product_path)[:-len(".yaml")] if product_path.endswith(".yaml") else os.path.basename(product_path)
    out_dir = argv[2] if len(argv) > 2 else os.path.join(ROOT, "out", pid) + os.sep
    ctx = P.load_context(product_path, out_dir)
    if ctx["v"]["status"] == "BLOCKED":
        print("BLOCKED: " + "; ".join(ctx["v"]["errors"]), file=sys.stderr)
        return 1
    if cmd == "skeleton":
        print(yaml.safe_dump(P.skeleton(ctx), allow_unicode=True, sort_keys=False, width=110))
        return 0
    if cmd == "qa":
        r = pkgqa.run(P.load_package(out_dir), ctx)
        print(yaml.safe_dump(r, allow_unicode=True, sort_keys=False, width=120))
        return 0 if r["status"] != "failed" else 1
    r = pipeline.run(product_path, out_dir)
    print(yaml.safe_dump({k: r[k] for k in ("product", "package", "landing", "markdown", "deck", "markdown_qa", "files", "warnings", "errors")}
                         | {"qa": r["qa"]["status"] if r["qa"] else None}, allow_unicode=True, sort_keys=False, width=120))
    return 0 if r["package"] == "generated" and not r["errors"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
