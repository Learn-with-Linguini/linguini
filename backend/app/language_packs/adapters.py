"""Adapt validated bound sentences to the existing M01 task and grading contracts."""

from __future__ import annotations

import random
from uuid import NAMESPACE_URL, uuid5

from app.ai.features.learning_tasks.mission_a0 import (
    A0LessonResult,
    _build_question,
    _choice_question,
    _marker_question,
    _other,
    _sections,
)
from app.ai.features.learning_tasks.mission_a2 import MissionA2Question, MissionA2Result
from app.ai.features.learning_tasks.mission_m01 import (
    CONFIRM_IDS,
    DESCRIBE_SECTION,
    IDENTIFY_SECTION,
    M01LessonResult,
    M01Question,
)
from app.missions import get_mission
from app.services.mission_lessons_a0 import a0_lesson_task
from app.services.mission_lessons_a2 import m01_a2_task
from app.services.mission_lessons_m01 import m01_lesson_task

from .generation import derive_chunks

# Explicit demo callers only; application callers always supply their session ID.
_SESSION_ID = uuid5(NAMESPACE_URL, "language-packs/demo")


def _objects(facts, vocabulary, separator=" "):
    terms = {term.fact_id: term for term in vocabulary.terms}
    rows, by_fact = [], {}
    for obj in facts.scene_facts.objects:
        term = terms.get(obj.fact_id)
        if term is None:
            continue
        forms = term.forms_by_key
        bare = forms.get("bare", term.target_text)
        indefinite = forms.get("indefinite") or separator.join(
            filter(
                None,
                [
                    forms.get("article_indefinite"),
                    bare,
                ],
            )
        )
        row = dict(
            key=str(obj.scene_object_id),
            fact_id=obj.fact_id,
            source=obj.label,
            label=obj.label,
            englishLabel=obj.label,
            marker=obj.marker,
            noun=bare,
            bareNoun=bare,
            gender=term.agreement,
            name=forms.get("definite", bare),
            chunk=forms.get("definite", bare),
            nounPhrase=indefinite,
            identify="",
            isIt="",
            vocabularyItemId=str(term.vocabulary_item_id) if term.vocabulary_item_id else None,
        )
        rows.append(row)
        by_fact[obj.fact_id] = row
    return rows, by_fact


# Keys of in-sentence gender agreement forms; other keys (modifier, predicative,
# case forms) are not wrong-agreement alternatives.
AGREEMENT_KEYS = frozenset({"masculine", "feminine", "neuter"})


def _form(term, gender):
    return term.forms_by_key.get(gender) or term.forms_by_key.get("default", term.target_text)


def _standalone_form(term, gender):
    """A detail named on its own (a choice), e.g. German rot rather than attributive rote."""
    return term.forms_by_key.get("predicative") or _form(term, gender)


def _detail_options(facts, vocabulary, attribute, gender, *, include_pack=False, pack=None):
    terms = {term.fact_id: term for term in vocabulary.terms}
    selected = terms[attribute.fact_id]
    options = [_standalone_form(selected, gender)]
    meanings = {options[0].casefold(): attribute.value}
    # Distractors are approved translations, never an implicit per-language lexicon.
    for other in facts.scene_facts.attributes:
        if (
            other.kind != attribute.kind
            or other.value == attribute.value
            or other.fact_id not in terms
        ):
            continue
        if pack is not None:
            if attribute.kind == "colour" and other.value in pack.lexical.get(
                "confusable_colours", {}
            ).get(attribute.value, "").split("|"):
                continue
            if attribute.kind != "colour" and other.value not in pack.lexical.get(
                "attribute_contrasts", {}
            ).get(f"{attribute.kind}:{attribute.value}", "").split("|"):
                continue
        form = _standalone_form(terms[other.fact_id], gender)
        if form.casefold() not in {value.casefold() for value in options}:
            options.append(form)
            meanings[form.casefold()] = other.value
        if len(options) == 3:
            break
    # Preserve existing scene-colour choices; use pack colours when no distinct
    # scene colour is available. Other detail kinds keep their existing fill rule.
    if include_pack and len(options) < (2 if attribute.kind == "colour" else 3):
        for term in sorted(vocabulary.terms, key=lambda t: t.provenance != "modelProposal"):
            if term.linguistic.get("attribute-kind") != attribute.kind:
                continue
            proposed = term.provenance == "modelProposal"
            if proposed and term.linguistic.get("contrast-for") != attribute.fact_id:
                continue
            if (
                attribute.kind == "colour"
                and pack is not None
                and term.source_text
                in (pack.lexical.get("confusable_colours", {}).get(attribute.value, "").split("|"))
            ):
                continue
            if (
                attribute.kind != "colour"
                and not proposed
                and pack is not None
                and term.source_text
                not in (
                    pack.lexical.get("attribute_contrasts", {})
                    .get(f"{attribute.kind}:{attribute.value}", "")
                    .split("|")
                )
            ):
                continue
            form = _standalone_form(term, gender)
            if form.casefold() not in {value.casefold() for value in options}:
                options.append(form)
                meanings[form.casefold()] = term.source_text
            if len(options) == 3:
                break
    if len(options) < 2:
        raise ValueError(
            f"M01 needs a contrasting approved detail option for {attribute.kind}:"
            f"{attribute.value} (agreement={gender!r}). Supply a distinct validated "
            "scene translation or model-proposed alternative. Pack reference "
            "vocabulary is optional; missing or unsuitable candidates must be retried."
        )
    return options, meanings


def validate_lesson_inputs(level, pack, facts, vocabulary, plan):
    """Reject missing A1 choice data before any model generation or repair calls."""
    if level != "A1":
        return
    spec = next(slot for slot in plan.slots if slot.slot_id == "chooseAttribute").specs[0]
    attribute = next(
        attr for attr in facts.scene_facts.attributes if attr.fact_id == spec.bindings["attribute"]
    )
    subject = next(term for term in vocabulary.terms if term.fact_id == spec.bindings["object"])
    _detail_options(
        facts, vocabulary, attribute, subject.agreement, include_pack=True, pack=pack,
    )


def build_lesson(
    level, pack, facts, vocabulary, plan, accepted, *, builder_selection=None, session_id=None
):
    session_id = session_id or _SESSION_ID
    selection = builder_selection or {}
    rows, by_fact = _objects(
        facts,
        vocabulary,
        " " if pack.language.word_separator == "space" else "",
    )
    terms = {term.fact_id: term for term in vocabulary.terms}
    attrs = {attr.fact_id: attr for attr in facts.scene_facts.attributes}
    specs = {slot.slot_id: {spec.use: spec for spec in slot.specs} for slot in plan.slots}
    sentences = {
        (item.candidate.slot_id, item.candidate.spec_id): item.candidate for item in accepted
    }
    labels = {label.semantic: label for label in pack.labels}
    seed = selection.get("seed", str(session_id))

    def candidate(slot, use=None):
        spec = specs[slot][use] if use is not None else next(iter(specs[slot].values()))
        return sentences[(slot, spec.spec_id)]

    def label(semantic):
        return labels[semantic].text

    def shuffle(values, salt):
        result = list(values)
        random.Random(f"{seed}:{salt}").shuffle(result)
        return result

    def chunks(sentence, extras=(), phrase=False):
        sentence = derive_chunks(
            sentence,
            pack.language.word_separator,
            phrase_chunks=phrase,
            phrase_boundaries=pack.language.phrase_boundaries,
        )
        answers = [chunk.text for chunk in sentence.chunks]
        if phrase:
            extras = [
                chunk.text
                for text in extras
                for chunk in derive_chunks(
                    sentence.model_copy(update={"text": text}),
                    pack.language.word_separator,
                    phrase_chunks=True,
                    phrase_boundaries=pack.language.phrase_boundaries,
                ).chunks
            ]
        return dict(
            correct_text=sentence.text,
            answer_chunks=answers,
            token_bank=shuffle([*answers, *extras], sentence.slot_id),
            distractor_chunks=list(extras),
        )

    vocabulary_ids = {
        row["key"]: row["vocabularyItemId"] for row in rows if row["vocabularyItemId"]
    }
    payload = dict(
        targetLanguage=pack.language.code,
        missionId="M01",
        practiceLevel=level,
        contentVersion=plan.content_version,
        seed=seed,
    )
    if level == "A0":
        focus = [
            by_fact[next(iter(specs[f"matchName-{i}"].values())).bindings["object"]] for i in (1, 2)
        ]
        translations = {label("what-is-this"): labels["what-is-this"].meaning}
        templates = next(
            c.templates for c in pack.constructions if c.construction_id == "identify-object"
        )
        taught = []
        for row in rows:
            english = row["source"]
            indefinite = f"{'an' if english[:1].lower() in 'aeiou' else 'a'} {english}"
            for name, meaning in (
                (row["name"], f"the {english}"),
                (templates.get("identify", "").format(**row), f"This is {indefinite}."),
                (templates.get("question", "").format(**row), f"Is this {indefinite}?"),
                (templates.get("find", "").format(**row), f"Find the {english}."),
                (templates.get("slot", "").format(**row), f"the {english}"),
            ):
                if name:
                    taught.append(name)
                    translations[name] = meaning
        for row, index in zip(focus, (1, 2), strict=True):
            for field, slot in (
                ("name", "matchName"),
                ("isIt", "confirmName"),
                ("identify", "buildIdentify"),
            ):
                sentence = candidate(f"{slot}-{index}")
                row[field] = sentence.text
                translations[sentence.text] = sentence.translation
        payload.update(
            focus=[row["key"] for row in focus],
            approvedObjects=rows,
            approvedTranslations=translations,
            whatIsThis=label("what-is-this"),
            yesNo=[label("yes-answer"), label("no-answer")],
            approvedSentenceChunks=list(dict.fromkeys([*translations, *taught])),
            approvedArticlesOrEndings=[],
            approvedNumberWords={},
        )
        questions = []
        for index, (section, target) in enumerate(_sections(payload), 1):
            slot = f"confirmName-{index}"
            spec = next(iter(specs[slot].values()))
            other = _other(payload, target, f"tile-{index}")
            extra_noun = next((
                term.forms_by_key.get("bare", term.target_text)
                for term in vocabulary.terms
                if term.provenance == "modelProposal"
                and term.linguistic.get("alternative-kind") == "noun"
                and term.linguistic.get("contrast-for") == target["fact_id"]
            ), other["noun"])
            marker = _marker_question(
                payload, "matchName", section, target, target["name"], index=index
            )
            confirm = _choice_question(
                payload,
                "confirmName",
                section,
                target,
                target["isIt"],
                payload["yesNo"],
                payload["yesNo"][0 if spec.truth else 1],
                index=index,
                shuffle=False,
                statement_true=spec.truth,
                stated_key=by_fact[spec.bindings["object"]]["key"],
                audio_text=target["isIt"],
            )
            built = _build_question(
                payload,
                "buildIdentify",
                section,
                target,
                payload["whatIsThis"],
                target["identify"],
                extra_noun,
                index=index,
            )
            # Use only chunks derived after complete-sentence validation.
            built["token_bank"] = chunks(candidate(f"buildIdentify-{index}"), [extra_noun])[
                "token_bank"
            ]
            questions.extend((marker, confirm, built))
        result = A0LessonResult(title="Name the objects", questions=questions)
        task = a0_lesson_task(
            session_id, get_mission("M01", level, 1), payload, result, vocabulary_ids
        )
    elif level == "A1":
        pairs = []
        for slot in ("chooseAttribute", "describeObject"):
            spec = next(iter(specs[slot].values()))
            obj, detail = by_fact[spec.bindings["object"]], attrs[spec.bindings["attribute"]]
            if detail.object_fact_id != obj["fact_id"]:
                raise ValueError("attribute is bound to another object instance")
            term = terms[detail.fact_id]
            pairs.append(
                dict(
                    **obj,
                    attributeKey=detail.fact_id,
                    attributeType=detail.kind,
                    attributeSource=detail.value,
                    agreedForm=_form(term, obj["gender"]),
                    before=term.position == "before",
                )
            )
        first, second = pairs
        # The chosen detail stands alone; the described one agrees inside the sentence.
        first["agreedForm"] = _standalone_form(terms[first["attributeKey"]], first["gender"])
        options, meanings = _detail_options(
            facts,
            vocabulary,
            attrs[first["attributeKey"]],
            first["gender"],
            include_pack=True,
            pack=pack,
        )
        prompt_label = labels.get(f"attribute-prompt-{first['attributeType']}") or labels.get(
            "attribute-prompt"
        )
        if prompt_label is None:
            raise ValueError("pack needs a prompt for the selected attribute construction")
        payload.update(
            pairs=pairs,
            attributeOptions=options,
            attributeMeanings=meanings,
            describeExtras=[],
            attributePromptTranslation=prompt_label.meaning,
        )
        description_term = terms[second["attributeKey"]]
        canonical = candidate("describeObject").text
        # Wrong-agreement tiles exist only for gendered languages, and only when the
        # alternative form would actually change the canonical sentence.
        extras = [] if pack.language.grammatical_gender == "none" else list(
            dict.fromkeys(
                form
                for key, form in description_term.forms_by_key.items()
                if key in AGREEMENT_KEYS
                and form != second["agreedForm"]
                and second["agreedForm"] in canonical
            )
        )
        payload["describeExtras"] = extras
        construction = next(
            c for c in pack.constructions if c.construction_id == "describe-attribute"
        )
        payload["packCorrections"] = [
            dict(
                mistake="wrongGender",
                answers=[canonical.replace(second["agreedForm"], form)],
                correction=canonical,
                explanation=f"The word agrees with {second['nounPhrase']}: {second['agreedForm']}.",
            )
            for form in extras
        ] + [
            dict(
                mistake="wordOrder",
                correction=canonical,
                explanation=construction.templates.get("word_order_feedback", construction.summary),
            )
        ]
        templates = next(
            c.templates for c in pack.constructions if c.construction_id == "yes-no-identification"
        )
        payload.update(
            yes=label("yes"),
            no=label("no"),
            confirmPrompt=templates.get("question", "{noun}"),
            sentenceStart=templates.get("sentence_start", ""),
        )
        questions = []
        for index, shown in enumerate(pairs, 1):
            slot = f"confirmObject-{index}"
            prompt, answer, contrast = (
                candidate(slot, use) for use in ("prompt", "answer", "option")
            )
            choices = [
                {"option_id": "confirm-1", "label": answer.text},
                {"option_id": "confirm-2", "label": contrast.text},
            ]
            orders = selection.get("layout", {}).get("confirmOrders")
            order = orders[index - 1] if orders is not None else shuffle(
                range(2), f"confirm-order-{index}",
            )
            choices = [
                dict(option_id=f"confirm-{i + 1}", label=choices[value]["label"])
                for i, value in enumerate(order)
            ]
            questions.append(
                M01Question(
                    question_id=CONFIRM_IDS[index - 1],
                    purpose="confirmObject",
                    section=IDENTIFY_SECTION,
                    prompt=prompt.text,
                    interaction_type="multipleChoice",
                    options=choices,
                    correct_option_id=next(
                        o["option_id"] for o in choices if o["label"] == answer.text
                    ),
                    correct_text=None,
                    token_bank=[],
                    translation=None,
                    object_key=shown["key"],
                    attribute_keys=[],
                    statement_correct=specs[slot]["prompt"].truth,
                )
            )
        attribute_order = selection.get("layout", {}).get("attributeOrder")
        if attribute_order is None:
            attribute_order = shuffle(range(len(options)), "attribute-order")
        detail_options = [
            {"option_id": f"attribute-{i}", "label": value[:1].upper() + value[1:]}
            for i, value in enumerate([options[j] for j in attribute_order if j < len(options)], 1)
        ]
        questions.append(
            M01Question(
                question_id="choose-attribute",
                purpose="chooseAttribute",
                section=DESCRIBE_SECTION,
                prompt=prompt_label.text,
                interaction_type="multipleChoice",
                options=detail_options,
                correct_option_id=next(
                    o["option_id"]
                    for o in detail_options
                    if o["label"].casefold() == first["agreedForm"].casefold()
                ),
                correct_text=None,
                token_bank=[],
                translation=None,
                object_key=first["key"],
                attribute_keys=[first["attributeKey"]],
            )
        )
        sentence = candidate("describeObject")
        questions.append(
            M01Question(
                question_id="describe-object",
                purpose="describeObject",
                section=DESCRIBE_SECTION,
                prompt=label("describe-object"),
                interaction_type="sentenceBuilding",
                options=[],
                correct_option_id=None,
                correct_text=sentence.text,
                token_bank=chunks(sentence, extras)["token_bank"],
                translation=sentence.translation,
                object_key=second["key"],
                attribute_keys=[second["attributeKey"]],
            )
        )
        result = M01LessonResult(
            title="Name it and describe it",
            explanation="Use the details shown in the scene.",
            questions=questions,
        )
        task = m01_lesson_task(
            session_id, get_mission("M01", level, 1), payload, result, vocabulary_ids
        )
    elif level == "A2":
        first_spec = specs["chooseSceneMarker"]["fact1"]
        first = by_fact[first_spec.bindings.get("object") or first_spec.bindings["subject"]]
        detail = attrs.get(first_spec.bindings.get("attribute"))
        third = by_fact[specs["chooseSceneDescription"]["connected"].bindings["other-object"]]
        fact1, fact2 = candidate("chooseSceneMarker", "fact1"), candidate("buildSceneFact", "fact2")
        descriptions = [
            candidate("buildSceneDescription", use) for use in ("fact1", "fact2", "fact3")
        ]
        full = " ".join(sentence.text for sentence in descriptions)
        relation_id = first_spec.bindings.get("relation") or specs["buildSceneFact"][
            "fact2"
        ].bindings.get("relation")
        relation = next(
            (rel for rel in facts.scene_facts.relations if rel.fact_id == relation_id), None
        )
        if detail:
            detail_options, _ = _detail_options(
                facts, vocabulary, detail, first["gender"], include_pack=True, pack=pack
            )
            order = pack.lexical.get("choice_order", {}).get(detail.kind) or pack.lexical.get(
                "attribute_contrasts", {}
            ).get(f"{detail.kind}:{detail.value}")
            if order and not any(t.provenance == "modelProposal" for t in vocabulary.terms):
                detail_options = [_standalone_form(terms[detail.fact_id], first["gender"])]
                detail_rows = [dict(option_id="detail-correct", label=detail_options[0])]
                for index, value in enumerate(order.split("|")):
                    term = next(
                        (
                            t
                            for t in vocabulary.terms
                            if t.source_text == value
                            and t.linguistic.get("attribute-kind") == detail.kind
                        ),
                        None,
                    )
                    if term:
                        form = _standalone_form(term, first["gender"])
                        if form.casefold() not in {v.casefold() for v in detail_options}:
                            detail_options.append(form)
                            detail_rows.append(dict(option_id=f"detail-{index}", label=form))
                    if len(detail_options) == 3:
                        break
            else:
                detail_rows = [
                    dict(option_id="detail-correct" if i == 0 else f"detail-{i}", label=v)
                    for i, v in enumerate(detail_options)
                ]
        else:
            reference = by_fact[first_spec.bindings["reference"]]
            separator = " " if pack.language.word_separator == "space" else ""
            detail_options = [separator.join([terms[relation_id].target_text, reference["name"]])]
            for term in vocabulary.terms:
                if "relation-kind" in term.linguistic and term.linguistic["relation-kind"] != str(
                    relation.relation
                ):
                    value = separator.join([term.target_text, reference["name"]])
                    if value not in detail_options:
                        detail_options.append(value)
                if len(detail_options) == 3:
                    break
            if len(detail_options) < 2:
                raise ValueError("A2 needs approved contrasting relation options")
            detail_rows = [
                dict(option_id="detail-correct" if i == 0 else f"detail-{i}", label=v)
                for i, v in enumerate(detail_options)
            ]
        payload.update(
            approvedFacts=dict(
                approvedObjects=rows,
                sceneFacts=facts.model_dump(mode="json"),
                approvedVocabulary=vocabulary.model_dump(mode="json"),
            ),
            selection=dict(
                attributeKey=detail.fact_id if detail else None,
                relationKey=relation_id,
                firstFactKind="attribute" if detail else "relation",
                secondObjectKey=None,
                thirdObjectKey=third["key"],
            ),
        )
        planning = [
            f"The {first['source']} is {detail.value}."
            if detail
            else fact1.translation or fact1.text,
            fact2.translation or fact2.text,
            descriptions[2].translation or descriptions[2].text,
        ]
        section1, section2, section3 = (
            "Task 1 · Notice the facts",
            "Task 2 · Describe the scene",
            "Task 3 · Check a detail",
        )
        prompt1 = label("touch-object").replace("{f['first']}", fact1.text)
        marker_options = [
            {"option_id": row["key"], "label": str(row["marker"])} for row in (first, third)
        ]
        connected, wrong_attribute, wrong_existence = (
            candidate("chooseSceneDescription", use)
            for use in ("connected", "wrongAttribute", "wrongExistence")
        )
        description_options = [
            dict(option_id=key, label=sentence.text)
            for key, sentence in (
                ("description-correct", connected),
                ("description-attribute", wrong_attribute),
                ("description-existence", wrong_existence),
            )
        ]
        # A full false clause is a distractor; it has already passed sentence validation.
        false_clause = (
            candidate("chooseSceneDescription", "falseFirst").text
            if "falseFirst" in specs["chooseSceneDescription"]
            else wrong_attribute.text
        )
        full_candidate = descriptions[0].model_copy(update={"text": full, "chunks": []})
        questions = [
            MissionA2Question(
                question_id="m01-q1",
                purpose="chooseSceneMarker",
                prompt=prompt1,
                interaction_type="multipleChoice",
                options=shuffle(marker_options, "m01-q1"),
                correct_option_id=first["key"],
                object_key=first["key"],
                section=section1,
                marker_object_ids={row["key"]: row["key"] for row in (first, third)},
            ),
            MissionA2Question(
                question_id="m01-q2",
                purpose="buildSceneFact",
                prompt=label("build-second-fact"),
                interaction_type="sentenceBuilding",
                object_key=first["key"],
                section=section1,
                **chunks(fact2, [label("connector-distractor")]),
            ),
            MissionA2Question(
                question_id="m01-q3",
                purpose="chooseSceneDescription",
                prompt=label("choose-description"),
                interaction_type="multipleChoice",
                options=shuffle(description_options, "m01-q3"),
                correct_option_id="description-correct",
                object_key=first["key"],
                section=section2,
            ),
            MissionA2Question(
                question_id="m01-q4",
                purpose="buildSceneDescription",
                prompt=label("describe-scene"),
                interaction_type="sentenceBuilding",
                object_key=first["key"],
                section=section2,
                planning_facts=planning,
                **chunks(full_candidate, [false_clause], phrase=True),
            ),
            MissionA2Question(
                question_id="m01-q5",
                purpose="followUpSceneFact",
                prompt=candidate("followUpSceneFact", "followup").text,
                interaction_type="multipleChoice",
                options=shuffle(detail_rows, "m01-q5"),
                correct_option_id="detail-correct",
                object_key=first["key"],
                section=section3,
            ),
        ]
        result = MissionA2Result(title="Describe the scene", questions=questions)
        task = m01_a2_task(
            session_id, get_mission("M01", level, 1), payload, result, vocabulary_ids
        )
    else:
        raise ValueError(f"unsupported M01 level {level}")
    return result, _with_romanization(task, result, pack, accepted, vocabulary), payload


def _with_romanization(task, result, pack, accepted, vocabulary):
    """Expose spellings only for text already visible; never reveal a built answer."""
    spellings = {label.text: label.romanization for label in pack.labels if label.romanization}
    spellings.update(
        {term.forms_by_key.get("definite", term.target_text): term.romanization
         for term in vocabulary.terms if term.romanization}
    )
    for sentence in accepted:
        candidate = sentence.candidate
        spellings.update({span.native: span.latin for span in candidate.support_romanizations})
        if candidate.romanization:
            spellings[candidate.text] = "".join(span.latin for span in candidate.romanization)
            for span in candidate.romanization:
                spellings[span.native.strip()] = span.latin.strip()
            spans = candidate.romanization
            for start in range(len(spans)):
                for end in range(start + 1, len(spans) + 1):
                    native = "".join(span.native for span in spans[start:end]).strip()
                    latin = "".join(span.latin for span in spans[start:end]).strip()
                    spellings[native] = latin
    questions = []
    for question, original in zip(task.public_content.questions, result.questions, strict=True):
        modes = None
        if original.correct_text:
            # The canonical native sentence is also the private answer; joining modes
            # describe answer positions, so identical tiles remain interchangeable.
            base = next(
                (
                    item.candidate
                    for item in accepted
                    if item.candidate.text == original.correct_text
                ),
                None,
            )
            if base is None:
                base = accepted[0].candidate.model_copy(
                    update={
                        "text": original.correct_text,
                        "romanization": [],
                    }
                )
            phrase = getattr(original, "answer_chunks", [])
            derived = derive_chunks(
                base,
                pack.language.word_separator,
                phrase_chunks=bool(phrase and any(" " in p for p in phrase)),
                phrase_boundaries=pack.language.phrase_boundaries,
            )
            modes = [chunk.join for chunk in derived.chunks]
            question = question.model_copy(update={"token_bank": original.token_bank})
        for text in [question.prompt, *question.token_bank]:
            if text and not any(char.isalpha() for char in text):
                spellings[text] = text
            for label in pack.labels:
                if label.romanization and "{f['first']}" in label.text:
                    for sentence in accepted:
                        native = label.text.replace("{f['first']}", sentence.candidate.text)
                        latin = spellings.get(sentence.candidate.text)
                        if native == text and latin:
                            spellings[text] = label.romanization.replace("{f['first']}", latin)
        visible = [
            question.prompt,
            *question.token_bank,
            *(option.label for option in question.options),
        ]
        values = {text: spellings[text] for text in visible if text in spellings}
        for text in visible:
            if text not in values:
                spelling = next(
                    (
                        value
                        for native, value in spellings.items()
                        if native.casefold() == text.casefold()
                    ),
                    None,
                )
                if spelling:
                    values[text] = spelling
        if pack.language.romanization_required and any(
            any(char.isalpha() for char in text) and text not in values for text in visible
        ):
            raise ValueError("required romanization is missing for displayed text or a tile")
        questions.append(
            question.model_copy(
                update={
                    "romanizations": values or None
                    if pack.language.romanization_required
                    or any(item.candidate.romanization for item in accepted)
                    else None,
                    "sentence_join_modes": modes,
                }
            )
        )
    content = {"questions": questions}
    if task.public_content.prep:
        prep = []
        for card in task.public_content.prep:
            spelling = spellings.get(card.text)
            if pack.language.romanization_required and not spelling:
                raise ValueError("required romanization is missing for a preparation card")
            prep.append(card.model_copy(update={"romanization": spelling}))
        content["prep"] = prep
    return task.model_copy(
        update={"public_content": task.public_content.model_copy(update=content)}
    )
