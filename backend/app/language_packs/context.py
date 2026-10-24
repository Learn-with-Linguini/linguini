"""An immutable, serializable pack snapshot for one normal pack-lesson operation."""

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from app.config import (
    get_language_pack_experimental,
    get_language_pack_register,
    get_language_pack_releases,
)
from app.schemas.language_context import LanguageDisplayContext

from .fingerprint import pack_fingerprint
from .loader import load_packs
from .schema import LanguagePack

logger = logging.getLogger(__name__)

def mission_key_text(key) -> str:
    mission_id, level, content_version = key
    return f"{mission_id}:{level}:{content_version}"


def _parse_key(text):
    mission_id, level, content_version = text.split(":")
    return mission_id, level, int(content_version)


@dataclass(frozen=True)
class LanguageContext:
    pack_json: str
    display_json: str
    ready_levels: tuple[str, ...]
    experimental: bool
    # "M01:A0:1" keys. Ready missions pass every gate; declared missions are those the
    # pack has the constructions and labels for (diagnostic: see ``owns``).
    ready_missions: tuple[str, ...] = ()
    declared_missions: tuple[str, ...] = ()

    @classmethod
    def from_snapshot(cls, snapshot):
        """Restore session-owned data, checking current gates against that same pack."""
        from .runtime import check_pack_readiness

        levels = tuple(snapshot["readyLevels"])
        # Snapshots saved before multi-mission packs only recorded M01 levels.
        ready = tuple(snapshot.get("readyMissions") or (f"M01:{level}:1" for level in levels))
        declared = tuple(snapshot.get("declaredMissions") or (
            f"M01:{level}:1" for level in ("A0", "A1", "A2")
        ))
        context = cls(
            snapshot["pack"],
            snapshot["display"],
            levels,
            snapshot["experimental"],
            ready,
            declared,
        )
        if not context.ready_missions:
            raise ValueError("Saved language context has no ready mission levels")
        pack, display = context.pack, context.display
        if (pack.pack_id, pack.language.code, pack.language_register.register_id) != (
            display.pack_id,
            display.language_code,
            display.register_id,
        ):
            raise ValueError("Saved language context does not match its pack snapshot")
        experimental = False
        for text in context.ready_missions:
            mission_id, level, content_version = _parse_key(text)
            _, experimental = check_pack_readiness(pack, level, content_version, mission_id)
        return cls(
            context.pack_json, context.display_json, context.ready_levels, experimental,
            context.ready_missions, context.declared_missions,
        )

    def _keys(self, values, level=None):
        keys = [_parse_key(text) for text in values]
        return [key for key in keys if level is None or key[1] == str(level)]

    def ready_missions_at(self, level):
        """Ready (mission_id, level, content_version) keys at a level, in catalog order."""
        return self._keys(self.ready_missions, level)

    def declares(self, mission_id, level):
        """Whether the pack has the constructions and labels for this mission template."""
        return any(key[0] == mission_id for key in self._keys(self.declared_missions, level))

    def owns(self, mission_id):
        """Whether the mission has a pack implementation: it is generated from the pack
        when ready and otherwise not offered."""
        from .lessons import PACK_MISSION_IDS

        return mission_id in PACK_MISSION_IDS

    def is_ready(self, mission):
        return any(
            key[0] == mission.mission_id
            for key in self._keys(self.ready_missions, mission.practice_level)
        )

    @property
    def pack(self):
        # Return a private copy so consumers cannot mutate another stage's snapshot.
        return LanguagePack.model_validate_json(self.pack_json)

    @property
    def display(self):
        return LanguageDisplayContext.model_validate_json(self.display_json)

    def translation_guidance(self):
        pack = self.pack
        return {
            "context": self.display.model_dump(mode="json"),
            "variety": pack.variety.model_dump(mode="json"),
            "register": pack.language_register.model_dump(mode="json"),
            "constructions": [c.model_dump(mode="json") for c in pack.constructions],
            "reference_vocabulary": pack.lexical,
        }

    def attach(self, task):
        return task.model_copy(
            update={
                "public_content": task.public_content.model_copy(
                    update={"language_context": self.display},
                )
            }
        )

    def snapshot(self):
        return dict(
            pack=self.pack_json,
            display=self.display_json,
            readyLevels=list(self.ready_levels),
            readyMissions=list(self.ready_missions),
            declaredMissions=list(self.declared_missions),
            experimental=self.experimental,
        )


# Resolved contexts by loaded pack set and release gates. Every request resolves one, and
# readiness only changes with the packs, the gates or the evidence on disk. A loaded pack
# set is cached for the process, so its id is stable.
_CONTEXTS: dict[tuple, "LanguageContext | None"] = {}


def _evidence_revision():
    folder = os.getenv("LINGUINI_LANGUAGE_PACK_EVIDENCE_DIR", "")
    if not folder or not Path(folder).is_dir():
        return folder
    return folder, tuple(
        (path.name, path.stat().st_mtime_ns, path.stat().st_size)
        for path in sorted(Path(folder).glob("*.json"))
    )


def resolve_language_context(language, register=None):
    """The language's pack context, or ``None`` when it has no pack with a ready mission.

    Mission lessons come only from language packs, so ``None`` means the language has
    no mission lessons. A broken or ambiguous pack configuration still raises.
    """
    packs = load_packs()
    key = (
        id(packs), language.casefold(), register or get_language_pack_register(),
        get_language_pack_experimental(), get_language_pack_releases(), _evidence_revision(),
    )
    if key not in _CONTEXTS:
        _CONTEXTS[key] = _resolve(packs, language, register)
    return _CONTEXTS[key]


def _resolve(packs, language, register):
    from .capabilities import pack_mission_keys
    from .runtime import check_pack_readiness, mission_capability_for

    # Profiles historically normalize codes to lowercase; pack tags preserve
    # canonical BCP 47 casing. Compare tags without changing the pack's locale.
    canonical = next(
        (p.language.code for p in packs.packs if p.language.code.casefold() == language.casefold()),
        language,
    )
    if not any(p.language.code == canonical for p in packs.packs):
        return None
    selected_register = register or get_language_pack_register()
    if not selected_register:
        matches = [p for p in packs.packs if p.language.code == canonical]
        if len(matches) != 1:
            raise ValueError(f"Expected one pack for {language!r}; specify a register explicitly")
        pack = matches[0]
    else:
        pack = packs.get(canonical, selected_register)
    # Serialize before publishing the context. No later stage reopens pack files.
    snapshot = pack.model_dump_json(by_alias=False)
    fingerprint = hashlib.sha256(
        json.dumps(
            pack_fingerprint(pack, [c.construction_id for c in pack.constructions], "context.v1"),
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    ready, declared, experimental, errors = [], [], False, []
    for key in pack_mission_keys():
        mission_id, level, content_version = key
        if mission_capability_for(pack, level, content_version, mission_id).structurally_supported:
            declared.append(mission_key_text(key))
        try:
            _, experimental = check_pack_readiness(pack, level, content_version, mission_id)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        ready.append(mission_key_text(key))
    if not ready:
        # Unreviewed or unreleased packs stay hidden outside explicit local experiments.
        logger.info("Pack %r has no ready mission levels: %s", pack.pack_id, "; ".join(errors))
        return None
    ready_levels = tuple(
        level for level in ("A0", "A1", "A2") if any(f":{level}:" in key for key in ready)
    )
    language_settings = pack.language
    display = LanguageDisplayContext(
        pack_id=pack.pack_id,
        pack_version=pack.pack_version,
        fingerprint=fingerprint,
        language_code=language_settings.code,
        locale=language_settings.locale,
        variety=pack.variety.variety_id,
        register=pack.language_register.register_id,
        script=language_settings.script,
        direction=language_settings.direction,
        articles=language_settings.articles,
        grammatical_gender=language_settings.grammatical_gender,
        romanization_required=language_settings.romanization_required,
        romanization_convention=language_settings.romanization_convention
        or (
            "Latin transliteration, not English-sound respelling"
            if language_settings.romanization_required
            else None
        ),
        speech_locale=language_settings.speech.synthesis_locale,
        speech_synthesis=language_settings.speech.synthesis,
        speech_recognition=language_settings.speech.recognition,
    )
    return LanguageContext(
        snapshot,
        display.model_dump_json(by_alias=False),
        ready_levels,
        experimental,
        tuple(ready),
        tuple(declared),
    )


def operation_context(mode, profile, snapshot=None):
    if str(mode) != "lesson":
        return None
    if snapshot is not None:
        context = LanguageContext.from_snapshot(snapshot)
        if context.display.language_code.casefold() != profile["target_language_code"].casefold():
            raise ValueError("Saved language context does not match the session language")
        return context
    return resolve_language_context(
        profile["target_language_code"].lower(), profile.get("language_register")
    )
