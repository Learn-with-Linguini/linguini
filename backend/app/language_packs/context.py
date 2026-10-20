"""An immutable, serializable pack snapshot for one normal M01 operation."""

import hashlib
import json
from dataclasses import dataclass

from app.config import get_language_pack_register, get_m01_language_packs_enabled
from app.schemas.language_context import LanguageDisplayContext

from .fingerprint import pack_fingerprint
from .loader import load_packs
from .schema import LanguagePack


@dataclass(frozen=True)
class LanguageContext:
    pack_json: str
    display_json: str
    ready_levels: tuple[str, ...]
    experimental: bool

    @classmethod
    def from_snapshot(cls, snapshot):
        """Restore session-owned data, checking current gates against that same pack."""
        from .runtime import check_pack_readiness

        context = cls(
            snapshot["pack"],
            snapshot["display"],
            tuple(snapshot["readyLevels"]),
            snapshot["experimental"],
        )
        if not context.ready_levels:
            raise ValueError("Saved language context has no ready M01 levels")
        pack, display = context.pack, context.display
        if (pack.pack_id, pack.language.code, pack.language_register.register_id) != (
            display.pack_id,
            display.language_code,
            display.register_id,
        ):
            raise ValueError("Saved language context does not match its pack snapshot")
        experimental = False
        for level in context.ready_levels:
            _, experimental = check_pack_readiness(pack, level, 1)
        return cls(context.pack_json, context.display_json, context.ready_levels, experimental)

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
            experimental=self.experimental,
        )


def resolve_language_context(language, register=None):
    if not get_m01_language_packs_enabled():
        return None
    from .runtime import check_pack_readiness

    packs = load_packs()
    # Profiles historically normalize codes to lowercase; pack tags preserve
    # canonical BCP 47 casing. Compare tags without changing the pack's locale.
    canonical = next(
        (p.language.code for p in packs.packs if p.language.code.casefold() == language.casefold()),
        language,
    )
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
    ready, experimental, errors = [], False, []
    for level in ("A0", "A1", "A2"):
        try:
            _, experimental = check_pack_readiness(pack, level, 1)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        ready.append(level)
    if not ready:
        raise ValueError(f"Pack {pack.pack_id!r} has no ready M01 levels: " + "; ".join(errors))
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
        tuple(ready),
        experimental,
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
