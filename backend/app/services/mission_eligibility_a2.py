"""Eligibility rules for A2 missions, based only on learner-confirmed scene facts."""

_SCENE_RELATIONS = {"on", "under", "next_to", "in_front_of", "behind"}


def _label(obj):
    return obj.label.strip().casefold()


def _attrs(obj):
    from app.services.mission_eligibility import confirmed_attributes

    return {(kind, value) for _key, kind, value in confirmed_attributes(obj)}


def _relation_rows(mission, objects, relations):
    from app.services.mission_eligibility import relation_type

    labels = {str(obj.id): _label(obj) for obj in objects}
    allowed = set(mission.photo_requirements.relations) or _SCENE_RELATIONS
    return [
        (str(row.subject_scene_object_id), relation_type(row),
         str(row.reference_scene_object_id))
        for row in relations
        if relation_type(row) in allowed
        and str(row.subject_scene_object_id) in labels
        and str(row.reference_scene_object_id) in labels
        and labels[str(row.subject_scene_object_id)]
        != labels[str(row.reference_scene_object_id)]
    ]


def _describe_scene(objects, relations):
    from app.services.mission_eligibility import confirmed_attributes

    distinct_labels = {
        str(obj.label).strip().casefold() for obj in objects if getattr(obj, "label", None)
    }
    if len(distinct_labels) < 3:
        return ["Confirm at least three scene objects for a description mission."]
    attributes = {
        (str(obj.id), kind, value)
        for obj in objects
        for _key, kind, value in confirmed_attributes(obj)
    }
    relation_facts = {
        (subject, kind, reference)
        for subject, kind, reference in relations
    }
    distinct_labels = {_label(obj) for obj in objects}
    fact_count = len(attributes) + len(relation_facts) + int(len(distinct_labels) >= 3)
    if not (attributes or relation_facts):
        return ["Confirm at least one reviewed attribute or object relation."]
    if fact_count < 2:
        return ["Confirm at least two distinct facts for a short scene description."]
    return []


def _find_target(mission, objects, relations):
    by_id = {str(obj.id): obj for obj in objects}
    rows = relations
    for target_id, target in by_id.items():
        for attribute in _attrs(target):
            for subject_id, relation, reference_id in rows:
                if subject_id != target_id:
                    continue
                matching = [
                    candidate_id for candidate_id, candidate in by_id.items()
                    if attribute in _attrs(candidate)
                    and (candidate_id, relation, reference_id) in rows
                ]
                if len(matching) != 1:
                    continue
                distractors = [
                    candidate_id for candidate_id in by_id
                    if candidate_id != target_id
                    and int(attribute in _attrs(by_id[candidate_id]))
                    + int((candidate_id, relation, reference_id) in rows) <= 1
                ]
                if distractors:
                    return []
    return ["Confirm an object with a reviewed attribute and a relation that uniquely identify it."]


def _compare_quantities(mission, counted_groups):
    from app.services.mission_eligibility import countable_groups

    groups = countable_groups(mission, counted_groups)
    by_label = {}
    for group in groups:
        by_label.setdefault(group["label"].strip().casefold(), []).append(group)
    distinct = [rows[0] for rows in by_label.values()]
    if len(distinct) >= 2 and any(
        left["quantity"] != right["quantity"]
        for index, left in enumerate(distinct)
        for right in distinct[index + 1:]
    ):
        return []
    return ["Confirm two differently named groups with different quantities from 2 to 10."]


def _fictional_ownership(objects, relations):
    relation_rows = set(relations)
    by_id = {str(obj.id): obj for obj in objects}
    for assigned_id, assigned in by_id.items():
        details = [("attribute", item) for item in _attrs(assigned)]
        details.extend(
            ("relation", (kind, reference))
            for subject, kind, reference in relation_rows if subject == assigned_id
        )
        for kind, detail in details:
            alternatives = [
                (candidate_id, candidate) for candidate_id, candidate in by_id.items()
                if candidate_id != assigned_id
                and (
                    _label(candidate) == _label(assigned)
                    if any(
                        other_id != assigned_id
                        and _label(other) == _label(assigned)
                        for other_id, other in by_id.items()
                    )
                    else True
                )
            ]
            for candidate_id, candidate in alternatives:
                shares = (
                    detail in _attrs(candidate)
                    if kind == "attribute"
                    else (candidate_id, detail[0], detail[1]) in relation_rows
                )
                if not shares:
                    return []
    return ["Confirm an object detail that distinguishes it from another photo object."]


def eligibility_reasons(rule, mission, objects, relations, counted_groups):
    rows = _relation_rows(mission, objects, relations)
    if rule == "describeScene":
        return _describe_scene(objects, rows)
    if rule == "findTarget":
        return _find_target(mission, objects, rows)
    if rule == "compareQuantities":
        return _compare_quantities(mission, counted_groups)
    if rule == "fictionalOwnership":
        return _fictional_ownership(objects, rows)
    return []
