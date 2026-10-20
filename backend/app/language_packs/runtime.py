"""Bridge confirmed lesson data to the shared M01 pipeline. No sample inputs."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from app.config import (
    get_language_pack_experimental,
    get_m01_language_packs_enabled,
)

from .capabilities import mission_capability
from .generation import ApprovedTerm, ApprovedVocabulary, BoundSceneFacts
from .loader import load_packs


def runtime_pack(language: str, level: str, content_version: int, register: str):
    pack = load_packs().get(language, register)
    return check_pack_readiness(pack, level, content_version)


def check_pack_readiness(pack, level, content_version):
    experimental = get_language_pack_experimental()
    evidence = None
    evidence_dir = os.getenv("LINGUINI_LANGUAGE_PACK_EVIDENCE_DIR", "")
    if evidence_dir:
        path = Path(evidence_dir) / f"{pack.pack_id}-M01-{level}.json"
        if path.is_file():
            evidence = json.loads(path.read_text("utf-8"))
            evidence = evidence.get("evaluation_record", evidence)
    capability = mission_capability(
        pack,
        ("M01", level, content_version),
        evaluation_record=evidence,
    )
    if not capability.structurally_supported or not (experimental or capability.release_enabled):
        raise ValueError("M01 language pack unavailable: " + "; ".join(capability.blockers))
    return pack, experimental


def available_pack_languages():
    """Discover selectable M01 languages under the same runtime/release gates."""
    if not get_m01_language_packs_enabled():
        return []
    from .context import resolve_language_context

    languages = []
    for language in sorted({p.language.code for p in load_packs().packs}):
        # Missing selected registers/ambiguous configurations are actionable.
        # Unreviewed packs remain hidden outside explicit local experiments.
        try:
            context = resolve_language_context(language)
        except ValueError as exc:
            if "no ready M01 levels" in str(exc):
                continue
            raise
        languages.append(dict(code=language, levels=list(context.ready_levels),
                              experimental=context.experimental, language_context=context.display))
    return sorted(languages, key=lambda language: language["code"])


def session_inputs(pack, objects, relations, words, translated_scene, markers):
    """Use instance IDs, not labels, including repeated names and attribute values."""
    if translated_scene is None:
        raise ValueError("M01 packs require the confirmed scene's translations")
    translated = {row.key: row for row in translated_scene.objects}
    attrs = {row.key: row for row in translated_scene.attributes}
    rels = {row.key: row for row in translated_scene.relationships}
    terms, object_facts, attribute_facts, relation_facts = [], [], [], []
    separator = " " if pack.language.word_separator == "space" else ""
    for index, (obj, word) in enumerate(zip(objects, words, strict=True), 1):
        key = str(obj.id)
        term = translated.get(key)
        if term is None:
            raise ValueError(f"missing translated object {key}")
        bare = term.translation
        article = term.article
        if article and bare.casefold().startswith(article.casefold() + separator):
            bare = bare[len(article + separator) :]
        # Catalog metadata may predate this pack/register. Session translations
        # are canonical for this operation.
        gender = term.gender
        if pack.language.grammatical_gender == "none":
            gender = None
        forms = {"bare": bare, "definite": getattr(term, "native_display", None) or
                 separator.join(filter(None, [article, bare]))}
        if article:
            forms["article_definite"] = article
        indefinite = pack.lexical.get("indefinite_articles", {}).get(gender)
        if indefinite:
            forms["article_indefinite"] = indefinite
            forms["indefinite"] = separator.join([indefinite, bare])
        fid = f"object:{key}"
        object_facts.append(
            dict(
                fact_id=fid,
                scene_object_id=obj.id,
                label=obj.label,
                marker=markers.get(key, index),
            )
        )
        terms.append(
            ApprovedTerm(
                term_id=f"object-{key}",
                fact_id=fid,
                source_text=obj.label,
                target_text=bare,
                forms=list(dict.fromkeys(forms.values())),
                forms_by_key=forms,
                part_of_speech="noun",
                agreement=gender,
                vocabulary_item_id=word.id,
                provenance="sessionTranslation",
                romanization=getattr(term, "romanization", None),
            )
        )
        confirmed = []
        for attr_key, value in (obj.attributes or {}).items():
            kind = {"color": "colour"}.get(attr_key.casefold(), attr_key.casefold())
            if kind in {"colour", "size", "shape", "material", "pattern", "state"} and isinstance(
                value, str
            ):
                value = value.strip().casefold()
                value = pack.lexical.get("attribute_aliases", {}).get(f"{kind}:{value}", value)
                confirmed.append((attr_key, kind, value))
        for attr_key, kind, value in confirmed:
            source_key = f"{key}:{attr_key}"
            translated_attr = attrs.get(source_key)
            if translated_attr is None:
                continue
            afid = f"attribute:{source_key}"
            attribute_facts.append(
                dict(
                    fact_id=afid,
                    object_fact_id=fid,
                    kind=kind,
                    value=value,
                )
            )
            text = translated_attr.translation
            forms = {"default": text}
            prefix = f"{kind}:{value}:"
            forms.update(
                {
                    key[len(prefix) :]: form
                    for key, form in pack.lexical.get("attribute_forms", {}).items()
                    if key.startswith(prefix)
                }
            )
            terms.append(
                ApprovedTerm(
                    term_id=f"attribute-{key}-{attr_key}",
                    fact_id=afid,
                    source_text=value,
                    target_text=text,
                    forms=list(dict.fromkeys(forms.values())),
                    forms_by_key=forms,
                    part_of_speech="adjective",
                    provenance="sessionTranslation",
                    position=pack.lexical.get("attribute_positions", {}).get(f"{kind}:{value}"),
                )
            )
    ids = {str(obj.id) for obj in objects}
    for rel in relations:
        subject, reference = str(rel.subject_scene_object_id), str(rel.reference_scene_object_id)
        term = rels.get(str(rel.id))
        if subject not in ids or reference not in ids or term is None:
            continue
        fid = f"relation:{rel.id}"
        relation_facts.append(
            dict(
                fact_id=fid,
                subject_fact_id=f"object:{subject}",
                reference_fact_id=f"object:{reference}",
                relation=re.sub(r"(?<=[a-z])(?=[A-Z])", "_", rel.relation).lower(),
            )
        )
        terms.append(
            ApprovedTerm(
                term_id=f"relation-{rel.id}",
                fact_id=fid,
                source_text=term.source,
                target_text=term.translation,
                forms=[term.translation],
                part_of_speech="preposition",
                provenance="sessionTranslation",
            )
        )
    return BoundSceneFacts(
        scene_facts=dict(
            objects=object_facts,
            attributes=attribute_facts,
            relations=relation_facts,
        )
    ), ApprovedVocabulary(terms=terms)
