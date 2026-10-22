"""Building blocks shared by every pack mission: specs, scene rows and lesson assembly."""

from __future__ import annotations

import random
from unicodedata import name as unicode_name
from uuid import NAMESPACE_URL, uuid5

from app.ai.features.learning_tasks.mission import fold
from app.missions import get_mission

from ..generation import derive_chunks

# Explicit demo callers only; application callers always supply their session ID.
DEMO_SESSION_ID = uuid5(NAMESPACE_URL, "language-packs/demo")


# ---------------------------------------------------------------- planning


class SpecBuilder:
    """Raw slot specs for ``bind_plan``, in planned order.

    Spec IDs are ``<slot>-<suffix or use>``; a slot set to ``skip`` has no sentences
    of its own (it reuses sentences generated for another slot).
    """

    def __init__(self) -> None:
        self._specs: dict[str, list[dict]] = {}

    def add(self, slot, use, construction, bindings, *, truth=True, labels=(),
            counterfactual=None, suffix=None) -> None:
        self._specs.setdefault(slot, []).append(dict(
            spec_id=f"{slot}-{suffix or use}",
            construction_id=construction,
            use=use,
            bindings=bindings,
            truth=truth,
            labels=list(labels),
            counterfactual=counterfactual or {},
        ))

    def skip(self, slot) -> None:
        self._specs[slot] = []

    def build(self) -> dict[str, list[dict]]:
        return self._specs


def usable_objects(facts, vocabulary):
    """Confirmed objects that have a session translation, in scene order."""
    terms = {term.fact_id for term in vocabulary.terms}
    return [obj for obj in facts.scene_facts.objects if obj.fact_id in terms]


def object_name(vocabulary, obj) -> str:
    """The folded target-language noun a learner sees for ``obj``."""
    term = next(term for term in vocabulary.terms if term.fact_id == obj.fact_id)
    return fold(term.forms_by_key.get("bare", term.target_text))


def differently_named(objects, vocabulary):
    """The first object of each target-language name, in order.

    Two objects with one name are interchangeable to a learner: a name alone never
    picks out one of them, so contrasts and false statements need another name.
    """
    seen, named = set(), []
    for obj in objects:
        name = object_name(vocabulary, obj)
        if name not in seen:
            seen.add(name)
            named.append(obj)
    return named


# ---------------------------------------------------------------- assembly


def check_questions(questions, purposes, mission_id) -> None:
    """The mission's question sequence and answerable shapes, as dev's lessons expect."""
    if [question.purpose for question in questions] != purposes:
        raise ValueError(f"assembled {mission_id} questions do not preserve the mission sequence")
    if len({question.question_id for question in questions}) != len(questions):
        raise ValueError(f"assembled {mission_id} question IDs must be unique")
    for question in questions:
        if question.interaction_type == "sentenceBuilding":
            if not question.correct_text or not question.token_bank or question.options:
                raise ValueError("assembled building question needs a native answer and tiles")
        else:
            ids = [option.option_id for option in question.options]
            if len(ids) < 2 or len(ids) != len(set(ids)) or question.correct_option_id not in ids:
                raise ValueError("assembled choices need unique IDs and an offered answer")
            if len({fold(option.label) for option in question.options}) != len(ids):
                raise ValueError("assembled choices must be distinct")


def scene_rows(facts, vocabulary, separator=" "):
    """One row per translated object, in the shape dev's task builders read."""
    terms = {term.fact_id: term for term in vocabulary.terms}
    rows, by_fact = [], {}
    for obj in facts.scene_facts.objects:
        term = terms.get(obj.fact_id)
        if term is None:
            continue
        forms = term.forms_by_key
        bare = forms.get("bare", term.target_text)
        indefinite = forms.get("indefinite") or separator.join(
            filter(None, [forms.get("article_indefinite"), bare])
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


def latin_of(candidate) -> str:
    """The aligned Latin spelling of a generated sentence (empty when not required)."""
    return "".join(span.latin for span in candidate.romanization)


class LessonContext:
    """Accepted sentences, labels and scene rows for assembling one mission lesson."""

    def __init__(self, mission_id, level, pack, facts, vocabulary, plan, accepted, *,
                 builder_selection=None, session_id=None):
        self.mission_id = mission_id
        self.level = level
        self.pack = pack
        self.facts = facts
        self.vocabulary = vocabulary
        self.plan = plan
        self.accepted = accepted
        self.session_id = session_id or DEMO_SESSION_ID
        self.selection = builder_selection or {}
        self.seed = self.selection.get("seed", str(self.session_id))
        self.mission = get_mission(mission_id, level, plan.content_version)
        separator = " " if pack.language.word_separator == "space" else ""
        self.rows, self.by_fact = scene_rows(facts, vocabulary, separator)
        self.terms = {term.fact_id: term for term in vocabulary.terms}
        self.terms_by_id = {term.term_id: term for term in vocabulary.terms}
        self.attributes = {attr.fact_id: attr for attr in facts.scene_facts.attributes}
        self.relations = {rel.fact_id: rel for rel in facts.scene_facts.relations}
        self.labels = {label.semantic: label for label in pack.labels}
        self.extra_spellings: dict[str, str] = {}
        self._specs = {slot.slot_id: slot.specs for slot in plan.slots}
        self._sentences = {
            (item.candidate.slot_id, item.candidate.spec_id): item.candidate for item in accepted
        }

    # Planned specs and their accepted sentences.

    def specs(self, slot):
        return self._specs[slot]

    def spec(self, slot, use=None):
        """The slot's spec with this use (the last one, as planned), else its first spec."""
        specs = self._specs[slot]
        if use is None:
            return specs[0]
        return [spec for spec in specs if spec.use == use][-1]

    def has_use(self, slot, use) -> bool:
        return any(spec.use == use for spec in self._specs[slot])

    def sentence(self, slot, use=None):
        return self._sentences[(slot, self.spec(slot, use).spec_id)]

    def sentence_for(self, slot, spec):
        return self._sentences[(slot, spec.spec_id)]

    def sentence_by_id(self, slot, suffix):
        return self._sentences[(slot, f"{slot}-{suffix}")]

    # Fixed text, randomness and tiles.

    def label(self, semantic, **values) -> str:
        """A pack label with ``{name}`` placeholders filled; its spelling is recorded."""
        label = self.labels[semantic]
        text, spelling = label.text, label.romanization
        for key, value in values.items():
            text = text.replace(f"{{{key}}}", value)
            spelling = spelling.replace(f"{{{key}}}", value) if spelling else spelling
        if spelling:
            self.extra_spellings[text] = spelling
        return text

    def shuffle(self, values, salt):
        result = list(values)
        random.Random(f"{self.seed}:{salt}").shuffle(result)
        return result

    def chunks(self, candidate, extras=(), *, phrase=False, salt=None) -> dict:
        """Answer chunks and a seeded tile bank for a validated sentence."""
        language = self.pack.language
        derived = derive_chunks(
            candidate, language.word_separator,
            phrase_chunks=phrase, phrase_boundaries=language.phrase_boundaries,
        )
        answers = [chunk.text for chunk in derived.chunks]
        if phrase:
            extras = [
                chunk.text
                for text in extras
                for chunk in derive_chunks(
                    derived.model_copy(update={"text": text}), language.word_separator,
                    phrase_chunks=True, phrase_boundaries=language.phrase_boundaries,
                ).chunks
            ]
        return dict(
            correct_text=derived.text,
            answer_chunks=answers,
            token_bank=self.shuffle([*answers, *extras], salt or derived.slot_id),
            distractor_chunks=list(extras),
        )

    # Payload and the finished task.

    @property
    def vocabulary_ids(self):
        return {row["key"]: row["vocabularyItemId"] for row in self.rows if row["vocabularyItemId"]}

    def payload(self, **fields) -> dict:
        return dict(
            targetLanguage=self.pack.language.code,
            missionId=self.mission_id,
            practiceLevel=self.level,
            contentVersion=self.plan.content_version,
            seed=self.seed,
            **fields,
        )

    def finish(self, task, result):
        return with_romanization(
            task, result, self.pack, self.accepted, self.vocabulary, self.extra_spellings,
        )


def _latin_script(text) -> bool:
    return all("LATIN" in unicode_name(char, "") for char in text if char.isalpha())


def with_romanization(task, result, pack, accepted, vocabulary, extra_spellings=None):
    """Expose spellings only for text already visible; never reveal a built answer.

    ``extra_spellings`` covers prompts a mission composes from several spelled parts.
    Text already in Latin script (English meanings, markers) needs no spelling.
    """
    spellings = {label.text: label.romanization for label in pack.labels if label.romanization}
    spellings.update(extra_spellings or {})
    spellings.update(
        {term.forms_by_key.get("definite", term.target_text): term.romanization
         for term in vocabulary.terms if term.romanization}
    )
    for sentence in accepted:
        candidate = sentence.candidate
        spellings.update({span.native: span.latin for span in candidate.support_romanizations})
        if candidate.romanization:
            spellings[candidate.text] = latin_of(candidate)
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
        # Situation questions (A0 M04) have no built answer.
        if getattr(original, "correct_text", None):
            # The canonical native sentence is also the private answer; joining modes
            # describe answer positions, so identical tiles remain interchangeable.
            base = next(
                (item.candidate for item in accepted
                 if item.candidate.text == original.correct_text),
                None,
            )
            if base is None:
                base = accepted[0].candidate.model_copy(
                    update={"text": original.correct_text, "romanization": []}
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
                    (value for native, value in spellings.items()
                     if native.casefold() == text.casefold()),
                    None,
                )
                if spelling:
                    values[text] = spelling
        if pack.language.romanization_required and any(
            any(char.isalpha() for char in text) and text not in values
            and not _latin_script(text)
            for text in visible
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
