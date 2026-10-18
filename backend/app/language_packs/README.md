# Language-pack foundation

This package defines strict contracts for opt-in language packs, lesson capability
plans, deterministic structural checks, reviewed-form assessment, and sentence-tile
assembly. It is intentionally not imported by the application runtime and no packs
are loaded unless a caller explicitly supplies pack roots.

Pack directories contain a `pack.toml` file and an optional, separately loaded
`evaluation.toml` file. The preview CLI validates and prints local plans without
accessing a database, calling a model, or writing output files:

```sh
python -m app.language_packs.preview validate --pack-dir tests/fixtures/language_packs/es-basic
python -m app.language_packs.preview capability --pack-dir tests/fixtures/language_packs/es-basic --language es --register everyday
python -m app.language_packs.preview plan --pack-dir tests/fixtures/language_packs/es-basic --language es --register everyday --level A0 --scene scene.json
python -m app.language_packs.preview assemble --pack-dir tests/fixtures/language_packs/es-basic --language es --register everyday --level A0 --scene scene.json --candidates candidates.json
```

Release allowlists are explicit and default to empty. Structural validation checks
references, reviewed vocabulary forms, labels, chunk reconstruction, and Unicode
normalization; it does not infer meaning, grammaticality, or learner readiness.

The fixture pack is unreviewed test data and is not a claim of linguistic validation.
