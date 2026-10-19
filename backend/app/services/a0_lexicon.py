"""Reviewed closed content for the A0 scene missions.

Every noun form, gender, French elision and Korean final consonant here was
reviewed by hand; nothing is inferred from English, the photo, colour or spelling.
An object takes part in an A0 mission only when its English label is listed here.
"""

from __future__ import annotations

from dataclasses import dataclass

A0_LANGUAGES = ("es", "fr", "de", "ko")


@dataclass(frozen=True)
class Noun:
    noun: str
    # "masculine" / "feminine" / "neuter"; ``None`` for Korean, which has no gender.
    gender: str | None
    plural: str
    # French: the definite form elides to l' (reviewed pronunciation, e.g. h muet).
    elides: bool = False
    # Korean: the noun ends in a final consonant (batchim).
    batchim: bool = False


def _n(noun, gender, plural, *, elides=False):
    return Noun(noun, gender, plural, elides=elides)


def _ko(noun, batchim):
    return Noun(noun, None, noun, batchim=batchim)


M, F, N = "masculine", "feminine", "neuter"

REVIEWED_NOUNS: dict[str, dict[str, Noun]] = {
    "cup": dict(es=_n("taza", F, "tazas"), fr=_n("tasse", F, "tasses"),
                de=_n("Tasse", F, "Tassen"), ko=_ko("컵", True)),
    "table": dict(es=_n("mesa", F, "mesas"), fr=_n("table", F, "tables"),
                  de=_n("Tisch", M, "Tische"), ko=_ko("테이블", True)),
    "book": dict(es=_n("libro", M, "libros"), fr=_n("livre", M, "livres"),
                 de=_n("Buch", N, "Bücher"), ko=_ko("책", True)),
    "apple": dict(es=_n("manzana", F, "manzanas"), fr=_n("pomme", F, "pommes"),
                  de=_n("Apfel", M, "Äpfel"), ko=_ko("사과", False)),
    "chair": dict(es=_n("silla", F, "sillas"), fr=_n("chaise", F, "chaises"),
                  de=_n("Stuhl", M, "Stühle"), ko=_ko("의자", False)),
    "plant": dict(es=_n("planta", F, "plantas"), fr=_n("plante", F, "plantes"),
                  de=_n("Pflanze", F, "Pflanzen"), ko=_ko("식물", True)),
    "lamp": dict(es=_n("lámpara", F, "lámparas"), fr=_n("lampe", F, "lampes"),
                 de=_n("Lampe", F, "Lampen"), ko=_ko("램프", False)),
    "bottle": dict(es=_n("botella", F, "botellas"), fr=_n("bouteille", F, "bouteilles"),
                   de=_n("Flasche", F, "Flaschen"), ko=_ko("병", True)),
    "plate": dict(es=_n("plato", M, "platos"), fr=_n("assiette", F, "assiettes", elides=True),
                  de=_n("Teller", M, "Teller"), ko=_ko("접시", False)),
    "bag": dict(es=_n("bolso", M, "bolsos"), fr=_n("sac", M, "sacs"),
                de=_n("Tasche", F, "Taschen"), ko=_ko("가방", True)),
    "pen": dict(es=_n("bolígrafo", M, "bolígrafos"), fr=_n("stylo", M, "stylos"),
                de=_n("Stift", M, "Stifte"), ko=_ko("펜", True)),
    "phone": dict(es=_n("teléfono", M, "teléfonos"), fr=_n("téléphone", M, "téléphones"),
                  de=_n("Handy", N, "Handys"), ko=_ko("전화기", False)),
    "clock": dict(es=_n("reloj", M, "relojes"), fr=_n("horloge", F, "horloges", elides=True),
                  de=_n("Uhr", F, "Uhren"), ko=_ko("시계", False)),
    "tree": dict(es=_n("árbol", M, "árboles"), fr=_n("arbre", M, "arbres", elides=True),
                 de=_n("Baum", M, "Bäume"), ko=_ko("나무", False)),
    "window": dict(es=_n("ventana", F, "ventanas"), fr=_n("fenêtre", F, "fenêtres"),
                   de=_n("Fenster", N, "Fenster"), ko=_ko("창문", True)),
    "door": dict(es=_n("puerta", F, "puertas"), fr=_n("porte", F, "portes"),
                 de=_n("Tür", F, "Türen"), ko=_ko("문", True)),
    "spoon": dict(es=_n("cuchara", F, "cucharas"), fr=_n("cuillère", F, "cuillères"),
                  de=_n("Löffel", M, "Löffel"), ko=_ko("숟가락", True)),
    "fork": dict(es=_n("tenedor", M, "tenedores"), fr=_n("fourchette", F, "fourchettes"),
                 de=_n("Gabel", F, "Gabeln"), ko=_ko("포크", False)),
    "egg": dict(es=_n("huevo", M, "huevos"), fr=_n("œuf", M, "œufs", elides=True),
                de=_n("Ei", N, "Eier"), ko=_ko("달걀", True)),
    "key": dict(es=_n("llave", F, "llaves"), fr=_n("clé", F, "clés"),
                de=_n("Schlüssel", M, "Schlüssel"), ko=_ko("열쇠", False)),
    "shoe": dict(es=_n("zapato", M, "zapatos"), fr=_n("chaussure", F, "chaussures"),
                 de=_n("Schuh", M, "Schuhe"), ko=_ko("신발", True)),
}

_DEFINITE = {
    "es": {M: "el", F: "la"}, "fr": {M: "le", F: "la"},
    "de": {M: "der", F: "die", N: "das"},
}
_DEFINITE_PLURAL = {"es": {M: "los", F: "las"}, "fr": {M: "les", F: "les"},
                    "de": {M: "die", F: "die", N: "die"}}
_ACCUSATIVE_DE = {M: "den", F: "die", N: "das"}
_INDEFINITE = {
    "es": {M: "un", F: "una"}, "fr": {M: "un", F: "une"},
    "de": {M: "ein", F: "eine", N: "ein"},
}
NUMBER_WORDS = {"es": {2: "dos", 3: "tres"}, "fr": {2: "deux", 3: "trois"},
                "de": {2: "zwei", 3: "drei"}, "ko": {1: "한", 2: "두", 3: "세"}}
ENGLISH_NUMBERS = {1: "one", 2: "two", 3: "three"}
YES_NO = {"es": ("Sí.", "No."), "fr": ("Oui.", "Non."), "de": ("Ja.", "Nein."),
          "ko": ("네.", "아니요.")}
WHAT_IS_THIS = {"es": "¿Qué es esto?", "fr": "Qu'est-ce que c'est ?",
                "de": "Was ist das?", "ko": "이것은 뭐예요?"}
# The full set of Korean noun endings an A0 mission may teach; they are copula
# endings chosen by the final consonant, never articles.
KOREAN_ENDINGS = ("이에요", "예요")


def reviewed_noun(label: str, language: str) -> Noun | None:
    entry = REVIEWED_NOUNS.get(" ".join(label.casefold().split()))
    return entry.get(language) if entry else None


def form(language: str, noun: Noun) -> str:
    """The word that goes with the noun in an A0 chunk: definite form or Korean ending."""
    if language == "ko":
        return KOREAN_ENDINGS[0] if noun.batchim else KOREAN_ENDINGS[1]
    if language == "fr" and noun.elides:
        return "l'"
    return _DEFINITE[language][noun.gender]


def plural_form(language: str, noun: Noun) -> str | None:
    return None if language == "ko" else _DEFINITE_PLURAL[language][noun.gender]


def join(language: str, word: str, noun: str) -> str:
    """``word`` and ``noun`` as one chunk: ``la tasse``, ``l'arbre``, ``책이에요``."""
    if language == "ko":
        return f"{noun}{word}"
    return f"{word}{noun}" if word.endswith("'") else f"{word} {noun}"


def chunk(language: str, noun: Noun) -> str:
    return join(language, form(language, noun), noun.noun)


def situational_noun(language: str, noun: Noun, *, accusative=False, topic=False) -> str:
    """A reviewed noun chunk for the A0 ownership and preference missions."""
    if language == "ko":
        particle = ("은" if noun.batchim else "는") if topic else (
            "을" if noun.batchim else "를"
        )
        return noun.noun + particle
    article = (
        _ACCUSATIVE_DE[noun.gender] if language == "de" and accusative
        else form(language, noun)
    )
    if language == "fr" and noun.elides:
        return f"{article}{noun.noun}"
    return f"{article} {noun.noun}"


def ownership_chunks(language: str, noun: Noun, source: str) -> dict[str, str]:
    """Closed M04 phrases for one reviewed noun."""
    if language == "ko":
        mine, not_mine, is_yours, mine_predicate, yours_predicate = (
            "제 거예요.", "제 거 아니에요.", "이거 본인 거예요?", "제 거예요", "본인 거예요"
        )
        x_mine = f"{situational_noun(language, noun, topic=True)} {mine_predicate}."
        x_yours = f"{situational_noun(language, noun, topic=True)} {yours_predicate}."
    elif language == "es":
        gender = "o" if noun.gender == M else "a"
        mine, not_mine, is_yours = (
            f"Es mí{gender}.",
            f"No es mí{gender}.",
            f"¿Es tuy{gender}?",
        )
        mine_predicate, yours_predicate = f"es mí{gender}", f"es tuy{gender}"
        name = situational_noun(language, noun)
        name = name[:1].upper() + name[1:]
        x_mine, x_yours = f"{name} es mí{gender}.", f"{name} es tuy{gender}."
    elif language == "fr":
        mine, not_mine, is_yours = "C'est à moi.", "Ce n'est pas à moi.", "C'est à toi ?"
        mine_predicate, yours_predicate = "est à moi", "est à toi"
        name = situational_noun(language, noun)
        name = name[:1].upper() + name[1:]
        x_mine, x_yours = f"{name} est à moi.", f"{name} est à toi."
    else:
        mine, not_mine, is_yours = "Das gehört mir.", "Das gehört mir nicht.", "Gehört das dir?"
        mine_predicate, yours_predicate = "gehört mir", "gehört dir"
        name = situational_noun(language, noun)
        name = name[:1].upper() + name[1:]
        x_mine, x_yours = f"{name} gehört mir.", f"{name} gehört dir."
    return {
        "mine": mine,
        "notMine": not_mine,
        "isYours": is_yours,
        "minePredicate": mine_predicate,
        "yoursPredicate": yours_predicate,
        "xMine": x_mine,
        "xYours": x_yours,
        "englishMine": f"The {source} is mine.",
        "englishYours": f"The {source} is yours.",
    }


def preference_chunks(language: str, noun: Noun, source: str) -> dict[str, str]:
    """Closed M05 phrases for one reviewed noun."""
    n = situational_noun(language, noun)
    a = situational_noun(language, noun, accusative=True)
    o = situational_noun(language, noun)
    if language == "es":
        like, dislike, question = f"Me gusta {n}.", f"No me gusta {n}.", f"¿Te gusta {n}?"
        choose, choose_noun = "¿Qué eliges?", f"Elijo {n}."
        like_frame, dislike_frame = "Me gusta ___", "No me gusta ___"
    elif language == "fr":
        like, dislike, question = f"J'aime {n}.", f"Je n'aime pas {n}.", f"Tu aimes {n} ?"
        choose, choose_noun = "Tu choisis quoi ?", f"Je choisis {n}."
        like_frame, dislike_frame = "J'aime ___", "Je n'aime pas ___"
    elif language == "de":
        like, dislike, question = f"Ich mag {a}.", f"Ich mag {a} nicht.", f"Magst du {a}?"
        choose, choose_noun = "Was nimmst du?", f"Ich nehme {a}."
        like_frame, dislike_frame = "Ich mag ___", "Ich mag ___ nicht"
    else:
        like, dislike, question = f"{o} 좋아해요.", f"{o} 안 좋아해요.", f"{o} 좋아해요?"
        choose, choose_noun = "뭐 골라요?", f"{o} 골라요."
        like_frame, dislike_frame = "___ 좋아해요", "___ 안 좋아해요"
    return {
        "like": like,
        "dislike": dislike,
        "doYouLike": question,
        "whatChoose": choose,
        "iChoose": choose_noun,
        "likeFrame": like_frame,
        "dislikeFrame": dislike_frame,
        "englishLike": f"I like the {source}.",
        "englishDislike": f"I don't like the {source}.",
        "englishDoYouLike": f"Do you like the {source}?",
    }


def form_options(language: str, noun: Noun, plurals_taught: bool) -> list[str]:
    """Reviewed forms for the noun's slot, the correct one first, at most three.

    Distractors differ from the answer in that one word only. Plural forms
    (``les``/``los``/``las``/plural ``die``) appear only once plurals were taught.
    """
    correct = form(language, noun)
    if language == "ko":
        return list(dict.fromkeys([correct, *KOREAN_ENDINGS]))
    singular = list(_DEFINITE[language].values())
    if language == "fr" and noun.elides:
        # l' replaces le/la before this noun's sound; le/la stay as distractors.
        singular.append("l'")
    others = [item for item in dict.fromkeys(singular) if item != correct]
    plural = plural_form(language, noun)
    if plurals_taught and plural not in {correct, *others}:
        others.append(plural)
    return [correct, *others][:3]


def plural_only(language: str, item: str) -> bool:
    """Whether ``item`` is only a plural form (``les``/``los``/``las``, not German ``die``)."""
    if language == "ko":
        return False
    singular = {*_DEFINITE[language].values(), "l'"}
    return item in _DEFINITE_PLURAL[language].values() and item not in singular


def indefinite_chunk(language: str, noun: Noun) -> str:
    if language == "ko":
        return noun.noun
    return f"{_INDEFINITE[language][noun.gender]} {noun.noun}"


def identify_sentence(language: str, noun: Noun) -> str:
    """"This is a cup." for the noun."""
    if language == "es":
        return f"Es {indefinite_chunk(language, noun)}."
    if language == "fr":
        return f"C'est {indefinite_chunk(language, noun)}."
    if language == "de":
        return f"Das ist {indefinite_chunk(language, noun)}."
    return f"이것은 {chunk(language, noun)}."


def is_it_question(language: str, noun: Noun) -> str:
    """"Is this a cup?" for the noun."""
    if language == "es":
        return f"¿Es {indefinite_chunk(language, noun)}?"
    if language == "fr":
        return f"C'est {indefinite_chunk(language, noun)} ?"
    if language == "de":
        return f"Ist das {indefinite_chunk(language, noun)}?"
    return f"이것은 {chunk(language, noun)}?"


def name_chunk(language: str, noun: Noun) -> str:
    """The taught name: the noun with its definite form (bare noun in Korean)."""
    return noun.noun if language == "ko" else chunk(language, noun)


def find_prompt(language: str, noun: Noun) -> str:
    """"Find the cup." for the noun."""
    if language == "es":
        return f"Busca {chunk(language, noun)}."
    if language == "fr":
        return f"Trouve {chunk(language, noun)}."
    if language == "de":
        return f"Finde {_ACCUSATIVE_DE[noun.gender]} {noun.noun}."
    return f"{noun.noun}{'을' if noun.batchim else '를'} 찾으세요."


def number_word(language: str, noun: Noun, quantity: int) -> str:
    """The number word before the noun; in Korean with the counter 개."""
    if language == "ko":
        return f"{NUMBER_WORDS['ko'][quantity]} 개"
    if quantity == 1:
        return _INDEFINITE[language][noun.gender]
    return NUMBER_WORDS[language][quantity]


def quantity_chunk(language: str, noun: Noun, quantity: int) -> str:
    """"two apples": number and noun, never an existential sentence."""
    if language == "ko":
        return f"{noun.noun} {number_word(language, noun, quantity)}"
    shown = noun.noun if quantity == 1 else noun.plural
    return f"{number_word(language, noun, quantity)} {shown}"


def how_many(language: str, noun: Noun) -> str:
    if language == "es":
        return f"¿{'Cuántos' if noun.gender == M else 'Cuántas'} {noun.plural}?"
    if language == "fr":
        return f"Combien d'{noun.plural} ?" if noun.elides else f"Combien de {noun.plural} ?"
    if language == "de":
        return f"Wie viele {noun.plural}?"
    return f"{noun.noun} 몇 개?"
