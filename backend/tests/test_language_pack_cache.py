from pathlib import Path

from app.ai.cache.cache import CacheRequest, Generated, ResultCache
from app.ai.cache.store import CacheScope
from app.language_packs.fingerprint import (
    guidance_sha256,
    language_pack_feature_version,
    pack_fingerprint,
)
from app.language_packs.loader import load_pack

FIXTURE = Path(__file__).parent / "fixtures/language_packs/es-basic"


def _request(version, counter):
    def compute():
        counter[0] += 1
        return Generated({"result": "ok"}, deployment_id="local", model="stub")

    return CacheRequest(
        version=version,
        scope=CacheScope.public(),
        payload={"targetLanguage": "es", "objects": []},
        generation={"temperature": 0},
        approved_deployments=frozenset({"local"}),
        compute=compute,
        encode=lambda result: result,
        decode=lambda result: result,
    )


def test_pack_guidance_fingerprint_is_stable_and_tracks_guidance_and_versions():
    pack = load_pack(FIXTURE)
    construction_ids = ["identify-object"]
    fingerprint = pack_fingerprint(pack, construction_ids, "gen-v1")
    original = language_pack_feature_version(
        "language-pack", "gen-v1", fingerprint
    )
    same = language_pack_feature_version(
        "language-pack", "gen-v1", fingerprint
    )
    changed_guidance = pack.model_copy(
        update={
            "constructions": [
                construction.model_copy(update={"guidance": "Changed structural guidance."})
                if construction.construction_id == "identify-object"
                else construction
                for construction in pack.constructions
            ]
        }
    )
    changed_version = pack.model_copy(
        update={
            "constructions": [
                construction.model_copy(update={"version": construction.version + 1})
                if construction.construction_id == "identify-object"
                else construction
                for construction in pack.constructions
            ]
        }
    )

    assert original == same
    assert guidance_sha256(pack, construction_ids) != guidance_sha256(
        changed_guidance, construction_ids
    )
    assert language_pack_feature_version(
        "language-pack", "gen-v1",
        pack_fingerprint(changed_guidance, construction_ids, "gen-v1"),
    ) != original
    assert language_pack_feature_version(
        "language-pack", "gen-v1",
        pack_fingerprint(changed_version, construction_ids, "gen-v1"),
    ) != original
    assert language_pack_feature_version(
        "language-pack",
        "gen-v2",
        pack_fingerprint(pack, construction_ids, "gen-v2"),
    ) != original


def test_result_cache_hits_identical_inputs_and_misses_changed_pack_version():
    pack = load_pack(FIXTURE)
    store_calls = [0]
    cache = ResultCache()
    version = language_pack_feature_version(
        "language-pack", "gen-v1",
        pack_fingerprint(pack, ["identify-object"], "gen-v1"),
    )
    first = cache.get_or_generate(_request(version, store_calls))
    second = cache.get_or_generate(_request(version, store_calls))
    changed_pack = pack.model_copy(
        update={"pack_version": pack.pack_version + 1}
    )
    changed = language_pack_feature_version(
        "language-pack",
        "gen-v1",
        pack_fingerprint(changed_pack, ["identify-object"], "gen-v1"),
    )
    third = cache.get_or_generate(_request(changed, store_calls))

    assert first == second == third == {"result": "ok"}
    assert store_calls == [2]
