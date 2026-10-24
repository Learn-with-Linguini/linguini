"""The M03 A1 lesson task: grading, corrections and shown fields."""



M03_FOCUS = "sayHowMany"






EVALUATIONS = {
    "chooseQuantity": (["say-quantity"], "recognition", ["quantity-matches-photo"]),
    "buildQuantity": (
        ["say-quantity", "plural-noun"],
        "construction",
        ["quantity-matches-photo", "plural-form-correct"],
    ),
    "matchQuantity": (["understand-quantity"], "recognition", ["understands-quantity"]),
}




