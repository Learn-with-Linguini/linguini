"""Gold translations for the scene vocabulary, with article and gender.

This is the reference data the translation eval scores against. It is kept
apart from the cases because the same English word is translated by many cases
and duplicating "chair -> la chaise, feminine" into each of them would
guarantee the copies drift.

A word can have more than one right answer. "shelf" is *el estante* or *la
estantería*, and those differ in gender -- so gender is never checked in the
abstract, only against the reading the model actually chose. Checking it
absolutely would mark a correct translation wrong.

Two entries are here specifically because they break the pattern a model is
likely to have memorised:

- ``bean`` in French is *le haricot*, not *l'haricot*: the h is aspirated, so
  the article does not elide.
- ``water`` in Spanish is *el agua*, and the noun is still feminine. Article
  and gender genuinely disagree, which is why the schema carries them as
  separate fields.

Only entries we are confident about belong here. A wrong gold answer is worse
than a missing one: it silently penalises the correct model.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Reading:
    """One acceptable translation of an English word, with its own grammar.

    ``article`` and ``gender`` describe *this* reading. A different acceptable
    reading of the same word may carry different values.
    """

    translation: str
    article: str
    gender: str


# English noun -> acceptable readings, best first.
FRENCH_NOUNS: dict[str, tuple[Reading, ...]] = {
    "desk": (Reading("bureau", "le", "masculine"),),
    "table": (Reading("table", "la", "feminine"),),
    "chair": (Reading("chaise", "la", "feminine"),),
    "globe": (Reading("globe", "le", "masculine"),),
    "book": (Reading("livre", "le", "masculine"),),
    "bookshelf": (
        Reading("étagère", "l'", "feminine"),
        Reading("bibliothèque", "la", "feminine"),
    ),
    "shelf": (
        Reading("étagère", "l'", "feminine"),
        Reading("rayon", "le", "masculine"),
    ),
    "window": (Reading("fenêtre", "la", "feminine"),),
    "door": (Reading("porte", "la", "feminine"),),
    "notebook": (Reading("cahier", "le", "masculine"),),
    "pencil case": (Reading("trousse", "la", "feminine"),),
    "backpack": (Reading("sac à dos", "le", "masculine"),),
    "bag": (Reading("sac", "le", "masculine"),),
    "water bottle": (
        Reading("bouteille", "la", "feminine"),
        Reading("gourde", "la", "feminine"),
    ),
    "cup": (Reading("tasse", "la", "feminine"),),
    "spoon": (Reading("cuillère", "la", "feminine"),),
    "clock": (Reading("horloge", "l'", "feminine"),),
    "plant": (Reading("plante", "la", "feminine"),),
    "apple": (Reading("pomme", "la", "feminine"),),
    "orange": (Reading("orange", "l'", "feminine"),),
    "pear": (Reading("poire", "la", "feminine"),),
    "tomato": (Reading("tomate", "la", "feminine"),),
    "potato": (Reading("pomme de terre", "la", "feminine"),),
    "onion": (Reading("oignon", "l'", "masculine"),),
    "garlic": (Reading("ail", "l'", "masculine"),),
    "egg": (Reading("œuf", "l'", "masculine"),),
    # Aspirated h: the article does not elide.
    "bean": (Reading("haricot", "le", "masculine"),),
    "basket": (Reading("panier", "le", "masculine"),),
    "shopping basket": (Reading("panier", "le", "masculine"),),
    "crate": (
        Reading("cagette", "la", "feminine"),
        Reading("caisse", "la", "feminine"),
    ),
    "box": (
        Reading("boîte", "la", "feminine"),
        Reading("carton", "le", "masculine"),
    ),
    "bin": (Reading("poubelle", "la", "feminine"),),
    "doormat": (Reading("paillasson", "le", "masculine"),),
    "sign": (Reading("panneau", "le", "masculine"),),
    "light": (
        Reading("lumière", "la", "feminine"),
        Reading("lampe", "la", "feminine"),
    ),
    "floor": (Reading("sol", "le", "masculine"),),
    "wall": (Reading("mur", "le", "masculine"),),
    "ceiling": (Reading("plafond", "le", "masculine"),),
    "water": (Reading("eau", "l'", "feminine"),),
}

SPANISH_NOUNS: dict[str, tuple[Reading, ...]] = {
    "desk": (
        Reading("escritorio", "el", "masculine"),
        Reading("pupitre", "el", "masculine"),
    ),
    "table": (Reading("mesa", "la", "feminine"),),
    "chair": (Reading("silla", "la", "feminine"),),
    "globe": (Reading("globo", "el", "masculine"),),
    "book": (Reading("libro", "el", "masculine"),),
    "bookshelf": (Reading("estantería", "la", "feminine"),),
    "shelf": (
        Reading("estante", "el", "masculine"),
        Reading("estantería", "la", "feminine"),
    ),
    "window": (Reading("ventana", "la", "feminine"),),
    "door": (Reading("puerta", "la", "feminine"),),
    "notebook": (Reading("cuaderno", "el", "masculine"),),
    "pencil case": (Reading("estuche", "el", "masculine"),),
    "backpack": (Reading("mochila", "la", "feminine"),),
    "bag": (Reading("bolsa", "la", "feminine"),),
    "water bottle": (Reading("botella", "la", "feminine"),),
    "cup": (Reading("taza", "la", "feminine"),),
    "spoon": (Reading("cuchara", "la", "feminine"),),
    "clock": (Reading("reloj", "el", "masculine"),),
    "plant": (Reading("planta", "la", "feminine"),),
    "apple": (Reading("manzana", "la", "feminine"),),
    "orange": (Reading("naranja", "la", "feminine"),),
    "pear": (Reading("pera", "la", "feminine"),),
    "tomato": (Reading("tomate", "el", "masculine"),),
    "potato": (
        Reading("patata", "la", "feminine"),
        Reading("papa", "la", "feminine"),
    ),
    "onion": (Reading("cebolla", "la", "feminine"),),
    "garlic": (Reading("ajo", "el", "masculine"),),
    "egg": (Reading("huevo", "el", "masculine"),),
    "bean": (
        Reading("judía", "la", "feminine"),
        Reading("frijol", "el", "masculine"),
        Reading("alubia", "la", "feminine"),
    ),
    "basket": (
        Reading("cesta", "la", "feminine"),
        Reading("canasta", "la", "feminine"),
    ),
    "shopping basket": (Reading("cesta", "la", "feminine"),),
    "crate": (
        Reading("caja", "la", "feminine"),
        Reading("cajón", "el", "masculine"),
    ),
    "box": (Reading("caja", "la", "feminine"),),
    "bin": (Reading("papelera", "la", "feminine"),),
    "doormat": (Reading("felpudo", "el", "masculine"),),
    "sign": (
        Reading("letrero", "el", "masculine"),
        Reading("cartel", "el", "masculine"),
    ),
    "light": (Reading("luz", "la", "feminine"),),
    "floor": (Reading("suelo", "el", "masculine"),),
    "wall": (Reading("pared", "la", "feminine"),),
    "ceiling": (Reading("techo", "el", "masculine"),),
    # Feminine noun that takes "el" in the singular: article and gender
    # genuinely disagree.
    "water": (Reading("agua", "el", "feminine"),),
}

NOUNS: dict[str, dict[str, tuple[Reading, ...]]] = {
    "fr": FRENCH_NOUNS,
    "es": SPANISH_NOUNS,
}

# Attributes and relationships carry no article or gender, so they are scored
# as plain accept-lists. Spanish adjectives inflect, and the prompt asks for a
# bare form, so both inflections are accepted.
FRENCH_ATTRIBUTES: dict[str, tuple[str, ...]] = {
    "red": ("rouge",),
    "blue": ("bleu", "bleue"),
    "green": ("vert", "verte"),
    "yellow": ("jaune",),
    "white": ("blanc", "blanche"),
    "black": ("noir", "noire"),
    "brown": ("marron", "brun", "brune"),
    "orange": ("orange",),
    "pink": ("rose",),
    "wooden": ("en bois", "de bois"),
    "metal": ("en métal", "métallique", "de métal"),
    "plastic": ("en plastique", "de plastique"),
    "large": ("grand", "grande"),
    "small": ("petit", "petite"),
    "round": ("rond", "ronde"),
    "open": ("ouvert", "ouverte"),
    "empty": ("vide",),
}

SPANISH_ATTRIBUTES: dict[str, tuple[str, ...]] = {
    "red": ("rojo", "roja"),
    "blue": ("azul",),
    "green": ("verde",),
    "yellow": ("amarillo", "amarilla"),
    "white": ("blanco", "blanca"),
    "black": ("negro", "negra"),
    "brown": ("marrón", "café"),
    "orange": ("naranja", "anaranjado"),
    "pink": ("rosa", "rosado"),
    "wooden": ("de madera",),
    "metal": ("de metal", "metálico"),
    "plastic": ("de plástico",),
    "large": ("grande",),
    "small": ("pequeño", "pequeña"),
    "round": ("redondo", "redonda"),
    "open": ("abierto", "abierta"),
    "empty": ("vacío", "vacía"),
}

ATTRIBUTES: dict[str, dict[str, tuple[str, ...]]] = {
    "fr": FRENCH_ATTRIBUTES,
    "es": SPANISH_ATTRIBUTES,
}

FRENCH_RELATIONS: dict[str, tuple[str, ...]] = {
    "on": ("sur",),
    "under": ("sous",),
    "left_of": ("à gauche de", "a gauche de"),
    "right_of": ("à droite de", "a droite de"),
    "above": ("au-dessus de", "au dessus de"),
    "below": ("en dessous de", "au-dessous de"),
    "inside": ("dans", "à l'intérieur de"),
    "in_front_of": ("devant",),
    "behind": ("derrière", "derriere"),
    "next_to": ("à côté de", "a cote de"),
    "near": ("près de", "pres de", "proche de"),
}

SPANISH_RELATIONS: dict[str, tuple[str, ...]] = {
    "on": ("sobre", "en", "encima de"),
    "under": ("debajo de", "bajo"),
    "left_of": ("a la izquierda de",),
    "right_of": ("a la derecha de",),
    "above": ("encima de", "arriba de", "sobre"),
    "below": ("debajo de", "abajo de"),
    "inside": ("dentro de", "en"),
    "in_front_of": ("delante de", "frente a"),
    "behind": ("detrás de", "detras de"),
    "next_to": ("al lado de", "junto a"),
    "near": ("cerca de",),
}

RELATIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "fr": FRENCH_RELATIONS,
    "es": SPANISH_RELATIONS,
}

SUPPORTED_LANGUAGES = ("fr", "es")

LANGUAGE_NAMES = {"fr": "French", "es": "Spanish"}
