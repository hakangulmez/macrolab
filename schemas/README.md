# JSON contracts

`analysis_config.schema.json` defines the public configuration envelope and
`model_result.schema.json` defines result/check/sample/sensitivity envelopes.
Plugin parameter schemas are returned by the model registry and compatibility API.
`validated_config` additionally enforces bounds, model-specific parameter schemas,
role/ordering membership, frequency-specific defaults and finite JSON values in
both runtimes. No configuration contains executable code.

Configuration hashes use canonical sorted-key compact UTF-8 JSON after explicit
default expansion. Compressed versioned URL tokens contain configuration only;
loading validates decompression size and the same model/input constraints.
