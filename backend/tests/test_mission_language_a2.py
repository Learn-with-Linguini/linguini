from app.services.mission_language_a2 import (
    A2_ENABLED_LANGUAGES,
    comparative,
    existential,
    korean_particle,
    possessive,
    validate_comparative,
    validate_existential,
    validate_korean_counter,
    validate_korean_particle,
    validate_possessive,
)


def test_only_spanish_and_french_are_enabled() -> None:
    assert A2_ENABLED_LANGUAGES == {"es", "fr"}


def test_existential_frames_cover_es_fr_and_de() -> None:
    assert existential("es", "dos", "libros") == "Hay dos libros."
    assert existential("fr", "deux", "livres") == "Il y a deux livres."
    assert existential("de", "zwei", "Bücher") == "Es gibt zwei Bücher."
    assert validate_existential("Hay dos libros.", "es")
    assert validate_existential("Il y a deux livres.", "fr")
    assert validate_existential("Es gibt zwei Bücher.", "de")
    assert existential("ko", "두", "책", "권") == "책이 두 권 있어요."
    assert validate_existential("책이 두 권 있어요.", "ko")
    assert validate_korean_counter("책이 두 권 있어요.", "권")


def test_comparatives_check_direction_in_all_four_languages() -> None:
    cases = [
        ("es", "libros", "tazas", "Hay más libros que tazas.", "Hay menos libros que tazas."),
        (
            "fr",
            "livres",
            "tasses",
            "Il y a plus de livres que de tasses.",
            "Il y a moins de livres que de tasses.",
        ),
        (
            "de",
            "Bücher",
            "Tassen",
            "Es gibt mehr Bücher als Tassen.",
            "Es gibt weniger Bücher als Tassen.",
        ),
        ("ko", "책", "컵", "책이 컵보다 더 많아요.", "책이 컵보다 더 적어요."),
    ]
    for language, subject, reference, greater, lesser in cases:
        assert comparative(language, subject, reference, True) == greater
        assert comparative(language, subject, reference, False) == lesser
        assert validate_comparative(greater, language, greater=True)
        assert validate_comparative(lesser, language, greater=False)
        assert not validate_comparative(lesser, language, greater=True)


def test_possessive_agreement_in_es_fr_de_and_ko() -> None:
    assert possessive("es", "feminine") == "mi"
    assert possessive("es", "masculine", number="plural") == "mis"
    assert possessive("fr", "feminine", noun="tasse") == "ma"
    assert possessive("fr", "feminine", noun="amie") == "mon"
    assert possessive("fr", "masculine", number="plural") == "mes"
    assert possessive("de", "masculine", case="accusative") == "meinen"
    assert possessive("de", "feminine") == "meine"
    assert possessive("ko", "feminine") == "제"
    assert possessive("ko", "feminine", formal=False) == "내"
    assert validate_possessive("ma tasse est rouge", "fr", "feminine", noun="tasse")


def test_korean_particles_follow_batchim() -> None:
    assert korean_particle("책", subject=True) == "이"
    assert korean_particle("사과", subject=True) == "가"
    assert korean_particle("책") == "은"
    assert korean_particle("사과") == "는"
    assert validate_korean_particle("책이 있어요.", "책", subject=True)
    assert validate_korean_particle("사과는 있어요.", "사과")
