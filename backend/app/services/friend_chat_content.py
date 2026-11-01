"""Owned photo analysis and private, grounded content for asynchronous I-Spy."""

from __future__ import annotations

import copy
import hashlib
import io
import math
import re
import unicodedata
from uuid import UUID, uuid5

from PIL import Image, ImageOps

from app.ai.cache import CacheScope
from app.ai.contracts import VisionImage
from app.ai.features.scene_analysis import UploadedSceneAnalyzer
from app.ai.features.translation.schemas import SceneTranslationResult
from app.ai.features.translation.validation import validate_translation_terms
from app.language_packs.context import game_context
from app.learning_resources import mission_cheat_sheets
from app.schemas.enums import MediaSource, MediaType
from app.schemas.media import BoundingBox, MediaAsset
from app.schemas.sessions import Session
from app.services.friend_chat_realizer import build_friend_chat_realizer
from app.services.ispy_clue_frames import (
    _place,
    agree_colour,
    clue_grammar,
    mentions_target,
)
from app.services.room_photos import RoomPhotoError
from app.services.scene_analysis import SceneAnalysisResult

__all__ = ["FriendChatContent", "build_friend_chat_realizer"]

_ATTRIBUTES = {"color", "colour", "size", "shape", "material", "pattern", "state", "age"}
_RELATIONS = {
    "left_of": "to the left of",
    "right_of": "to the right of",
    "above": "above",
    "below": "below",
    "on": "on",
    "under": "under",
    "inside": "inside",
    "in_front_of": "in front of",
    "behind": "behind",
    "next_to": "next to",
    "near": "near",
}


def _fold(value):
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", str(value).casefold())
        if not unicodedata.combining(char)
    )


def _words(value):
    return re.findall(r"[^\W_]+", _fold(value), re.UNICODE)


def _same_name(first, second):
    a, b = _words(first), _words(second)
    if a == b:
        return True
    return len(a) == len(b) == 1 and (
        a[0].rstrip("s") == b[0].rstrip("s") or a[0].removesuffix("es") == b[0]
    )


def _scope(content):
    return f"user:{content['ownerId']}:friend-round:{content['roundId']}"


def _language(profile):
    context = game_context(profile)
    if context is None:
        raise RoomPhotoError(
            "friend_chat_language_unavailable",
            "This learning language is not available for I-Spy yet.",
            retryable=False,
        )
    return context


def _sheet(language, mission):
    candidates = [
        sheet
        for sheet in mission_cheat_sheets().values()
        if sheet.language_code.casefold() == language.casefold()
        and sheet.mission_id == mission
        and str(sheet.practice_level) == "A0"
    ]
    return max(candidates, key=lambda sheet: sheet.content_version) if candidates else None


def _sheet_ref(sheet):
    return {
        "missionId": sheet.mission_id,
        "practiceLevel": str(sheet.practice_level),
        "contentVersion": sheet.content_version,
    }


def _avoid(target):
    term = target.get("term", {})
    phrases = [
        target.get("label"),
        target.get("translation"),
        term.get("translation"),
        term.get("plural"),
        term.get("romanization"),
    ]
    phrases += target.get("alternativeLabels", [])
    displays = [target.get("word"), term.get("nativeDisplay")]
    article = term.get("article")
    for display in filter(None, displays):
        bare = str(display).strip()
        if article and _fold(bare).startswith(_fold(article)):
            bare = bare[len(article) :].strip()
        phrases.append(bare)
    forms = set()
    for phrase in filter(None, phrases):
        phrase = str(phrase).strip()
        forms.add(phrase)
        # A compound noun's head still directly names the answer.
        words = _words(phrase)
        if words:
            forms.add(words[0])
        for word in words:
            if len(word) > 2:
                forms.update([word + ending for ending in ("s", "es", "x", "n", "en")])
    return sorted(forms)


def _near(first, second):
    """One transparent edit, without fuzzy matching short unrelated words."""
    if min(len(first), len(second)) < 5 or abs(len(first) - len(second)) > 1:
        return False
    if len(first) == len(second):
        differences = [
            index for index, (a, b) in enumerate(zip(first, second, strict=True)) if a != b
        ]
        if len(differences) <= 1:
            return True
        return (
            len(differences) == 2
            and differences[1] == differences[0] + 1
            and first[differences[0]] == second[differences[1]]
            and first[differences[1]] == second[differences[0]]
        )
    shorter, longer = sorted((first, second), key=len)
    return any(longer[:index] + longer[index + 1 :] == shorter for index in range(len(longer)))


def _names_target(text, target):
    forms = _avoid(target)
    if mentions_target(text, forms):
        return True
    tokens = _words(text)
    bare = {"".join(_words(form)) for form in forms}
    for token in tokens:
        decoded = token.translate(str.maketrans("013457", "oieast"))
        if decoded in bare or any(_near(decoded, form) for form in bare):
            return True
        # Korean nouns retain their stem before case/topic particles.
        if any("HANGUL" in unicodedata.name(char, "") for char in token):
            if any(
                len(form) >= 1 and token.startswith(form) and len(token) - len(form) <= 4
                for form in bare
            ):
                return True
    for start in range(len(tokens)):
        for stop in range(start + 2, min(start + 7, len(tokens) + 1)):
            pieces = tokens[start:stop]
            joined = "".join(pieces)
            if joined in bare and (len(joined) >= 4 or all(len(piece) == 1 for piece in pieces)):
                return True
    # Punctuation between letters is an obvious spelling variation, too.
    letters = re.sub(r"[^\w\s]", "", _fold(text))
    return mentions_target(letters, forms)


class _BytesStorage:
    def __init__(self, key, data):
        self.key, self.data = key, data

    def download(self, key):
        if key != self.key:
            raise ValueError("Unexpected photo key.")
        return self.data


class FriendChatContent:
    def __init__(self, preparer, *, moderator=None, realizer=None):
        self.preparer, self.moderator, self.realizer = preparer, moderator, realizer

    def _analyze_bytes(self, round_id, owner_id, asset, profile, data):
        analyzer = self.preparer.analyzer
        if analyzer is None:
            raise RoomPhotoError(
                "friend_chat_analysis_unavailable", "Photo analysis is unavailable. Try again."
            )
        image = VisionImage(data=data, mime_type=asset.mime_type)
        if isinstance(analyzer, UploadedSceneAnalyzer):
            analyzer = copy.copy(analyzer)
            analyzer._storage = _BytesStorage(asset.storage_key, data)
            # Retain the application's normal moderator, including on cropped images.
            if self.moderator is not None:
                analyzer._image_moderator = self.moderator
        elif self.moderator is not None:
            try:
                verdict = self.moderator.moderate(image)
                if not isinstance(verdict.flagged, bool):
                    raise ValueError("Missing moderation verdict.")
            except Exception as error:
                raise RoomPhotoError(
                    "friend_chat_moderation_unavailable",
                    "This photo could not be checked before sharing. Try again.",
                ) from error
            if verdict.flagged:
                raise RoomPhotoError(
                    "friend_chat_photo_rejected",
                    "This photo cannot be shared. Choose another photo.",
                    retryable=False,
                )
        identity = Session(
            id=round_id,
            user_id=owner_id,
            scene_media_asset_id=asset.id,
            language_profile_id=UUID(str(profile["id"])),
        )
        try:
            result = SceneAnalysisResult.model_validate(
                analyzer.analyze(identity, asset, profile, None)
            )
            if not result.objects or len({item.id for item in result.objects}) != len(
                result.objects
            ):
                raise ValueError("Analysis must identify distinct objects.")
            if any(item.session_id != round_id for item in result.objects):
                raise ValueError("Analysis returned objects from another photo.")
            return result
        except RoomPhotoError:
            raise
        except Exception as error:
            rejected = getattr(error, "code", None) == "imageModerationFailed"
            raise RoomPhotoError(
                "friend_chat_photo_rejected" if rejected else "friend_chat_analysis_failed",
                "This photo cannot be shared. Choose another photo."
                if rejected
                else "Photo analysis did not finish. Try checking the photo again.",
                retryable=not rejected,
            ) from error

    def _translate(self, content, objects, relations, profile):
        if self.preparer.translator is None:
            raise RoomPhotoError(
                "friend_chat_translation_unavailable", "Photo words could not be translated."
            )
        context = _language(profile)
        ids = {str(obj.id) for obj in objects}
        relations = [
            row
            for row in relations
            if str(row.subject_scene_object_id) in ids and str(row.reference_scene_object_id) in ids
        ]
        attributes = [
            {"key": f"{obj.id}:{kind}", "source": value}
            for obj in objects
            for kind, value in (obj.attributes or {}).items()
            if kind in _ATTRIBUTES and isinstance(value, str) and value.strip()
        ]
        payload = {
            "targetLanguage": context.display.language_code,
            "sceneTitle": content["title"],
            "sceneSummary": content.get("summary", "")[:1000],
            "objects": [{"key": str(obj.id), "source": obj.label} for obj in objects],
            "attributes": attributes,
            "relationships": [{"key": str(row.id), "source": row.relation} for row in relations],
        }
        try:
            translated = SceneTranslationResult.model_validate(
                self.preparer.translator.translate(
                    payload,
                    language_context=context,
                    cache_scope=CacheScope(_scope(content)),
                )
            )
            validate_translation_terms(payload, translated, context)
            for group in (translated.objects, translated.attributes, translated.relationships):
                if len(group) != len({term.key for term in group}):
                    raise ValueError("Translation repeated a fact.")
        except Exception as error:
            raise RoomPhotoError(
                "friend_chat_translation_failed", "Photo words could not be translated. Try again."
            ) from error
        terms = {
            term.key: term.model_dump(mode="json", by_alias=True) for term in translated.objects
        }
        rows = []
        for obj in objects:
            term = terms[str(obj.id)]
            row = {
                "key": str(obj.id),
                "label": obj.label,
                "word": term["nativeDisplay"],
                "translation": term["source"],
                "term": term,
                "attributes": obj.attributes or {},
            }
            if obj.bounding_box:
                box = {key: float(value) for key, value in obj.bounding_box.model_dump().items()}
                row.update(
                    x=box["x"] + box["width"] / 2,
                    y=box["y"] + box["height"] / 2,
                    width=box["width"],
                    height=box["height"],
                    region=box,
                )
            elif obj.anchor_point:
                row.update(x=float(obj.anchor_point.x), y=float(obj.anchor_point.y))
            else:
                continue
            rows.append(row)
        return (
            rows,
            [
                {
                    "key": str(row.id),
                    "subjectObjectKey": str(row.subject_scene_object_id),
                    "referenceObjectKey": str(row.reference_scene_object_id),
                    "relation": row.relation,
                }
                for row in relations
            ],
            [term.model_dump(mode="json", by_alias=True) for term in translated.attributes],
            [term.model_dump(mode="json", by_alias=True) for term in translated.relationships],
        )

    def analyze(self, round_id, owner_id, asset, profile):
        if (
            asset.owner_user_id != owner_id
            or asset.media_type is not MediaType.IMAGE
            or asset.source not in {MediaSource.USER_UPLOAD, MediaSource.CAMERA}
        ):
            raise RoomPhotoError(
                "friend_chat_photo_invalid",
                "Choose one of your own uploaded photos.",
                retryable=False,
            )
        _language(profile)
        try:
            data = self.preparer.storage.download(asset.storage_key)
        except Exception as error:
            raise RoomPhotoError(
                "friend_chat_photo_unavailable", "The photo could not be opened. Try again."
            ) from error
        result = self._analyze_bytes(round_id, owner_id, asset, profile, data)
        content = {
            "version": 1,
            "roundId": str(round_id),
            "ownerId": str(owner_id),
            "mediaAssetId": str(asset.id),
            "storageKey": asset.storage_key,
            "mimeType": asset.mime_type,
            "title": result.title[:100],
            "summary": result.summary[:1000],
            "contentHash": hashlib.sha256(data).hexdigest(),
        }
        rows, relations, attributes, positions = self._translate(
            content,
            result.objects[:20],
            result.relations,
            profile,
        )
        content.update(
            objects=rows, relations=relations, attributeTerms=attributes, relationTerms=positions
        )
        if not rows:
            raise RoomPhotoError(
                "friend_chat_no_objects", "No usable objects were found. Choose another photo."
            )
        return content

    def _region_target(self, content, x, y, label, profile):
        if (
            not isinstance(x, (float, int))
            or isinstance(x, bool)
            or not isinstance(y, (float, int))
            or isinstance(y, bool)
            or not math.isfinite(x)
            or not math.isfinite(y)
            or not 0 <= x <= 1
            or not 0 <= y <= 1
        ):
            raise RoomPhotoError(
                "friend_chat_target_invalid",
                "Tap a point inside the photo.",
                retryable=False,
            )
        try:
            original = self.preparer.storage.download(content["storageKey"])
            with Image.open(io.BytesIO(original)) as raw:
                image = ImageOps.exif_transpose(raw).convert("RGB")
                width, height = image.size
                # The crop is a request to inspect this region, never the guessed answer region.
                left, top = max(0, int((x - 0.20) * width)), max(0, int((y - 0.20) * height))
                right, bottom = (
                    min(width, int((x + 0.20) * width)),
                    min(height, int((y + 0.20) * height)),
                )
                if right <= left or bottom <= top:
                    raise ValueError("Empty selected region.")
                output = io.BytesIO()
                image.crop((left, top, right, bottom)).save(output, format="PNG")
            crop_asset = MediaAsset(
                id=UUID(content["mediaAssetId"]),
                owner_user_id=UUID(content["ownerId"]),
                media_type="image",
                source="userUpload",
                storage_key=content["storageKey"],
                mime_type="image/png",
            )
            crop_id = uuid5(UUID(content["roundId"]), f"region:{left}:{top}:{right}:{bottom}")
            result = self._analyze_bytes(
                crop_id,
                UUID(content["ownerId"]),
                crop_asset,
                profile,
                output.getvalue(),
            )
            local_x = (x * width - left) / (right - left)
            local_y = (y * height - top) / (bottom - top)
            candidates = [
                obj
                for obj in result.objects
                if obj.bounding_box
                and float(obj.bounding_box.x)
                <= local_x
                <= float(obj.bounding_box.x + obj.bounding_box.width)
                and float(obj.bounding_box.y)
                <= local_y
                <= float(obj.bounding_box.y + obj.bounding_box.height)
            ]
            if not candidates:
                raise RoomPhotoError(
                    "friend_chat_target_unconfirmed",
                    "We could not identify that object and name. "
                    "Tap its centre or try another name.",
                    retryable=False,
                )
            mapped = []
            for obj in candidates[:20]:
                box = obj.bounding_box
                mapped.append(
                    obj.model_copy(
                        update={
                            "session_id": UUID(content["roundId"]),
                            "bounding_box": BoundingBox.model_validate(
                                {
                                    "x": (left + float(box.x) * (right - left)) / width,
                                    "y": (top + float(box.y) * (bottom - top)) / height,
                                    "width": float(box.width) * (right - left) / width,
                                    "height": float(box.height) * (bottom - top) / height,
                                }
                            ),
                        }
                    )
                )
            rows, _relations, attributes, _positions = self._translate(content, mapped, [], profile)
            if label:
                rows = [
                    row
                    for row in rows
                    if any(
                        _same_name(label, name)
                        for name in filter(
                            None,
                            [
                                row["label"],
                                row["word"],
                                row["term"].get("translation"),
                                row["term"].get("nativeDisplay"),
                                row["term"].get("romanization"),
                            ],
                        )
                    )
                ]
            if not rows:
                raise RoomPhotoError(
                    "friend_chat_target_unconfirmed",
                    "That name does not match an object at this point. "
                    "Try another name or choose the suggested object.",
                    retryable=False,
                )
            row = min(rows, key=lambda item: item["width"] * item["height"])
            row["custom"] = True
            row["attributeTerms"] = [
                term for term in attributes if term["key"].startswith(row["key"] + ":")
            ]
            return row
        except RoomPhotoError:
            raise
        except Exception as error:
            raise RoomPhotoError(
                "friend_chat_region_unavailable", "That region could not be checked. Try again."
            ) from error

    def select_target(self, content, object_key=None, x=None, y=None, label=None, profile=None):
        if profile is None:
            raise RoomPhotoError("friend_chat_profile_required", "Choose your learning profile.")
        if object_key:
            target = next((row for row in content["objects"] if row["key"] == object_key), None)
            if target is None:
                raise RoomPhotoError(
                    "friend_chat_target_invalid",
                    "Choose an object from this photo.",
                    retryable=False,
                )
            target = copy.deepcopy(target)
            if not target.get("region"):
                target = self._region_target(
                    content, target["x"], target["y"], target["label"], profile
                )
        else:
            target = self._region_target(content, x, y, label, profile)
        target["clueOptions"] = self._options(content, target, profile)
        if not target["clueOptions"] and str(profile.get("proficiency_level")) == "A0":
            raise RoomPhotoError(
                "friend_chat_no_clue",
                "Choose an object with a clear description or position for a beginner clue.",
                retryable=False,
            )
        return target

    def _facts(self, content, target, profile):
        language = _language(profile).display.language_code
        completed = set(profile.get("completed_missions") or [])
        beginner = str(profile.get("proficiency_level", "A0")) == "A0"
        facts = []

        def add(key, kind, meaning, mission, **details):
            sheet = _sheet(language, mission)
            # A bounded construction can be introduced with its existing canonical sheet.
            if beginner and mission not in completed and sheet is None:
                return
            facts.append(
                {
                    "id": key,
                    "concept": kind,
                    "meaning": meaning,
                    "cheatSheet": _sheet_ref(sheet) if sheet else None,
                    **details,
                }
            )

        for kind, value in target.get("attributes", {}).items():
            if kind in _ATTRIBUTES and isinstance(value, str) and value.strip():
                add(
                    f"attribute:{target['key']}:{kind}",
                    "adjective",
                    f"It is {value}.",
                    "M02",
                    attributeKind=kind,
                    value=value,
                )
        region = target.get("region")
        if region:
            positions = []
            if region["x"] + region["width"] < 0.5:
                positions.append(("left", "on the left"))
            elif region["x"] > 0.5:
                positions.append(("right", "on the right"))
            if region["y"] + region["height"] < 0.5:
                positions.append(("top", "near the top"))
            elif region["y"] > 0.5:
                positions.append(("bottom", "near the bottom"))
            for position, meaning in positions:
                add(
                    f"position:{target['key']}:{position}",
                    "position",
                    f"It is {meaning}.",
                    "M02",
                    position=position,
                )
        objects = {row["key"]: row for row in content["objects"]}
        for relation in content.get("relations", []):
            if relation["subjectObjectKey"] != target["key"]:
                continue
            reference = objects.get(relation["referenceObjectKey"])
            meaning = _RELATIONS.get(relation["relation"])
            if not reference or not meaning or _names_target(reference["word"], target):
                continue
            add(
                f"relation:{relation['key']}",
                "position",
                f"It is {meaning} the {reference['label']}.",
                "M02",
                relation=relation["relation"],
                reference=reference["term"],
            )
        count = target.get("attributes", {}).get("quantity")
        try:
            count = int(count)
        except (TypeError, ValueError):
            count = 0
        if 1 < count <= 20:
            add(
                f"quantity:{target['key']}",
                "quantity",
                f"There are {count} of them.",
                "M03",
                quantity=count,
            )
        return facts[:12]

    def _options(self, content, target, profile):
        context = _language(profile)
        facts = self._facts(content, target, profile)
        if not facts:
            return []
        if self.realizer is not None:
            construction_ids = {
                "describe-attribute",
                "find-object",
                "location-phrase",
                "how-many-question",
                "quantity-statement",
            }
            payload = {
                "targetLanguage": context.display.language_code,
                "register": context.display.register_id,
                "level": str(profile.get("proficiency_level", "A0")),
                "target": target["term"],
                "facts": facts,
                "languageGuidance": [
                    item.model_dump(mode="json", by_alias=True)
                    for item in context.pack.constructions
                    if item.construction_id in construction_ids
                ],
            }
            realized = self.realizer.realize(payload, scope=_scope(content))
        else:
            realized = self._closed_grammar_options(content, target, facts, profile)
        by_id = {fact["id"]: fact for fact in facts}
        options = []
        for row in realized:
            fact = by_id.get(row.get("factId"))
            if not fact or _names_target(row.get("text", ""), target):
                continue
            text, meaning = row.get("text", "").strip(), row.get("translation", "").strip()
            if not text or not meaning or _names_target(meaning, target):
                continue
            if any(option["text"].casefold() == text.casefold() for option in options):
                continue
            options.append(
                {
                    "id": str(uuid5(UUID(target["key"]), f"clue:{fact['id']}:{text}")),
                    "text": text,
                    "translation": meaning,
                    "concept": fact["concept"],
                    "cheatSheet": fact["cheatSheet"],
                    "factId": fact["id"],
                }
            )
        return options

    @staticmethod
    def _closed_grammar_options(content, target, facts, profile):
        language = _language(profile).display.language_code
        grammar = clue_grammar(language)
        if grammar is None:
            return []
        attributes = {
            term["key"]: term
            for term in [*content.get("attributeTerms", []), *target.get("attributeTerms", [])]
        }
        positions = {term["key"]: term for term in content.get("relationTerms", [])}
        rows = []
        for fact in facts:
            phrase = None
            if fact.get("attributeKind") in {"color", "colour"}:
                term = attributes.get(f"{target['key']}:{fact['attributeKind']}")
                if term:
                    adjective = agree_colour(
                        language, term["translation"], target["term"].get("gender")
                    )
                    if adjective:
                        phrase = (
                            f"{grammar.prefix('colour', target['term'].get('gender'))} {adjective}"
                        )
            elif fact["concept"] == "position":
                term = positions.get(fact["id"].removeprefix("relation:"))
                if term:
                    place = _place(language, term["translation"], fact["reference"])
                    if place:
                        phrase = (
                            f"{grammar.prefix('location', target['term'].get('gender'))} {place}"
                        )
            if phrase:
                rows.append(
                    {
                        "factId": fact["id"],
                        "text": phrase.rstrip(".") + ".",
                        "translation": fact["meaning"],
                    }
                )
        return rows

    def clue_options(self, content, target, profile):
        return target.get("clueOptions") or self._options(content, target, profile)

    def validate_clue(self, text, target, content, profile, previous_clues=()):
        text = unicodedata.normalize("NFC", str(text)).strip()
        if not 2 <= len(text) <= 500 or any(unicodedata.category(c) == "Cc" for c in text):
            raise RoomPhotoError(
                "friend_chat_clue_invalid",
                "Write a short clue before sending.",
                retryable=False,
            )
        if _names_target(text, target):
            raise RoomPhotoError(
                "friend_chat_clue_names_target",
                "Describe the object without its name or translation.",
                retryable=False,
            )
        current = set(_words(text))
        if any(current <= set(_words(previous)) for previous in previous_clues):
            raise RoomPhotoError(
                "friend_chat_clue_repeated",
                "Add a new detail to help your friend.",
                retryable=False,
            )
        options = self.clue_options(content, target, profile)
        remainder = text
        selected = []
        for option in sorted(options, key=lambda row: len(row["text"]), reverse=True):
            remainder, count = re.subn(re.escape(option["text"]), "", remainder, flags=re.I)
            if count:
                selected.append(option)
        reviewed_pieces = not remainder.strip(" .!?\n\t")
        if previous_clues and reviewed_pieces:
            old_facts = {
                option.get("factId")
                for option in options
                if any(_fold(option["text"]) in _fold(old) for old in previous_clues)
            }
            if not any(option.get("factId") not in old_facts for option in selected):
                raise RoomPhotoError(
                    "friend_chat_clue_repeated",
                    "Add a new detail to help your friend.",
                    retryable=False,
                )
        if str(profile.get("proficiency_level")) == "A0":
            if not reviewed_pieces:
                raise RoomPhotoError(
                    "friend_chat_clue_unsupported",
                    "Use the reviewed description pieces for this beginner clue.",
                    retryable=False,
                )
        elif not reviewed_pieces:
            if self.realizer is None:
                raise RoomPhotoError(
                    "friend_chat_clue_check_unavailable",
                    "Free-text clue checking is unavailable. "
                    "Use the reviewed clue pieces or try again.",
                )
            assessment = self.realizer.assess(
                {
                    "targetLanguage": _language(profile).display.language_code,
                    "level": str(profile.get("proficiency_level")),
                    "target": target["term"],
                    "clue": text,
                    "confirmedFacts": self._facts(content, target, profile),
                    "previousClues": list(previous_clues),
                },
                scope=_scope(content),
            )
            if not assessment.get("inTargetLanguage"):
                raise RoomPhotoError(
                    "friend_chat_clue_wrong_language",
                    "Write the clue in your learning language.",
                    retryable=False,
                )
            if assessment.get("revealsAnswer"):
                raise RoomPhotoError(
                    "friend_chat_clue_names_target",
                    "Describe the object without its name or translation.",
                    retryable=False,
                )
            if not assessment.get("grounded"):
                raise RoomPhotoError(
                    "friend_chat_clue_unsupported",
                    "Use details confirmed in this photo or choose a reviewed clue piece.",
                    retryable=False,
                )
            if not assessment.get("addsInformation"):
                raise RoomPhotoError(
                    "friend_chat_clue_repeated",
                    "Add a new detail to help your friend.",
                    retryable=False,
                )
        return text

    def suggest_clue(self, content, target, profile):
        options = self.clue_options(content, target, profile)
        if not options:
            raise RoomPhotoError(
                "friend_chat_no_clue",
                "Choose an object with a clear description or position.",
                retryable=False,
            )
        return " ".join(row["text"] for row in options[:2])

    def private_help(self, content, target, clue, profile):
        options = target.get("clueOptions") or []
        matching = [row for row in options if _fold(row["text"]).strip(".") in _fold(clue)]
        level = str(profile.get("proficiency_level", "A0"))
        facts = self._facts(content, target, profile)
        if self.realizer is not None:
            result = self.realizer.explain(
                {
                    "targetLanguage": _language(profile).display.language_code,
                    "level": level,
                    "clue": clue,
                    "confirmedFacts": [{"meaning": fact["meaning"]} for fact in facts],
                    "knownClueMeanings": [
                        {"text": row["text"], "meaning": row["translation"]} for row in matching
                    ],
                },
                scope=_scope(content),
            )
        else:
            result = {
                "explanation": " ".join(row["translation"] for row in matching)
                or "Listen to the clue and look for the described features or position.",
                "vocabulary": [
                    {"word": row["text"], "meaning": row["translation"]}
                    for row in matching[: 1 if level == "A1" else 8]
                ],
                "hint": None,
            }
        if level == "A0" and not result.get("hint"):
            other = next((row for row in options if row not in matching), None)
            result["hint"] = other["translation"] if other else None
        if level != "A0":
            result["hint"] = None
        result["vocabulary"] = [
            row
            for row in result.get("vocabulary", [])
            if _fold(row["word"]) in _fold(clue)
            and not _names_target(row["word"], target)
            and not _names_target(row["meaning"], target)
        ][: 1 if level == "A1" else 8]
        if _names_target(result["explanation"], target) or (
            result.get("hint") and _names_target(result["hint"], target)
        ):
            raise RoomPhotoError(
                "friend_chat_help_unavailable",
                "Private help could not be prepared safely. Try again.",
            )
        sheets = []
        for option in options:
            if option.get("cheatSheet") and option["cheatSheet"] not in sheets:
                sheets.append(option["cheatSheet"])
        result["cheatsheetRefs"] = [
            {
                "missionCode": sheet["missionId"],
                "level": sheet["practiceLevel"],
                "contentVersion": sheet["contentVersion"],
            }
            for sheet in sheets
        ]
        return result
