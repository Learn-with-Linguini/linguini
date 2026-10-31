"""Photo provenance, truthful clue pieces and answer privacy for friend conversations."""

import copy
import io
import json
from types import SimpleNamespace
from uuid import uuid4, uuid5

import pytest
from pack_translation import pack_shaped
from PIL import Image

from app.ai.cache import ResultCache
from app.ai.contracts.text import TextModelConfig, TextModelResponse
from app.ai.features.moderation import ImageModerationResult
from app.ai.features.scene_analysis import UploadedSceneAnalyzer
from app.ai.observability import NoOpAITracer
from app.ai.routing import as_routed
from app.schemas.media import MediaAsset, SceneObject, SceneObjectRelation
from app.services.friend_chat_content import FriendChatContent
from app.services.friend_chat_realizer import FriendChatRealizer
from app.services.room_photos import RoomPhotoError, RoomPhotoPreparer
from app.services.scene_analysis import SceneAnalysisResult


def image_bytes():
    output = io.BytesIO()
    Image.new("RGB", (100, 100), "white").save(output, format="PNG")
    return output.getvalue()


class Storage:
    def __init__(self):
        self.data = image_bytes()

    def download(self, _key):
        return self.data


class Analyzer:
    def __init__(self):
        self.calls = []
        self.region = False

    def analyze(self, identity, asset, profile, _scene):
        self.calls.append((identity, asset, profile))
        if self.region:
            objects = [
                SceneObject(
                    id=uuid5(identity.id, "apple"),
                    session_id=identity.id,
                    label="apple",
                    bounding_box={"x": 0.35, "y": 0.35, "width": 0.3, "height": 0.3},
                    attributes={"color": "red", "shape": "round"},
                )
            ]
            relations = []
        else:
            objects = [
                SceneObject(
                    id=uuid5(identity.id, "cup"),
                    session_id=identity.id,
                    label="cup",
                    bounding_box={"x": 0.1, "y": 0.2, "width": 0.2, "height": 0.3},
                    attributes={"color": "red", "size": "small", "material": "ceramic"},
                ),
                SceneObject(
                    id=uuid5(identity.id, "book"),
                    session_id=identity.id,
                    label="book",
                    bounding_box={"x": 0.7, "y": 0.2, "width": 0.2, "height": 0.3},
                    attributes={"color": "blue"},
                ),
            ]
            relations = [
                SceneObjectRelation(
                    id=uuid5(identity.id, "near"),
                    subject_scene_object_id=objects[0].id,
                    relation="next_to",
                    reference_scene_object_id=objects[1].id,
                )
            ]
        return SceneAnalysisResult(
            title="A desk",
            summary="A small red cup beside a blue book.",
            objects=objects,
            relations=relations,
        )


class Translator:
    def __init__(self):
        self.calls = []
        self.omit = False

    def translate(self, payload, **options):
        self.calls.append((copy.deepcopy(payload), options))
        nouns = {
            "cup": ("tasse", "la", "feminine"),
            "book": ("livre", "le", "masculine"),
            "apple": ("pomme", "la", "feminine"),
        }
        words = {
            "red": "rouge",
            "blue": "bleu",
            "small": "petit",
            "ceramic": "en céramique",
            "round": "rond",
            "next_to": "à côté de",
        }
        objects = [
            {
                **row,
                "translation": nouns[row["source"]][0],
                "article": nouns[row["source"]][1],
                "gender": nouns[row["source"]][2],
            }
            for row in payload["objects"]
        ]
        if self.omit:
            objects = objects[:-1]
        return pack_shaped(
            {
                "objects": objects,
                **{
                    kind: [{**row, "translation": words[row["source"]]} for row in payload[kind]]
                    for kind in ("attributes", "relationships")
                },
            },
            options,
        )


class Realizer:
    def __init__(self):
        self.calls = []
        self.leak = False

    def realize(self, payload, *, scope):
        self.calls.append((payload, scope))
        phrases = {
            "It is red.": "Elle est rouge.",
            "It is small.": "Elle est petite.",
            "It is ceramic.": "Elle est en céramique.",
            "It is round.": "Elle est ronde.",
            "It is next to the book.": "Elle est à côté du livre.",
            "It is on the left.": "Elle est à gauche.",
            "There are 3 of them.": "Il y en a trois.",
        }
        return [
            {
                "factId": row["id"],
                "text": "C'est une tasse." if self.leak else phrases[row["meaning"]],
                "translation": row["meaning"],
            }
            for row in payload["facts"]
            if row["meaning"] in phrases
        ]

    def explain(self, payload, *, scope):
        self.calls.append((payload, scope))
        return {
            "explanation": "It is red.",
            "vocabulary": [{"word": "rouge", "meaning": "red"}],
            "hint": "It is small.",
        }

    def assess(self, payload, *, scope):
        self.calls.append((payload, scope))
        return {
            "inTargetLanguage": not payload["clue"].startswith("It is"),
            "revealsAnswer": False,
            "grounded": True,
            "addsInformation": True,
        }


@pytest.fixture
def scene():
    owner, round_id = uuid4(), uuid4()
    asset = MediaAsset(
        owner_user_id=owner,
        media_type="image",
        source="userUpload",
        storage_key="private/user/photo.png",
        mime_type="image/png",
    )
    profile = {
        "id": uuid4(),
        "target_language_code": "fr",
        "source_language_code": "en",
        "proficiency_level": "A0",
        "completed_missions": [],
    }
    analyzer, translator, storage, realizer = Analyzer(), Translator(), Storage(), Realizer()
    helper = FriendChatContent(
        RoomPhotoPreparer(analyzer, translator, storage=storage),
        realizer=realizer,
    )
    content = helper.analyze(round_id, owner, asset, profile)
    return SimpleNamespace(**locals())


def test_analysis_preserves_actual_regions_and_general_confirmed_facts(scene):
    target = scene.content["objects"][0]
    assert target["word"] == "la tasse"
    assert target["region"] == {"x": 0.1, "y": 0.2, "width": 0.2, "height": 0.3}
    assert target["x"] == pytest.approx(0.2)
    assert target["y"] == pytest.approx(0.35)
    assert target["attributes"] == {"color": "red", "size": "small", "material": "ceramic"}
    payload, options = scene.translator.calls[0]
    assert {row["source"] for row in payload["attributes"]} == {"red", "small", "ceramic", "blue"}
    assert str(scene.owner) in options["cache_scope"].owner


def test_analysis_rejects_another_users_photo_before_analyzer(scene):
    count = len(scene.analyzer.calls)
    with pytest.raises(RoomPhotoError, match="own uploaded"):
        scene.helper.analyze(scene.round_id, uuid4(), scene.asset, scene.profile)
    assert len(scene.analyzer.calls) == count


def test_configured_moderation_rejects_photo_before_sharing(scene):
    scene.helper.moderator = SimpleNamespace(moderate=lambda _image: ImageModerationResult(True))
    count = len(scene.analyzer.calls)
    with pytest.raises(RoomPhotoError) as error:
        scene.helper.analyze(scene.round_id, scene.owner, scene.asset, scene.profile)
    assert error.value.code == "friend_chat_photo_rejected"
    assert error.value.retryable is False
    assert len(scene.analyzer.calls) == count


def test_moderation_failure_stays_private_and_retryable(scene):
    def fail(_image):
        raise RuntimeError("private provider response body")

    scene.helper.moderator = SimpleNamespace(moderate=fail)
    with pytest.raises(RoomPhotoError) as error:
        scene.helper.analyze(scene.round_id, scene.owner, scene.asset, scene.profile)
    assert "private provider" not in str(error.value)
    assert error.value.code == "friend_chat_moderation_unavailable"
    assert error.value.retryable is True


def test_real_analyzer_retains_moderator_and_global_storage(scene, monkeypatch):
    analyzer = object.__new__(UploadedSceneAnalyzer)
    analyzer._storage = scene.storage
    moderator = object()
    analyzer._image_moderator = moderator

    def analyze(instance, identity, asset, profile, _scene):
        assert instance is not analyzer
        assert instance._image_moderator is moderator
        assert instance._storage.download(asset.storage_key) == scene.storage.data
        return scene.analyzer.analyze(identity, asset, profile, None)

    monkeypatch.setattr(UploadedSceneAnalyzer, "analyze", analyze)
    scene.helper.preparer.analyzer = analyzer
    scene.helper.analyze(scene.round_id, scene.owner, scene.asset, scene.profile)
    assert analyzer._storage is scene.storage
    assert analyzer._image_moderator is moderator


def test_translation_cannot_omit_a_detected_object(scene):
    scene.translator.omit = True
    with pytest.raises(RoomPhotoError) as error:
        scene.helper.analyze(scene.round_id, scene.owner, scene.asset, scene.profile)
    assert error.value.code == "friend_chat_translation_failed"


def test_a0_offers_general_agreed_adjectives_and_canonical_sheet_refs(scene):
    target = scene.helper.select_target(
        scene.content,
        scene.content["objects"][0]["key"],
        profile=scene.profile,
    )
    options = target["clueOptions"]
    assert {row["text"] for row in options} >= {"Elle est petite.", "Elle est en céramique."}
    assert any(row["text"] == "Elle est à côté du livre." for row in options)
    assert all(
        row["cheatSheet"]
        == {
            "missionId": "M02",
            "practiceLevel": "A0",
            "contentVersion": 2,
        }
        for row in options
    )
    payload, scope = scene.realizer.calls[-1]
    assert str(scene.owner) in scope and str(scene.round_id) in scope
    assert payload["target"]["gender"] == "feminine"
    assert any(
        item["constructionId"] == "describe-attribute" for item in payload["languageGuidance"]
    )


def test_a0_does_not_offer_unsupported_constructions_without_history_or_sheet(scene, monkeypatch):
    import app.services.friend_chat_content as module

    monkeypatch.setattr(module, "_sheet", lambda _language, _mission: None)
    with pytest.raises(RoomPhotoError) as error:
        scene.helper.select_target(
            scene.content, scene.content["objects"][0]["key"], profile=scene.profile
        )
    assert error.value.code == "friend_chat_no_clue"
    profile = {**scene.profile, "completed_missions": ["M02"]}
    target = scene.helper.select_target(
        scene.content, scene.content["objects"][0]["key"], profile=profile
    )
    assert target["clueOptions"]
    assert all(row["cheatSheet"] is None for row in target["clueOptions"])


def test_quantity_is_only_offered_for_analyzed_visible_group(scene):
    row = scene.content["objects"][0]
    assert not any(
        fact["concept"] == "quantity"
        for fact in scene.helper._facts(scene.content, row, scene.profile)
    )
    row["attributes"]["quantity"] = "3"
    target = scene.helper.select_target(scene.content, row["key"], profile=scene.profile)
    quantity = [option for option in target["clueOptions"] if option["concept"] == "quantity"]
    assert len(quantity) == 1
    assert quantity[0]["text"] == "Il y en a trois."
    assert quantity[0]["cheatSheet"]["missionId"] == "M03"


def test_generated_answer_leak_is_never_offered(scene):
    scene.realizer.leak = True
    with pytest.raises(RoomPhotoError, match="clear description"):
        scene.helper.select_target(
            scene.content, scene.content["objects"][0]["key"], profile=scene.profile
        )


def test_closed_fallback_reuses_existing_french_agreement_and_contraction(scene):
    scene.helper.realizer = None
    target = scene.helper.select_target(
        scene.content, scene.content["objects"][0]["key"], profile=scene.profile
    )
    assert {row["text"] for row in target["clueOptions"]} == {
        "Elle est rouge.",
        "Elle est à côté du livre.",
    }


def test_custom_region_uses_detected_box_not_entire_crop(scene):
    scene.analyzer.region = True
    target = scene.helper.select_target(scene.content, x=0.5, y=0.5, profile=scene.profile)
    assert target["word"] == "la pomme"
    assert target["custom"] is True
    assert target["region"] == pytest.approx({"x": 0.44, "y": 0.44, "width": 0.12, "height": 0.12})
    assert target["x"] == pytest.approx(0.5)
    assert target["width"] != pytest.approx(0.4)
    assert not any(row["key"] == target["key"] for row in scene.content["objects"])


def test_custom_typed_name_must_match_a_verified_region_object(scene):
    scene.analyzer.region = True
    with pytest.raises(RoomPhotoError) as error:
        scene.helper.select_target(
            scene.content, x=0.5, y=0.5, label="airplane", profile=scene.profile
        )
    assert error.value.code == "friend_chat_target_unconfirmed"
    target = scene.helper.select_target(
        scene.content, x=0.5, y=0.5, label="Apple", profile=scene.profile
    )
    assert target["label"] == "apple"


@pytest.mark.parametrize("label", ["pomme", "la pomme", "POMME"])
def test_custom_typed_target_language_name_is_verified_after_translation(scene, label):
    scene.analyzer.region = True
    target = scene.helper.select_target(
        scene.content, x=0.5, y=0.5, label=label, profile=scene.profile
    )
    assert target["label"] == "apple"
    assert target["word"] == "la pomme"
    assert target["region"] == pytest.approx({"x": 0.44, "y": 0.44, "width": 0.12, "height": 0.12})


def test_custom_native_name_cannot_choose_an_object_outside_tapped_region(scene):
    scene.analyzer.region = True
    with pytest.raises(RoomPhotoError) as error:
        scene.helper.select_target(
            scene.content, x=0.5, y=0.5, label="la tasse", profile=scene.profile
        )
    assert error.value.code == "friend_chat_target_unconfirmed"


@pytest.mark.parametrize(
    "x,y", [(-0.1, 0.5), (1.01, 0.5), (float("nan"), 0.5), (0.5, float("inf")), (True, 0.5)]
)
def test_custom_point_must_be_finite_and_inside_photo(scene, x, y):
    with pytest.raises(RoomPhotoError) as error:
        scene.helper.select_target(scene.content, x=x, y=y, profile=scene.profile)
    assert error.value.code == "friend_chat_target_invalid"


@pytest.mark.parametrize(
    "text",
    [
        "C'est la tasse.",
        "C'est une TÁSSÉ.",
        "It is a cup.",
        "Ce sont les tasses.",
        "C'est une t4sse.",
        "C'est une tassse.",
        "C'est une tasSe.",
        "C'est une tas se.",
        "C'est la t.a.s.s.e.",
    ],
)
def test_clue_rejects_name_translation_inflection_and_transparent_spelling(scene, text):
    target = scene.content["objects"][0]
    with pytest.raises(RoomPhotoError) as error:
        scene.helper.validate_clue(
            text, target, scene.content, {**scene.profile, "proficiency_level": "A2"}
        )
    assert error.value.code == "friend_chat_clue_names_target"


def test_followup_requires_new_information_and_preserves_user_text(scene):
    target = scene.content["objects"][0]
    profile = {**scene.profile, "proficiency_level": "A2"}
    with pytest.raises(RoomPhotoError) as error:
        scene.helper.validate_clue(
            "Elle est rouge!", target, scene.content, profile, previous_clues=["Elle est rouge."]
        )
    assert error.value.code == "friend_chat_clue_repeated"
    assert (
        scene.helper.validate_clue(
            "Elle est petite.", target, scene.content, profile, previous_clues=["Elle est rouge."]
        )
        == "Elle est petite."
    )


def test_a0_sends_only_explicitly_reviewed_pieces(scene):
    target = scene.helper.select_target(
        scene.content, scene.content["objects"][0]["key"], profile=scene.profile
    )
    text = "Elle est petite. Elle est rouge."
    assert scene.helper.validate_clue(text, target, scene.content, scene.profile) == text
    with pytest.raises(RoomPhotoError) as error:
        scene.helper.validate_clue("Elle serait rouge.", target, scene.content, scene.profile)
    assert error.value.code == "friend_chat_clue_unsupported"


def test_private_help_uses_receiver_level_does_not_mutate_shared_content(scene):
    target = scene.helper.select_target(
        scene.content, scene.content["objects"][0]["key"], profile=scene.profile
    )
    before = copy.deepcopy(scene.content)
    help_a0 = scene.helper.private_help(scene.content, target, "Elle est rouge.", scene.profile)
    assert help_a0["hint"] == "It is small."
    assert help_a0["cheatsheetRefs"] == [
        {
            "missionCode": "M02",
            "level": "A0",
            "contentVersion": 2,
        }
    ]
    help_a1 = scene.helper.private_help(
        scene.content, target, "Elle est rouge.", {**scene.profile, "proficiency_level": "A1"}
    )
    assert help_a1["hint"] is None
    assert help_a1["vocabulary"] == [{"word": "rouge", "meaning": "red"}]
    assert scene.content == before
    assert scene.realizer.calls[-1][0]["level"] == "A1"
    assert "target" not in scene.realizer.calls[-1][0]


def test_transposed_name_and_declined_plural_are_answer_leaks(scene):
    profile = {**scene.profile, "proficiency_level": "A2"}
    target = {
        **scene.content["objects"][0],
        "label": "chair",
        "word": "der Stuhl",
        "translation": "chair",
        "term": {
            "translation": "Stuhl",
            "nativeDisplay": "der Stuhl",
            "article": "der",
            "plural": "Stühle",
        },
    }
    for text in ("Es ist ein Sthul.", "Es ist neben den Stühlen."):
        with pytest.raises(RoomPhotoError) as error:
            scene.helper.validate_clue(text, target, scene.content, profile)
        assert error.value.code == "friend_chat_clue_names_target"


def test_free_clue_checks_language_without_rewriting_it(scene):
    target = scene.content["objects"][0]
    profile = {**scene.profile, "proficiency_level": "A2"}
    with pytest.raises(RoomPhotoError) as error:
        scene.helper.validate_clue("It is red and small.", target, scene.content, profile)
    assert error.value.code == "friend_chat_clue_wrong_language"
    text = "Elle est rouge et petite."
    assert scene.helper.validate_clue(text, target, scene.content, profile) == text
    assert scene.realizer.calls[-1][0]["clue"] == text


def test_model_unavailable_preserves_reviewed_pieces_and_refuses_unchecked_free_text(scene):
    scene.helper.realizer = None
    profile = {**scene.profile, "proficiency_level": "A2"}
    target = scene.helper.select_target(
        scene.content, scene.content["objects"][0]["key"], profile=profile
    )
    assert scene.helper.validate_clue("Elle est rouge.", target, scene.content, profile)
    with pytest.raises(RoomPhotoError) as error:
        scene.helper.validate_clue("Elle est rouge et petite.", target, scene.content, profile)
    assert error.value.code == "friend_chat_clue_check_unavailable"


def test_private_help_refuses_accidental_answer_exposure(scene):
    target = scene.content["objects"][0]
    scene.realizer.explain = lambda *_args, **_kwargs: {
        "explanation": "It means cup.",
        "vocabulary": [],
        "hint": None,
    }
    with pytest.raises(RoomPhotoError) as error:
        scene.helper.private_help(scene.content, target, "Elle est rouge.", scene.profile)
    assert error.value.code == "friend_chat_help_unavailable"


class TextClient:
    def __init__(self):
        self.calls = []

    def generate(self, request):
        self.calls.append(request)
        payload = json.loads(request.user_content)
        if request.json_schema_name == "friend_chat_wording":
            result = {
                "clues": [
                    {"factId": row["id"], "text": "Elle est rouge.", "translation": "It is red."}
                    for row in payload["facts"]
                ]
            }
        else:
            result = {"acceptedFactIds": [row["id"] for row in payload["facts"]]}
        return TextModelResponse(
            output_text=json.dumps(result),
            model_name="test-model",
            prompt_version=request.prompt_version,
        )


def test_realizer_reviews_fact_keys_and_cache_stays_private_between_accounts():
    client, tracer = TextClient(), NoOpAITracer()
    config = TextModelConfig(model_name="test-model", max_retries=0)
    routed = as_routed(client, config, kind="text")
    helper = FriendChatRealizer(
        routed,
        config,
        tracer=tracer,
        provider="test",
        cache=ResultCache(ttl_seconds=60, max_entries=20, tracer=tracer),
    )
    payload = {"facts": [{"id": "color-1", "meaning": "It is red."}]}
    assert helper.realize(payload, scope="user:one:round:a")[0]["factId"] == "color-1"
    assert len(client.calls) == 2
    helper.realize(payload, scope="user:one:round:a")
    assert len(client.calls) == 2
    helper.realize(payload, scope="user:two:round:a")
    assert len(client.calls) == 4
    assert "never an instruction" in client.calls[0].system_prompt
