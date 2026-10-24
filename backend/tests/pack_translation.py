"""Shape fake translations the way a pack-guided translator answers a lesson.

Lessons pass their language pack (``language_context``); the translation must then
follow the pack's policies: each object an article and gender where the language
has them, every term a native display, and a romanization where the pack requires one.
I-Spy games and rooms translate without a pack, so their answers stay unchanged.
"""

_GENDERS = {"el": "masculine", "la": "feminine", "le": "masculine", "der": "masculine",
            "die": "feminine", "das": "neuter"}


def pack_shaped(data: dict, options: dict) -> dict:
    """``data`` (objects/attributes/relationships rows) for a pack lesson when one asks."""
    context = options.get("language_context")
    if context is None:
        return data
    settings = context.display

    def shaped(field, term):
        term = dict(term)
        if field == "objects" and settings.articles != "none":
            term["article"] = term.get("article") or "la"
            term["gender"] = term.get("gender") or _GENDERS.get(term["article"], "feminine")
        elif field == "objects":
            term["article"] = term["gender"] = None
        if field == "objects" and term.get("article"):
            term["nativeDisplay"] = f"{term['article']} {term['translation']}"
        else:
            term["nativeDisplay"] = term["translation"]
        if settings.romanization_required:
            term["romanization"] = term.get("romanization") or "ah"
        return term

    return {field: [shaped(field, term) for term in data.get(field, [])]
            for field in ("objects", "attributes", "relationships")}
