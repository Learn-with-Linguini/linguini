"""Reviewed singular preference sentences for A1 roleplay missions."""

from app.services.possessives import (
    _article,
    _gender,
    _korean_particle,
    _name,
    _noun,
    _with_article,
)


def preference_sentence(language, person, name, like, noun, gender):
    """A reviewed singular like/dislike sentence, or None when its form is uncertain."""
    noun = _noun(language, noun, gender)
    if language not in {"es", "fr", "de", "ko"} or noun is None:
        return None
    if person not in {"first", "third"} or not isinstance(like, bool):
        return None
    if person == "third" and _name(name) is None:
        return None
    if language == "es":
        phrase = _with_article(_article(language, noun, gender), noun)
        if person == "first":
            return f"{'Me gusta' if like else 'No me gusta'} {phrase}."
        prefix = "A {} {} gusta".format(name, "le" if like else "no le")
        return f"{prefix} {phrase}."
    if language == "fr":
        article = _article(language, noun, gender)
        phrase = _with_article(article, noun)
        if person == "first":
            verb = "J'aime" if like else "Je n'aime pas"
            return f"{verb} {phrase}."
        verb = "aime" if like else "n'aime pas"
        return f"{name} {verb} {phrase}."
    if language == "de":
        gender = _gender(language, gender)
        article = _article(language, noun, gender)
        phrase = _with_article(article, noun[:1].upper() + noun[1:])
        subject = "Ich" if person == "first" else name
        suffix = "" if like else " nicht"
        return f"{subject} mag {phrase}{suffix}."
    particle = _korean_particle(noun)
    if particle is None:
        return None
    phrase = f"{noun}{particle}"
    if person == "first":
        return f"저는 {phrase}{'' if like else ' 안'} 좋아해요."
    subject = "아나는" if name == "Ana" else "레오는"
    return f"{subject} {phrase}{'' if like else ' 안'} 좋아해요."
