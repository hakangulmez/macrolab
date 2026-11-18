# MacroLab v2.8.0-beta.3 — English UI and narrated demo

18 November 2026. Maintenance release, explicitly approved by Hakan after previewing the complete Heart-narrated video. Feature development remains frozen.

[MacroLab](https://hakangulmez.github.io/macrolab/) · [Narrated demo and transcript](https://hakangulmez.github.io/macrolab/demo/) · [Case study](https://hakangulmez.github.io/macrolab/case-study/) · [Preserved evaluation record](https://hakangulmez.github.io/macrolab/publication/)

## Approved changes

- Active interface text is English: the home/demo description, navigation label, experimental heading, beta warning and the duplicate comparison notice. On the case-study and publication pages, only Turkish copy was removed or translated; English research prose, numerical results, figures, quotations and limitations are preserved.
- The demo is82seconds:75seconds of genuine browser recording using the existing **Same ECB shock · pooled** template and country/outcome selectors, followed by a clearly separate7-second summary graphic. Germany, France, Italy and Spain are shown sequentially for GDP and prices. Zoom magnifies the existing chart and controls; it adds no application feature.
- The final graphic states **“Summary graphic built from results exported from MacroLab”**. Its values were checked against the actual CSV export. Shading is the existing pooled68% pointwise conditional interval; country confidence bands were not invented.
- The unchanged176-word script is narrated by the locally generated Kokoro `af_heart` preset. Speech lasts81.4305seconds. Eleven caption cues were rebuilt from the exact generated-audio sample boundaries and pauses. Visible captions sit above the player controls; an accessible VTT file and transcript remain available.
- The model is used only to prepare a static media file. No speech API, model weights or new inference dependencies are shipped with the application. No paid speech service was used. [Source voice model](https://huggingface.co/hexgrad/Kokoro-82M).

Approved MP4 SHA-256: `53550a53512917f2c894b7bf52e440cdc3497be19bd3900f9754464466ab6d29`.

## Three preserved local measurements

| Local research-candidate measurement | Complete positive references | Safe negative abstentions | Complete comparisons | Unrejected false premises |
| ------------------------------------ | ---------------------------: | ------------------------: | -------------------: | ------------------------: |
| First20 — initial measurement        |                         7/14 |                       5/6 |                  0/3 |                         1 |
| Same20 — observed **retest**         |                        13/14 |                       6/6 |                  3/3 |                         0 |
| New25 — first final measurement      |                        10/17 |                       4/8 |                  2/5 |                         4 |

**None of these rows measures the currently deployed public search binary.** They are archived measurements of local research candidates. The observed retest is development evidence, not a new independent validation. The new25 failed its acceptance gate; the failed correction remains excluded. No correction round or new semantic benchmark was run for this release. Source references were AI-curated, not independently human-validated. [Immutable measurement records](MAINTENANCE_EVALUATIONS.json).

The visible English warning remains **“Beta; unreliable on questions with false premises.”** All substantive limitations remain visible on the site and in the README.

## Verification and boundaries

The English maintenance code passed284 public-baseline web tests and305 private-checkout tests before the final voice change. The latter include private, unpublished research tests and are not presented as tests of the deployed source. Compiled application assets and page markup remained exact after those checks; only the demo video, caption timing and poster changed. These code-test results are retained rather than relabelled as fresh runs.

The earlier20 desktop/mobile/theme presentation views passed with no horizontal overflow or serious/critical accessibility findings. The approved Heart rendition then passed4 targeted media views and12 sampled native-caption timing checks. The browser served the exact approved MP4 and decoded its mono44.1kHz audio without clipping or player errors. These are media checks, not independent judgements of narration quality.

A fresh run of the existing pooled template in the previous public build and the English preview matched completely after excluding only elapsed timing fields (`runtime_ms` and `template_timing`). All117 protected published resources, including the live search worker, report shards, numerical data and runtime, remain exact. Earlier160,958-field regression evidence is retained with hash proof; the full numerical regression was not rerun.

A clean rebuild must reproduce the complete reviewed site before publication. Exact parent, inventory, remote-head and private-visibility checks guard the fast-forward publication. Public source parent: `ddcdb2b3490d289d7be550e42ae90058ba36eae1`; Pages parent: `446b978f335a3d00c7e3ccc6fd27b41318516db6`.

The old WebM and earlier narration drafts remain preserved in immutable history and local release evidence. The obsolete active WebM is replaced by the approved MP4. Private history, failed private correction code, local voice tools, weights and research archives are excluded from the public package. Portfolio, pre-existing untracked reports, the swap file and `.DS_Store` are outside this release. No force push, tag or GitHub release is requested. Private backup remains private.

Final deployment identifiers, live file hashes and browser checks are recorded in the private release evidence and reported to Hakan after Pages succeeds. Further work remains maintenance only.
