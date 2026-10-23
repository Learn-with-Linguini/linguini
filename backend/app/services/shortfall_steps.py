"""Concrete next steps for a scene no mission fits, worded from the learner's own review.

Each step names one kind of fact (``objects``, ``counts``, ``attributes`` or
``relations``) and says exactly what to add, such as "Mark 1 more cup so there
are 2 cups." Steps describe the confirmed facts only; they never guess what else
is in the photo.
"""


from app.services.quantities import english_plural

MAX_NAMED = 3
A0_EXAMPLES = ("cup", "book", "chair", "bottle", "apple", "pen")
REQUESTABLE_EXAMPLES = ("bottle", "apple", "cup")


def _key(label):
    return label.strip().casefold()


def _article(label):
    return f"{'an' if label[:1].casefold() in 'aeiou' else 'a'} {label}"


def _amount(number, label):
    return f"{number} {label if number == 1 else english_plural(label)}"


def _join(items, word="and"):
    items = list(items)
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} {word} {items[-1]}"


def _labels(objects):
    """Distinct confirmed names, in review order."""
    return list(dict.fromkeys(obj.label.strip() for obj in objects if obj.label.strip()))


def _quantities(objects, counted_groups):
    """``key -> (name, quantity)``: markers per name, overridden by confirmed counts."""
    quantities = {}
    for obj in objects:
        name, count = quantities.get(_key(obj.label), (obj.label.strip(), 0))
        quantities[_key(obj.label)] = (name, count + 1)
    for group in counted_groups:
        quantities[_key(group["label"])] = (group["label"].strip(), int(group["quantity"]))
    return quantities


def _count_step(low, high, quantities, allowed=lambda _name: True, example="cup"):
    """The smallest change that brings one named group into ``low``-``high``."""
    best = None
    for name, quantity in quantities.values():
        if not allowed(name):
            continue
        distance = low - quantity if quantity < low else quantity - high
        if distance > 0 and (best is None or distance < best[0]):
            best = (distance, name, quantity)
    if best is None:
        return f"Mark {low} matching objects, such as {_amount(low, example)}."
    distance, name, quantity = best
    if quantity < low:
        return (
            f"Mark {distance} more {name if distance == 1 else english_plural(name)} "
            f"so there are {_amount(low, name)}."
        )
    return (
        f"Remove {distance} {name} marker{'' if distance == 1 else 's'} "
        f"so there are {_amount(high, name)}."
    )


def _objects_step(need, labels):
    have = f" (so far: {_join(labels[:MAX_NAMED])})" if labels else ""
    noun = "object" if need == 1 else "objects"
    return f"Mark {need} more different {noun} you can see{have}."


def _a0_objects_step(objects):
    labels = _labels(objects)
    named = {_key(label) for label in labels}
    examples = [name for name in A0_EXAMPLES if name not in named][:MAX_NAMED]
    need = max(1, 2 - len(named))
    have = f" (so far: {_join(labels[:MAX_NAMED])})" if labels else ""
    return (
        f"Mark {need} more different object{'' if need == 1 else 's'} you can see{have}, "
        f"such as {_join([_article(name) for name in examples], 'or')}."
    )


def _attributes_step(need, objects):
    from app.services.mission_eligibility import confirmed_attributes

    plain = [
        label for label in _labels(objects)
        if not any(confirmed_attributes(obj) for obj in objects if _key(obj.label) == _key(label))
    ]
    adjective = "a colour, size, shape, material, pattern or state"
    if not plain:
        return f"Mark another object and give it {adjective}."
    if need <= 1:
        return f"Give the {plain[0]} {adjective} you can see."
    named = _join([f"the {label}" for label in plain[:need]])
    if len(plain) < need:
        extra = need - len(plain)
        return (
            f"Give {named} {adjective}, then mark {extra} more "
            f"object{'' if extra == 1 else 's'} and describe {'it' if extra == 1 else 'them'} too."
        )
    return f"Give {named} {adjective}."


def _relations_step(labels):
    if len(labels) < 2:
        return "Mark another object, then say where one is, such as on or next to the other."
    return f"Add a connection between two objects, such as “{labels[0]} on {labels[1]}”."


def _compare_step(mission, quantities):
    """A2: two differently named groups with different quantities."""
    low, high = mission.photo_requirements.min_quantity, mission.photo_requirements.max_quantity
    valid = [(name, quantity) for name, quantity in quantities.values() if low <= quantity <= high]
    others = [(name, quantity) for name, quantity in quantities.values() if quantity < low]
    if len(valid) >= 2:
        name, quantity = valid[0]
        target = quantity + 1 if quantity < high else quantity - 1
        verb = "Mark 1 more" if target > quantity else "Remove 1"
        return (
            f"{verb} {name} so there are {_amount(target, name)}; "
            "the two groups need different numbers."
        )
    if len(valid) == 1:
        name, quantity = valid[0]
        target = 3 if quantity == 2 else 2
        if others:
            other, count = others[0]
            more = other if target - count == 1 else english_plural(other)
            return (
                f"Mark {target - count} more {more} so there are {_amount(target, other)} "
                f"next to the {_amount(quantity, name)}."
            )
        return f"Mark {target} of another kind of object, next to the {_amount(quantity, name)}."
    return "Count two kinds of objects with different numbers, such as 2 cups and 3 books."


def mission_steps(mission, objects, relations, counted_groups, kinds):
    """``[{"kind", "text"}]``: what to add for each kind this mission is short of."""
    from app.services.mission_eligibility import confirmed_attributes

    requirements = mission.photo_requirements
    labels = _labels(objects)
    level = str(mission.practice_level)
    rule = requirements.eligibility_rule
    quantities = _quantities(objects, counted_groups)
    steps = []

    def add(kind, text):
        if kind in kinds and text and {"kind": kind, "text": text} not in steps:
            steps.append({"kind": kind, "text": text})

    if level == "A0":
        add("objects", _a0_objects_step(objects))
        add("counts", _count_step(
            requirements.min_quantity, requirements.max_quantity, quantities,
        ))
    else:
        need = max(requirements.min_confirmed_objects, 3 if rule == "describeScene" else 0)
        if len(labels) < need:
            add("objects", _objects_step(need - len(labels), labels))
        if rule == "requestableItem":
            examples = _join([_article(name) for name in REQUESTABLE_EXAMPLES], "or")
            add("objects", "Mark a food, drink or everyday object you could ask for, "
                f"such as {examples}.")
        if rule == "compareQuantities":
            add("counts", _compare_step(mission, quantities))
        elif requirements.min_counted_groups:
            add("counts", _count_step(
                requirements.min_quantity, requirements.max_quantity, quantities,
            ))
        described = {_key(obj.label) for obj in objects if confirmed_attributes(obj)}
        add("attributes", _attributes_step(
            max(1, requirements.min_coloured_objects - len(described)), objects,
        ))
        add("relations", _relations_step(labels))
    return steps
