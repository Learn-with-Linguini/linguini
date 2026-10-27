"""Pack-mission normal dispatch for every bundled pack and level. Provider responses are mocked.

The mocked sentences are test data shaped like each pack's examples; they are not
model evidence or a claim that the generated language has been reviewed.
"""

import json
import re
import unicodedata
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.ai.cache.store import CacheScope
from app.ai.contracts.text import TextModelConfig, TextModelResponse
from app.ai.features.learning_tasks.service import LearningTaskService
from app.ai.observability import NoOpAITracer
from app.language_packs.evaluation import evaluate_pack
from app.language_packs.generation import ApprovedVocabulary
from app.language_packs.loader import load_pack
from app.missions import get_mission
from app.repositories.postgres.workflow import (
    PostgresWorkflowRepository,
    _lesson_answer_is_correct,
    evaluate,
)
from app.schemas.enums import SessionMode
from app.schemas.tasks import SessionTaskPublic, SubmitVocabularyReviewAttemptRequest
from app.services.mission_roleplay import assign_a0_scenario, assign_roleplay

PACKS = Path(__file__).parents[1] / "app/language_packs/packs"
SAMPLES = Path(__file__).parents[1] / "app/language_packs/samples"
LOCALES = {"es": "es-ES", "fr": "fr-FR", "de": "de-DE", "ko": "ko-KR"}
# Mocked languages whose pack requires romanization of translations.
ROMANIZED = {"ko"}
COUNTS = {
    "M01": {"A0": 6, "A1": 4, "A2": 5}, "M02": {"A0": 6, "A1": 4, "A2": 5},
    "M03": {"A0": 6, "A1": 3, "A2": 5}, "M04": {"A0": 6, "A1": 3, "A2": 5},
    "M05": {"A0": 6, "A1": 3}, "M06": {"A2": 6}, "M13": {"A0": 6},
}
# M06 builds its order as two tasks (place the order, finish it); others build one.
TASKS = {"M06": 2}
# Every pack mission at every level it has a template for.
MISSION_LEVELS = [(mission, level) for mission, levels in COUNTS.items() for level in levels]
MISSION_VERSIONS = {("M02", "A1"): 2}
# A1 describes the second object, so its colour has a distinct Korean modifier form.
SCENE = (("cup", "red"), ("book", "white"), ("table", "green"))
# Learner counts: three cups (A0's one small group) and five books (A2's second group).
COUNTED = (("cup", 3), ("book", 5))


def latin(text):
    """Deterministic Latin spelling for mocked Hangul output (test data only)."""
    out = ""
    for char in text:
        if char.isascii() or not char.isalpha() and unicodedata.category(char)[0] != "M":
            out += char
            continue
        name = unicodedata.name(char, "")
        last = name.split()[-1].lower()
        if "HANGUL SYLLABLE" in name:
            out += last
    return out


def spans(text):
    """Aligned native/Latin spans: each word and punctuation mark separately."""
    return [
        dict(native=part, latin=latin(part))
        for part in re.findall(r"\s*(?:[^\s.,!?;:]+|[.,!?;:])", text)
    ]


def _batchim(word):
    code = ord(word[-1]) - 0xAC00
    return 0 <= code < 11172 and code % 28 != 0


def _ko(word, consonant, vowel):
    return word + (consonant if _batchim(word) else vowel)


# Per-language test lexicon: nouns (bare, definite article, gender), colours by
# agreement key and relation. Values mirror each pack's reference examples.
LEXICON = {
    "es": dict(
        nouns={"cup": ("taza", "la", "feminine"), "book": ("libro", "el", "masculine"),
               "table": ("mesa", "la", "feminine"), "coffee": ("café", "el", "masculine"),
               "chair": ("silla", "la", "feminine"), "toy": ("juguete", "el", "masculine")},
        indefinite={"masculine": "un", "feminine": "una"},
        colours={"red": ("rojo", "roja"), "green": ("verde", "verde"),
                 "white": ("blanco", "blanca"), "blue": ("azul", "azul"),
                 "black": ("negro", "negra")},
        on="sobre",
        relations={"on": "sobre", "under": "debajo de", "next to": "al lado de"},
    ),
    "fr": dict(
        nouns={"cup": ("tasse", "la", "feminine"), "book": ("livre", "le", "masculine"),
               "table": ("table", "la", "feminine"), "coffee": ("café", "le", "masculine"),
               "chair": ("chaise", "la", "feminine"), "toy": ("jouet", "le", "masculine")},
        indefinite={"masculine": "un", "feminine": "une"},
        colours={"red": ("rouge", "rouge"), "green": ("vert", "verte"),
                 "white": ("blanc", "blanche"), "blue": ("bleu", "bleue"),
                 "black": ("noir", "noire")},
        on="sur",
        relations={"on": "sur", "under": "sous", "next to": "à côté de"},
    ),
    "de": dict(
        nouns={"cup": ("Tasse", "die", "feminine"), "book": ("Buch", "das", "neuter"),
               "table": ("Tisch", "der", "masculine"), "coffee": ("Kaffee", "der", "masculine"),
               "chair": ("Stuhl", "der", "masculine"), "toy": ("Spielzeug", "das", "neuter")},
        indefinite={"masculine": "ein", "feminine": "eine", "neuter": "ein"},
        dative={"masculine": "dem", "feminine": "der", "neuter": "dem"},
        colours={"red": ("roter", "rote", "rotes"), "green": ("grüner", "grüne", "grünes"),
                 "white": ("weißer", "weiße", "weißes"), "blue": ("blauer", "blaue", "blaues"),
                 "black": ("schwarzer", "schwarze", "schwarzes")},
        base={"red": "rot", "green": "grün", "white": "weiß", "blue": "blau",
              "black": "schwarz"},
        on="auf",
        relations={"on": "auf", "under": "unter", "next to": "neben"},
        accusative={"masculine": "den", "feminine": "die", "neuter": "das"},
        pronouns={"masculine": "Er", "feminine": "Sie", "neuter": "Es"},
    ),
    "ko": dict(
        nouns={"cup": ("컵", None, None), "book": ("책", None, None),
               "table": ("탁자", None, None), "coffee": ("커피", None, None),
               "chair": ("의자", None, None), "toy": ("장난감", None, None)},
        colours={"red": "빨간색", "green": "초록색", "white": "흰색", "blue": "파란색",
                 "black": "검은색"},
        modifiers={"red": "빨간", "white": "하얀", "blue": "파란", "black": "검은"},
        on="위에",
        relations={"on": "위에", "under": "아래에", "next to": "옆에"},
    ),
}
GENDER_INDEX = {"masculine": 0, "feminine": 1, "neuter": 2}


def _colour(language, value, gender):
    forms = LEXICON[language]["colours"][value]
    if isinstance(forms, str):
        return LEXICON[language].get("modifiers", {}).get(value, forms)
    return forms[GENDER_INDEX[gender]]


def _capitalised(text):
    return text[:1].upper() + text[1:]


# Constructions each pack marks with the "phrase" feature.
PHRASES = {"location-phrase", "quantity-chunk", "order-phrase", "noun-word-pair"}
M02_CONSTRUCTIONS = {
    "find-object", "where-question", "location-phrase", "target-clue", "target-location",
}


def _m02_sentence(language, construction, use, obj, attr, rel, ref):
    """M02's sentence types in each pack's taught pattern, with realized surfaces."""
    lex = LEXICON[language]
    bare, article, gender = lex["nouns"][obj]
    definite = f"{article} {bare}" if article else bare
    rel_text = lex["relations"][rel or "on"]
    ref_bare, ref_article, ref_gender = lex["nouns"][ref] if ref else ("", None, None)
    realized = {}
    if language in {"es", "fr"}:
        place = f"{rel_text} {ref_article} {ref_bare}" if ref else ""
        for wrong, right in (("de el ", "del "), ("de le ", "du "), ("à le ", "au ")):
            place = place.replace(wrong, right)
        adj = _colour(language, attr, gender) if attr else ""
        if language == "es":
            texts = {"find-object": f"Busca {definite}.",
                     "where-question": f"¿Dónde está {definite}?",
                     "target-location": f"{_capitalised(definite)} {adj} está {place}."}
            clue, no = (f"Es {adj}." if attr else f"Está {place}."), "No"
        else:
            pronoun = "Elle" if gender == "feminine" else "Il"
            texts = {"find-object": f"Trouve {definite}.",
                     "where-question": f"Où est {definite} ?",
                     "target-location": f"{_capitalised(definite)} {adj} est {place}."}
            clue = f"{pronoun} est {adj}." if attr else f"{pronoun} est {place}."
            no = "Non"
    elif language == "de":
        dative = f"{lex['dative'][ref_gender]} {ref_bare}" if ref else ""
        place = f"{rel_text} {dative}" if ref else ""
        if ref:
            realized["reference"] = dative
        base = lex["base"][attr] if attr else ""
        pronoun = lex["pronouns"][gender]
        texts = {"find-object": f"Finde {lex['accusative'][gender]} {bare}.",
                 "where-question": f"Wo ist {definite}?",
                 "target-location": f"{_capitalised(article)} {base}e {bare} ist {place}."}
        clue = f"{pronoun} ist {base}." if attr else f"{pronoun} ist {place}."
        no = "Nein"
    else:
        place = f"{ref_bare} {rel_text}" if ref else ""
        colour = lex["colours"][attr] if attr else ""
        modifier = lex.get("modifiers", {}).get(attr, colour) if attr else ""
        subject = _ko(bare, "이", "가")
        texts = {"find-object": f"{_ko(bare, '을', '를')} 찾아보세요.",
                 "where-question": f"{subject} 어디에 있어요?",
                 "target-location": f"{modifier} {subject} {place} 있어요."}
        clue = f"{_ko(colour, '이에요', '예요')}." if attr else f"{place} 있어요."
        no = "아니요"
    texts["location-phrase"] = place
    if construction == "target-clue":
        if use != "clarify":
            text = clue
        elif language == "ko":
            text = f"{no}, {clue}"
        else:
            text = f"{no}, {clue[:1].lower()}{clue[1:]}"
    else:
        text = texts[construction]
    if language == "ko":
        # Agglutinated nouns and colour words carry particles and endings.
        words = [word.strip(".,!?") for word in text.split()]
        noun = next((w for w in words if w.startswith(bare) and w != bare), None)
        if noun:
            realized["object"] = noun
        if attr:
            realized["attribute"] = next(
                (w for w in words if w.startswith(colour) or w == modifier), modifier,
            )
    return text, realized


def _sentence(language, construction, use, truth, obj, attr, other, rel, ref):
    """Return (text, realized surfaces by role) in the pack's taught pattern."""
    if construction in M02_CONSTRUCTIONS:
        return _m02_sentence(language, construction, use, obj, attr, rel, ref)
    lex = LEXICON[language]
    rel_text = lex["relations"][rel or "on"]
    bare, article, gender = lex["nouns"][obj]
    definite = f"{article} {bare}" if article else bare
    indefinite = f"{lex['indefinite'][gender]} {bare}" if "indefinite" in lex else bare
    adj = _colour(language, attr, gender) if attr else ""
    other_bare = lex["nouns"][other][0] if other else ""
    other_gender = lex["nouns"][other][2] if other else None
    other_indef = (
        f"{lex['indefinite'][other_gender]} {other_bare}" if other and "indefinite" in lex
        else other_bare
    )
    ref_bare, ref_article, ref_gender = lex["nouns"][ref] if ref else ("", None, None)
    realized = {}
    if language == "es":
        noun_adj = f"{indefinite} {adj}" if adj else indefinite
        existence = f"Hay {noun_adj}."
        text = {
            ("identify-object", "name"): definite,
            ("identify-object", None): f"Es {indefinite}.",
            ("yes-no-identification", "question"): f"¿Es {indefinite}?",
            ("yes-no-identification", "answer"): f"{'Sí' if truth else 'No'}, es {indefinite}.",
            ("describe-attribute", "followup"): f"¿De qué color es {definite}?",
            ("describe-attribute", None): f"Es {noun_adj}.",
            ("scene-existence", "fact3"): f"También hay {indefinite}.",
            ("scene-existence", None): existence,
            ("scene-location", None): f"{_capitalised(definite)} está {rel_text} "
            f"{ref_article} {ref_bare}.",
            ("connected-description", "wrongExistence"): f"{existence[:-1]} y no hay "
            f"{other_indef}.",
            ("connected-description", None): f"{existence[:-1]} y también hay {other_indef}.",
        }
    elif language == "fr":
        noun_adj = f"{indefinite} {adj}" if adj else indefinite
        existence = f"Il y a {noun_adj}."
        text = {
            ("identify-object", "name"): definite,
            ("identify-object", None): f"C'est {indefinite}.",
            ("yes-no-identification", "question"): f"C'est {indefinite} ?",
            ("yes-no-identification", "answer"): f"{'Oui' if truth else 'Non'}, c'est "
            f"{indefinite}.",
            ("describe-attribute", "followup"): f"De quelle couleur est {definite} ?",
            ("describe-attribute", None): f"C'est {noun_adj}.",
            ("scene-existence", "fact3"): f"Il y a aussi {indefinite}.",
            ("scene-existence", None): existence,
            ("scene-location", None): f"{_capitalised(definite)} est {rel_text} "
            f"{ref_article} {ref_bare}.",
            ("connected-description", "wrongExistence"): f"{existence[:-1]}, mais il n'y a "
            f"pas de {other_bare}.",
            ("connected-description", None): f"{existence[:-1]} et il y a aussi {other_indef}.",
        }
    elif language == "de":
        noun_adj = f"{lex['indefinite'][gender]} {adj} {bare}" if adj else indefinite
        existence = f"Es gibt {noun_adj}."
        dative = f"{lex['dative'][ref_gender]} {ref_bare}" if ref else ""
        if ref:
            realized["reference"] = dative
        text = {
            ("identify-object", "name"): definite,
            ("identify-object", None): f"Das ist {indefinite}.",
            ("yes-no-identification", "question"): f"Ist das {indefinite}?",
            ("yes-no-identification", "answer"): f"{'Ja' if truth else 'Nein'}, das ist "
            f"{indefinite}.",
            ("describe-attribute", "followup"): f"Welche Farbe hat {definite}?",
            ("describe-attribute", None): f"Das ist {noun_adj}.",
            ("scene-existence", "fact3"): f"Es gibt auch {indefinite}.",
            ("scene-existence", None): existence,
            ("scene-location", None): f"{_capitalised(definite)} ist {rel_text} {dative}.",
            ("connected-description", "wrongExistence"): f"{existence[:-1]}, aber es gibt "
            f"kein {other_bare}.",
            ("connected-description", None): f"{existence[:-1]} und es gibt auch "
            f"{other_indef}.",
        }
    elif language == "ko":
        copula = _ko(bare, "이에요", "예요")
        subject = _ko(bare, "이", "가")
        prefix = f"{adj} " if adj else ""
        other_topic = _ko(other_bare, "은", "는") if other else ""
        text = {
            ("identify-object", "name"): bare,
            ("identify-object", None): f"{copula}.",
            ("yes-no-identification", "question"): f"{copula}?",
            ("yes-no-identification", "answer"): f"{'네' if truth else '아니요'}, {copula}.",
            ("describe-attribute", "followup"): f"{_ko(bare, '은', '는')} 무슨 색이에요?",
            ("describe-attribute", None): f"{prefix}{copula}.",
            ("scene-existence", "fact3"): f"{bare}도 있어요.",
            ("scene-existence", None): f"{prefix}{subject} 있어요.",
            ("scene-location", None): f"{subject} {ref_bare} {rel_text} 있어요.",
            ("connected-description", "wrongExistence"): f"{prefix}{subject} 있고 "
            f"{other_topic} 없어요.",
            ("connected-description", None): f"{prefix}{subject} 있고 {other_bare}도 있어요.",
        }
    else:
        raise AssertionError(f"no mock grammar for {language}")
    use_key = {"prompt": "question", "option": "answer"}.get(use, use)
    key = next(
        (k for k in ((construction, use_key), (construction, None)) if k in text), None
    )
    if key is None:
        raise AssertionError((construction, use))
    sentence = text[key]
    if language == "ko":
        # Agglutinated nouns carry particles, so claim the inflected word.
        words = [word.strip(".,!?") for word in sentence.split()]
        for role, noun in (("object", bare), ("other-object", other_bare)):
            match = next((w for w in words if noun and w.startswith(noun) and w != noun), None)
            if match:
                realized[role] = match
        if adj:
            realized["attribute"] = adj
    return sentence, realized


M03_CONSTRUCTIONS = {
    "how-many-question", "quantity-chunk", "quantity-statement", "quantity-comparison",
    "quantity-pair",
}
PLURALS = {
    "es": {"cup": "tazas", "book": "libros", "table": "mesas", "coffee": "cafés",
           "chair": "sillas", "toy": "juguetes"},
    "fr": {"cup": "tasses", "book": "livres", "table": "tables", "coffee": "cafés",
           "chair": "chaises", "toy": "jouets"},
    "de": {"cup": "Tassen", "book": "Bücher", "table": "Tische", "coffee": "Kaffees",
           "chair": "Stühle", "toy": "Spielzeuge"},
}
COUNTING = {
    "es": dict(statement="Hay {n} {p}.", no="No, hay {n} {p}.",
               compare="Hay {c} {p1} que {p2}.", more="más", fewer="menos",
               pair="Hay {n1} {p1} y {n2} {p2}."),
    "fr": dict(statement="Il y a {n} {p}.", no="Non, il y a {n} {p}.",
               compare="Il y a {c} de {p1} que de {p2}.", more="plus", fewer="moins",
               pair="Il y a {n1} {p1} et {n2} {p2}."),
    "de": dict(statement="Es gibt {n} {p}.", no="Nein, es gibt {n} {p}.",
               compare="Es gibt {c} {p1} als {p2}.", more="mehr", fewer="weniger",
               pair="Es gibt {n1} {p1} und {n2} {p2}."),
}
SINGULAR_NUMBERS = {"un", "una", "une", "ein", "eine"}


def _number(term, gender):
    """A number as written with its noun: the count's own form, else the agreeing one."""
    if term["termId"].startswith("count-"):
        return term["targetText"]
    forms = term["formsByKey"]
    return forms.get(f"with-noun-{gender}") or forms.get("with-noun-any") or term["targetText"]


M04_CONSTRUCTIONS = {
    "ownership-question", "ownership-statement", "owned-object", "possessive-statement",
    "whose-question", "owned-description",
}
# Possessives as each pack writes them: determiner forms by gender, predicate forms.
POSSESSIVES = {
    "es": {"first": (("mi", "mi"), ("mío", "mía")), "second": (("tu", "tu"), ("tuyo", "tuya")),
           "third": ("su", "su")},
    "fr": {"first": (("mon", "ma"), "moi"), "second": (("ton", "ta"), "toi"),
           "third": ("son", "sa")},
    "de": {"first": (("mein", "meine", "mein"), "mir"),
           "second": (("dein", "deine", "dein"), "dir"),
           "leo": ("sein", "seine", "sein"), "ana": ("ihr", "ihre", "ihr")},
    "ko": {"first": "제", "second": "본인"},
}
CAST = {"ko": {"ana": "아나", "leo": "레오"}}


def _m04_sentence(language, construction, spec, terms):
    """M04's ownership sentences in each pack's taught pattern, with realized surfaces."""
    lex = LEXICON[language]
    bindings = dict(spec["bindings"])
    for role, term_id in spec["counterfactual"].items():
        bindings[role] = terms[term_id]["factId"]
    labels = spec["labels"]
    source = terms[bindings.get("object", bindings.get("target"))]["sourceText"]
    bare, article, gender = lex["nouns"][source]
    owner = (terms[bindings["owner"]]["linguistic"]["possessor"]
             if "owner" in bindings else None)
    name = CAST.get(language, {}).get(owner, (owner or "").capitalize())
    index = GENDER_INDEX.get(gender, 0)
    attribute = terms[bindings["attribute"]]["sourceText"] if "attribute" in bindings else None
    reference = (lex["nouns"][terms[bindings["reference"]]["sourceText"]]
                 if "reference" in bindings else None)
    relation = (lex["relations"][terms[bindings["relation"]]["sourceText"]]
                if "relation" in bindings else None)
    forms = POSSESSIVES[language]
    realized = {}
    if language == "ko":
        def topic(word):
            return _ko(word, "은", "는")

        def copula(word):
            return _ko(word, "이에요", "예요")

        mine = forms.get(owner, name)
        prefix = {"yes": "네, ", "no": "아니요, "}.get(next(iter(labels), ""), "")
        text = {
            "ownership-question": "이거 본인 거예요?",
            "ownership-statement": "제 거예요." if spec["truth"] else "제 거 아니에요.",
            "owned-object": f"{prefix}{topic(bare)} {mine} 거예요.",
            "possessive-statement": f"{prefix}{forms.get(owner, name + '의')} {copula(bare)}.",
            "whose-question": f"이 {topic(bare)} 누구 거예요?",
        }.get(construction)
        if construction == "owned-description":
            text = (f"제 {topic(bare)} {copula(lex['colours'][attribute])}." if attribute
                    else f"제 {topic(bare)} {reference[0]} {relation} 있어요.")
        words = [word.strip(".,!?") for word in text.split()]
        noun = next((w for w in words if w.startswith(bare) and w != bare), None)
        if noun:
            realized["object"] = noun
        if attribute:
            colour = lex["colours"][attribute]
            realized["attribute"] = next(w for w in words if w.startswith(colour))
        return text, realized
    definite = f"{article} {bare}"
    if language == "fr" and bare[0] in "aeiouéè":
        definite = f"l'{bare}"
    place = f"{relation} {reference[1]} {reference[0]}" if reference else ""
    if language == "de" and reference:
        place = f"{relation} {lex['dative'][reference[2]]} {reference[0]}"
    if language == "es":
        determiner = forms[owner][0][index] if owner in forms else forms["third"][index]
        predicate = forms[owner][1][index] if owner in forms else f"de {name}"
        yes, no = "Sí", "No"
        texts = {
            "ownership-question": f"¿Es {predicate}?",
            "ownership-statement": f"Es {predicate}." if spec["truth"] else f"No es {predicate}.",
            "owned-object": f"{_capitalised(definite)} es {predicate}.",
            "possessive-statement": f"Es {determiner} {bare}.",
            "whose-question": f"¿De quién es {definite}?",
            "owned-description": (
                f"{_capitalised(determiner)} {bare} es {_colour(language, attribute, gender)}."
                if attribute else f"{_capitalised(determiner)} {bare} está {place}."
            ),
        }
    elif language == "fr":
        vowel = bare[0] in "aeiouéè"
        mine = forms.get(owner, forms["third"])
        determiner = (mine[0] if owner in forms else mine)[0 if vowel else index]
        predicate = f"à {forms[owner][1]}" if owner in forms else f"à {name}"
        yes, no = "Oui", "Non"
        texts = {
            "ownership-question": "C'est à toi ?",
            "ownership-statement": "C'est à moi." if spec["truth"] else "Ce n'est pas à moi.",
            "owned-object": f"{_capitalised(definite)} est {predicate}.",
            "possessive-statement": f"C'est {determiner} {bare}.",
            "whose-question": f"À qui est {definite} ?",
            "owned-description": (
                f"{_capitalised(determiner)} {bare} est {_colour(language, attribute, gender)}."
                if attribute else f"{_capitalised(determiner)} {bare} est {place}."
            ),
        }
    else:
        mine = forms[owner][0] if owner in {"first", "second"} else forms.get(owner, ("",) * 3)
        determiner = mine[index]
        predicate = forms[owner][1] if owner in {"first", "second"} else name
        yes, no = "Ja", "Nein"
        texts = {
            "ownership-question": "Gehört das dir?",
            "ownership-statement": ("Das gehört mir." if spec["truth"]
                                    else "Das gehört mir nicht."),
            "owned-object": f"{_capitalised(definite)} gehört {predicate}.",
            "possessive-statement": f"Das ist {determiner} {bare}.",
            "whose-question": f"Wem gehört {definite}?",
            "owned-description": (
                f"{_capitalised(determiner)} {bare} ist {lex['base'][attribute]}."
                if attribute else f"{_capitalised(determiner)} {bare} ist {place}."
            ),
        }
    text = texts[construction]
    if labels:
        word = yes if labels[0] == "yes" else no
        text = f"{word}, {text[:1].lower()}{text[1:]}"
    return text, realized


M05_CONSTRUCTIONS = {"my-preference", "their-preference", "preference-question",
                     "choice-statement"}


def _m05_sentence(language, construction, spec, terms):
    """M05's like/dislike sentences in each pack's taught pattern, with realized surfaces.

    A bound preference with a term names its cast member; without one the sentence is
    the learner's own (first person) or a question to them (second person).
    """
    lex = LEXICON[language]
    bare, article, gender = lex["nouns"][terms[spec["bindings"]["object"]]["sourceText"]]
    person = terms.get(spec["bindings"].get("preference"))
    name = person["targetText"] if person else None
    dislike = spec["use"] == "dislike"
    if language == "ko":
        obj = _ko(bare, "을", "를")
        topic = _ko(name, "은", "는") if name else None
        verb = "안 좋아해요" if dislike else "좋아해요"
        text = {
            "my-preference": f"저는 {obj} {verb}.",
            "their-preference": f"{topic} {obj} {verb}.",
            "preference-question": f"{topic} {obj} 좋아해요?" if name else f"{obj} 좋아해요?",
            "choice-statement": f"저는 {obj} 골라요.",
        }[construction]
        realized = {"object": obj, **({"preference": topic} if topic else {})}
        return text, realized
    definite = f"{article} {bare}"
    if language == "fr" and bare[0] in "aeiouéè":
        definite = f"l'{bare}"
    if language == "es":
        text = {
            "my-preference": f"{'No me' if dislike else 'Me'} gusta {definite}.",
            "their-preference": f"A {name} {'no ' if dislike else ''}le gusta {definite}.",
            "preference-question": (f"¿A {name} le gusta {definite}?" if name
                                    else f"¿Te gusta {definite}?"),
            "choice-statement": f"Elijo {definite}.",
        }[construction]
    elif language == "fr":
        connector = "qu'" if name and name[0] in "AEIOUÉ" else "que "
        text = {
            "my-preference": f"Je n'aime pas {definite}." if dislike else f"J'aime {definite}.",
            "their-preference": (f"{name} n'aime pas {definite}." if dislike
                                 else f"{name} aime {definite}."),
            "preference-question": (f"Est-ce {connector}{name} aime {definite} ?" if name
                                    else f"Tu aimes {definite} ?"),
            "choice-statement": f"Je choisis {definite}.",
        }[construction]
    else:
        noun = f"{lex['accusative'][gender]} {bare}"
        negation = " nicht" if dislike else ""
        text = {
            "my-preference": f"Ich mag {noun}{negation}.",
            "their-preference": f"{name} mag {noun}{negation}.",
            "preference-question": f"Mag {name} {noun}?" if name else f"Magst du {noun}?",
            "choice-statement": f"Ich nehme {noun}.",
        }[construction]
    return text, {}


M06_CONSTRUCTIONS = {
    "polite-request", "order-phrase", "detail-question", "detail-reply", "order-repeat",
    "order-confirmation", "order-repair",
}
# Order words as each pack's examples write them: [one masculine, one feminine], 2, 3.
M06_NUMBERS = {
    "es": (("un", "una"), "dos", "tres"), "fr": (("un", "une"), "deux", "trois"),
    "de": (("einen", "eine", "ein"), "zwei", "drei"), "ko": ("한", "두", "세"),
}
M06_COUNTERS = {"cup": "개", "book": "권", "coffee": "잔"}
# Detail words by language: agreeing (masculine, feminine) for es/fr, base for de/ko.
M06_DETAILS = {
    "es": {"size:small": ("pequeño", "pequeña"), "size:large": ("grande", "grande"),
           "serviceSetting:eatIn": "para tomar aquí", "serviceSetting:takeAway": "para llevar",
           "temperature:hot": ("caliente", "caliente"), "temperature:cold": ("frío", "fría"),
           "colour:blue": ("azul", "azul"), "colour:red": ("rojo", "roja"),
           "colour:black": ("negro", "negra")},
    "fr": {"size:small": ("petit", "petite"), "size:large": ("grand", "grande"),
           "serviceSetting:eatIn": "sur place", "serviceSetting:takeAway": "à emporter",
           "temperature:hot": ("chaud", "chaude"), "temperature:cold": ("froid", "froide"),
           "colour:blue": ("bleu", "bleue"), "colour:red": ("rouge", "rouge"),
           "colour:black": ("noir", "noire")},
    "de": {"size:small": "klein", "size:large": "groß", "serviceSetting:eatIn": "für hier",
           "serviceSetting:takeAway": "zum Mitnehmen", "temperature:hot": "heiß",
           "temperature:cold": "kalt", "colour:blue": "blau", "colour:red": "rot",
           "colour:black": "schwarz"},
    "ko": {"size:small": "작은", "size:large": "큰", "serviceSetting:eatIn": "먹고 갈게요",
           "serviceSetting:takeAway": "포장", "temperature:hot": "따뜻한",
           "temperature:cold": "차가운", "colour:blue": "파란색", "colour:red": "빨간색",
           "colour:black": "검은색"},
}
M06_QUESTIONS = {
    "es": {"askColour": "¿De qué color?", "askServiceSetting": "¿Para tomar aquí o para llevar?",
           "askTemperature": "¿Caliente o frío?", "askSize": "¿Grandes o pequeños?"},
    "fr": {"askColour": "De quelle couleur ?", "askServiceSetting": "Sur place ou à emporter ?",
           "askTemperature": "Chaud ou froid ?", "askSize": "Des grosses ou des petites ?"},
    "de": {"askColour": "Welche Farbe?", "askServiceSetting": "Für hier oder zum Mitnehmen?",
           "askTemperature": "Heiß oder kalt?", "askSize": "Große oder kleine?"},
    "ko": {"askColour": "무슨 색이요?",
           "askServiceSetting": "드시고 가세요, 아니면 포장이세요?",
           "askTemperature": "따뜻한 걸로 드릴까요, 차가운 걸로 드릴까요?",
           "askSize": "큰 걸로 드릴까요, 작은 걸로 드릴까요?"},
}


def _m06_sentence(language, construction, spec, terms):
    """M06's order sentences in each pack's taught pattern (test data, not model output).

    ``terms`` holds the vocabulary by fact and term ID: the order's own quantity and
    details (``request-*``) and the alternatives a false spec binds (``number-N``,
    ``detail-*``).
    """
    if construction == "order-confirmation":
        return {"es": "Sí, eso es.", "fr": "Oui, c'est ça.", "de": "Ja, genau.",
                "ko": "네, 맞아요."}[language], {}
    bindings = dict(spec["bindings"])
    for role, term_id in spec["counterfactual"].items():
        bindings[role] = terms[term_id]["factId"]
    source = terms[bindings.get("object", bindings.get("target"))]["sourceText"]
    bare, _article, gender = LEXICON[language]["nouns"][source]
    ordered = next(term for term in terms.values() if term["factId"] == "request:quantity")
    count = int(ordered["linguistic"]["value"])

    def value(role):
        term = terms[bindings[role]]
        if role == "quantity":
            return int(term["linguistic"].get("quantity") or term["linguistic"]["value"])
        return f"{term['linguistic']['field']}:{term['linguistic']['value']}"

    def detail(role, quantity=count, capital=False):
        word = M06_DETAILS[language][value(role)]
        if isinstance(word, tuple):
            word = word[gender == "feminine"]
            if quantity > 1 and language in {"es", "fr"} and not word.endswith("s"):
                word += "es" if language == "es" and word[-1] not in "aeiouáéó" else "s"
        return _capitalised(word) if capital else word

    quantity = value("quantity") if "quantity" in bindings else count
    if language == "ko":
        def phrase():
            size = f"{M06_DETAILS['ko'][value('size')]} " if "size" in bindings else ""
            return f"{size}{bare} {M06_NUMBERS['ko'][quantity - 1]} {M06_COUNTERS[source]}"

        def reply(role):
            word = M06_DETAILS["ko"][value(role)]
            if value(role).split(":")[0] in {"temperature", "size"}:
                return f"{word} 걸로 주세요"
            return word if word.endswith("요") else f"{word}{_ko_tail(word)}"

        text = {
            "polite-request": lambda: f"{phrase()} "
                              f"{'빌려 주세요' if spec['use'] == 'borrow' else '주세요'}.",
            "order-phrase": phrase,
            "detail-question": lambda: M06_QUESTIONS["ko"][spec["use"]],
            "detail-reply": lambda: f"{reply('detail')}.",
            "order-repeat": lambda: f"{phrase()}, {reply('detail')}?",
            "order-confirmation": lambda: "네, 맞아요.",
            "order-repair": lambda: (
                f"아니요, {M06_NUMBERS['ko'][quantity - 1]} {M06_COUNTERS[source]}"
                f"{_ko_tail(M06_COUNTERS[source])}." if "quantity" in bindings
                else f"아니요, {reply(next(r for r in ('detail', 'size') if r in bindings))}."
            ),
        }[construction]()
        return text, {}

    noun = bare if quantity == 1 else PLURALS[language][source]
    numbers = M06_NUMBERS[language]
    if quantity == 1:
        number = numbers[0][GENDER_INDEX[gender]] if language == "de" else numbers[0][
            gender == "feminine"]
    else:
        number = numbers[quantity - 1]
    if language == "es":
        size = f" {detail('size', quantity)}" if "size" in bindings else ""
        phrase = f"{number} {noun}{size}"
        tail = "por favor"
        frames = {"order": "Quisiera {np}, por favor.", "borrow": "¿Me prestas {np}, por favor?",
                  "pass": "¿Me pasas {np}, por favor?"}
        repeat = "Entonces, {np}, {detail}, ¿verdad?"
        confirm, repair = "Sí, eso es.", "En realidad, {value}, por favor."
    elif language == "fr":
        size = f"{detail('size', quantity)} " if "size" in bindings else ""
        phrase = f"{number} {size}{noun}"
        tail = "s'il te plaît" if source in {"cup", "book"} else "s'il vous plaît"
        frames = {"order": "Je voudrais {np}, s'il vous plaît.",
                  "borrow": "Tu peux me prêter {np}, s'il te plaît ?",
                  "pass": "Tu peux me passer {np}, s'il te plaît ?"}
        repeat = "Alors, {np}, {detail}, c'est ça ?"
        confirm, repair = "Oui, c'est ça.", "En fait, {value}, " + tail + "."
    else:
        ending = ("e" if quantity > 1 or gender == "feminine"
                  else "es" if gender == "neuter" else "en")
        size = f"{M06_DETAILS['de'][value('size')]}{ending} " if "size" in bindings else ""
        phrase = f"{number} {size}{noun}"
        tail = "bitte"
        frames = {"order": "Ich hätte gern {np}, bitte.",
                  "borrow": "Kannst du mir bitte {np} leihen?",
                  "pass": "Kannst du mir bitte {np} geben?"}
        repeat = "Also, {np}, {detail}, richtig?"
        confirm, repair = "Ja, genau.", "Eigentlich {value}, bitte."
    if construction == "polite-request":
        text = frames[spec["use"]].format(np=phrase)
    elif construction == "order-phrase":
        text = phrase
    elif construction == "detail-question":
        text = M06_QUESTIONS[language][spec["use"]]
    elif construction == "detail-reply":
        text = f"{detail('detail', capital=True)}, {tail}."
    elif construction == "order-repeat":
        text = repeat.format(np=phrase, detail=detail("detail"))
    elif construction == "order-confirmation":
        text = confirm
    elif "quantity" in bindings:
        text = ("En fait, j'en voudrais {value}." if language == "fr" else repair).format(
            value=number if quantity > 1 or language != "de" else "einen")
    else:
        text = repair.format(value=detail(next(r for r in ("detail", "size") if r in bindings)))
    return text, {}


def _ko_tail(word):
    """이요 after a final consonant, 요 after a vowel."""
    return "이요" if _batchim(word) else "요"


def _m03_sentence(language, construction, spec, terms):
    """M03's counting sentences in each pack's taught pattern, with realized surfaces."""
    lex = LEXICON[language]
    bindings = dict(spec["bindings"])
    for role, term_id in spec["counterfactual"].items():
        bindings[role] = terms[term_id]["factId"]

    def noun(role):
        source = terms[bindings[role]]["sourceText"]
        return (source, *lex["nouns"][source])

    def count(role):
        noun_role = "object" if role == "count" else role.split("-")[0]
        return _number(terms[bindings[role]], noun(noun_role)[3])

    if language == "ko":
        def subject(role):
            return _ko(noun(role)[1], "이", "가")

        if construction == "how-many-question":
            text = f"{subject('object')} 몇 개 있어요?"
        elif construction == "quantity-chunk":
            text = f"{noun('object')[1]} {count('count')}"
        elif construction == "quantity-statement":
            text = f"{subject('object')} {count('count')} 있어요."
            text = f"아니요, {text}" if spec["use"] == "correction" else text
        elif construction == "quantity-comparison":
            ending = "많아요" if "more" in spec["labels"] else "적어요"
            text = f"{subject('first')} {noun('second')[1]}보다 {ending}."
        else:
            text = (f"{subject('first')} {count('first-count')} 있고 "
                    f"{subject('second')} {count('second-count')} 있어요.")
        words = [word.strip(".,!?") for word in text.split()]
        realized = {}
        for role in ("object", "first", "second"):
            if role in bindings:
                bare = noun(role)[1]
                match = next((w for w in words if w.startswith(bare) and w != bare), None)
                if match:
                    realized[role] = match
        return text, realized

    frames = COUNTING[language]

    def plural(role, number=None):
        source, bare, *_rest = noun(role)
        return bare if number in SINGULAR_NUMBERS else PLURALS[language][source]

    if construction == "how-many-question":
        gender = noun("object")[3]
        text = {
            "es": f"¿{'Cuántas' if gender == 'feminine' else 'Cuántos'} {plural('object')} hay?",
            "fr": f"Combien de {plural('object')} y a-t-il ?",
            "de": f"Wie viele {plural('object')} gibt es?",
        }[language]
    elif construction == "quantity-chunk":
        number = count("count")
        text = f"{number} {plural('object', number)}"
    elif construction == "quantity-statement":
        frame = frames["no"] if spec["use"] == "correction" else frames["statement"]
        text = frame.format(n=count("count"), p=plural("object"))
    elif construction == "quantity-comparison":
        text = frames["compare"].format(
            c=frames["more" if "more" in spec["labels"] else "fewer"],
            p1=plural("first"), p2=plural("second"))
    else:
        text = frames["pair"].format(n1=count("first-count"), p1=plural("first"),
                                     n2=count("second-count"), p2=plural("second"))
    return text, {}


class MockPackProvider:
    """Deterministic provider double; its grammar is test data, not model evidence."""

    def __init__(self, language):
        self.language = language
        self.requests = []
        self.review_requests = []

    def _response(self, request, value):
        return TextModelResponse(
            output_text=json.dumps(value, ensure_ascii=False),
            model_name="mocked-pack-provider",
            prompt_version=request.prompt_version,
        )

    def _proposals(self, request):
        lex = LEXICON[self.language]
        terms = json.loads(request.user_content)["session_vocabulary"]["terms"]
        forms, distractors = [], []
        for term in terms:
            proposed = {}
            if term["partOfSpeech"] == "noun" and self.language in PLURALS:
                proposed["plural"] = PLURALS[self.language][term["sourceText"]]
            if term["partOfSpeech"] == "noun" and "indefinite" in lex:
                article = lex["indefinite"][term["agreement"]]
                proposed.update(
                    indefinite=f"{article} {term['targetText']}", article_indefinite=article
                )
                if "dative" in lex:
                    proposed["definite_dative"] = (
                        f"{lex['dative'][term['agreement']]} {term['targetText']}"
                    )
                    proposed["definite_accusative"] = (
                        f"{lex['accusative'][term['agreement']]} {term['targetText']}"
                    )
            elif term["partOfSpeech"] == "preposition":
                for meaning, native in lex["relations"].items():
                    if meaning != term["sourceText"]:
                        distractors.append(dict(
                            for_fact_id=term["factId"], meaning=meaning, text=native, forms=[],
                        ))
            elif term["partOfSpeech"] == "adjective":
                value = term["sourceText"]
                agreement = lex["colours"][value]
                if isinstance(agreement, tuple):
                    keys = ("masculine", "feminine", "neuter")
                    proposed.update(zip(keys, agreement, strict=False))
                    if value in lex.get("base", {}):
                        proposed["predicative"] = lex["base"][value]
                elif value in lex.get("modifiers", {}):
                    proposed["modifier"] = lex["modifiers"][value]
                for meaning in ("blue", "black"):
                    if meaning == value:
                        continue
                    native = lex.get("base", {}).get(meaning) or (
                        lex["colours"][meaning]
                        if isinstance(lex["colours"][meaning], str)
                        else lex["colours"][meaning][0]
                    )
                    options = lex["colours"][meaning]
                    agreed = (
                        dict(zip(("masculine", "feminine", "neuter"), options, strict=False))
                        if isinstance(options, tuple)
                        else {"modifier": lex.get("modifiers", {}).get(meaning, options)}
                    )
                    if meaning in lex.get("base", {}):
                        agreed["predicative"] = lex["base"][meaning]
                    distractors.append(dict(
                        for_fact_id=term["factId"], meaning=meaning, text=native,
                        forms=[dict(key=key, text=text) for key, text in agreed.items()],
                    ))
            forms.append(dict(
                term_id=term["termId"],
                forms=[dict(key=key, text=value) for key, value in proposed.items()],
                agreement=term["agreement"], position=term["position"],
            ))
        return self._response(request, {"forms": forms, "distractors": distractors})

    def generate(self, request):
        if request.json_schema_name == "language_vocabulary_proposals":
            return self._proposals(request)
        if request.json_schema_name == "language_content_review":
            self.review_requests.append(request)
            return self._response(request, dict(
                meaning_matches=True, grammatical=True, level_register_ok=True,
                distractors_suitable=True, distinct=True, unambiguous=True,
                scene_claims_supported=True, certain=True, issues=[],
            ))
        self.requests.append(request)
        data = json.loads(request.user_content)
        romanize = data["language"].get("romanizationRequired", False)
        vocabulary = data.get("candidate_vocabulary", data.get("approved_vocabulary"))
        terms = {term["factId"]: term for term in vocabulary["terms"]}
        terms_by_id = {term["termId"]: term for term in vocabulary["terms"]}
        candidates = []
        for spec in data["specs"]:
            bindings = dict(spec["bindings"])
            for role, tid in spec["counterfactual"].items():
                bindings[role] = terms_by_id[tid]["factId"]

            def source(role, bindings=bindings):
                term = terms.get(bindings.get(role))
                return term["sourceText"] if term else None

            object_role = next(
                (role for role in ("object", "subject", "target") if role in bindings), "object"
            )
            if spec["construction_id"] in M03_CONSTRUCTIONS:
                text, realized = _m03_sentence(
                    self.language, spec["construction_id"], spec, {**terms, **terms_by_id},
                )
            elif spec["construction_id"] in M04_CONSTRUCTIONS:
                text, realized = _m04_sentence(
                    self.language, spec["construction_id"], spec, {**terms, **terms_by_id},
                )
            elif spec["construction_id"] in M05_CONSTRUCTIONS:
                text, realized = _m05_sentence(
                    self.language, spec["construction_id"], spec, {**terms, **terms_by_id},
                )
            elif spec["construction_id"] == "noun-word-pair":
                bare, article, _gender = LEXICON[self.language]["nouns"][source("object")]
                if self.language == "ko":
                    # M13's Korean chunk: the noun with its copula ending, as one word.
                    text = bare + ("이에요" if _batchim(bare) else "예요")
                    realized = {"object": text}
                else:
                    text = (f"l'{bare}" if self.language == "fr" and bare[0] in "aeiouéè"
                            else f"{article} {bare}")
                    realized = {}
            elif spec["construction_id"] in M06_CONSTRUCTIONS:
                text, realized = _m06_sentence(
                    self.language, spec["construction_id"], spec, {**terms, **terms_by_id},
                )
            else:
                text, realized = _sentence(
                    self.language, spec["construction_id"], spec["use"], spec["truth"],
                    source(object_role),
                    source("attribute") if spec["use"] != "followup" else None,
                    source("other-object"), source("relation"), source("reference"),
                )
            allowed = {item["role"]: item["term_id"] for item in spec["realization_terms"]}
            if "object" in realized and "object" not in allowed:
                realized["subject"] = realized.pop("object")
            candidates.append(dict(
                slot_id=spec["slot_id"],
                spec_id=spec["spec_id"],
                text=text,
                translation=f"Mock meaning: {source(object_role)}",
                romanization=spans(text) if romanize else [],
                realizations=[
                    dict(term_id=allowed[role], surface=surface)
                    for role, surface in realized.items()
                    if role in allowed and surface in text
                ],
            ))
        support = []
        if romanize:
            texts = {
                form for term in vocabulary["terms"]
                for form in [*term["forms"], *term["formsByKey"].values()]
            }
            support = [dict(native=text, latin=latin(text)) for text in sorted(texts)]
        return self._response(
            request, {"candidates": candidates, "support_romanizations": support}
        )


def build_scene(language, items=SCENE):
    lex = LEXICON[language]
    objects, words, translated, attrs = [], [], [], []
    for index, (source, colour) in enumerate(items, 1):
        bare, article, gender = lex["nouns"][source]
        oid = UUID(int=index)
        objects.append(SimpleNamespace(id=oid, label=source, attributes={"color": colour}))
        words.append(SimpleNamespace(id=UUID(int=index + 10), display_text=bare,
                                     gender=gender))
        native = f"{article} {bare}" if article else bare
        translated.append(SimpleNamespace(
            key=str(oid), source=source, translation=bare, article=article,
            gender=gender, native_display=native,
            romanization=latin(native) if language in ROMANIZED else None,
        ))
        value = lex.get("base", {}).get(colour) or (
            lex["colours"][colour] if isinstance(lex["colours"][colour], str)
            else lex["colours"][colour][0]
        )
        attrs.append(SimpleNamespace(key=f"{oid}:color", source=colour, translation=value))
    relation = SimpleNamespace(
        id=UUID(int=30),
        subject_scene_object_id=objects[0].id,
        reference_scene_object_id=objects[2].id,
        relation="on",
    )
    translation = SimpleNamespace(
        objects=translated,
        attributes=attrs,
        relationships=[SimpleNamespace(key=str(relation.id), source="on",
                                       translation=lex["on"])],
    )
    return objects, [relation], words, translation


@pytest.fixture
def scene():
    return build_scene


def _counted_groups(objects):
    by_label = {obj.label: obj.id for obj in objects}
    return [dict(sceneObjectIds=[str(by_label[label])], quantity=quantity)
            for label, quantity in COUNTED if label in by_label]


def _dispatch(language, level, scene, provider, monkeypatch, mission_id="M01", reaction="like",
              progress=None, scenario=None):
    from app.language_packs.context import resolve_language_context

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_EXPERIMENTAL", "true")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_DIRS", str(PACKS / LOCALES[language] / "everyday"))
    objects, relations, words, translated = scene
    mission = get_mission(mission_id, level, MISSION_VERSIONS.get((mission_id, level), 1))
    markers = {str(obj.id): index for index, obj in enumerate(objects, 1)}
    # M04: the learner says the cup is theirs (A0); M05: they pick the cup over the book
    # (A0). A1 assigns the saved role-play.
    learner_facts = {
        "M04": {"ownedObjectId": str(objects[0].id), "pretend": False},
        "M05": {"preference": {"sceneObjectIds": [str(objects[0].id), str(objects[1].id)],
                               "chosenObjectId": str(objects[0].id), "reaction": "like"}},
    }
    if reaction == "dislike":
        # The learner rates one object and does not like it: they take another instead.
        learner_facts["M05"] = {"preference": {"sceneObjectIds": [str(objects[0].id)],
                                               "reaction": "dislike"}}
    if scenario is not None:
        # No learner choice: the plan assigns the A0 scenario (``scenario`` its reaction).
        learner_facts[mission_id] = assign_a0_scenario(mission, UUID(int=100), objects, markers)
        if mission_id == "M05":
            learner_facts[mission_id]["preference"]["reaction"] = scenario
    roleplay_facts = {
        mission_id: assign_roleplay(mission, UUID(int=100), objects, markers)
    } if mission_id in {"M04", "M05"} else {}
    own_choice = mission_id in {"M04", "M05"}
    claim = SimpleNamespace(
        profile={"target_language_code": language},
        session_id=UUID(int=100),
        missions=[mission],
        counted_groups=_counted_groups(objects),
        mission_progress=progress or {},
        review_markers=markers if own_choice else {},
        roleplay_facts=roleplay_facts,
        learner_facts={mission_id: learner_facts[mission_id]} if own_choice else {},
        cache_scope=CacheScope.user("mock-user"),
        language_context=resolve_language_context(language),
    )
    service = LearningTaskService(
        provider,
        TextModelConfig(model_name="mocked-pack-provider"),
        tracer=NoOpAITracer(),
        provider="mock",
    )
    repo = SimpleNamespace(learning_task_generator=service)
    return PostgresWorkflowRepository._mission_lessons(
        repo, claim, objects, relations, words, translated, []
    )


def _assert_gradable(task):
    """Every correct answer grades correct, and every wrong choice grades wrong."""
    questions = task.public_content.questions
    answers = task.answer_key.correct_option_ids
    assert all(
        _lesson_answer_is_correct(task, q.question_id, answers[q.question_id]) for q in questions
    )
    assert evaluate(task, SubmitVocabularyReviewAttemptRequest(answers=answers))
    wrong = {
        q.question_id: next(
            (o.option_id for o in q.options if o.option_id != answers[q.question_id]),
            "incorrect",
        )
        for q in questions
    }
    assert not evaluate(task, SubmitVocabularyReviewAttemptRequest(answers=wrong))


def _assert_m06_order(tasks):
    """Dev's two-task M06 contract: one transaction, the scenario card on task 1, and a
    Q6 answer that confirms or repairs exactly as the transaction says."""
    first, second = tasks
    transaction = first.answer_key.mission_state["transaction"]
    assert second.answer_key.mission_state["transaction"] == transaction
    assert first.public_content.scenario is not None
    assert first.public_content.scenario.alternatives == []
    assert second.public_content.scenario is None
    assert [q.question_id for q in first.public_content.questions] == [
        "m06-q1", "m06-q2", "m06-q3",
    ]
    by_id = {q.question_id: q for task in tasks for q in task.public_content.questions}
    q2 = by_id["m06-q2"]
    assert q2.slot_template.count("___") == 1
    assert transaction["answers"]["m06-q6"]["correct"] == (
        second.answer_key.correct_option_ids["m06-q6"]
    )
    repaired = transaction["mismatch"]["flag"]
    confirm = transaction["dialogue"][-1]["text"]
    assert confirm == by_id["m06-q6"].audio_text
    q6 = second.answer_key.mission_state["answers"]["m06-q6"]
    assert repaired != any(chunk in q6["model"] for chunk in ("Sí", "Oui", "Ja", "네"))
    assert set(q6["chunks"]) <= set(by_id["m06-q6"].token_bank)


@pytest.mark.parametrize(("mission_id", "level"), MISSION_LEVELS)
@pytest.mark.parametrize("language", list(LOCALES))
def test_pack_missions_dispatch_for_every_pack_and_level(
    language, level, mission_id, scene, monkeypatch,
):
    pack = load_pack(PACKS / LOCALES[language] / "everyday")
    assert pack.lexical == {}
    provider = MockPackProvider(language)
    tasks = _dispatch(language, level, scene(language), provider, monkeypatch, mission_id)

    assert len(tasks) == TASKS.get(mission_id, 1)
    assert {task.public_content.mission_id for task in tasks} == {mission_id}
    assert sum(len(task.public_content.questions) for task in tasks) == (
        COUNTS[mission_id][level]
    )
    assert len(provider.requests) == 1, "sentences should pass without repair"
    data = json.loads(provider.requests[0].user_content)
    assert data["language"]["code"] == language
    # Names, positions and number-noun chunks are phrases; everything else is a sentence.
    for spec in data["specs"]:
        phrase = spec["use"] == "name" or spec["construction_id"] in PHRASES
        assert spec["form"] == ("phrase" if phrase else "sentence"), spec["spec_id"]
    assert "evaluations" not in data and "acceptable" not in data

    for task in tasks:
        _assert_gradable(task)
    task = tasks[0]
    answers = task.answer_key.correct_option_ids
    questions = [question for task in tasks for question in task.public_content.questions]
    for question in questions:
        if question.interaction_type == "sentenceBuilding":
            assert question.sentence_join_modes
        labels = [option.label for option in question.options]
        assert len({label.casefold() for label in labels}) == len(labels)
        shown = [question.prompt, *labels, *question.token_bank]
        if pack.language.romanization_required and any(
            char.isalpha() and not char.isascii() for text in shown for char in text
        ):
            assert question.romanizations
    if pack.language.romanization_required and task.public_content.prep:
        assert all(card.romanization for card in task.public_content.prep)
    if mission_id == "M06":
        _assert_m06_order(tasks)

    by_id = {q.question_id: q for q in questions}
    if mission_id == "M01" and level == "A1":
        chosen = by_id["choose-attribute"]
        correct = next(
            o.label for o in chosen.options if o.option_id == answers[chosen.question_id]
        )
        # A colour chosen on its own is not an attributive form (German Rot, not Rote).
        assert correct.casefold() == {"de": "rot", "ko": "빨간색"}.get(
            language, correct.casefold()
        )
        describe = by_id["describe-object"]
        tiles = len(describe.token_bank) - len(describe.sentence_join_modes)
        if pack.language.grammatical_gender == "none":
            assert tiles == 0, "genderless packs have no wrong-agreement tiles"
        else:
            assert tiles > 0
    if mission_id == "M01" and level == "A2" and language == "de":
        followup = by_id["m01-q5"]
        assert {o.label for o in followup.options} >= {"rot"}


@pytest.mark.parametrize(("mission_id", "level"), MISSION_LEVELS)
@pytest.mark.parametrize("language", list(LOCALES))
def test_sample_vocabulary_covers_every_valid_evaluation_sentence(language, level, mission_id):
    locale = LOCALES[language]
    pack = load_pack(PACKS / locale / "everyday")
    vocabulary = ApprovedVocabulary.model_validate_json(
        (SAMPLES / locale / "vocabulary.json").read_text("utf-8")
    )
    report, record = evaluate_pack(pack, level, vocabulary, mission_id=mission_id)
    # Structure plus the pack's declared checks (and es.py for Spanish) must accept
    # every valid sentence: a check that rejects one would fail real lessons.
    failures = [
        (item["sentence"], item["reasons"])
        for case in report["cases"]
        for item in case["acceptable"]
        if not item["accepted"]
    ]
    assert not failures
    assert record.valid_alternatives_accepted == record.valid_alternatives
    # Including the held-out cases written after the shared rules, nothing is missed.
    assert record.missed_rejects == 0
    assert record.thresholds_met


@pytest.mark.parametrize("language", list(LOCALES))
def test_m05_a0_dislike_has_the_learner_take_another_object(language, scene, monkeypatch):
    provider = MockPackProvider(language)
    (task,) = _dispatch(language, "A0", scene(language), provider, monkeypatch, "M05",
                        reaction="dislike")
    questions = {q.question_id: q for q in task.public_content.questions}
    answers = task.answer_key.correct_option_ids
    heard = questions["M05-Q2"]
    assert next(o.label for o in heard.options if o.option_id == answers["M05-Q2"]) == (
        "Don't like"
    )
    last = questions["M05-Q6"]
    chosen = last.option_object_ids[answers["M05-Q6"]]
    # The learner keeps the other object; the disliked one stays behind.
    assert str(chosen) == str(UUID(int=2))
    assert last.slot_template.count("___") == 1
    assert evaluate(task, SubmitVocabularyReviewAttemptRequest(answers=answers))



@pytest.mark.parametrize(("mission_id", "scenario"),
                         [("M04", "like"), ("M05", "like"), ("M05", "dislike")])
@pytest.mark.parametrize("language", list(LOCALES))
def test_a0_situation_without_a_choice_states_the_assigned_scenario(
    language, mission_id, scenario, scene, monkeypatch,
):
    objects = scene(language)[0]
    (task,) = _dispatch(language, "A0", scene(language), MockPackProvider(language),
                        monkeypatch, mission_id, scenario=scenario)
    _assert_gradable(task)
    questions = task.public_content.questions
    premises = {question.roleplay_premise for question in questions}
    assert len(premises) == 1
    (premise,) = premises
    assert premise.startswith("Let's pretend ")
    facts = assign_a0_scenario(get_mission(mission_id, "A0", 1), UUID(int=100), objects,
                               {str(obj.id): index for index, obj in enumerate(objects, 1)})
    snapshot = task.public_content.mission_snapshot
    assert snapshot.pretend is True
    if mission_id == "M04":
        owned = next(obj for obj in objects if str(obj.id) == facts["ownedObjectId"])
        assert premise == f"Let's pretend the {owned.label} is yours."
        assert str(snapshot.owned_object_id) == facts["ownedObjectId"]
        return
    focus, other = (next(obj for obj in objects if str(obj.id) == key)
                    for key in facts["preference"]["sceneObjectIds"])
    pick = questions[0]
    answers = task.answer_key.correct_option_ids
    assert str(pick.marker_object_ids[answers[pick.question_id]]) == str(focus.id)
    if scenario == "like":
        assert premise == f"Let's pretend you like the {focus.label}."
        assert pick.prompt == "Which one do you like? Tap it in your photo."
    else:
        assert premise == (f"Let's pretend you don't like the {focus.label}, "
                           f"so you pick the {other.label}.")
        assert pick.prompt == "Which one don't you like? Tap it in your photo."
        last = next(q for q in questions if q.question_id == "M05-Q6")
        assert str(last.option_object_ids[answers["M05-Q6"]]) == str(other.id)


@pytest.mark.parametrize("mission_id", ["M04", "M05"])
def test_a0_situation_from_the_learner_choice_has_no_scenario(mission_id, scene, monkeypatch):
    (task,) = _dispatch("es", "A0", scene("es"), MockPackProvider("es"), monkeypatch,
                        mission_id)
    assert all(q.roleplay_premise is None for q in task.public_content.questions)
    assert not task.public_content.mission_snapshot.pretend


@pytest.mark.parametrize("language", list(LOCALES))
@pytest.mark.parametrize("scenario", [None, "like"])
def test_a0_ownership_prompts_answers_and_dialogue_agree(language, scenario, scene, monkeypatch):
    (task,) = _dispatch(language, "A0", scene(language), MockPackProvider(language), monkeypatch,
                        "M04", scenario=scenario)
    questions = {question.question_id: question for question in task.public_content.questions}
    answers = task.answer_key.correct_option_ids

    def answer(question):
        return next(option.label for option in question.options
                    if option.option_id == answers[question.question_id])

    heard = questions["M04-Q2"]
    assert "What does Linguini ask?" in heard.prompt
    assert {option.label for option in heard.options} == {"Is this yours?", "Do you like it?"}
    assert answer(heard) == "Is this yours?"
    assert heard.option_icons[answers[heard.question_id]] == "belongs"
    assert heard.listen_first

    for question_id in ("M04-Q3", "M04-Q4", "M04-Q6"):
        question = questions[question_id]
        assert "yours" in question.prompt
        assert "yours" in question.instruction

    # The graded words must actually complete the displayed sentence in each
    # language, including its punctuation and object-specific ownership form.
    for question_id in ("M04-Q3", "M04-Q4", "M04-Q5", "M04-Q6"):
        question = questions[question_id]
        assert question.slot_template.replace("___", answer(question)) == question.complete_chunk

    dialogue = questions["M04-Q6"]
    assert dialogue.dialogue[0].text == heard.audio_text
    assert dialogue.dialogue[1].translation == dialogue.complete_translation
    _assert_gradable(task)


CAFE = (("coffee", "black"), ("cup", "red"), ("table", "green"))


@pytest.mark.parametrize("mode", ["chunkChoice", "wordBank", "openCloze"])
@pytest.mark.parametrize("language", list(LOCALES))
def test_m06_cafe_order_in_every_reply_mode(language, mode, monkeypatch):
    """A café order (a size and a served detail) for every pack, practised as dev's
    history decides: choose the reply, build it from tiles, or type it."""
    provider = MockPackProvider(language)
    tasks = _dispatch(language, "A2", build_scene(language, CAFE), provider, monkeypatch,
                      "M06", progress={"m06Q5Mode": mode})
    assert len(provider.requests) == 1, "sentences should pass without repair"
    for task in tasks:
        _assert_gradable(task)
    _assert_m06_order(tasks)
    transaction = tasks[0].answer_key.mission_state["transaction"]
    assert transaction["scenario"] == "cafe" and transaction["itemKey"] == "coffee"
    assert transaction["requestDetails"]["size"] in {"small", "large"}
    assert transaction["q5Mode"] == mode
    q5 = next(q for q in tasks[1].public_content.questions if q.question_id == "m06-q5")
    assert q5.interaction_type == {
        "chunkChoice": "multipleChoice", "wordBank": "sentenceBuilding",
        "openCloze": "textCloze",
    }[mode]
    data = json.loads(provider.requests[0].user_content)
    uses = {spec["spec_id"]: spec["use"] for spec in data["specs"]}
    assert uses["listenOrderCard-request"] == "order"
    replies = [spec_id for spec_id in uses if spec_id.startswith("replyWithDetail-")]
    assert len(replies) == {"chunkChoice": 3, "wordBank": 2, "openCloze": 1}[mode]


def test_m06_saved_order_is_reused(monkeypatch):
    """A regenerated lesson keeps the saved transaction (dev's m06Transaction)."""
    language = "es"
    first = _dispatch(language, "A2", build_scene(language, CAFE), MockPackProvider(language),
                      monkeypatch, "M06")
    saved = dict(first[0].answer_key.mission_state["transaction"])
    saved["quantity"] = 3 if saved["quantity"] == 2 else 2
    saved["mismatch"] = {"flag": False, "field": None, "servedValue": None,
                         "correctedValue": None}
    again = _dispatch(language, "A2", build_scene(language, CAFE), MockPackProvider(language),
                      monkeypatch, "M06", progress={"m06Transaction": saved})
    transaction = again[0].answer_key.mission_state["transaction"]
    assert transaction["quantity"] == saved["quantity"]
    assert transaction["mismatch"]["flag"] is False
    assert again[1].answer_key.correct_option_ids["m06-q6"] == "Sí, eso es."


@pytest.mark.parametrize(("language", "mission_id", "equivalent"), [
    ("es", "M04", "Es mia."),
    ("fr", "M05", "J’aime la tasse."),
])
def test_a0_situation_typed_answers_are_private_and_accept_equivalents(
    language, mission_id, equivalent, scene, monkeypatch,
):
    (task,) = _dispatch(language, "A0", scene(language), MockPackProvider(language), monkeypatch,
                        mission_id)
    public = SessionTaskPublic.from_internal(task, mode=SessionMode.LESSON)
    assert "answerKey" not in public.model_dump(mode="json", by_alias=True)
    typed = task.answer_key.accepted_text_answers_by_question
    question_id, accepted = next((key, answers) for key, answers in typed.items() if answers)
    assert all(_lesson_answer_is_correct(task, question_id, answer) for answer in accepted)
    # Typed answers forgive a missing accent (Spanish) and a curly apostrophe (French).
    assert _lesson_answer_is_correct(task, question_id, equivalent)

