"""Precompute language-independent objects for the bundled preloaded scenes.

Runs the configured scene analyzer once per bundled image and stores up to six
distinct English object labels, with bounded repeated instances, markers,
attributes and relations in the image's one ``preloaded_scenes`` row, so the
Scene Analysis review screen opens with suggested objects already on the photo.
Learners' sessions translate them into their target language. Public tasks,
rounds and prompts are placeholders only.

It then generates validated translation, lesson and I-Spy clue templates per
target language through the normal routed services and stores them
server-only under ``content["generated"]``, keyed by target language. A
learner session that accepts the scene unchanged maps them onto its own
references and builds fresh tasks without a model call; anything else uses
normal routed generation. Templates are reused on reruns while scene facts and
prompt/schema/validator versions still match.

Import-safe: all side effects live under ``main()``.

    python -m app.scripts.precompute_preloaded_scenes \
        --dry-run --json out.json --state state.json --report report.json
    python -m app.scripts.precompute_preloaded_scenes \
        --from-json out.json --emit-migration migration.sql
    python -m app.scripts.precompute_preloaded_scenes \
        --reground --reground-fallback-threshold 0.25 \
        --dry-run --json out.json --report report.json
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import sys
import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.ai.cache import GENERATED_CONTENT_KEY
from app.ai.contracts import VisionImage
from app.ai.features.object_grounding import GroundedBox
from app.ai.pool import ProviderPool
from app.ai.registry import (
    build_ispy_clue_generator,
    build_learning_task_generator,
    build_object_grounder,
    build_scene_translator,
    build_uploaded_scene_analyzer,
)
from app.ai.settings import AiFeature, load_ai_settings
from app.database import create_database_engine, read_connection
from app.repositories.postgres.media_assets import media_assets
from app.repositories.postgres.scenes import preloaded_scenes
from app.schemas.media import MediaAsset, SceneObject
from app.schemas.scenes import PreloadedSceneDetail
from app.schemas.sessions import Session
from app.scripts.preloaded_templates import (
    STAGE_FEATURES,
    STAGES,
    CallBudget,
    CallCountingTracer,
    StageOutcome,
    error_code,
    generate_row_templates,
    route_calls,
)
from app.services.image_storage import ImageStorage
from app.services.session_plan import ENGLISH_ARTICLES, strip_english_article

logger = logging.getLogger("precompute_preloaded_scenes")

MAX_OBJECTS = 6
MAX_INSTANCES_PER_LABEL = 10
MAX_PINS = 12
REGROUND_FALLBACK_THRESHOLD = 0.25

SCENE_SLUGS = ("street", "cafe", "market", "bedroom", "kitchen", "park")

def scene_row_id(slug: str) -> UUID:
    """Stable row id shared by the database write and the emitted migration."""
    return uuid5(NAMESPACE_URL, f"linguini:preloaded-scene:{slug}")


def slugify_label(label: str, index: int, taken: set[str]) -> str:
    """ASCII-fold an English label into a unique item id."""
    folded = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-") or f"item-{index}"
    candidate = base
    suffix = 2
    while candidate in taken:
        candidate = f"{base}-{suffix}"
        suffix += 1
    taken.add(candidate)
    return candidate


def box_centre_percent(
    x: float, y: float, width: float, height: float
) -> tuple[float, float]:
    """Return a normalized box centre as clamped 0..100 percentages."""
    return (
        round(min(100.0, max(0.0, (float(x) + float(width) / 2) * 100)), 1),
        round(min(100.0, max(0.0, (float(y) + float(height) / 2) * 100)), 1),
    )


def marker_percent(obj: SceneObject) -> tuple[float, float]:
    """Anchor point or bounding-box centre, as 0..100 percentages."""
    if obj.anchor_point is not None:
        return box_centre_percent(
            obj.anchor_point.x, obj.anchor_point.y, 0, 0
        )
    elif obj.bounding_box is not None:
        box = obj.bounding_box
        return box_centre_percent(box.x, box.y, box.width, box.height)
    else:
        return box_centre_percent(0.5, 0.5, 0, 0)


def _bare_label_key(label: str) -> str:
    normalized = " ".join(label.split())
    if normalized.casefold().startswith(ENGLISH_ARTICLES):
        normalized = strip_english_article(normalized)
    return normalized.casefold()


def assign_instances(
    items: list[dict[str, Any]],
    detections: Mapping[str, list[GroundedBox]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Assign each label's closest detections to its stored markers."""
    updated = [dict(item) for item in items]
    indexed_detections = {
        _bare_label_key(label): boxes
        for label, boxes in detections.items()
    }
    grouped: dict[str, list[int]] = {}
    for index, item in enumerate(items):
        label = _bare_label_key(str(item["translation"]))
        grouped.setdefault(label, []).append(index)

    matched_items: set[int] = set()
    for label, item_indexes in grouped.items():
        boxes = indexed_detections.get(label, [])
        candidates = [
            (
                math.hypot(
                    float(items[item_index]["x"]) - centre_x,
                    float(items[item_index]["y"]) - centre_y,
                ),
                item_index,
                detection_index,
                centre_x,
                centre_y,
            )
            for item_index in item_indexes
            for detection_index, box in enumerate(boxes)
            for centre_x, centre_y in [
                box_centre_percent(box.x, box.y, box.width, box.height)
            ]
        ]
        unused_items = set(item_indexes)
        unused_detections = set(range(len(boxes)))
        while unused_items and unused_detections:
            available = [
                candidate
                for candidate in candidates
                if candidate[1] in unused_items and candidate[2] in unused_detections
            ]
            if not available:
                break
            _, item_index, detection_index, centre_x, centre_y = min(
                available, key=lambda candidate: candidate[:3]
            )
            updated[item_index]["x"] = centre_x
            updated[item_index]["y"] = centre_y
            matched_items.add(item_index)
            unused_items.remove(item_index)
            unused_detections.remove(detection_index)

    ungrounded = [
        str(item["id"])
        for index, item in enumerate(items)
        if index not in matched_items
    ]
    return updated, ungrounded


def reground_row(
    row: dict[str, Any],
    image: VisionImage,
    grounder,
    *,
    fallback_threshold: float = REGROUND_FALLBACK_THRESHOLD,
) -> tuple[dict[str, Any], list[str]]:
    """Recompute stored item markers while retaining the row's scene facts."""
    media_asset = (
        row.get("media_asset")
        or row.get("asset")
        or row.get("mediaAsset")
    )
    if media_asset is None:
        raise ValueError("regrounding requires the row's media asset")
    content = row["content"]
    items = [
        {**item, "translation": strip_english_article(item["translation"])}
        for item in content["items"]
    ]
    labels = []
    seen_labels = set()
    for item in items:
        key = item["translation"].casefold()
        if key not in seen_labels:
            labels.append(item["translation"])
            seen_labels.add(key)
    detections: dict[str, list[GroundedBox]] = {}
    for label in labels:
        for detected_label, boxes in grounder.ground_instances(
            image, [label]
        ).items():
            detections.setdefault(detected_label, []).extend(boxes)
    assigned, ungrounded = assign_instances(items, detections)
    ungrounded_set = set(ungrounded)
    still_ungrounded = set(ungrounded)
    for label in labels:
        label_key = _bare_label_key(label)
        unmatched_items = [
            item
            for item in assigned
            if item["id"] in ungrounded_set
            and _bare_label_key(item["translation"]) == label_key
        ]
        if not unmatched_items:
            continue
        fallback = grounder.ground_instances(
            image, [label], threshold=fallback_threshold
        )
        fallback_boxes = [
            box
            for detected_label, boxes in fallback.items()
            if _bare_label_key(detected_label) == label_key
            for box in boxes
        ]
        assigned_markers = [
            (float(item["x"]), float(item["y"]))
            for item in assigned
            if item["id"] not in ungrounded_set
            and _bare_label_key(item["translation"]) == label_key
        ]
        fallback_boxes = [
            box
            for box in fallback_boxes
            if all(
                math.hypot(centre_x - marker_x, centre_y - marker_y) > 3.0
                for centre_x, centre_y in [
                    box_centre_percent(box.x, box.y, box.width, box.height)
                ]
                for marker_x, marker_y in assigned_markers
            )
        ]
        fallback_assigned, fallback_ungrounded = assign_instances(
            unmatched_items, {label: fallback_boxes}
        )
        fallback_ungrounded_set = set(fallback_ungrounded)
        for item in fallback_assigned:
            if item["id"] not in fallback_ungrounded_set:
                still_ungrounded.discard(item["id"])
                target = next(
                    stored for stored in assigned if stored["id"] == item["id"]
                )
                target["x"] = item["x"]
                target["y"] = item["y"]
    ungrounded = [
        str(item["id"])
        for item in items
        if str(item["id"]) in still_ungrounded
    ]
    updated_content = build_scene_content(
        slug=row["slug"],
        title=row["title"],
        description=row["description"],
        difficulty=row["difficulty"],
        media_asset=media_asset,
        items=assigned,
        relations=content.get("relations", []),
    )
    if GENERATED_CONTENT_KEY in content:
        updated_content[GENERATED_CONTENT_KEY] = content[GENERATED_CONTENT_KEY]
    updated_row = {
        key: value
        for key, value in row.items()
        if key not in {"media_asset", "asset", "mediaAsset"}
    }
    updated_row["content"] = updated_content
    return updated_row, ungrounded


def select_objects(
    objects: list[SceneObject],
    *,
    max_labels: int = MAX_OBJECTS,
    max_per_label: int = MAX_INSTANCES_PER_LABEL,
    max_total: int = MAX_PINS,
) -> list[SceneObject]:
    """Keep a breadth-first set of labels, then bounded instances in analyzer order."""
    chosen_labels: set[str] = set()
    selected: dict[int, tuple[SceneObject, str]] = {}
    counts: dict[str, int] = {}
    for index, obj in enumerate(objects):
        key = obj.label.casefold().strip()
        if not key or key in chosen_labels:
            continue
        if len(chosen_labels) >= max_labels or len(selected) >= max_total:
            break
        chosen_labels.add(key)
        selected[index] = (obj, key)
        counts[key] = 1

    for index, obj in enumerate(objects):
        key = obj.label.casefold().strip()
        if (
            index in selected
            or not key
            or key not in chosen_labels
            or len(selected) >= max_total
        ):
            continue
        count = counts.get(key, 0)
        if count >= max_per_label:
            continue
        counts[key] = count + 1
        selected[index] = (obj, key)

    kept = []
    for index in sorted(selected):
        obj, key = selected[index]
        attributes = dict(obj.attributes or {})
        count = counts[key]
        if count > 1:
            attributes["quantity"] = str(count)
        else:
            attributes.pop("quantity", None)
        kept.append(
            obj.model_copy(
                update={
                    "attributes": (
                        attributes
                        if obj.attributes is not None or count > 1
                        else None
                    )
                }
            )
        )
    return kept


def placeholder_activities(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Minimal placeholder activities; the runtime regenerates real tasks."""
    first = items[0]
    return {
        "tasks": [
            {
                "id": "words",
                "kind": "word",
                "title": "Words in this scene",
                "summary": "Suggested words for this photo.",
                "xp": 8,
                "itemIds": [item["id"] for item in items],
                "note": None,
            }
        ],
        "rounds": [
            {
                "id": "round-1",
                "clue": first["translation"],
                "clueTranslation": first["translation"],
                "answerId": first["id"],
                "choices": [
                    {"id": item["id"], "label": item["translation"]}
                    for item in items[:4]
                ],
                "encouragement": "Keep looking closely!",
            }
        ],
        "prompts": [
            {
                "id": "prompt-1",
                "itemId": first["id"],
                "suggestions": [],
                "llmGuess": "",
                "feedback": "",
            }
        ],
    }


def build_items(objects: list[SceneObject]) -> list[dict[str, Any]]:
    """Assemble one language-independent scene item per object, in analyzer order."""
    items: list[dict[str, Any]] = []
    taken: set[str] = set()
    for index, obj in enumerate(objects, start=1):
        x, y = marker_percent(obj)
        translation = strip_english_article(obj.label)
        items.append(
            {
                "id": slugify_label(translation, index, taken),
                "translation": translation,
                "wordClass": "noun",
                "marker": index,
                "x": x,
                "y": y,
                "attributes": {
                    key: value for key, value in (obj.attributes or {}).items()
                    if isinstance(value, str) and value.strip()
                },
            }
        )
    return items


def build_scene_content(
    *,
    slug: str,
    title: str,
    description: str | None,
    difficulty: str,
    media_asset: MediaAsset | dict[str, Any],
    items: list[dict[str, Any]],
    relations: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Validate a full scene row; return the stored content payload."""
    detail = PreloadedSceneDetail.model_validate(
        {
            "sceneId": slug,
            "title": title,
            "description": description,
            "difficulty": difficulty,
            "mediaAsset": media_asset,
            "items": items,
            "relations": relations or [],
            **placeholder_activities(items),
        }
    )
    return detail.model_dump(
        mode="json", by_alias=True, include={"items", "tasks", "rounds", "prompts", "relations"}
    )


def _synthetic_session(slug: str, asset: MediaAsset) -> Session:
    return Session(
        user_id=uuid5(NAMESPACE_URL, f"linguini:preloaded-scene-user:{slug}"),
        language_profile_id=uuid5(
            NAMESPACE_URL, f"linguini:preloaded-scene-profile:{slug}"
        ),
        scene_media_asset_id=asset.id,
    )


def _load_base_scenes(engine, slugs: list[str]) -> list[dict[str, Any]]:
    with read_connection(engine) as connection:
        rows = (
            connection.execute(
                select(
                    preloaded_scenes,
                    *[
                        column.label(f"asset_{column.name}")
                        for column in media_assets.c
                    ],
                )
                .select_from(
                    preloaded_scenes.join(
                        media_assets,
                        media_assets.c.id == preloaded_scenes.c.media_asset_id,
                    )
                )
                .where(preloaded_scenes.c.slug.in_(slugs))
                .order_by(preloaded_scenes.c.sort_order, preloaded_scenes.c.slug)
            )
            .mappings()
            .all()
        )
    bases = []
    for row in rows:
        asset = MediaAsset.model_validate(
            {column.name: row[f"asset_{column.name}"] for column in media_assets.c}
        )
        bases.append(
            {
                "id": row["id"],
                "slug": row["slug"],
                "title": row["title"],
                "description": row["description"],
                "difficulty": row["difficulty"],
                "sort_order": row["sort_order"],
                "media_asset_id": row["media_asset_id"],
                "content": row["content"],
                "is_active": row["is_active"],
                "asset": asset,
            }
        )
    return bases


def _load_stored_rows(
    engine, slugs: list[str]
) -> tuple[list[dict[str, Any]], list[MediaAsset]]:
    bases = _load_base_scenes(engine, slugs)
    missing = [slug for slug in slugs if slug not in {base["slug"] for base in bases}]
    if missing:
        raise RuntimeError(f"stored scenes not found in the database: {missing}")
    rows = [
        {
            "id": base["id"],
            "slug": base["slug"],
            "media_asset_id": base["media_asset_id"],
            "title": base["title"],
            "description": base["description"],
            "difficulty": base["difficulty"],
            "content": base["content"],
            "sort_order": base["sort_order"],
            "is_active": base["is_active"],
        }
        for base in bases
    ]
    return rows, [base["asset"] for base in bases]


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


_MIGRATION_COLUMNS = (
    "id",
    "slug",
    "media_asset_id",
    "title",
    "description",
    "difficulty",
    "content",
    "sort_order",
    "is_active",
    "created_at",
    "updated_at",
)

_MIGRATION_UPDATE = (
    "content",
    "media_asset_id",
    "title",
    "description",
    "difficulty",
    "sort_order",
    "is_active",
)


def emit_migration_sql(rows: list[dict[str, Any]]) -> str:
    """Render rows as an idempotent INSERT ... ON CONFLICT migration body."""
    lines = [
        "-- Precomputed suggested scene vocabulary (items only; tasks, rounds and",
        "-- prompts are placeholders regenerated at runtime). Reuses existing media assets.",
        "BEGIN;",
        "",
    ]
    updates = ", ".join(
        f"{column} = EXCLUDED.{column}" for column in _MIGRATION_UPDATE
    )
    for row in rows:
        values = []
        for column in _MIGRATION_COLUMNS:
            if column in ("created_at", "updated_at"):
                values.append("now()")
            elif column == "content":
                text = json.dumps(row["content"], ensure_ascii=False)
                values.append(f"'{text.replace(chr(39), chr(39) * 2)}'::jsonb")
            else:
                values.append(_sql_literal(row[column]))
        lines.append(
            "INSERT INTO public.preloaded_scenes ("
            + ", ".join(_MIGRATION_COLUMNS)
            + ") VALUES (\n    "
            + ", ".join(values)
            + f"\n) ON CONFLICT (slug) DO UPDATE SET {updates}, updated_at = now();\n"
        )
    lines.append("COMMIT;")
    return "\n".join(lines)


def _artifact_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(row["id"]),
            "slug": row["slug"],
            "title": row["title"],
            "description": row["description"],
            "difficulty": row["difficulty"],
            "sortOrder": row["sort_order"],
            "mediaAssetId": str(row["media_asset_id"]),
            "content": row["content"],
        }
        for row in rows
    ]


def write_json_artifact(
    path: Path, rows: list[dict[str, Any]], assets: list[MediaAsset]
) -> None:
    document = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "rows": _artifact_rows(rows),
        "mediaAssets": [
            asset.model_dump(mode="json", by_alias=True) for asset in assets
        ],
    }
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2))


def load_json_artifact(
    path: Path,
) -> tuple[list[dict[str, Any]], dict[UUID, MediaAsset], int]:
    """Load rows and re-validate every one through PreloadedSceneDetail."""
    document = json.loads(path.read_text())
    assets = {
        UUID(asset["id"]): MediaAsset.model_validate(asset)
        for asset in document["mediaAssets"]
    }
    rows = []
    failures = 0
    for raw in document["rows"]:
        row = {
            "id": UUID(raw["id"]),
            "slug": raw["slug"],
            "title": raw["title"],
            "description": raw["description"],
            "difficulty": raw["difficulty"],
            "sort_order": raw["sortOrder"],
            "media_asset_id": UUID(raw["mediaAssetId"]),
            "is_active": True,
            "content": raw["content"],
        }
        asset = assets.get(row["media_asset_id"])
        try:
            if asset is None:
                raise ValueError("unknown mediaAssetId")
            PreloadedSceneDetail.model_validate(
                {
                    **{
                        key: value
                        for key, value in row["content"].items()
                        if key != GENERATED_CONTENT_KEY
                    },
                    "sceneId": row["slug"],
                    "title": row["title"],
                    "description": row["description"],
                    "difficulty": row["difficulty"],
                    "mediaAsset": asset,
                }
            )
        except (ValueError, ValidationError) as error:
            failures += 1
            logger.error("row %s failed validation: %s", row["slug"], error)
            continue
        rows.append(row)
    return rows, assets, failures


def _compute_rows(
    engine,
    settings,
    slugs: list[str],
    *,
    tracer: CallCountingTracer,
    budget: CallBudget,
    outcomes: list[StageOutcome],
    done: frozenset[str] = frozenset(),
    checkpoint=None,
) -> tuple[list[dict[str, Any]], list[MediaAsset], int]:
    """Analyze and build one row per scene missing from ``done``.

    A base starts only when its worst-case call count fits ``budget``.
    ``checkpoint(rows, assets)`` runs after each base.
    """
    storage = ImageStorage(
        os.getenv("SUPABASE_URL", "").strip(),
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
    )
    pool = ProviderPool.from_settings(settings)
    grounder = build_object_grounder(settings)
    analyzer = build_uploaded_scene_analyzer(
        settings,
        storage,
        tracer,
        object_grounder=grounder,
        pool=pool,
    )
    if analyzer is None:
        raise RuntimeError(
            "sceneAnalysis is not configured; enable routes.sceneAnalysis in the "
            "AI config file and set its credential's API key."
        )
    analysis_calls = route_calls(settings, AiFeature.SCENE_ANALYSIS) + (1 if grounder else 0)

    bases = _load_base_scenes(engine, slugs)
    missing = [slug for slug in slugs if slug not in {base["slug"] for base in bases}]
    if missing:
        raise RuntimeError(f"base scenes not found in the database: {missing}")

    rows: list[dict[str, Any]] = []
    assets: list[MediaAsset] = []
    failures = 0
    for base in bases:
        if base["slug"] in done:
            continue
        asset = base["asset"]
        assets.append(asset)

        def report(stage, status, reason, base=base):
            outcomes.append(StageOutcome(base["slug"], "", stage, status, reason))

        if not budget.allows(analysis_calls):
            report("analysis", "missing", "callBudget")
            continue
        session = _synthetic_session(base["slug"], asset)
        try:
            analysis = analyzer.analyze(session, asset, {}, None)
        except Exception as error:
            failures += 1
            logger.error("%s: analysis failed: %s", base["slug"], error_code(error))
            report("analysis", "failed", error_code(error))
            continue
        finally:
            if grounder:
                budget.add_unrouted(1)
        objects = select_objects(analysis.objects)
        if not objects:
            failures += 1
            logger.error("%s: analysis returned no objects", base["slug"])
            report("analysis", "failed", "noObjects")
            continue
        try:
            items = build_items(objects)
            item_ids = {str(obj.id): item["id"] for obj, item in zip(objects, items, strict=True)}
            relations = [
                {
                    "subjectItemId": item_ids[str(relation.subject_scene_object_id)],
                    "relation": relation.relation,
                    "referenceItemId": item_ids[str(relation.reference_scene_object_id)],
                }
                for relation in analysis.relations
                if str(relation.subject_scene_object_id) in item_ids
                and str(relation.reference_scene_object_id) in item_ids
            ]
            content = build_scene_content(
                slug=base["slug"],
                title=base["title"],
                description=base["description"],
                difficulty=base["difficulty"],
                media_asset=asset,
                items=items,
                relations=relations,
            )
        except Exception as error:
            failures += 1
            logger.error("%s failed: %s", base["slug"], error_code(error))
            report("analysis", "failed", error_code(error))
            continue
        rows.append(
            {
                "id": base["id"],
                "slug": base["slug"],
                "media_asset_id": asset.id,
                "title": base["title"],
                "description": base["description"],
                "difficulty": base["difficulty"],
                "content": content,
                "sort_order": base["sort_order"],
                "is_active": True,
            }
        )
        logger.info("%s: %d objects", base["slug"], len(objects))
        if checkpoint is not None:
            checkpoint(rows, assets)
    return rows, assets, failures


def _template_services(settings, tracer) -> dict[str, Any]:
    pool = ProviderPool.from_settings(settings)
    return {
        "translation": build_scene_translator(settings, tracer, pool=pool),
        "lessons": build_learning_task_generator(settings, tracer, pool=pool),
        "clues": build_ispy_clue_generator(settings, tracer, pool=pool),
    }


def write_report(
    path: Path, outcomes: list[StageOutcome], budget: CallBudget, *, dry_run: bool
) -> None:
    """A JSON report of every stage outcome: statuses and codes only."""
    summary: dict[str, int] = {}
    for outcome in outcomes:
        summary[outcome.status] = summary.get(outcome.status, 0) + 1
    document = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "dryRun": dry_run,
        "maxProviderCalls": budget.limit,
        "providerCalls": budget.used,
        "summary": summary,
        "outcomes": [outcome.to_json() for outcome in outcomes],
    }
    path.write_text(json.dumps(document, indent=2))


def _write_rows(engine, rows: list[dict[str, Any]]) -> None:
    now = datetime.now(UTC)
    with engine.begin() as connection:
        for row in rows:
            connection.execute(
                insert(preloaded_scenes)
                .values(
                    **row,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    index_elements=["slug"],
                    set_={
                        "content": row["content"],
                        "media_asset_id": row["media_asset_id"],
                        "title": row["title"],
                        "description": row["description"],
                        "difficulty": row["difficulty"],
                        "sort_order": row["sort_order"],
                        "is_active": row["is_active"],
                        "updated_at": now,
                    },
                )
            )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--slug",
        action="append",
        dest="slugs",
        help="scene slug (repeatable; default: all bundled scenes)",
    )
    parser.add_argument(
        "--language",
        action="append",
        dest="languages",
        help=(
            "template target language with a ready pack (repeatable; default: every "
            "released pack language)"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="compute and validate rows without writing to the database",
    )
    parser.add_argument(
        "--json",
        type=Path,
        metavar="PATH",
        help="dump the computed rows and media assets to a JSON file",
    )
    parser.add_argument(
        "--from-json",
        type=Path,
        metavar="PATH",
        help=(
            "load previously computed rows instead of analyzing scenes; templates "
            "are only checked unless --max-provider-calls is given"
        ),
    )
    parser.add_argument(
        "--state",
        type=Path,
        metavar="PATH",
        help="resumable progress file, saved after each scene; rows in it are not recomputed",
    )
    parser.add_argument(
        "--report",
        type=Path,
        metavar="PATH",
        help="write a JSON report of every stage outcome (statuses and error codes only)",
    )
    parser.add_argument(
        "--max-provider-calls",
        type=int,
        metavar="N",
        help="hard cap on outbound model calls for the whole run; 0 only checks templates",
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=STAGES,
        help="template stages allowed to call a provider (repeatable; default: all)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="regenerate the selected templates even when they still match",
    )
    parser.add_argument(
        "--skip-templates",
        action="store_true",
        help="do not check or generate lesson and clue templates",
    )
    parser.add_argument(
        "--reground",
        action="store_true",
        help=(
            "recompute stored item marker positions with the object grounder, "
            "without scene analysis"
        ),
    )
    parser.add_argument(
        "--reground-fallback-threshold",
        type=float,
        default=REGROUND_FALLBACK_THRESHOLD,
        help=(
            "Grounding DINO threshold for a second pass on items missed by "
            f"the primary pass (default: {REGROUND_FALLBACK_THRESHOLD})"
        ),
    )
    parser.add_argument(
        "--emit-migration",
        type=Path,
        metavar="PATH",
        help="write an INSERT ... ON CONFLICT migration.sql for the rows",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env.local"),
        help="dotenv file loaded before reading settings (default: .env.local)",
    )
    return parser.parse_args(argv)


def template_languages(requested, discovered):
    """The languages that get templates: ``requested``, each with a ready pack, or by
    default every released (non-experimental) pack language.

    An experimental pack is used only when asked for by name, so a local experiment
    never writes templates for it by default.
    """
    ready = {language["code"]: language for language in discovered}
    if requested:
        unknown = sorted({code for code in requested if code not in ready})
        if unknown:
            raise ValueError(f"no ready language pack for {', '.join(unknown)}")
        return list(dict.fromkeys(requested))
    return sorted(code for code, language in ready.items() if not language["experimental"])


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")

    env_file = args.env_file
    if env_file is not None and env_file.exists():
        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)

    if args.max_provider_calls is not None and args.max_provider_calls < 0:
        logger.error("--max-provider-calls must be 0 or more")
        return 2
    slugs = args.slugs or list(SCENE_SLUGS)
    from app.language_packs.runtime import available_pack_languages

    try:
        languages = template_languages(args.languages, available_pack_languages())
    except ValueError as error:
        logger.error("%s", error)
        return 2
    if not languages and not args.skip_templates:
        logger.warning("no released language pack is ready; no templates will be made")

    def wanted(row):
        return row["slug"] in slugs

    settings = load_ai_settings()
    tracer = CallCountingTracer()
    limit = args.max_provider_calls
    if limit is None and args.from_json:
        limit = 0
    budget = CallBudget(limit, tracer)
    outcomes: list[StageOutcome] = []
    saved: dict[str, dict[str, Any]] = {}
    assets_by_id: dict[UUID, MediaAsset] = {}
    if args.state and args.state.exists() and not args.reground:
        state_rows, state_assets, _ = load_json_artifact(args.state)
        saved = {row["slug"]: row for row in state_rows if wanted(row)}
        assets_by_id.update(state_assets)
        logger.info("resuming %d rows from %s", len(saved), args.state)

    def checkpoint(rows):
        if args.state:
            write_json_artifact(args.state, rows, list(assets_by_id.values()))

    engine = None
    if args.from_json:
        rows, loaded_assets, failures = load_json_artifact(args.from_json)
        rows = [
            row if args.reground else saved.get(row["slug"], row)
            for row in rows
            if wanted(row)
        ]
        assets_by_id.update(loaded_assets)
    else:
        engine = create_database_engine()
        if args.reground:
            rows, loaded_assets = _load_stored_rows(engine, slugs)
            failures = 0
            assets_by_id.update({asset.id: asset for asset in loaded_assets})
        else:
            kept = list(saved.values())

            def save_computed(computed, computed_assets):
                assets_by_id.update({asset.id: asset for asset in computed_assets})
                checkpoint(kept + computed)

            computed, computed_assets, failures = _compute_rows(
                engine,
                settings,
                slugs,
                tracer=tracer,
                budget=budget,
                outcomes=outcomes,
                done=frozenset(saved),
                checkpoint=save_computed,
            )
            assets_by_id.update({asset.id: asset for asset in computed_assets})
            rows = kept + computed

    if args.reground:
        try:
            grounder = build_object_grounder(settings)
        except Exception as error:
            logger.error("--reground requires an available object grounder: %s", error_code(error))
            return 2
        if grounder is None or not callable(getattr(grounder, "ground_instances", None)):
            logger.error(
                "--reground requires a configured object grounder with ground_instances"
            )
            return 2
        storage = ImageStorage(
            os.getenv("SUPABASE_URL", "").strip(),
            os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
        )
        regrounded_rows = []
        for row in rows:
            try:
                asset = assets_by_id[row["media_asset_id"]]
                image = VisionImage(
                    data=storage.download(asset.storage_key),
                    mime_type=asset.mime_type,
                )
                regrounded, ungrounded = reground_row(
                    {**row, "media_asset": asset},
                    image,
                    grounder,
                    fallback_threshold=args.reground_fallback_threshold,
                )
            except Exception as error:
                failures += 1
                reason = error_code(error)
                logger.error("%s: grounding failed: %s", row["slug"], reason)
                outcomes.append(
                    StageOutcome(row["slug"], "", "grounding", "failed", reason)
                )
                continue
            for old, new in zip(
                row["content"]["items"],
                regrounded["content"]["items"],
                strict=True,
            ):
                logger.info(
                    "%s item %s: (%s, %s) -> (%s, %s)",
                    row["slug"],
                    old["id"],
                    old["x"],
                    old["y"],
                    new["x"],
                    new["y"],
                )
            reason = f"ungrounded:{len(ungrounded)}" if ungrounded else None
            if ungrounded:
                logger.warning(
                    "%s: ungrounded items kept at prior markers: %s",
                    row["slug"],
                    ", ".join(ungrounded),
                )
            outcomes.append(
                StageOutcome(row["slug"], "", "grounding", "generated", reason)
            )
            regrounded_rows.append(regrounded)
            checkpoint(regrounded_rows)
        rows = regrounded_rows
    assets = list(assets_by_id.values())

    if not args.skip_templates:
        services = _template_services(settings, tracer)
        reserve = {
            stage: route_calls(settings, feature) for stage, feature in STAGE_FEATURES.items()
        }
        for row in rows:
            for language in languages:
                outcomes.extend(
                    generate_row_templates(
                        row,
                        language,
                        services,
                        budget,
                        reserve,
                        stages=frozenset(args.only or STAGES),
                        force=args.force,
                    )
                )
            checkpoint(rows)
    logger.info("provider calls: %d", budget.used)
    if args.report:
        write_report(args.report, outcomes, budget, dry_run=args.dry_run)
        logger.info("wrote report to %s", args.report)
    failures += sum(outcome.status == "failed" for outcome in outcomes)

    if args.json:
        write_json_artifact(args.json, rows, assets)
        logger.info("wrote %d rows to %s", len(rows), args.json)
    if args.emit_migration:
        args.emit_migration.write_text(emit_migration_sql(rows))
        logger.info("wrote migration SQL to %s", args.emit_migration)
    if not args.dry_run:
        if args.from_json:
            engine = create_database_engine()
        if engine is None:
            engine = create_database_engine()
        _write_rows(engine, rows)
        logger.info("upserted %d rows", len(rows))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
