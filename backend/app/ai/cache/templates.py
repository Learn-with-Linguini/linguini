"""Precomputed, validated feature results for unchanged curated scenes.

Templates are stored server-only under ``preloaded_scenes.content["generated"]``
with references in ``ReferenceMap`` alias form, so one template applies to
every session of the same scene. A template matches on feature, target
language, prompt/schema/validator variant and a fingerprint of the canonical
payload. Deployment and model are provenance only: a route change does not
make a template stale.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.ai.cache.cache import FeatureVersion, Generated
from app.ai.cache.references import ReferenceMap

logger = logging.getLogger(__name__)

TEMPLATE_ARTIFACT_VERSION = "preloaded-templates.v1"
GENERATED_CONTENT_KEY = "generated"


class TemplateMissing(LookupError):
    """No template matched and the template set does not allow generation."""


def template_variant(version: FeatureVersion) -> str:
    return f"{version.prompt_version}|{version.schema_version}|{version.validator_version}"


def template_fingerprint(version: FeatureVersion, payload: Mapping[str, Any]) -> str:
    material = {
        "feature": version.feature,
        "variant": template_variant(version),
        "payload": ReferenceMap(payload).canonical_payload(payload),
    }
    text = json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass(frozen=True)
class Template:
    feature: str
    language: str
    variant: str
    fingerprint: str
    result: Any
    deployment_id: str
    model: str
    created_at: str

    @property
    def slot(self) -> tuple[str, str, str]:
        return self.feature, self.language, self.variant

    def to_json(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "language": self.language,
            "variant": self.variant,
            "fingerprint": self.fingerprint,
            "result": self.result,
            "provenance": {
                "deploymentId": self.deployment_id,
                "model": self.model,
                "createdAt": self.created_at,
            },
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Template:
        provenance = data["provenance"]
        return cls(
            feature=str(data["feature"]),
            language=str(data["language"]),
            variant=str(data["variant"]),
            fingerprint=str(data["fingerprint"]),
            result=data["result"],
            deployment_id=str(provenance["deploymentId"]),
            model=str(provenance["model"]),
            created_at=str(provenance["createdAt"]),
        )


class TemplateSet:
    """Templates for one or more scene rows.

    ``reuse=False`` ignores matches, ``generate=False`` raises ``TemplateMissing``
    instead of calling a provider, and ``record=True`` keeps every freshly
    validated result as a new template.
    """

    def __init__(
        self,
        templates: Iterable[Template] = (),
        *,
        reuse: bool = True,
        generate: bool = True,
        record: bool = False,
    ) -> None:
        self.reuse = reuse
        self.generate = generate
        self._record = record
        self._templates = {template.slot: template for template in templates}
        self._recorded: list[Template] = []
        self._lock = threading.Lock()

    @classmethod
    def from_content(
        cls, contents: Iterable[Mapping[str, Any] | None], **options: bool
    ) -> TemplateSet:
        templates = []
        for content in contents:
            generated = (content or {}).get(GENERATED_CONTENT_KEY) or {}
            if generated.get("artifactVersion") != TEMPLATE_ARTIFACT_VERSION:
                continue
            for raw in generated.get("templates", []):
                try:
                    templates.append(Template.from_json(raw))
                except (KeyError, TypeError, AttributeError):
                    logger.warning("Skipping a malformed scene template.")
        return cls(templates, **options)

    def __len__(self) -> int:
        return len(self._templates)

    @property
    def templates(self) -> list[Template]:
        with self._lock:
            return sorted(self._templates.values(), key=lambda template: template.slot)

    @property
    def recorded(self) -> list[Template]:
        with self._lock:
            return list(self._recorded)

    def content(self) -> dict[str, Any]:
        return {
            "artifactVersion": TEMPLATE_ARTIFACT_VERSION,
            "templates": [template.to_json() for template in self.templates],
        }

    def lookup(self, version: FeatureVersion, payload: Mapping[str, Any]) -> Any | None:
        """The matching template mapped onto ``payload``'s references, if any."""
        if not self.reuse:
            return None
        slot = (version.feature, str(payload.get("targetLanguage")), template_variant(version))
        with self._lock:
            template = self._templates.get(slot)
        if template is None or template.fingerprint != template_fingerprint(version, payload):
            return None
        return ReferenceMap(payload).from_aliases(template.result)

    def record[T](
        self,
        version: FeatureVersion,
        payload: Mapping[str, Any],
        generated: Generated[T],
        encode: Callable[[T], Any],
    ) -> None:
        if not self._record:
            return
        aliased = ReferenceMap(payload).to_aliases(encode(generated.result))
        if aliased is None:
            return
        template = Template(
            feature=version.feature,
            language=str(payload.get("targetLanguage")),
            variant=template_variant(version),
            fingerprint=template_fingerprint(version, payload),
            result=aliased,
            deployment_id=generated.deployment_id or "",
            model=generated.model or "",
            created_at=datetime.now(UTC).isoformat(),
        )
        with self._lock:
            self._templates[template.slot] = template
            self._recorded.append(template)
