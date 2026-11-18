# Ask the reports evaluation

Current beta: `ask-reports-beta.gold.json` and `ask-reports-beta.results.json`. See [beta gate and limitations](../../docs/ASK_THE_REPORTS.md).

The 92 questions comprise 62 observed development, 20 previously held-out and 10 Claude-selected/Hakan-reviewed external cases. All are now regression questions. Original r5/r6/external results are preserved; a retest is not an unseen test.

Ordinary positives require expected evidence in the first five primary results. Comparison questions use the explicitly authorized chronological-list rule, exact references and ascending dates, without a verdict. External IDs remain strict. False-premise questions require `not_found` and empty primary/comparison lists; related context is not credited.

The evaluator uses the shipped static index without a private corpus or model. Internal gold was source-curated by Codex, not independently human validated. The raw archive is needed only for rebuilding shards.
