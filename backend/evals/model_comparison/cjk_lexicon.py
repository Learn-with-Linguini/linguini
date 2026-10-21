"""Accepted Japanese and Korean renderings for the CJK translation probe.

Japanese and Korean have no articles or grammatical gender, and the production
translation prompt only claims French and Spanish. These cases measure how
well each model would translate if the app extended the contract; they also
show that the current validator (article required on every object) rejects
every correct Japanese/Korean answer.

Lists are deliberately permissive (kana/kanji spellings, common synonyms).
"""

from __future__ import annotations

ACCEPTED: dict[str, dict[str, tuple[str, ...]]] = {
    "ja": {
        "desk": ("机", "つくえ", "デスク"),
        "chair": ("椅子", "いす", "イス", "チェア"),
        "book": ("本", "ほん", "書籍"),
        "window": ("窓", "まど"),
        "clock": ("時計", "とけい", "掛け時計"),
        "notebook": ("ノート", "帳面", "ノートブック"),
        "apple": ("りんご", "リンゴ", "林檎"),
        "orange": ("オレンジ", "みかん", "ミカン"),
        "egg": ("卵", "たまご", "玉子", "タマゴ"),
        "bread": ("パン",),
        "water bottle": ("水筒", "ペットボトル", "ボトル", "水のボトル", "ウォーターボトル"),
        "wooden": ("木製", "木製の", "木の", "木でできた"),
        "red": ("赤い", "赤", "あかい", "赤色", "赤色の"),
        "on": ("上", "の上", "の上に", "上に"),
        "under": ("下", "の下", "の下に", "下に"),
        "inside": ("中", "の中", "の中に", "中に", "内"),
        "next_to": ("隣", "の隣", "の隣に", "横", "の横に", "そば", "となり"),
    },
    "ko": {
        "desk": ("책상",),
        "chair": ("의자",),
        "book": ("책",),
        "window": ("창문", "창"),
        "clock": ("시계", "벽시계"),
        "notebook": ("공책", "노트"),
        "apple": ("사과",),
        "orange": ("오렌지", "귤"),
        "egg": ("달걀", "계란"),
        "bread": ("빵",),
        "water bottle": ("물병", "생수병", "물통", "워터보틀"),
        "wooden": ("나무", "나무로 된", "나무의", "목제", "목재", "나무로 만든"),
        "red": ("빨간", "빨간색", "빨강", "붉은", "빨간색의"),
        "on": ("위", "위에", "~위에"),
        "under": ("아래", "아래에", "밑", "밑에"),
        "inside": ("안", "안에", "속", "속에"),
        "next_to": ("옆", "옆에"),
    },
}


def accepted(language: str, source: str, returned: str) -> bool:
    candidate = returned.strip().replace(" ", "")
    for option in ACCEPTED[language].get(source, ()):
        option = option.replace(" ", "")
        if candidate == option or (len(option) >= 2 and option in candidate):
            return True
    return False
