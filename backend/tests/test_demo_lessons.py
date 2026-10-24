import base64
from io import BytesIO
from uuid import uuid4

from PIL import Image

from app.schemas.demo import DemoPhotoRequest
from app.schemas.media import AnchorPoint, SceneObject
from app.schemas.translation import SceneTranslationResult, TranslatedTerm
from app.services.demo_lessons import DemoLessonService
from app.services.scene_analysis import SceneAnalysisResult


def _image() -> str:
    buffer = BytesIO()
    Image.new("RGB", (80, 60), "orange").save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode()


class Analyzer:
    def analyze_bytes(self, session, _asset, _data):
        labels = ["cup", "table", "window", "chair", "plant", "lamp"]
        return SceneAnalysisResult(
            title="A café table",
            summary="A cup on a table beside a window.",
            objects=[
                SceneObject(
                    id=uuid4(),
                    session_id=session.id,
                    label=label,
                    anchor_point=AnchorPoint(x=(index + 1) / 7, y=0.5),
                    source_object_key=f"object-{index}",
                )
                for index, label in enumerate(labels)
            ],
        )


class Translator:
    def translate(self, payload):
        translations = {
            "cup": "taza",
            "table": "mesa",
            "window": "ventana",
            "chair": "silla",
            "plant": "planta",
        }
        supporting = {
            "red": "rojo",
            "small": "pequeño",
            "bright": "luminoso",
            "next to": "al lado de",
            "in front of": "delante de",
            "behind": "detrás de",
        }
        return SceneTranslationResult(
            objects=[
                TranslatedTerm(
                    key=item["key"],
                    source=item["source"],
                    translation=translations[item["source"]],
                    article="la",
                    gender="feminine",
                    phonetic_text="TAH-sah",
                )
                for item in payload["objects"]
            ],
            attributes=[
                TranslatedTerm(
                    key=item["key"],
                    source=item["source"],
                    translation=supporting[item["source"]],
                )
                for item in payload["attributes"]
            ],
            relationships=[
                TranslatedTerm(
                    key=item["key"],
                    source=item["source"],
                    translation=supporting[item["source"]],
                )
                for item in payload["relationships"]
            ],
        )


def test_guest_demo_analyzes_and_translates_without_persistence():
    response = DemoLessonService(Analyzer(), Translator()).analyze(
        DemoPhotoRequest(imageBase64=_image(), targetLanguage="es")
    )

    assert response.title == "A café table"
    assert response.width == 80
    assert response.height == 60
    assert [word.source for word in response.words] == ["cup", "table", "window", "chair", "plant"]
    assert [word.translation for word in response.words] == [
        "la taza",
        "la mesa",
        "la ventana",
        "la silla",
        "la planta",
    ]
    assert [(term.source, term.translation) for term in response.adjectives] == [
        ("red", "rojo"),
        ("small", "pequeño"),
        ("bright", "luminoso"),
    ]
    assert [(term.source, term.translation) for term in response.prepositions] == [
        ("next to", "al lado de"),
        ("in front of", "delante de"),
        ("behind", "detrás de"),
    ]
