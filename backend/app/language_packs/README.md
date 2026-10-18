# Language-pack foundation

This package defines strict contracts for opt-in language packs, lesson capability
plans, deterministic structural checks, reviewed-form assessment, and sentence-tile
assembly. It is intentionally not imported by the application runtime and no packs
are loaded unless a caller explicitly supplies pack roots.

Packs live at `<root>/<locale>/<register>/` (for example `packs/es-ES/everyday/`). `pack.toml`
holds metadata and references every content file: `labels.toml` (fixed learner-facing text keyed by
semantic IDs), `constructions/*.toml` (grammar guidance, features, constraints, version),
`examples/*.toml` (scene facts, bindings, sentences, chunks, alternatives, contrasts, mistakes) and
`evaluations/*.toml` (held-out cases per mission level). Evaluations are loaded only through
`load_evaluation_cases` and never appear in guidance or cache fingerprints. Release configuration and
evaluation reports are kept outside packs. The preview CLI validates and prints local plans without
accessing a database, calling a model, or writing output files (run from `backend/`):

```sh
python -m app.language_packs.preview validate --pack-dir app/language_packs/packs/es-ES/everyday
python -m app.language_packs.preview capability --pack-dir app/language_packs/packs/es-ES/everyday --language es --register everyday
python -m app.language_packs.preview plan --pack-dir app/language_packs/packs/es-ES/everyday --language es --register everyday --level A0 --scene scene.json
```

Release allowlists are explicit and default to empty. Structural validation checks
references, reviewed vocabulary forms, labels, chunk reconstruction, and Unicode
normalization; it does not infer meaning, grammaticality, or learner readiness.

The fixture pack is unreviewed test data and is not a claim of linguistic validation.
