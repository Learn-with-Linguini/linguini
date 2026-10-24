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
        labels = ["cup", "table", "window"]
        return SceneAnalysisResult(
            title="A café table",
            summary="A cup on a table beside a window.",
            objects=[
                SceneObject(
                    id=uuid4(),
                    session_id=session.id,
                    label=label,
                    anchor_point=AnchorPoint(x=(index + 1) / 4, y=0.5),
                    source_object_key=f"object-{index}",
                )
                for index, label in enumerate(labels)
            ],
        )


class Translator:
    def translate(self, payload):
        translations = {"cup": "taza", "table": "mesa", "window": "ventana"}
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
            attributes=[],
            relationships=[],
        )


def test_guest_demo_analyzes_and_translates_without_persistence():
    response = DemoLessonService(Analyzer(), Translator()).analyze(
        DemoPhotoRequest(imageBase64=_image(), targetLanguage="es")
    )

    assert response.title == "A café table"
    assert response.width == 80
    assert response.height == 60
    assert [word.source for word in response.words] == ["cup", "table", "window"]
    assert [word.translation for word in response.words] == [
        "la taza",
        "la mesa",
        "la ventana",
    ]
