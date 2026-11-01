# Mission cheatsheets

Create one language folder and one TOML file for every supported mission version. The
loader ignores this README and reads `*/*.toml` files only.

Example path for the first Korean M01 A1 sheet:

```text
ko/M01-A1.toml
```

Use the schema in `app/schemas/learning_resources.py`. A concept's `concept_id` must
match a target ID or language-pattern ID in the corresponding mission definition.

An A0 activity may use the single available A0 sheet for its mission and language even
when the activity and learning-resource content versions differ. If more than one A0
sheet exists for that mission and language, callers must request an exact version.
