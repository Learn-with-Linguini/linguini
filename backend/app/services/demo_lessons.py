"""One stateless photo analysis and translation for the public guest demo."""

import base64
import binascii
from uuid import uuid4

from app.repositories.postgres.workflow import translation_payload
from app.schemas.demo import DemoPhotoRequest, DemoPhotoResponse, DemoTerm, DemoWord
from app.schemas.enums import MediaSource, MediaType
from app.schemas.media import MediaAsset
from app.schemas.sessions import Session
from app.services.image_storage import InvalidImageUpload
from app.services.image_uploads import sanitize_image_upload
from app.services.scene_analysis import SceneAnalysisError, uploaded_scene_title


class DemoLessonError(Exception):
    pass


def _decode_image(value: str) -> bytes:
    encoded = value.split(",", 1)[1] if value.startswith("data:") and "," in value else value
    try:
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidImageUpload("The uploaded image could not be read.") from exc


def _display_translation(article: str | None, word: str) -> str:
    if not article:
        return word
    separator = "" if article.endswith(("'", "’")) else " "
    return f"{article}{separator}{word}"


class DemoLessonService:
    def __init__(self, analyzer, translator) -> None:
        self.analyzer = analyzer
        self.translator = translator

    def analyze(self, request: DemoPhotoRequest) -> DemoPhotoResponse:
        if self.analyzer is None or self.translator is None:
            raise DemoLessonError("The photo demo is temporarily unavailable.")

        clean, mime_type, width, height = sanitize_image_upload(
            _decode_image(request.image_base64)
        )
        demo_id, owner_id, profile_id = uuid4(), uuid4(), uuid4()
        asset = MediaAsset(
            id=uuid4(), owner_user_id=owner_id, media_type=MediaType.IMAGE,
            source=MediaSource.USER_UPLOAD, storage_key=f"guest-demo/{demo_id}",
            mime_type=mime_type, width=width, height=height,
        )
        session = Session(
            id=demo_id, user_id=owner_id, language_profile_id=profile_id,
            scene_media_asset_id=asset.id,
        )
        try:
            analysis = self.analyzer.analyze_bytes(session, asset, clean)
            objects = analysis.objects[:5]
            if len(objects) < 5:
                raise DemoLessonError("Choose a photo with at least five clear objects.")
            object_ids = {item.id for item in objects}
            payload = translation_payload(
                request.target_language, uploaded_scene_title(analysis),
                analysis.summary or "Objects found in a guest photo.", objects,
                [row for row in analysis.relations
                 if row.subject_scene_object_id in object_ids
                 and row.reference_scene_object_id in object_ids],
            )
            existing_attributes = {term["source"].strip().lower() for term in payload["attributes"]}
            existing_relations = {
                term["source"].strip().lower() for term in payload["relationships"]
            }
            for index, source in enumerate(("red", "small", "bright")):
                if source not in existing_attributes:
                    payload["attributes"].append(
                        {"key": f"demo:adjective:{index}", "source": source}
                    )
            for index, source in enumerate(("next to", "in front of", "behind")):
                if source not in existing_relations:
                    payload["relationships"].append(
                        {"key": f"demo:preposition:{index}", "source": source}
                    )
            translated = self.translator.translate(payload)
        except DemoLessonError:
            raise
        except SceneAnalysisError as exc:
            raise DemoLessonError("We couldn't find enough objects in that photo.") from exc
        except Exception as exc:
            raise DemoLessonError("We couldn't prepare this photo lesson.") from exc

        terms = {term.key: term for term in translated.objects}
        words = []
        for item in objects:
            term = terms.get(str(item.id))
            if term is None:
                continue
            words.append(
                DemoWord(
                    id=item.id,
                    source=item.label,
                    translation=_display_translation(term.article, term.translation),
                    article=term.article,
                    gender=term.gender,
                    phonetic_text=term.phonetic_text,
                    bounding_box=item.bounding_box,
                    anchor_point=item.anchor_point,
                )
            )
        if len(words) < 5:
            raise DemoLessonError("We couldn't translate enough objects in that photo.")
        adjectives = _unique_terms(
            [term for term in translated.attributes if not term.key.endswith(":quantity")], 3
        )
        prepositions = _unique_terms(translated.relationships, 3)
        return DemoPhotoResponse(
            id=demo_id, title=uploaded_scene_title(analysis), summary=analysis.summary,
            width=width, height=height, words=words,
            adjectives=adjectives, prepositions=prepositions,
        )


def _unique_terms(terms, limit: int) -> list[DemoTerm]:
    result: list[DemoTerm] = []
    seen: set[tuple[str, str]] = set()
    for term in terms:
        pair = (term.source.strip(), term.translation.strip())
        normalized = (pair[0].lower(), pair[1].lower())
        if not all(pair) or normalized in seen:
            continue
        seen.add(normalized)
        result.append(DemoTerm(source=pair[0], translation=pair[1]))
        if len(result) == limit:
            break
    return result
