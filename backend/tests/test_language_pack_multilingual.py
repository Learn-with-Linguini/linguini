"""M01 normal dispatch for every bundled pack and level. Provider responses are mocked.

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
from app.schemas.tasks import SubmitVocabularyReviewAttemptRequest

PACKS = Path(__file__).parents[1] / "app/language_packs/packs"
SAMPLES = Path(__file__).parents[1] / "app/language_packs/samples"
LOCALES = {"es": "es-ES", "fr": "fr-FR", "de": "de-DE", "ko": "ko-KR"}
# Mocked languages whose pack requires romanization of translations.
ROMANIZED = {"ko"}
COUNTS = {
    "M01": {"A0": 6, "A1": 4, "A2": 5}, "M02": {"A0": 6, "A1": 4, "A2": 5},
    "M03": {"A0": 6, "A1": 3, "A2": 5},
}
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
               "table": ("mesa", "la", "feminine")},
        indefinite={"masculine": "un", "feminine": "una"},
        colours={"red": ("rojo", "roja"), "green": ("verde", "verde"),
                 "white": ("blanco", "blanca"), "blue": ("azul", "azul"),
                 "black": ("negro", "negra")},
        on="sobre",
        relations={"on": "sobre", "under": "debajo de", "next to": "al lado de"},
    ),
    "fr": dict(
        nouns={"cup": ("tasse", "la", "feminine"), "book": ("livre", "le", "masculine"),
               "table": ("table", "la", "feminine")},
        indefinite={"masculine": "un", "feminine": "une"},
        colours={"red": ("rouge", "rouge"), "green": ("vert", "verte"),
                 "white": ("blanc", "blanche"), "blue": ("bleu", "bleue"),
                 "black": ("noir", "noire")},
        on="sur",
        relations={"on": "sur", "under": "sous", "next to": "à côté de"},
    ),
    "de": dict(
        nouns={"cup": ("Tasse", "die", "feminine"), "book": ("Buch", "das", "neuter"),
               "table": ("Tisch", "der", "masculine")},
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
               "table": ("탁자", None, None)},
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
PHRASES = {"location-phrase", "quantity-chunk"}
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
    "es": {"cup": "tazas", "book": "libros", "table": "mesas"},
    "fr": {"cup": "tasses", "book": "livres", "table": "tables"},
    "de": {"cup": "Tassen", "book": "Bücher", "table": "Tische"},
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


def build_scene(language):
    lex = LEXICON[language]
    objects, words, translated, attrs = [], [], [], []
    for index, (source, colour) in enumerate(SCENE, 1):
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
            for label, quantity in COUNTED]


def _dispatch(language, level, scene, provider, monkeypatch, mission_id="M01"):
    from app.language_packs.context import resolve_language_context

    monkeypatch.setenv("LINGUINI_LANGUAGE_PACKS", "true")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_EXPERIMENTAL", "true")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_DIRS", str(PACKS / LOCALES[language] / "everyday"))
    objects, relations, words, translated = scene
    claim = SimpleNamespace(
        profile={"target_language_code": language},
        session_id=UUID(int=100),
        missions=[get_mission(mission_id, level, MISSION_VERSIONS.get((mission_id, level), 1))],
        counted_groups=_counted_groups(objects),
        mission_progress={},
        review_markers={},
        roleplay_facts={},
        learner_facts={},
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


@pytest.mark.parametrize("mission_id", ["M01", "M02", "M03"])
@pytest.mark.parametrize("level", ["A0", "A1", "A2"])
@pytest.mark.parametrize("language", list(LOCALES))
def test_pack_missions_dispatch_for_every_pack_and_level(
    language, level, mission_id, scene, monkeypatch,
):
    pack = load_pack(PACKS / LOCALES[language] / "everyday")
    assert pack.lexical == {}
    provider = MockPackProvider(language)
    (task,) = _dispatch(language, level, scene(language), provider, monkeypatch, mission_id)

    assert task.public_content.mission_id == mission_id
    questions = task.public_content.questions
    assert len(questions) == COUNTS[mission_id][level]
    assert len(provider.requests) == 1, "sentences should pass without repair"
    data = json.loads(provider.requests[0].user_content)
    assert data["language"]["code"] == language
    # Names, positions and number-noun chunks are phrases; everything else is a sentence.
    for spec in data["specs"]:
        phrase = spec["use"] == "name" or spec["construction_id"] in PHRASES
        assert spec["form"] == ("phrase" if phrase else "sentence"), spec["spec_id"]
    assert "evaluations" not in data and "acceptable" not in data

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
    for question in questions:
        if question.interaction_type == "sentenceBuilding":
            assert question.sentence_join_modes
        labels = [option.label for option in question.options]
        assert len({label.casefold() for label in labels}) == len(labels)
        if pack.language.romanization_required:
            assert question.romanizations
    if pack.language.romanization_required and task.public_content.prep:
        assert all(card.romanization for card in task.public_content.prep)

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


@pytest.mark.parametrize("level", ["A0", "A1", "A2"])
@pytest.mark.parametrize("language", list(LOCALES))
def test_sample_vocabulary_covers_every_valid_evaluation_sentence(language, level):
    locale = LOCALES[language]
    pack = load_pack(PACKS / locale / "everyday")
    vocabulary = ApprovedVocabulary.model_validate_json(
        (SAMPLES / locale / "vocabulary.json").read_text("utf-8")
    )
    report, record = evaluate_pack(pack, level, vocabulary)
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
