"""Reviewed language chunks and deterministic transactions for M06 A2."""

import random
from uuid import UUID, uuid5

from app.ai.features.learning_tasks.mission_m06 import M06Question, MissionM06Result
from app.schemas.tasks import (
    GrammarLessonContent,
    GrammarLessonQuestion,
    MissionScenario,
    MissionScenarioAlternative,
    QuestionEvaluation,
    SessionTask,
    TaskAnswerKey,
    VocabularyChoice,
)
from app.services.mission_lessons import mission_fields
from app.services.mission_m06_lexicon import ITEMS, requestable_objects

NUMBERS = {
    "es": {1: "un", 2: "dos", 3: "tres"},
    "fr": {1: "un", 2: "deux", 3: "trois"},
    "de": {1: "ein", 2: "zwei", 3: "drei"},
    "ko": {1: "한", 2: "두", 3: "세"},
}
REQUEST_FRAMES = {
    "cafe": {
        "es": ("Quisiera", "{NP}, por favor."),
        "fr": ("Je voudrais", "{NP}, s'il vous plaît."),
        "de": ("Ich hätte gern", "{NP}, bitte."),
        "ko": ("", "{NP} 주세요."),
    },
    "shop": {
        "es": ("Quisiera", "{NP}, por favor."),
        "fr": ("Je voudrais", "{NP}, s'il vous plaît."),
        "de": ("Ich hätte gern", "{NP}, bitte."),
        "ko": ("", "{NP} 주세요."),
    },
    "classroom": {
        "es": ("¿Me prestas", "{NP}, por favor?"),
        "fr": ("Tu peux me prêter", "{NP}, s'il te plaît ?"),
        "de": ("Kannst du mir bitte", "{NP} leihen?"),
        "ko": ("", "{NP} 빌려 주세요."),
    },
    "home": {
        "es": ("¿Me pasas", "{NP}, por favor?"),
        "fr": ("Tu peux me passer", "{NP}, s'il te plaît ?"),
        "de": ("Kannst du mir bitte", "{NP} geben?"),
        "ko": ("", "{NP} 주세요."),
    },
}
WRONG_OPENERS = {
    "es": ("Tengo", "Hay"),
    "fr": ("J'ai", "Il y a"),
    "de": ("Ich habe", "Es gibt"),
    "ko": ("있어요", "이에요"),
}
FOLLOW_UPS = {
    "serviceSetting": {
        "es": (
            "¿Para tomar aquí o para llevar?",
            {
                "eatIn": ("Para tomar aquí, por favor.", "para tomar aquí"),
                "takeAway": ("Para llevar, por favor.", "para llevar"),
            },
        ),
        "fr": (
            "Sur place ou à emporter ?",
            {
                "eatIn": ("Sur place, s'il vous plaît.", "sur place"),
                "takeAway": ("À emporter, s'il vous plaît.", "à emporter"),
            },
        ),
        "de": (
            "Für hier oder zum Mitnehmen?",
            {
                "eatIn": ("Für hier, bitte.", "für hier"),
                "takeAway": ("Zum Mitnehmen, bitte.", "zum Mitnehmen"),
            },
        ),
        "ko": (
            "드시고 가세요, 아니면 포장이세요?",
            {
                "eatIn": ("먹고 갈게요.", "먹고 갈게요", "드시고 가시죠"),
                "takeAway": ("포장이요.", "포장이요", "포장이시죠"),
            },
        ),
    },
    "temperature": {
        "es": (
            "¿Caliente o frío?",
            {
                "hot": ("Calientes, por favor.", "calientes"),
                "cold": ("Fríos, por favor.", "fríos"),
            },
        ),
        "fr": (
            "Chaud ou froid ?",
            {
                "hot": ("Chauds, s'il vous plaît.", "chauds"),
                "cold": ("Froids, s'il vous plaît.", "froids"),
            },
        ),
        "de": (
            "Heiß oder kalt?",
            {
                "hot": ("Heiß, bitte.", "heiß"),
                "cold": ("Kalt, bitte.", "kalt"),
            },
        ),
        "ko": (
            "따뜻한 걸로 드릴까요, 차가운 걸로 드릴까요?",
            {
                "hot": ("따뜻한 걸로 주세요.", "따뜻한 걸로", "따뜻한 걸로요"),
                "cold": ("차가운 걸로 주세요.", "차가운 걸로", "차가운 걸로요"),
            },
        ),
    },
    "size": {
        "es": (
            "size",
            {
                "big": ("Grandes, por favor.", "grandes"),
                "small": ("Pequeñas, por favor.", "pequeñas"),
            },
        ),
        "fr": (
            "Des grosses ou des petites ?",
            {
                "big": ("Des grosses, s'il vous plaît.", "grosses"),
                "small": ("Des petites, s'il vous plaît.", "petites"),
            },
        ),
        "de": (
            "Große oder kleine?",
            {
                "big": ("Große, bitte.", "große"),
                "small": ("Kleine, bitte.", "kleine"),
            },
        ),
        "ko": (
            "큰 걸로 드릴까요, 작은 걸로 드릴까요?",
            {
                "big": ("큰 걸로 주세요.", "큰 걸로", "큰 걸로요"),
                "small": ("작은 걸로 주세요.", "작은 걸로", "작은 걸로요"),
            },
        ),
    },
    "colour": {
        "es": (
            "¿De qué color?",
            {
                "blue": ("azul", "azules"),
                "red": ("rojo", "roja", "rojos", "rojas"),
                "black": ("negro", "negra", "negros", "negras"),
            },
        ),
        "fr": (
            "De quelle couleur ?",
            {
                "blue": ("bleu", "bleue", "bleus", "bleues"),
                "red": ("rouge", "rouges"),
                "black": ("noir", "noire", "noirs", "noires"),
            },
        ),
        "de": (
            "Welche Farbe?",
            {
                "blue": ("Blau, bitte.", "Blau"),
                "red": ("Rot, bitte.", "Rot"),
                "black": ("Schwarz, bitte.", "Schwarz"),
            },
        ),
        "ko": (
            "무슨 색이요?",
            {
                "blue": ("파란색이요.", "파란색이요", "파란색이요"),
                "red": ("빨간색이요.", "빨간색이요", "빨간색이요"),
                "black": ("검은색이요.", "검은색이요", "검은색이요"),
            },
        ),
    },
}
CONFIRM = {"es": "Sí, eso es.", "fr": "Oui, c'est ça.", "de": "Ja, genau.", "ko": "네, 맞아요."}
REPAIR_PREFIX = {
    "quantity": {
        "es": "En realidad,",
        "fr": "En fait, j'en voudrais",
        "de": "Eigentlich",
        "ko": "아니요,",
    },
    "other": {"es": "En realidad,", "fr": "En fait,", "de": "Eigentlich", "ko": "아니요,"},
}
REPEAT_FRAMES = {
    "es": "Entonces, {NP}, {short}, ¿verdad?",
    "fr": "Alors, {NP}, {short}, c'est ça ?",
    "de": "Also, {NP}, {short}, richtig?",
    "ko": "{NP}, {tag}?",
}
ENGLISH_NUMBER = {1: "one", 2: "two", 3: "three"}
ENGLISH_SIZE = {"small": "small", "large": "large"}
ENGLISH_FIELDS = {
    "quantity": "quantity",
    "size": "size",
    "serviceSetting": "service setting",
    "temperature": "temperature",
    "colour": "colour",
    "item": "item",
}
SCENARIO_PROMPTS = {
    "cafeDrink": "Practise ordering this drink at a café.",
    "cafeFood": "Practise ordering this food at a café.",
    "shop": "Practise buying this at a shop.",
    "classroom": "Imagine you need to borrow this pen.",
    "home": "Imagine you ask someone at home to pass you this.",
}
_PLURAL_NUMBERS = {1: "one", 2: "two", 3: "three"}


def _nouns(item, language):
    return item.nouns[language]


def _request_np(item, language, quantity, size=None, *, neutral=False):
    noun_data = _nouns(item, language)
    if language == "ko":
        noun, counter = noun_data
        return f"{_ko_size(size)}{noun} {NUMBERS[language][quantity]} {counter}"
    singular, plural, gender = noun_data
    noun = singular if quantity == 1 else plural
    if language == "es":
        number = (
            "una"
            if quantity == 1 and gender == "feminine"
            else ("un" if quantity == 1 else NUMBERS[language][quantity])
        )
        adjective = _spanish_size(size, gender, quantity) if size else ""
        return " ".join(part for part in (number, noun, adjective) if part)
    if language == "fr":
        number = (
            ("une" if gender == "feminine" else "un")
            if quantity == 1
            else NUMBERS[language][quantity]
        )
        adjective = _french_size(size, quantity) if size else ""
        return " ".join(part for part in (number, adjective, noun) if part)
    number = (
        ("eine" if gender == "feminine" else "ein" if gender == "neuter" else "einen")
        if quantity == 1
        else NUMBERS[language][quantity]
    )
    if neutral and quantity == 1:
        number = "eine" if gender == "feminine" else "ein"
    adjective = _german_size(size, quantity, gender, neutral=neutral) if size else ""
    return " ".join(part for part in (number, adjective, noun) if part)


def _spanish_size(size, gender, quantity):
    if size is None:
        return ""
    adjective = "pequeño" if size == "small" else "grande"
    if gender == "feminine":
        adjective = "pequeña" if size == "small" else "grande"
    if quantity > 1:
        adjective += "s"
    return adjective


def _french_size(size, quantity):
    if size is None:
        return ""
    adjective = "petit" if size == "small" else "grand"
    if quantity > 1:
        adjective += "s"
    return adjective


def _german_size(size, quantity, gender, *, neutral=False):
    if size is None:
        return ""
    stem = "klein" if size == "small" else "groß"
    if quantity > 1:
        return f"{stem}e"
    if neutral:
        ending = "er" if gender == "masculine" else "es" if gender == "neuter" else "e"
    else:
        ending = "en" if gender == "masculine" else "es" if gender == "neuter" else "e"
    return stem + ending


def _ko_size(size):
    return {"small": "작은 ", "large": "큰 "}.get(size, "")


def _request(language, item, scenario, quantity, size):
    frame = REQUEST_FRAMES[scenario][language]
    np = _request_np(item, language, quantity, size)
    return (
        frame[0] + (" " if frame[0] and not frame[0].endswith("¿") else "") + frame[1].format(NP=np)
    )


def _scenario(item):
    return {
        "cafe": "cafeDrink" if item.key in {"coffee", "tea", "juice"} else "cafeFood",
        "shop": "shop",
        "classroom": "classroom",
        "home": "home",
    }[item.category]


def _follow_up_question(follow_type, language, item):
    if follow_type == "size" and language == "es":
        gender = _nouns(item, "es")[2]
        return "¿Grandes o pequeñas?" if gender == "feminine" else "¿Grandes o pequeños?"
    return FOLLOW_UPS[follow_type][language][0]


def _quantity_choices(scenario):
    return (2, 3) if scenario in {"cafe", "shop"} else (1, 2)


def select_transaction(session_id, item, language):
    """Choose every role-play detail from the stable session/item seed."""
    rng = random.Random(f"{session_id}:M06:{item.key}")
    scenario = item.category
    quantity = rng.choice(_quantity_choices(scenario))
    size = (
        rng.choice(("small", "large"))
        if scenario == "cafe"
        and item.key
        in {
            "coffee",
            "tea",
            "juice",
        }
        else None
    )
    if scenario == "cafe":
        follow_type = (
            rng.choice(("serviceSetting", "temperature"))
            if item.key
            in {
                "coffee",
                "tea",
            }
            else "serviceSetting"
        )
    elif scenario == "shop":
        follow_type = "size"
    else:
        follow_type = "colour"
    choices = {
        "serviceSetting": ("eatIn", "takeAway"),
        "temperature": ("hot", "cold"),
        "size": ("big", "small"),
        "colour": ("blue", "red", "black"),
    }[follow_type]
    value = rng.choice(choices)
    service_setting = (
        (value if follow_type == "serviceSetting" else rng.choice(("eatIn", "takeAway")))
        if scenario == "cafe"
        else None
    )
    mismatch = rng.random() < 0.5
    mismatch_fields = ["quantity", follow_type]
    if size:
        mismatch_fields.append("size")
    mismatch_field = rng.choice(mismatch_fields) if mismatch else None
    if mismatch_field == "quantity":
        served_value = next(number for number in _quantity_choices(scenario) if number != quantity)
        corrected_value = quantity
    elif mismatch_field == "size" and size:
        served_value = "large" if size == "small" else "small"
        corrected_value = size
    elif mismatch_field:
        served_value = next(candidate for candidate in choices if candidate != value)
        corrected_value = value
    else:
        served_value = corrected_value = None
    follow_up = dict(type=follow_type, value=value)
    request_details = {}
    if size:
        request_details["size"] = size
    return {
        "missionId": "M06",
        "contentVersion": 1,
        "itemKey": item.key,
        "scenario": scenario,
        "serviceSetting": service_setting,
        "quantity": quantity,
        "requestDetails": request_details,
        "followUp": follow_up,
        "requestPattern": scenario,
        "mismatch": {
            "flag": mismatch,
            "field": mismatch_field,
            "servedValue": served_value,
            "correctedValue": corrected_value,
        },
        "seed": f"{session_id}:M06:{item.key}",
    }


def _short_reply(language, follow_type, value, quantity, item):
    if follow_type == "size" and value == "large":
        value = "big"
    phrase = FOLLOW_UPS[follow_type][language][1][value]
    if follow_type == "size" and language == "es":
        reply = _reply(language, follow_type, value, quantity, item, item.category)
        return _lowercase_sentence(reply.removesuffix(", por favor."))
    if follow_type == "colour":
        _, _, gender = _nouns(item, language) if language != "ko" else ("", "", "")
        if language == "es":
            stem = {"blue": "azul", "red": "rojo", "black": "negro"}[value]
            form = stem
            if gender == "feminine":
                form = {"blue": "azul", "red": "roja", "black": "negra"}[value]
            if quantity > 1 and form != "azul":
                form += "s"
            elif quantity > 1:
                form = "azules"
            return _lowercase_sentence(form)
        if language == "fr":
            stem = {"blue": "bleu", "red": "rouge", "black": "noir"}[value]
            if gender == "feminine":
                stem = {"blue": "bleue", "red": "rouge", "black": "noire"}[value]
            if quantity > 1:
                stem += "s"
            return _lowercase_sentence(stem)
        return _lowercase_sentence(phrase[0] if language != "de" else phrase[1])
    return _lowercase_sentence(phrase[1] if len(phrase) > 1 else phrase[0])


def _reply(language, follow_type, value, quantity, item, scenario):
    if follow_type == "size" and value == "large":
        value = "big"
    phrase = FOLLOW_UPS[follow_type][language][1][value][0]
    if follow_type == "size" and language == "es":
        _, _, gender = _nouns(item, language)
        label = (
            "Grandes" if value == "big" else ("Pequeñas" if gender == "feminine" else "Pequeños")
        )
        return _capitalize_sentence(f"{label}, por favor.")
    if follow_type == "temperature" and language in {"es", "fr"} and quantity == 1:
        phrase = {
            "es": {"hot": "Caliente, por favor.", "cold": "Frío, por favor."},
            "fr": {"hot": "Chaud, s'il vous plaît.", "cold": "Froid, s'il vous plaît."},
        }[language][value]
    if follow_type == "colour":
        short = _short_reply(language, follow_type, value, quantity, item)
        if language == "es":
            return _capitalize_sentence(f"{short}, por favor.")
        if language == "fr":
            tail = "s'il te plaît" if scenario in {"classroom", "home"} else "s'il vous plaît"
            return _capitalize_sentence(f"{short}, {tail}.")
        return phrase
    return phrase


def _capitalize_sentence(value):
    return value[:1].upper() + value[1:]


def _lowercase_sentence(value):
    return value[:1].lower() + value[1:]


def _number(language, item, quantity, accusative=True):
    if language == "ko":
        return NUMBERS[language][quantity]
    if language == "de" and quantity == 1:
        _, _, gender = _nouns(item, language)
        return (
            "eine"
            if gender == "feminine"
            else "ein"
            if gender == "neuter"
            else ("einen" if accusative else "ein")
        )
    if language == "es" and quantity == 1:
        _, _, gender = _nouns(item, language)
        return "una" if gender == "feminine" else "un"
    if language == "fr" and quantity == 1:
        _, _, gender = _nouns(item, language)
        return "une" if gender == "feminine" else "un"
    return NUMBERS[language][quantity]


def _repeat(language, item, quantity, size, short, tag):
    np = _request_np(item, language, quantity, size, neutral=True)
    if language == "ko":
        return REPEAT_FRAMES[language].format(NP=np, tag=tag)
    return REPEAT_FRAMES[language].format(NP=np, short=short)


def _repair(language, field, value, transaction, item, follow_type):
    quantity = transaction["quantity"]
    if field == "quantity":
        number = _number(language, item, value)
        if language == "es":
            return f"En realidad, {number}, por favor."
        if language == "fr":
            return f"En fait, j'en voudrais {number}."
        if language == "de":
            return f"Eigentlich {number}, bitte."
        counter = _nouns(item, language)[1]
        particle = "이요" if counter in {"잔", "권"} else "요"
        return f"아니요, {number} {counter}{particle}."
    detail_type = "size" if field == "size" else follow_type
    reply = _reply(language, detail_type, value, quantity, item, transaction["scenario"])
    short = _short_reply(language, detail_type, value, quantity, item)
    if language == "es":
        return f"En realidad, {short}, por favor."
    if language == "fr":
        tail = (
            "s'il te plaît"
            if transaction["scenario"] in {"classroom", "home"}
            else "s'il vous plaît"
        )
        return f"En fait, {short}, {tail}."
    if language == "de":
        return f"Eigentlich {short}, bitte."
    return "아니요, " + reply[:-1] + "."


def _request_chunks(language, item, scenario, quantity, size):
    np = _request_np(item, language, quantity, size)
    opener, pattern = REQUEST_FRAMES[scenario][language]
    complete = _request(language, item, scenario, quantity, size)
    if language == "ko":
        noun_chunk = f"{_ko_size(size)}{_nouns(item, language)[0]}"
        count_chunk = f"{NUMBERS[language][quantity]} {_nouns(item, language)[1]}"
        verb = "빌려 주세요" if scenario == "classroom" else "주세요"
        return (
            [noun_chunk, count_chunk, verb, complete[-1]],
            complete,
            f"{noun_chunk} {count_chunk} ___" + complete[-1],
        )
    if language == "es":
        tail = ", por favor"
    elif language == "fr":
        tail = ", s'il vous plaît" if scenario in {"cafe", "shop"} else ", s'il te plaît"
    else:
        tail = ", bitte"
    mark = complete[-1]
    if language == "fr" and mark == "?":
        tail = ", s'il te plaît" if scenario in {"classroom", "home"} else ", s'il vous plaît"
    return [opener, np, tail, mark], complete, complete.replace(opener, "___", 1)


def _order_label(quantity, item, size=None):
    count = ENGLISH_NUMBER[quantity]
    parts = [count]
    if size:
        parts.append(ENGLISH_SIZE[size])
    label = item.label
    if quantity != 1 and not label.endswith("s"):
        label += "s"
    return " ".join((*parts, label))


def _shuffled(rng, choices):
    choices = list(choices)
    rng.shuffle(choices)
    return choices


def build_m06_result(payload):
    """Build the six questions entirely from the reviewed transaction snapshot."""
    language = payload["targetLanguage"]
    item = ITEMS[payload["itemKey"]]
    transaction = payload["transaction"]
    quantity = transaction["quantity"]
    size = transaction["requestDetails"].get("size")
    scenario = transaction["scenario"]
    follow_type = transaction["followUp"]["type"]
    follow_value = transaction["followUp"]["value"]
    request_chunks, request_text, request_template = _request_chunks(
        language, item, scenario, quantity, size
    )
    request_fields = {"item": item.key, "quantity": quantity, **transaction["requestDetails"]}
    follow_question = _follow_up_question(follow_type, language, item)
    follow_reply = _reply(language, follow_type, follow_value, quantity, item, scenario)
    short_reply = _short_reply(language, follow_type, follow_value, quantity, item)
    mismatch = transaction["mismatch"]
    shown_quantity = (
        mismatch["servedValue"]
        if mismatch["flag"] and mismatch["field"] == "quantity"
        else quantity
    )
    shown_size = (
        mismatch["servedValue"]
        if mismatch["flag"] and mismatch["field"] == "size" and size
        else size
    )
    shown_follow = (
        mismatch["servedValue"]
        if mismatch["flag"] and mismatch["field"] == follow_type
        else follow_value
    )
    shown_short = _short_reply(language, follow_type, shown_follow, shown_quantity, item)
    shown_tag = (
        FOLLOW_UPS[follow_type]["ko"][1][shown_follow][2]
        if language == "ko" and len(FOLLOW_UPS[follow_type]["ko"][1][shown_follow]) > 2
        else shown_short
    )
    repeat = _repeat(language, item, shown_quantity, shown_size, shown_short, shown_tag)
    repair_value = mismatch["correctedValue"]
    repair_field = mismatch["field"] or follow_type
    repair_value = repair_value if mismatch["flag"] else follow_value
    answer_q6 = (
        _repair(language, repair_field, repair_value, transaction, item, follow_type)
        if mismatch["flag"]
        else CONFIRM[language]
    )
    payload["expectedQ6Answer"] = answer_q6
    q6_chunks, repair_chunks = _response_chunks(
        language, repair_field, repair_value, transaction, item, follow_type
    )
    if not mismatch["flag"]:
        q6_chunks = _confirm_chunks(language)
    wrong_value = _wrong_value_chunk(language, mismatch, transaction, item, follow_type)
    seed = transaction["seed"]
    rng = random.Random(seed)
    item_option = next(
        (candidate for _obj, candidate in payload["alternatives"] if candidate.key != item.key),
        next(
            candidate
            for candidate in ITEMS.values()
            if candidate.category == item.category and candidate.key != item.key
        ),
    )
    wrong_quantity = next(number for number in _quantity_choices(scenario) if number != quantity)
    q1_options = [
        ("correct", _order_label(quantity, item, size), request_fields),
        (
            "wrong-quantity",
            _order_label(wrong_quantity, item, size),
            {
                **request_fields,
                "quantity": wrong_quantity,
            },
        ),
    ]
    distractor_field_map = {"wrong-quantity": {"quantity": str(wrong_quantity)}}
    if size:
        wrong_size = "large" if size == "small" else "small"
        q1_options.append(
            (
                "wrong-size",
                _order_label(quantity, item, wrong_size),
                {
                    **request_fields,
                    "size": wrong_size,
                },
            )
        )
        distractor_field_map["wrong-size"] = {"size": wrong_size}
    else:
        q1_options.append(
            (
                "wrong-item",
                _order_label(quantity, item_option),
                {
                    **request_fields,
                    "item": item_option.key,
                },
            )
        )
        distractor_field_map["wrong-item"] = {"item": item_option.key}
    q1_options = _shuffled(rng, q1_options)
    q1 = M06Question(
        question_id="m06-q1",
        purpose="listenOrderCard",
        prompt="Which order did you hear?",
        interaction_type="multipleChoice",
        options=[VocabularyChoice(option_id=key, label=label) for key, label, _ in q1_options],
        correct_option_id="correct",
        audio_text=request_text,
        listen_first=True,
        translation=None,
        gap_kind="orderCard",
        assistance_steps=[
            "replayAudio",
            "visualDetail",
            "phraseOnset",
            "chunkBank",
            "fullModel",
        ],
        target_id="understand-order",
        evidence_type="recognition",
        option_fields={
            key: {
                field: str(value)
                for field, value in values.items()
                if request_fields.get(field) != value
            }
            for key, _label, values in q1_options
        },
        distractor_fields={
            key: field
            for key, field in (
                ("wrong-quantity", "quantity"),
                ("wrong-size", "size"),
                ("wrong-item", "item"),
            )
            if key in {option_id for option_id, _label, _fields in q1_options}
        },
    )
    opener = REQUEST_FRAMES[scenario][language][0]
    if language == "ko":
        gap_answer = "빌려 주세요" if scenario == "classroom" else "주세요"
    else:
        gap_answer = opener
    wrong_openers = WRONG_OPENERS[language]
    q2_choices = _shuffled(
        rng,
        [
            ("correct", gap_answer),
            ("wrong-a", wrong_openers[0]),
            ("wrong-b", wrong_openers[1]),
        ],
    )
    q2 = M06Question(
        question_id="m06-q2",
        purpose="politeChunkGap",
        prompt="Choose the polite phrase that completes the request.",
        interaction_type="multipleChoice",
        options=[VocabularyChoice(option_id=key, label=label) for key, label in q2_choices],
        correct_option_id="correct",
        slot_template=request_template,
        complete_chunk=request_text,
        gap_kind="functionalChunk",
        assistance_steps=["phraseOnset", "chunkBank", "fullModel"],
        target_id="use-request-chunk",
        evidence_type="recognition",
        distractor_fields={"wrong-a": "functionalChunk", "wrong-b": "functionalChunk"},
    )
    wrong_open = wrong_openers[0]
    wrong_np = (
        f"{NUMBERS[language][wrong_quantity]} {_nouns(item, language)[1]}"
        if language == "ko"
        else _request_np(item, language, wrong_quantity, size)
    )
    q3_bank = _shuffled(rng, [*request_chunks, wrong_np, wrong_open])
    q3 = M06Question(
        question_id="m06-q3",
        purpose="buildRequest",
        prompt="Build a polite request for the item.",
        interaction_type="sentenceBuilding",
        correct_text=request_text,
        token_bank=q3_bank,
        correct_chunks=request_chunks,
        gap_kind="multiSlotRequest",
        assistance_steps=["phraseOnset", "chunkBank", "fullModel"],
        target_id="build-request",
        evidence_type="construction",
        distractor_fields={wrong_np: "quantity", wrong_open: "request"},
    )
    follow_type_label = {
        "serviceSetting": "Eat in or take away",
        "temperature": "Hot or cold",
        "size": "Which size",
        "colour": "Which colour",
    }[follow_type]
    given_field_labels = ["How many"]
    if size:
        given_field_labels.append("Which size")
    other_label = next(
        label
        for label in ("Which colour", "Hot or cold", "Eat in or take away", "Which size")
        if label != follow_type_label and label not in given_field_labels
    )
    q4_options = _shuffled(
        rng,
        [
            ("correct", follow_type_label),
            ("given", given_field_labels[0]),
            ("other", other_label),
        ],
    )
    q4 = M06Question(
        question_id="m06-q4",
        purpose="identifyMissingDetail",
        prompt="The server asks a question. What do they need to know?",
        interaction_type="multipleChoice",
        options=[VocabularyChoice(option_id=key, label=label) for key, label in q4_options],
        correct_option_id="correct",
        audio_text=follow_question,
        listen_first=True,
        gap_kind="missingDetail",
        assistance_steps=["replayAudio", "visualDetail", "fullModel"],
        target_id="identify-missing-detail",
        evidence_type="recognition",
        distractor_fields={"given": "quantity", "other": "other detail"},
    )
    q4.option_fields = {key: {"field": label} for key, label in q4_options}
    q5_mode = payload["q5Mode"]
    q5_accepted = [
        _capitalize_sentence(short_reply),
        _capitalize_sentence(follow_reply.rstrip(".")),
    ]
    q5_distractor = _opposite_value(follow_type, follow_value)
    other_type = (
        "serviceSetting"
        if follow_type == "colour"
        else ("colour" if follow_type == "serviceSetting" else "serviceSetting")
    )
    other_value = "takeAway" if other_type == "serviceSetting" else "blue"
    q5_other = _reply(language, other_type, other_value, quantity, item, scenario)
    q5_dialogue = [
        {"speaker": "learner", "text": request_text},
        {"speaker": "server", "text": follow_question},
    ]
    if q5_mode == "chunkChoice":
        q5_options = _shuffled(
            rng,
            [
                ("correct", follow_reply),
                (
                    "wrong-value",
                    _reply(language, follow_type, q5_distractor, quantity, item, scenario),
                ),
                ("wrong-detail", q5_other),
            ],
        )
        q5 = M06Question(
            question_id="m06-q5",
            purpose="replyWithDetail",
            prompt="Reply with the saved detail.",
            interaction_type="multipleChoice",
            options=[VocabularyChoice(option_id=key, label=label) for key, label in q5_options],
            correct_option_id="correct",
            accepted_answers=q5_accepted,
            gap_kind="detailGap",
            dialogue=q5_dialogue,
            assistance_steps=["phraseOnset", "chunkBank", "fullModel"],
            target_id="reply-with-detail",
            evidence_type="recognition",
            distractor_fields={"wrong-value": follow_type, "wrong-detail": follow_type},
        )
    elif q5_mode == "wordBank":
        q5_chunks = _reply_chunks(language, follow_type, follow_value, quantity, item, scenario)
        wrong_chunk = _reply_chunks(language, follow_type, q5_distractor, quantity, item, scenario)[
            0
        ]
        q5 = M06Question(
            question_id="m06-q5",
            purpose="replyWithDetail",
            prompt="Reply with the saved detail.",
            interaction_type="sentenceBuilding",
            correct_text=follow_reply,
            accepted_answers=q5_accepted,
            token_bank=_shuffled(rng, [*q5_chunks, wrong_chunk]),
            correct_chunks=q5_chunks,
            slot_template=_reply_template(language, follow_reply),
            complete_chunk=follow_reply,
            gap_kind="detailGap",
            dialogue=q5_dialogue,
            assistance_steps=["phraseOnset", "chunkBank", "fullModel"],
            target_id="reply-with-detail",
            evidence_type="construction",
            distractor_fields={wrong_chunk: follow_type},
        )
    else:
        q5 = M06Question(
            question_id="m06-q5",
            purpose="replyWithDetail",
            prompt="Reply with the saved detail.",
            interaction_type="textCloze",
            correct_text=_capitalize_sentence(short_reply),
            accepted_answers=q5_accepted,
            slot_template=_reply_template(language, follow_reply),
            complete_chunk=follow_reply,
            gap_kind="openCloze",
            dialogue=q5_dialogue,
            assistance_steps=["phraseOnset", "chunkBank", "fullModel"],
            target_id="reply-with-detail",
            evidence_type="construction",
            distractor_fields={},
        )
    dialogue = [
        {"speaker": "learner", "text": request_text},
        {"speaker": "server", "text": follow_question},
        {"speaker": "learner", "text": follow_reply},
        {"speaker": "server", "text": repeat},
    ]
    q6 = M06Question(
        question_id="m06-q6",
        purpose="confirmOrRepair",
        prompt="Listen to the server repeat your order. Confirm it or correct it.",
        interaction_type="sentenceBuilding",
        correct_text=answer_q6,
        token_bank=_shuffled(
            rng, dict.fromkeys([*_confirm_chunks(language), *repair_chunks, wrong_value])
        ),
        correct_chunks=q6_chunks,
        repair_chunks=repair_chunks,
        wrong_value_chunk=wrong_value,
        audio_text=repeat,
        gap_kind="dialogueResponse",
        dialogue=dialogue,
        assistance_steps=["replayAudio", "phraseOnset", "chunkBank", "fullModel"],
        target_id="confirm-or-repair",
        evidence_type="construction",
        distractor_fields={
            **{
                chunk: "confirmOrRepair"
                for chunk in (
                    set(_confirm_chunks(language) if mismatch["flag"] else repair_chunks)
                    - set(q6_chunks)
                )
            },
            wrong_value: mismatch["field"] or follow_type,
        },
    )
    result = MissionM06Result(questions=[q1, q2, q3, q4, q5, q6])
    transaction.update(
        {
            "dialogue": q6.dialogue or [],
            "optionOrder": {
                question.question_id: [option.option_id for option in question.options]
                for question in result.questions
            },
            "answers": {
                question.question_id: {
                    "correct": question.correct_option_id or question.correct_text,
                    "accepted": question.accepted_answers,
                }
                for question in result.questions
            },
            "distractorFields": {
                question.question_id: question.distractor_fields for question in result.questions
            },
            "gapKinds": {question.question_id: question.gap_kind for question in result.questions},
        }
    )
    return result


def _opposite_value(kind, value):
    return {
        "serviceSetting": {"eatIn": "takeAway", "takeAway": "eatIn"},
        "temperature": {"hot": "cold", "cold": "hot"},
        "size": {"big": "small", "small": "big"},
        "colour": {"blue": "red", "red": "black", "black": "blue"},
    }[kind][value]


def _reply_template(language, reply):
    if language == "ko":
        return "___"
    if language == "fr":
        tail = ", s'il vous plaît." if "vous" in reply else ", s'il te plaît."
        return "___" + tail
    if language == "de":
        return "___, bitte."
    return "___, por favor."


def _reply_chunks(language, follow_type, value, quantity, item, scenario):
    reply = _reply(language, follow_type, value, quantity, item, scenario)
    if language == "ko":
        return [reply[:-1], "."]
    if language == "fr":
        for tail in (", s'il vous plaît", ", s'il te plaît"):
            if reply.endswith(tail + "."):
                return [reply[: -len(tail + ".")], tail, "."]
    if language == "de" and reply.endswith(", bitte."):
        return [reply[: -len(", bitte.")], ", bitte", "."]
    if language == "es" and reply.endswith(", por favor."):
        return [reply[: -len(", por favor.")], ", por favor", "."]
    return [reply[:-1], "."]


def _confirm_chunks(language):
    return [CONFIRM[language][:-1], "."]


def _response_chunks(language, field, value, transaction, item, follow_type):
    confirm_chunks = _confirm_chunks(language)
    if field == "quantity":
        number = _number(language, item, value)
        if language == "es":
            chunks = ["En realidad,", number, ", por favor", "."]
        elif language == "fr":
            chunks = ["En fait, j'en voudrais", number, "."]
        elif language == "de":
            chunks = ["Eigentlich", number, ", bitte", "."]
        else:
            counter = _nouns(item, language)[1]
            particle = "이요" if counter in {"잔", "권"} else "요"
            chunks = ["아니요,", f"{number} {counter}{particle}", "."]
    else:
        detail_type = "size" if field == "size" else follow_type
        short = _short_reply(language, detail_type, value, transaction["quantity"], item)
        if language == "es":
            chunks = ["En realidad,", short, ", por favor", "."]
        elif language == "fr":
            tail = (
                ", s'il te plaît"
                if transaction["scenario"] in {"classroom", "home"}
                else ", s'il vous plaît"
            )
            chunks = ["En fait,", short, tail, "."]
        elif language == "de":
            chunks = ["Eigentlich", short, ", bitte", "."]
        else:
            chunks = [
                "아니요,",
                _reply(
                    language,
                    detail_type,
                    value,
                    transaction["quantity"],
                    item,
                    transaction["scenario"],
                )[:-1],
                ".",
            ]
    return (confirm_chunks if not transaction["mismatch"]["flag"] else chunks), chunks


def _wrong_value_chunk(language, mismatch, transaction, item, follow_type):
    field = mismatch["field"]
    if not mismatch["flag"]:
        field = follow_type
        value = _opposite_value(follow_type, transaction["followUp"]["value"])
    elif field == "quantity":
        value = next(
            number
            for number in _quantity_choices(transaction["scenario"])
            if number != transaction["quantity"]
        )
    else:
        value = mismatch["servedValue"]
    if field == "quantity":
        if language == "ko":
            counter = _nouns(item, language)[1]
            particle = "이요" if counter in {"잔", "권"} else "요"
            return f"{_number(language, item, value)} {counter}{particle}"
        return _number(language, item, value)
    detail_type = "size" if field == "size" else follow_type
    return _short_reply(language, detail_type, value, transaction["quantity"], item)


def _reply_template_for_server(language, reply):
    return _reply_template(language, reply)


def build_m06_payload(mission, language, objects, session_id, progress, review_markers, context):
    language = language.lower()
    if language not in {"es", "fr", "de", "ko"}:
        return {"invalidRoleplay": True}
    candidates = requestable_objects(objects)
    markers = review_markers or {}
    candidates.sort(key=lambda pair: (markers.get(str(pair[0].id), 10**6), str(pair[0].id)))
    if not candidates:
        return {"invalidRoleplay": True}
    saved = (progress or {}).get("m06Transaction")
    selected_id = (
        str(saved.get("sceneObjectId"))
        if saved
        else (
            str(context["selected_scene_object_id"])
            if context and context.get("selected_scene_object_id")
            else None
        )
    )
    selected = next((pair for pair in candidates if str(pair[0].id) == selected_id), None)
    primary_obj, item = selected or candidates[0]
    alternatives = [
        (obj, alternative)
        for obj, alternative in candidates
        if str(obj.id) != str(primary_obj.id) and alternative.label != item.label
    ][:2]
    transaction = saved or select_transaction(session_id, item, language)
    transaction = {
        **transaction,
        "sceneObjectId": str(primary_obj.id),
        "itemKey": item.key,
        "itemLabel": item.label,
        "scenario": item.category,
        "targetLanguage": language,
        "alternatives": [
            {"sceneObjectId": str(obj.id), "label": alt.label} for obj, alt in alternatives
        ],
        "scenarioAccepted": bool(
            transaction.get("scenarioAccepted", False)
            or (context or {}).get("scenario_accepted", False)
        ),
    }
    q5_mode = (progress or {}).get("m06Q5Mode")
    if saved:
        q5_mode = saved.get("q5Mode", q5_mode)
    if q5_mode is None:
        independent = (progress or {}).get("m06IndependentQ5", 0)
        completed = (progress or {}).get("m06CompletedLessons", 0)
        q5_mode = (
            "openCloze" if independent >= 2 else "wordBank" if completed >= 1 else "chunkChoice"
        )
    transaction["q5Mode"] = q5_mode
    return {
        "missionId": mission.mission_id,
        "practiceLevel": mission.practice_level,
        "contentVersion": mission.content_version,
        "targetLanguage": language,
        "sessionId": str(session_id),
        "itemKey": item.key,
        "itemLabel": item.label,
        "sceneObjectId": primary_obj.id,
        "scenarioPrompt": SCENARIO_PROMPTS[_scenario(item)],
        "alternatives": alternatives,
        "transaction": transaction,
        "q5Mode": q5_mode,
    }


def build_m06_tasks(session_id, mission, payload, result, _vocabulary_ids=None):
    """Return both contiguous M06 grammar tasks with stable namespace ids."""
    questions = result.questions if isinstance(result, MissionM06Result) else result["questions"]
    validate_questions = questions
    transaction = payload["transaction"]
    primary_id = UUID(transaction["sceneObjectId"])
    scenario = MissionScenario(
        scenario_id=f"m06-{transaction['itemKey']}",
        prompt=payload["scenarioPrompt"],
        scene_object_id=primary_id,
        item_label=transaction["itemLabel"],
        accepted=bool(transaction.get("scenarioAccepted", False)),
        alternatives=[
            MissionScenarioAlternative(
                scene_object_id=UUID(item["sceneObjectId"]), label=item["label"]
            )
            for item in transaction.get("alternatives", [])
        ],
    )
    task_ids = [
        uuid5(session_id, "mission:M06-A2.v1:lesson"),
        uuid5(session_id, "mission:M06-A2.v1:lesson-2"),
    ]
    built = []
    for task_index, task_questions in enumerate((validate_questions[:3], validate_questions[3:])):
        private_answers = {}
        distractors = {}
        option_order = {}
        gap_kinds = {}
        evaluations = []
        public_questions = []
        for question in task_questions:
            answer = (
                question.correct_option_id
                if question.interaction_type == "multipleChoice"
                else question.correct_text
            )
            private_answers[question.question_id] = {
                "correct": answer,
                "accepted": question.accepted_answers,
                "chunks": question.correct_chunks,
                "model": question.correct_text
                or next(
                    (
                        option.label
                        for option in question.options
                        if option.option_id == question.correct_option_id
                    ),
                    None,
                ),
            }
            distractors[question.question_id] = question.distractor_fields
            option_order[question.question_id] = [item.option_id for item in question.options]
            gap_kinds[question.question_id] = question.gap_kind
            public_questions.append(
                GrammarLessonQuestion(
                    question_id=question.question_id,
                    prompt=question.prompt,
                    interaction_type=question.interaction_type,
                    options=question.options,
                    token_bank=question.token_bank,
                    translation=question.translation,
                    audio_text=question.audio_text,
                    listen_first=question.listen_first,
                    slot_template=question.slot_template,
                    complete_chunk=question.complete_chunk,
                    gap_kind=question.gap_kind,
                    assistance_steps=question.assistance_steps,
                    dialogue=question.dialogue,
                    allow_retry=question.allow_retry,
                    wrong_field_tokens=question.distractor_fields,
                    section=(
                        "Task 1 · Place the order"
                        if task_index == 0
                        else "Task 2 · Finish the order"
                    ),
                )
            )
            evaluations.append(
                QuestionEvaluation(
                    question_id=question.question_id,
                    objective_id=mission.objective.objective_id,
                    target_ids=[question.target_id],
                    evidence_type=question.evidence_type,
                    scene_object_id=primary_id,
                )
            )
        mission_state = {
            "transaction": transaction,
            "answers": private_answers,
            "distractorFields": distractors,
            "optionOrder": option_order,
            "gapKinds": gap_kinds,
            "q5Mode": payload["q5Mode"],
            "scenarioAccepted": bool(transaction.get("scenarioAccepted", False)),
        }
        content = GrammarLessonContent(
            focus="sceneMissionM06A2",
            title="Ask for the details",
            questions=public_questions,
            check_each_question=True,
            scenario=scenario if task_index == 0 else None,
            **mission_fields(mission),
        )
        task = SessionTask(
            id=task_ids[task_index],
            session_id=session_id,
            phase="learning",
            kind="grammarLesson",
            order_index=task_index,
            public_content=content,
            answer_key=TaskAnswerKey(
                correct_option_ids={
                    q.question_id: (
                        q.correct_option_id
                        if q.interaction_type == "multipleChoice"
                        else q.correct_text
                    )
                    for q in task_questions
                },
                question_evaluations=evaluations,
                mission_state=mission_state,
            ),
            scene_object_id=primary_id,
        )
        built.append(task)
    return built


def _scenario_name(item):
    return _scenario(item)


def build_m06_lesson(
    mission,
    language,
    objects,
    _relations,
    _words,
    _scene,
    _counts,
    progress,
    session_id,
    review_markers=None,
    context=None,
):
    context = context or {}
    payload = build_m06_payload(
        mission, language, objects, session_id, progress, review_markers, context
    )
    if payload.get("invalidRoleplay"):
        return payload
    result = build_m06_result(payload)
    from app.ai.features.learning_tasks.mission_m06 import validate_m06_lesson

    validate_m06_lesson(payload, result)
    return payload


def build_m06_task_payload(payload):
    return payload
