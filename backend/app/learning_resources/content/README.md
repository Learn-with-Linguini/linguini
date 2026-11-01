# Learning resource content

This directory contains reviewed reference material shown by the learner UI. Content is
committed with the application so a deployed API and its curriculum always agree.

## Mission cheatsheets

Store one TOML file per mission version and target language:

```text
cheatsheets/<language-code>/<mission-id>-<level>.toml
cheatsheets/<language-code>/<mission-id>-<level>-<content-version>.toml
```

Version 1 omits the version suffix. Each concept must use the ID of a target or language
pattern in the matching file under `app/missions/definitions`. This makes stale or
misspelled curriculum links fail validation.

## Character references

Store reusable writing-system material separately:

```text
character-references/<language-code>/<reference-id>.toml
character-references/<language-code>/<reference-id>-<content-version>.toml
```

A cheatsheet may link to one character reference and to specific section IDs within it.
Languages that use the Latin alphabet do not need a character reference.

The API does not generate or rewrite this content. Add and review each language's files
in source control, then run the backend tests before merging.
