"""Create a small, auditable UI projection from an immutable static snapshot.

No collection, estimation or replacement of source observations. Annual inflation
is the arithmetic mean of twelve monthly y/y percentage changes, using exact
calendar matches. Incomplete years and unavailable prior-year months are omitted.
"""
import argparse
import hashlib
import json
from pathlib import Path


def annual_inflation(rows):
    monthly = {str(r[0])[:7]: float(r[1]) for r in rows if len(str(r[0])) == 7 and str(r[0])[4] == '-' and r[1] is not None}
    years = sorted({int(d[:4]) for d in monthly if int(d[:4]) >= 2000})
    result = []
    for year in years:
        dates = [f'{year}-{month:02d}' for month in range(1, 13)]
        previous = [f'{year-1}-{month:02d}' for month in range(1, 13)]
        if all(d in monthly for d in dates + previous) and all(monthly[d] > 0 for d in previous):
            result.append([year, sum(100 * (monthly[d] / monthly[p] - 1) for d, p in zip(dates, previous)) / 12])
    return result


def create(site, output):
    raw = (site / 'data/manifest.json').read_bytes()
    manifest = json.loads(raw)
    countries, inputs = [], []
    for country in manifest['countries']:
        iso = country['iso3']; entry = manifest['country_files'][iso]
        payload = (site / entry['url']).read_bytes()
        sha = hashlib.sha256(payload).hexdigest()
        assert sha == entry['sha256'], iso
        bundle = json.loads(payload)
        card = next(c for c in bundle['cards'] if c['concept_id'] == 'cpi')
        values = annual_inflation(bundle['series'].get('cpi', [])) if card['frequency'] == 'M' else []
        countries.append(dict(iso3=iso, name=country['name'], values=values, first_date=card['first_date'], sources=card['sources']))
        inputs.append(dict(path=entry['url'], sha256=sha))
    result = dict(snapshot_id=manifest['snapshot_id'], method='Annual mean of monthly year-on-year consumer-price inflation; twelve exact calendar pairs required; complete years only.', unit='Annual-average y/y inflation (%)', countries=countries, input_manifest_sha256=hashlib.sha256(raw).hexdigest(), inputs=inputs)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':'))+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); create(args.site, args.output)
