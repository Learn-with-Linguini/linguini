"""French-only deterministic fixtures adapted from test_language_pack_multilingual.

These are illustrative mock sentences, not reviewed production LLM output.
"""

import json
from types import SimpleNamespace
from uuid import UUID

from app.ai.contracts.text import TextModelResponse

SCENE = (("cup", "red"), ("book", "white"), ("table", "green"))
COUNTED = (("cup", 3), ("book", 5))
LEXICON = {
    "fr": dict(
        nouns={
            "cup": ("tasse", "la", "feminine"),
            "book": ("livre", "le", "masculine"),
            "table": ("table", "la", "feminine"),
            "coffee": ("café", "le", "masculine"),
            "chair": ("chaise", "la", "feminine"),
            "toy": ("jouet", "le", "masculine"),
        },
        indefinite={"masculine": "un", "feminine": "une"},
        colours={
            "red": ("rouge", "rouge"),
            "green": ("vert", "verte"),
            "white": ("blanc", "blanche"),
            "blue": ("bleu", "bleue"),
            "black": ("noir", "noire"),
        },
        on="sur",
        relations={"on": "sur", "under": "sous", "next to": "à côté de"},
    )
}
GENDER_INDEX = {"masculine": 0, "feminine": 1, "neuter": 2}


def _colour(language, value, gender):
    forms = LEXICON[language]["colours"][value]
    if isinstance(forms, str):
        return LEXICON[language].get("modifiers", {}).get(value, forms)
    return forms[GENDER_INDEX[gender]]


def _capitalised(text):
    return text[:1].upper() + text[1:]


M02_CONSTRUCTIONS = {
    "find-object",
    "where-question",
    "location-phrase",
    "target-clue",
    "target-location",
}


def _m02_sentence(language, construction, use, obj, attr, rel, ref):
    """M02's sentence types in each pack's taught pattern, with realized surfaces."""
    lex = LEXICON[language]
    bare, article, gender = lex["nouns"][obj]
    definite = f"{article} {bare}" if article else bare
    rel_text = lex["relations"][rel or "on"]
    ref_bare, ref_article, ref_gender = lex["nouns"][ref] if ref else ("", None, None)
    realized = {}
    place = f"{rel_text} {ref_article} {ref_bare}" if ref else ""
    for wrong, right in (("de el ", "del "), ("de le ", "du "), ("à le ", "au ")):
        place = place.replace(wrong, right)
    adj = _colour(language, attr, gender) if attr else ""
    pronoun = "Elle" if gender == "feminine" else "Il"
    texts = {
        "find-object": f"Trouve {definite}.",
        "where-question": f"Où est {definite} ?",
        "target-location": f"{_capitalised(definite)} {adj} est {place}.",
    }
    clue = f"{pronoun} est {adj}." if attr else f"{pronoun} est {place}."
    no = "Non"
    texts["location-phrase"] = place
    if construction == "target-clue":
        if use != "clarify":
            text = clue
        else:
            text = f"{no}, {clue[:1].lower()}{clue[1:]}"
    else:
        text = texts[construction]
    return (text, realized)


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
        f"{lex['indefinite'][other_gender]} {other_bare}"
        if other and "indefinite" in lex
        else other_bare
    )
    ref_bare, ref_article, ref_gender = lex["nouns"][ref] if ref else ("", None, None)
    realized = {}
    noun_adj = f"{indefinite} {adj}" if adj else indefinite
    existence = f"Il y a {noun_adj}."
    text = {
        ("identify-object", "name"): definite,
        ("identify-object", None): f"C'est {indefinite}.",
        ("yes-no-identification", "question"): f"C'est {indefinite} ?",
        ("yes-no-identification", "answer"): f"{('Oui' if truth else 'Non')}, c'est {indefinite}.",
        ("describe-attribute", "followup"): f"De quelle couleur est {definite} ?",
        ("describe-attribute", None): f"C'est {noun_adj}.",
        ("scene-existence", "fact3"): f"Il y a aussi {indefinite}.",
        ("scene-existence", None): existence,
        (
            "scene-location",
            None,
        ): f"{_capitalised(definite)} est {rel_text} {ref_article} {ref_bare}.",
        (
            "connected-description",
            "wrongExistence",
        ): f"{existence[:-1]}, mais il n'y a pas de {other_bare}.",
        ("connected-description", None): f"{existence[:-1]} et il y a aussi {other_indef}.",
    }
    use_key = {"prompt": "question", "option": "answer"}.get(use, use)
    key = next((k for k in ((construction, use_key), (construction, None)) if k in text), None)
    if key is None:
        raise AssertionError((construction, use))
    sentence = text[key]
    return (sentence, realized)


M03_CONSTRUCTIONS = {
    "how-many-question",
    "quantity-chunk",
    "quantity-statement",
    "quantity-comparison",
    "quantity-pair",
}
PLURALS = {
    "fr": {
        "cup": "tasses",
        "book": "livres",
        "table": "tables",
        "coffee": "cafés",
        "chair": "chaises",
        "toy": "jouets",
    }
}
COUNTING = {
    "fr": dict(
        statement="Il y a {n} {p}.",
        no="Non, il y a {n} {p}.",
        compare="Il y a {c} de {p1} que de {p2}.",
        more="plus",
        fewer="moins",
        pair="Il y a {n1} {p1} et {n2} {p2}.",
    )
}
SINGULAR_NUMBERS = {"un", "una", "une", "ein", "eine"}


def _number(term, gender):
    """A number as written with its noun: the count's own form, else the agreeing one."""
    if term["termId"].startswith("count-"):
        return term["targetText"]
    forms = term["formsByKey"]
    return forms.get(f"with-noun-{gender}") or forms.get("with-noun-any") or term["targetText"]


M04_CONSTRUCTIONS = {
    "ownership-question",
    "ownership-statement",
    "owned-object",
    "possessive-statement",
    "whose-question",
    "owned-description",
}
POSSESSIVES = {
    "fr": {
        "first": (("mon", "ma"), "moi"),
        "second": (("ton", "ta"), "toi"),
        "third": ("son", "sa"),
    }
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
    owner = terms[bindings["owner"]]["linguistic"]["possessor"] if "owner" in bindings else None
    name = CAST.get(language, {}).get(owner, (owner or "").capitalize())
    index = GENDER_INDEX.get(gender, 0)
    attribute = terms[bindings["attribute"]]["sourceText"] if "attribute" in bindings else None
    reference = (
        lex["nouns"][terms[bindings["reference"]]["sourceText"]]
        if "reference" in bindings
        else None
    )
    relation = (
        lex["relations"][terms[bindings["relation"]]["sourceText"]]
        if "relation" in bindings
        else None
    )
    forms = POSSESSIVES[language]
    realized = {}
    definite = f"{article} {bare}"
    if language == "fr" and bare[0] in "aeiouéè":
        definite = f"l'{bare}"
    place = f"{relation} {reference[1]} {reference[0]}" if reference else ""
    vowel = bare[0] in "aeiouéè"
    mine = forms.get(owner, forms["third"])
    determiner = (mine[0] if owner in forms else mine)[0 if vowel else index]
    predicate = f"à {forms[owner][1]}" if owner in forms else f"à {name}"
    yes, no = ("Oui", "Non")
    texts = {
        "ownership-question": "C'est à toi ?",
        "ownership-statement": "C'est à moi." if spec["truth"] else "Ce n'est pas à moi.",
        "owned-object": f"{_capitalised(definite)} est {predicate}.",
        "possessive-statement": f"C'est {determiner} {bare}.",
        "whose-question": f"À qui est {definite} ?",
        "owned-description": (
            f"{_capitalised(determiner)} {bare} est {_colour(language, attribute, gender)}."
        )
        if attribute
        else f"{_capitalised(determiner)} {bare} est {place}.",
    }
    text = texts[construction]
    if labels:
        word = yes if labels[0] == "yes" else no
        text = f"{word}, {text[:1].lower()}{text[1:]}"
    return (text, realized)


M05_CONSTRUCTIONS = {"my-preference", "their-preference", "preference-question", "choice-statement"}


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
    definite = f"{article} {bare}"
    if language == "fr" and bare[0] in "aeiouéè":
        definite = f"l'{bare}"
    connector = "qu'" if name and name[0] in "AEIOUÉ" else "que "
    text = {
        "my-preference": f"Je n'aime pas {definite}." if dislike else f"J'aime {definite}.",
        "their-preference": f"{name} n'aime pas {definite}."
        if dislike
        else f"{name} aime {definite}.",
        "preference-question": f"Est-ce {connector}{name} aime {definite} ?"
        if name
        else f"Tu aimes {definite} ?",
        "choice-statement": f"Je choisis {definite}.",
    }[construction]
    return (text, {})


M06_CONSTRUCTIONS = {
    "polite-request",
    "order-phrase",
    "detail-question",
    "detail-reply",
    "order-repeat",
    "order-confirmation",
    "order-repair",
}
M06_NUMBERS = {"fr": (("un", "une"), "deux", "trois")}
M06_COUNTERS = {"cup": "개", "book": "권", "coffee": "잔"}
M06_DETAILS = {
    "fr": {
        "size:small": ("petit", "petite"),
        "size:large": ("grand", "grande"),
        "serviceSetting:eatIn": "sur place",
        "serviceSetting:takeAway": "à emporter",
        "temperature:hot": ("chaud", "chaude"),
        "temperature:cold": ("froid", "froide"),
        "colour:blue": ("bleu", "bleue"),
        "colour:red": ("rouge", "rouge"),
        "colour:black": ("noir", "noire"),
    }
}
M06_QUESTIONS = {
    "fr": {
        "askColour": "De quelle couleur ?",
        "askServiceSetting": "Sur place ou à emporter ?",
        "askTemperature": "Chaud ou froid ?",
        "askSize": "Des grosses ou des petites ?",
    }
}


def _m06_sentence(language, construction, spec, terms):
    """M06's order sentences in each pack's taught pattern (test data, not model output).

    ``terms`` holds the vocabulary by fact and term ID: the order's own quantity and
    details (``request-*``) and the alternatives a false spec binds (``number-N``,
    ``detail-*``).
    """
    if construction == "order-confirmation":
        return ({"fr": "Oui, c'est ça."}[language], {})
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
            if quantity > 1 and language in {"es", "fr"} and (not word.endswith("s")):
                word += "s"
        return _capitalised(word) if capital else word

    quantity = value("quantity") if "quantity" in bindings else count
    noun = bare if quantity == 1 else PLURALS[language][source]
    numbers = M06_NUMBERS[language]
    if quantity == 1:
        number = numbers[0][gender == "feminine"]
    else:
        number = numbers[quantity - 1]
    size = f"{detail('size', quantity)} " if "size" in bindings else ""
    phrase = f"{number} {size}{noun}"
    tail = "s'il te plaît" if source in {"cup", "book"} else "s'il vous plaît"
    frames = {
        "order": "Je voudrais {np}, s'il vous plaît.",
        "borrow": "Tu peux me prêter {np}, s'il te plaît ?",
        "pass": "Tu peux me passer {np}, s'il te plaît ?",
    }
    repeat = "Alors, {np}, {detail}, c'est ça ?"
    confirm, repair = ("Oui, c'est ça.", "En fait, {value}, " + tail + ".")
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
        text = "En fait, j'en voudrais {value}.".format(
            value=number if quantity > 1 or language != "de" else "einen"
        )
    else:
        text = repair.format(value=detail(next(r for r in ("detail", "size") if r in bindings)))
    return (text, {})


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

    frames = COUNTING[language]

    def plural(role, number=None):
        source, bare, *_rest = noun(role)
        return bare if number in SINGULAR_NUMBERS else PLURALS[language][source]

    if construction == "how-many-question":
        text = {"fr": f"Combien de {plural('object')} y a-t-il ?"}[language]
    elif construction == "quantity-chunk":
        number = count("count")
        text = f"{number} {plural('object', number)}"
    elif construction == "quantity-statement":
        frame = frames["no"] if spec["use"] == "correction" else frames["statement"]
        text = frame.format(n=count("count"), p=plural("object"))
    elif construction == "quantity-comparison":
        text = frames["compare"].format(
            c=frames["more" if "more" in spec["labels"] else "fewer"],
            p1=plural("first"),
            p2=plural("second"),
        )
    else:
        text = frames["pair"].format(
            n1=count("first-count"),
            p1=plural("first"),
            n2=count("second-count"),
            p2=plural("second"),
        )
    return (text, {})


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
        forms, distractors = ([], [])
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
                        distractors.append(
                            dict(for_fact_id=term["factId"], meaning=meaning, text=native, forms=[])
                        )
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
                    distractors.append(
                        dict(
                            for_fact_id=term["factId"],
                            meaning=meaning,
                            text=native,
                            forms=[dict(key=key, text=text) for key, text in agreed.items()],
                        )
                    )
            forms.append(
                dict(
                    term_id=term["termId"],
                    forms=[dict(key=key, text=value) for key, value in proposed.items()],
                    agreement=term["agreement"],
                    position=term["position"],
                )
            )
        return self._response(request, {"forms": forms, "distractors": distractors})

    def generate(self, request):
        if request.json_schema_name == "language_vocabulary_proposals":
            return self._proposals(request)
        if request.json_schema_name == "language_content_review":
            self.review_requests.append(request)
            return self._response(
                request,
                dict(
                    meaning_matches=True,
                    grammatical=True,
                    level_register_ok=True,
                    distractors_suitable=True,
                    distinct=True,
                    unambiguous=True,
                    scene_claims_supported=True,
                    certain=True,
                    issues=[],
                ),
            )
        self.requests.append(request)
        data = json.loads(request.user_content)
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
                    self.language, spec["construction_id"], spec, {**terms, **terms_by_id}
                )
            elif spec["construction_id"] in M04_CONSTRUCTIONS:
                text, realized = _m04_sentence(
                    self.language, spec["construction_id"], spec, {**terms, **terms_by_id}
                )
            elif spec["construction_id"] in M05_CONSTRUCTIONS:
                text, realized = _m05_sentence(
                    self.language, spec["construction_id"], spec, {**terms, **terms_by_id}
                )
            elif spec["construction_id"] in M06_CONSTRUCTIONS:
                text, realized = _m06_sentence(
                    self.language, spec["construction_id"], spec, {**terms, **terms_by_id}
                )
            else:
                text, realized = _sentence(
                    self.language,
                    spec["construction_id"],
                    spec["use"],
                    spec["truth"],
                    source(object_role),
                    source("attribute") if spec["use"] != "followup" else None,
                    source("other-object"),
                    source("relation"),
                    source("reference"),
                )
            allowed = {item["role"]: item["term_id"] for item in spec["realization_terms"]}
            if "object" in realized and "object" not in allowed:
                realized["subject"] = realized.pop("object")
            candidates.append(
                dict(
                    slot_id=spec["slot_id"],
                    spec_id=spec["spec_id"],
                    text=text,
                    translation=f"Mock meaning: {source(object_role)}",
                    romanization=[],
                    realizations=[
                        dict(term_id=allowed[role], surface=surface)
                        for role, surface in realized.items()
                        if role in allowed and surface in text
                    ],
                )
            )
        support = []
        return self._response(request, {"candidates": candidates, "support_romanizations": support})


def build_scene(language, items=SCENE):
    lex = LEXICON[language]
    objects, words, translated, attrs = ([], [], [], [])
    for index, (source, colour) in enumerate(items, 1):
        bare, article, gender = lex["nouns"][source]
        oid = UUID(int=index)
        objects.append(SimpleNamespace(id=oid, label=source, attributes={"color": colour}))
        words.append(SimpleNamespace(id=UUID(int=index + 10), display_text=bare, gender=gender))
        native = f"{article} {bare}" if article else bare
        translated.append(
            SimpleNamespace(
                key=str(oid),
                source=source,
                translation=bare,
                article=article,
                gender=gender,
                native_display=native,
                romanization=None,
            )
        )
        value = lex.get("base", {}).get(colour) or (
            lex["colours"][colour]
            if isinstance(lex["colours"][colour], str)
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
        relationships=[SimpleNamespace(key=str(relation.id), source="on", translation=lex["on"])],
    )
    return (objects, [relation], words, translation)
