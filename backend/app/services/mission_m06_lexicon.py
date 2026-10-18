"""Closed, reviewed vocabulary for the M06 A2 request role-play."""

import re
from dataclasses import dataclass

EXCLUDED = frozenset({
    "sky", "road", "street", "building", "house", "tree", "person", "man",
    "woman", "child", "people", "wall", "floor", "ceiling", "window", "grass",
    "mountain", "cloud", "sea", "scenery", "table", "chair",
})


@dataclass(frozen=True)
class M06Item:
    key: str
    label: str
    category: str
    nouns: dict
    aliases: tuple[str, ...] = ()


ITEMS = {
    "coffee": M06Item("coffee", "coffee", "cafe", {
        "es": ("café", "cafés", "masculine"), "fr": ("café", "cafés", "masculine"),
        "de": ("Kaffee", "Kaffees", "masculine"), "ko": ("커피", "잔"),
    }),
    "tea": M06Item("tea", "tea", "cafe", {
        "es": ("té", "tés", "masculine"), "fr": ("thé", "thés", "masculine"),
        "de": ("Tee", "Tees", "masculine"), "ko": ("차", "잔"),
    }),
    "juice": M06Item("juice", "juice", "cafe", {
        "es": ("zumo", "zumos", "masculine"), "fr": ("jus", "jus", "masculine"),
        "de": ("Saft", "Säfte", "masculine"), "ko": ("주스", "잔"),
    }),
    "sandwich": M06Item("sandwich", "sandwich", "cafe", {
        "es": ("sándwich", "sándwiches", "masculine"),
        "fr": ("sandwich", "sandwichs", "masculine"),
        "de": ("Sandwich", "Sandwiches", "neuter"), "ko": ("샌드위치", "개"),
    }),
    "croissant": M06Item("croissant", "croissant", "cafe", {
        "es": ("cruasán", "cruasanes", "masculine"),
        "fr": ("croissant", "croissants", "masculine"),
        "de": ("Croissant", "Croissants", "neuter"), "ko": ("크루아상", "개"),
    }),
    "apple": M06Item("apple", "apple", "shop", {
        "es": ("manzana", "manzanas", "feminine"), "fr": ("pomme", "pommes", "feminine"),
        "de": ("Apfel", "Äpfel", "masculine"), "ko": ("사과", "개"),
    }),
    "banana": M06Item("banana", "banana", "shop", {
        "es": ("plátano", "plátanos", "masculine"), "fr": ("banane", "bananes", "feminine"),
        "de": ("Banane", "Bananen", "feminine"), "ko": ("바나나", "개"),
    }),
    "pen": M06Item("pen", "pen", "classroom", {
        "es": ("bolígrafo", "bolígrafos", "masculine"), "fr": ("stylo", "stylos", "masculine"),
        "de": ("Stift", "Stifte", "masculine"), "ko": ("펜", "자루"),
    }, ("ballpoint pen",)),
    "pencil": M06Item("pencil", "pencil", "classroom", {
        "es": ("lápiz", "lápices", "masculine"), "fr": ("crayon", "crayons", "masculine"),
        "de": ("Bleistift", "Bleistifte", "masculine"), "ko": ("연필", "자루"),
    }),
    "notebook": M06Item("notebook", "notebook", "classroom", {
        "es": ("cuaderno", "cuadernos", "masculine"), "fr": ("cahier", "cahiers", "masculine"),
        "de": ("Heft", "Hefte", "neuter"), "ko": ("공책", "권"),
    }),
    "book": M06Item("book", "book", "classroom", {
        "es": ("libro", "libros", "masculine"), "fr": ("livre", "livres", "masculine"),
        "de": ("Buch", "Bücher", "neuter"), "ko": ("책", "권"),
    }),
    "cup": M06Item("cup", "cup", "home", {
        "es": ("taza", "tazas", "feminine"), "fr": ("tasse", "tasses", "feminine"),
        "de": ("Tasse", "Tassen", "feminine"), "ko": ("컵", "개"),
    }, ("mug", "coffee cup")),
    "plate": M06Item("plate", "plate", "home", {
        "es": ("plato", "platos", "masculine"), "fr": ("assiette", "assiettes", "feminine"),
        "de": ("Teller", "Teller", "masculine"), "ko": ("접시", "개"),
    }),
    "umbrella": M06Item("umbrella", "umbrella", "home", {
        "es": ("paraguas", "paraguas", "masculine"),
        "fr": ("parapluie", "parapluies", "masculine"),
        "de": ("Regenschirm", "Regenschirme", "masculine"), "ko": ("우산", "개"),
    }),
}

_ALIASES = {
    alias: item.key for item in ITEMS.values() for alias in (*item.aliases, item.key)
}


def normalize_item_label(label):
    """Normalize only the reviewed English labels and their approved aliases."""
    if not isinstance(label, str):
        return None
    value = re.sub(r"^(?:a|an|the)\s+", "", label.strip().casefold())
    if value in EXCLUDED:
        return None
    if value in _ALIASES:
        return _ALIASES[value]
    return _ALIASES.get(value[:-1]) if value.endswith("s") else None


def requestable_objects(objects):
    """Return confirmed requestable objects in the supplied review-marker order."""
    result = []
    for obj in objects:
        key = normalize_item_label(getattr(obj, "label", None))
        if key:
            result.append((obj, ITEMS[key]))
    return result
