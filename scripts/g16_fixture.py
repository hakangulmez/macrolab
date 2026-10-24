"""New-snapshot inputs for unchanged template defaults and existing model-view fixtures."""

import json
from pathlib import Path

from macrolab.analysis.config import encode_config
from macrolab.analysis.engine import run_analysis
from macrolab.compare.methods import matched_pair

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g16"


def main():
    folder = OUT / "site/data"
    m = json.loads((folder / "manifest.json").read_text())
    bundle = {
        "schema_version": 1,
        "snapshot_id": m["snapshot_id"],
        "as_of_date": m["as_of_date"],
        "countries": {},
        "variants": json.loads((folder / "global-variants.json").read_text())["variants"],
    }
    for p in (folder / "countries").glob("*.json"):
        d = json.loads(p.read_text())
        cards = {c["concept_id"]: c for c in d["cards"]}
        bundle["countries"][p.stem] = {
            "metadata": d["country"],
            "series": {
                k: {"metadata": cards[k], "observations": v} for k, v in d["series"].items()
            },
        }

    def config(c):
        c = json.loads(
            json.dumps(c),
            parse_float=lambda x: int(float(x)) if float(x).is_integer() else float(x),
        )

        def change(v):
            if isinstance(v, dict):
                for k, x in v.items():
                    if k == "snapshot_id":
                        v[k] = m["snapshot_id"]
                    else:
                        change(x)
            elif isinstance(v, list):
                for x in v:
                    change(x)

        change(c)
        return c

    cases = {t["id"]: config(t["config"]) for t in m["templates"]}
    for group in ["panel", "bvar", "forecast", "diagnostic", "template"]:
        old = json.loads((OUT / "old" / f"{group}-fixture.json").read_text())
        selected = {n: config(c) for n, c in old["cases"].items()}
        f = dict(
            cases=selected, tokens={n: encode_config(c) for n, c in selected.items()}, bundle=bundle
        )
        (OUT / f"{group}-fixture.json").write_text(json.dumps(f) + "\n")
        cases.update(selected)
    for name in ["hd", "crisis"]:
        cases[name] = config(json.loads((OUT / "old" / f"{name}.json").read_text())["config"])
    for name, c in cases.items():
        print("Starting", name, flush=True)
        r = run_analysis(c, bundle)
        (OUT / f"{name}.json").write_text(json.dumps(r, allow_nan=False) + "\n")
        assert r["status"] == "ok", (name, r["checks"])
        if name in ["monetary_policy", "tur_pass_through"]:
            pair = matched_pair(
                r["config"],
                bundle,
                "gdp_real" if name == "monetary_policy" else "cpi",
                c["countries"][0],
            )
            for suffix in [".json"]:
                (OUT / (name + "-methods" + suffix)).write_text(json.dumps(pair) + "\n")
        print(name, r["status"], round(r["runtime_ms"]), flush=True)
    (OUT / "new-fixture-provenance.json").write_text(
        json.dumps(
            dict(
                snapshot_id=m["snapshot_id"],
                source="Static candidate data files; unchanged model/template configurations",
                reference="Native .json results; browser writes separate .browser.json evidence",
                cases=list(cases),
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
