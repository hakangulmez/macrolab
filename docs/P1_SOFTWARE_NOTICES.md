# P1 software notices — local inventory

**P2 adds the exact pinned Pyodide/CPython notices and source-access information.** The P1 inventory below remains the record for JavaScript, fonts and the nine scientific wheels. P1 performed no download; the separately approved P2 retrieval is documented at the end. Labels below are the packages’ own declarations, not an independent licence opinion. Publication remains a separate owner decision.

## Ready from local files

These files are copied into both static candidates under `licences/`, keeping each package’s notices together. The SHA-256 is over the exact existing notice bytes. The full manifest, target paths and byte counts are in ignored `runs/p1/software-notices-inventory.json`. Actual app imports were used to select the closure; development-only Playwright/axe tooling is not shipped as a browser dependency.

| Package/version | Declared licence | Exact local file | SHA-256 |
|---|---|---|---|
| MacroLab 0.4.0 | MIT | `LICENSE` | `b24c40a6d21394f343679ae6f6b9f21badda00b2af12110322d14f257473188d` |
| react 19.3.1 | MIT | `web/node_modules/react/LICENSE` | `da6d3703ed11cbe42bd212c725957c98da23cbff1998c05fa4b3d976d1a58e93` |
| react-dom 19.3.1 | MIT | `web/node_modules/react-dom/LICENSE` | `da6d3703ed11cbe42bd212c725957c98da23cbff1998c05fa4b3d976d1a58e93` |
| scheduler 0.28.0 | MIT | `web/node_modules/scheduler/LICENSE` | `da6d3703ed11cbe42bd212c725957c98da23cbff1998c05fa4b3d976d1a58e93` |
| echarts 6.1.0 | Apache-2.0 | `web/node_modules/echarts/LICENSE` | `634293835b43a6dd2094fa39182a3d9a6b9ca43b7fdb9ac354e8037af2a3093a` |
| echarts 6.1.0 | Apache-2.0 | `web/node_modules/echarts/NOTICE` | `d491d358344f842685c1b1585970999db65fe30ecf7ef3867af8814f4016c016` |
| echarts 6.1.0 | Apache-2.0 | `web/node_modules/echarts/licenses/LICENSE-d3` | `e1211892da0b0e0585b7aebe8f98c1274fba15bafe47fa1f4ee8a7a502c06304` |
| zrender 6.1.0 | BSD-3-Clause | `web/node_modules/zrender/LICENSE` | `a681e9d183c72b4af4856935893805eb48c08f0f5a3f260203db7444c20fb98a` |
| tslib 2.3.0 | 0BSD | `web/node_modules/tslib/LICENSE.txt` | `210b19e543130388c68654b7497e967119ce17145f66ab7d85688fbd70f08751` |
| tslib 2.3.0 | 0BSD | `web/node_modules/tslib/CopyrightNotice.txt` | `dd835e67a9a297da32f9467d7677a5d02c8e50e10f15da43b810147c79c04b9b` |
| ajv 8.20.0 | MIT | `web/node_modules/ajv/LICENSE` | `a05350a88e318e4f5f2c2a1ff1e2e88daa4dd38e6e78b71cccae422bdc762cc3` |
| fflate 0.8.3 | MIT | `web/node_modules/fflate/LICENSE` | `0a1df3a083d0c010560aa342e87959c8c1070e6fd54545741f083f22d0c8b551` |
| fast-deep-equal 3.1.3 | MIT | `web/node_modules/fast-deep-equal/LICENSE` | `7bf9b2de73a6b356761c948d0e9eeb4be6c1270bd04c79cd489c1e400ffdfc1a` |
| fast-uri 3.1.9 | BSD-3-Clause | `web/node_modules/fast-uri/LICENSE` | `b010b0dfdfdb23d7396e03b82cd4621fc9bb8f95d6b0aea70b9c24e12074c786` |
| json-schema-traverse 1.0.0 | MIT | `web/node_modules/json-schema-traverse/LICENSE` | `7bf9b2de73a6b356761c948d0e9eeb4be6c1270bd04c79cd489c1e400ffdfc1a` |
| require-from-string 2.0.2 | MIT | `web/node_modules/require-from-string/license` | `6ee0feb1f6ef996ff5a68600f8cf98909cf412d39ef3cdceaefd87d636fa1b7f` |
| @fontsource/inter 5.3.0 | OFL-1.1 | `web/node_modules/@fontsource/inter/LICENSE` | `3b0a5fca3d17942cde889069889dedbbbd075e9b599968c82a95f4d944e9b345` |
| @fontsource/ibm-plex-mono 5.3.0 | OFL-1.1 | `web/node_modules/@fontsource/ibm-plex-mono/LICENSE` | `23b0a9d0c6d3f140a0b77e483c5cfa6bba574325ef5cb189ed9f2fec4884533f` |

This includes ECharts’ `NOTICE` and embedded d3 notice, tslib’s copyright notice, and the full Inter/IBM Plex Mono OFL texts. The existing application build had no separately named licence/notice files or full licence-text markers in its JS/CSS/HTML; retaining package declarations alone would not address that packaging omission. Candidate-copy integration and readback are recorded separately below.

## Scientific wheels already preserve notices

The candidate prepares the nine pinned wheels byte-for-byte. Every wheel contains its own licence text; NumPy, SciPy and statsmodels also contain notices for bundled components. Their package notice paths and hashes are preserved in the inventory. Retaining the complete wheels retains these files; no wheel contents were stripped or rewritten.

| Wheel | Primary embedded notice |
|---|---|
| numpy 2.4.6 | `numpy-2.4.6.dist-info/licenses/LICENSE.txt` |
| packaging 26.1 | `packaging-26.1.dist-info/licenses/LICENSE` |
| pandas 3.0.2 | `pandas-3.0.2.dist-info/LICENSE` |
| patsy 1.0.2 | `patsy-1.0.2.dist-info/licenses/LICENSE.txt` |
| python-dateutil 2.9.0.post0 | `python_dateutil-2.9.0.post0.dist-info/LICENSE` |
| pytz 2026.1.post1 | `pytz-2026.1.post1.dist-info/LICENSE.txt` |
| scipy 1.18.0 | `scipy-1.18.0.dist-info/LICENSE.txt` |
| six 1.17.0 | `six-1.17.0.dist-info/LICENSE` |
| statsmodels 0.14.6 | `statsmodels-0.14.6.dist-info/licenses/LICENSE.txt` |

## Gap recorded at P1

**Pinned Pyodide 314.0.7 / CPython 3.14.2 full notices remain unresolved.** The cached official npm package declares `MPL-2.0` and identifies the Pyodide source repository, but the archive contains no full `LICENSE`, `NOTICE` or copyright file. The cached `python_stdlib.zip` also contains no such file. The five selected runtime assets do not supply a complete visible licence/third-party-notice package.

Do not substitute the host’s Python 3.11 notices for the pinned browser Python 3.14.2 runtime. Before publication, obtain and verify the exact runtime’s official full notices, associated component notices and any applicable source-availability information. That retrieval and review is a separate bounded follow-up; it was not performed or requested here. The local notice copies and retained wheel licences do not by themselves close this remaining issue.

## P1 integration state

Independent readback of `runs/p1/cleared/site/` and `runs/p1/all-local-only/site/` verified all 18 copied notice files against the original local files and this inventory, all 14 npm package versions/licence declarations against installed metadata, all nine scientific wheel hashes, and 36 embedded notice hashes. There were no mismatches. Both `licences/manifest.json` files have SHA-256 `d60b89c757138b7c6f4dfa4913d252cd47b8605a0415ee8765c73c9069729b66` and explicitly retain `incomplete_pending_runtime_notice_review` status.

The candidate manifest advertises the relative `licences/manifest.json` location. No software-notice result here approves publication, hosting or deployment.

## P2 pinned-runtime resolution

The approved one-time retrieval obtained the following unmodified official texts on 2026-10-21. The tracked `third_party/runtime/manifest.json` records each immutable URL, resolved URL, UTC retrieval time, byte count and SHA-256. The official release metadata and tag responses are preserved separately in ignored `runs/p2/runtime-notices/`.

| Pinned component and notice | SHA-256 |
|---|---|
| [Pyodide 314.0.7 MPL-2.0 text](https://raw.githubusercontent.com/pyodide/pyodide/b1e4fcc2488962f6360a97f19b9982d6fdb5d16f/LICENSE) | `1f256ecad192880510e84ad60474eab7589218784b9a50bc7ceee34c2b91f1d5` |
| [CPython 3.14.2 licence history and terms](https://raw.githubusercontent.com/python/cpython/df793163d5821791d4e7caf88885a2c11a107986/LICENSE) | `b0e25a78cffb43f4d92de8b61ccfa1f1f98ecbc22330b54b5251e7b6ba010231` |
| [CPython 3.14.2 incorporated-software acknowledgements](https://raw.githubusercontent.com/python/cpython/df793163d5821791d4e7caf88885a2c11a107986/Doc/license.rst) | `c695d550b135e53e38807e76496d1db17d22c40e461d1f3f354c86188d3305dd` |

The official Pyodide `314.0.7` tag and npm `gitHead` both resolve to `b1e4fcc2488962f6360a97f19b9982d6fdb5d16f`; npm integrity exactly matches the existing runtime lock. The annotated CPython `v3.14.2` tag resolves to `df793163d5821791d4e7caf88885a2c11a107986`; 3.14.2 is the Python version declared by that runtime lock. The complete CPython acknowledgement document is retained conservatively, including notices for optional components that may not be in the browser build.

`third_party/runtime/SOURCE_AVAILABILITY.md` identifies the exact corresponding upstream source trees and downloadable archives, including Pyodide's CPython build configuration and patches. MacroLab changes none of the upstream runtime or standard-library bytes. The copy helper checks the runtime versions, npm integrity, notice hashes and path containment before adding this bundle under `licences/runtime/`; ordinary preparation performs no network request. The pre-existing JavaScript/font and scientific-wheel notices remain intact.

Independent P2 artifact readback verified all 23 copied notice files (the prior 18 plus five runtime-bundle files), all nine unchanged scientific wheels, and 36 embedded notice hashes, with zero mismatches. The software manifest has SHA-256 `274cdb557026b7b11f822cfa9c50e426662f687ce6f1c6e1de6a15a2b2127ef7`; the pinned-runtime provenance manifest has SHA-256 `54d1643ac5c359515be6d3e5e4fec4cd9601c9bca3cff44ef6004c47e3dd6e0a`. Its status is `pinned_runtime_notices_packaged` with no remaining runtime notice item. Evidence is in ignored `runs/p2/software-notice-readback.json`; the P1 artifacts remain unchanged.

The bounded missing-notice/source-access item is addressed by this package. This is not a claim that MacroLab independently rebuilt the upstream WebAssembly binary or completed an unrestricted legal certification.
