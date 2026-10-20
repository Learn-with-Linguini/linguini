"""Stable generation fingerprints for language-pack guidance."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.ai.cache.cache import FeatureVersion

from .loader import guidance_for
from .schema import LanguagePack


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def guidance_sha256(pack: LanguagePack, construction_ids: list[str]) -> str:
    guidance = guidance_for(pack, construction_ids)
    return hashlib.sha256(
        _canonical_json(guidance.model_dump(mode="json", by_alias=False))
    ).hexdigest()


def pack_fingerprint(
    pack: LanguagePack,
    construction_ids: list[str],
    generation_version: str,
) -> dict[str, Any]:
    from .proposals import PROPOSAL_VERSION, REVIEW_VERSION
    from .validators import STRUCTURE_VERSION, validator_versions

    return {
        "format_version": pack.format_version,
        "pack_id": pack.pack_id,
        "pack_version": pack.pack_version,
        "language": pack.language.model_dump(mode="json", by_alias=False),
        "register_id": pack.language_register.register_id,
        "constructions": {
            construction.construction_id: construction.version
            for construction in pack.constructions
            if construction.construction_id in construction_ids
        },
        "guidance_sha256": guidance_sha256(pack, construction_ids),
        "generation_version": generation_version,
        "lexical": pack.lexical,
        "numbers": pack.numbers.model_dump(mode="json") if pack.numbers else None,
        "structure_version": STRUCTURE_VERSION,
        "proposal_version": PROPOSAL_VERSION,
        "content_review_version": REVIEW_VERSION,
        "validator_versions": validator_versions(pack.language.code, pack),
    }


def language_pack_feature_version(
    feature: str,
    generation_version: str,
    fingerprint: dict[str, Any],
) -> FeatureVersion:
    from .validators import STRUCTURE_VERSION

    cache_hash = hashlib.sha256(
        _canonical_json(
            {
                "fingerprint": fingerprint,
            }
        )
    ).hexdigest()[:12]
    return FeatureVersion(
        feature=feature,
        prompt_version=f"{generation_version}.{cache_hash}",
        schema_version="language-pack-contract.v3",
        validator_version=STRUCTURE_VERSION,
    )
