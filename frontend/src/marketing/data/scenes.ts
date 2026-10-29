import type { Scene } from "./types";

/**
 * Demo scenes for the landing page's "try it" session. Marker positions are
 * percentages of the photo and were checked against annotated renders.
 * IPA is a broad transcription of the noun without its article.
 */
export const scenes: Scene[] = [
  {
    "id": "hillside-street",
    "photo": "/photos/hillside-street.jpg",
    "title": "Hillside drive",
    "place": "A steep city street",
    "width": 1570,
    "height": 1047,
    "alt": "Winding red-brick street lined with flowering hydrangea hedges, pastel hillside houses and a red car in warm evening light",
    "words": [
      {
        "id": "car",
        "en": "car",
        "x": 47,
        "y": 62,
        "es": {
          "word": "el coche",
          "gender": "masculine",
          "ipa": "ˈkotʃe"
        },
        "fr": {
          "word": "la voiture",
          "gender": "feminine",
          "ipa": "vwatyʁ"
        },
        "de": {
          "word": "das Auto",
          "gender": "neuter",
          "ipa": "ˈaʊ̯to"
        },
        "ko": {
          "word": "차",
          "gender": "none",
          "ipa": "tɕʰa"
        }
      },
      {
        "id": "house",
        "en": "house",
        "x": 58,
        "y": 33,
        "es": {
          "word": "la casa",
          "gender": "feminine",
          "ipa": "ˈkasa"
        },
        "fr": {
          "word": "la maison",
          "gender": "feminine",
          "ipa": "mɛzɔ̃"
        },
        "de": {
          "word": "das Haus",
          "gender": "neuter",
          "ipa": "haʊ̯s"
        },
        "ko": {
          "word": "집",
          "gender": "none",
          "ipa": "tɕip"
        }
      },
      {
        "id": "tree",
        "en": "tree",
        "x": 84,
        "y": 52,
        "es": {
          "word": "el árbol",
          "gender": "masculine",
          "ipa": "ˈaɾbol"
        },
        "fr": {
          "word": "l’arbre",
          "gender": "masculine",
          "ipa": "aʁbʁ"
        },
        "de": {
          "word": "der Baum",
          "gender": "masculine",
          "ipa": "baʊ̯m"
        },
        "ko": {
          "word": "나무",
          "gender": "none",
          "ipa": "na.mu"
        }
      },
      {
        "id": "flower",
        "en": "flower",
        "x": 18,
        "y": 66,
        "es": {
          "word": "la flor",
          "gender": "feminine",
          "ipa": "floɾ"
        },
        "fr": {
          "word": "la fleur",
          "gender": "feminine",
          "ipa": "flœʁ"
        },
        "de": {
          "word": "die Blume",
          "gender": "feminine",
          "ipa": "ˈbluːmə"
        },
        "ko": {
          "word": "꽃",
          "gender": "none",
          "ipa": "k͈ot̚"
        }
      },
      {
        "id": "street",
        "en": "street",
        "x": 50,
        "y": 86,
        "es": {
          "word": "la calle",
          "gender": "feminine",
          "ipa": "ˈkaʎe"
        },
        "fr": {
          "word": "la rue",
          "gender": "feminine",
          "ipa": "ʁy"
        },
        "de": {
          "word": "die Straße",
          "gender": "feminine",
          "ipa": "ˈʃtʁaːsə"
        },
        "ko": {
          "word": "길",
          "gender": "none",
          "ipa": "kil"
        }
      }
    ],
    "ispy": {
      "es": {
        "clue": "Veo, veo… algo que es rojo y tiene cuatro ruedas.",
        "clueEn": "I spy… something that is red and has four wheels.",
        "answer": "el coche",
        "choices": [
          "la casa",
          "el coche",
          "el árbol",
          "la calle"
        ]
      },
      "fr": {
        "clue": "Je vois, je vois… quelque chose qui est rouge et qui a quatre roues.",
        "clueEn": "I spy… something that is red and has four wheels.",
        "answer": "la voiture",
        "choices": [
          "la maison",
          "l’arbre",
          "la voiture",
          "la rue"
        ]
      },
      "de": {
        "clue": "Ich sehe was, was du nicht siehst: etwas, das rot ist und vier Räder hat.",
        "clueEn": "I spy… something that is red and has four wheels.",
        "answer": "das Auto",
        "choices": [
          "das Haus",
          "das Auto",
          "der Baum",
          "die Straße"
        ]
      },
      "ko": {
        "clue": "빨간색이고 바퀴가 네 개 있는 것이 보여요.",
        "clueEn": "I spy… something that is red and has four wheels.",
        "answer": "차",
        "choices": [
          "집",
          "차",
          "나무",
          "길"
        ]
      }
    },
    "blankWordId": "flower",
    "blank": {
      "es": {
        "sentence": "Hay muchas ___ al lado de la calle.",
        "en": "There are lots of flowers beside the street.",
        "answer": "flores",
        "options": [
          "flor",
          "flores"
        ]
      },
      "fr": {
        "sentence": "Il y a beaucoup de ___ au bord de la rue.",
        "en": "There are lots of flowers along the street.",
        "answer": "fleurs",
        "options": [
          "fleurs",
          "fleur"
        ]
      },
      "de": {
        "sentence": "Es gibt viele ___ an der Straße.",
        "en": "There are lots of flowers beside the street.",
        "answer": "Blumen",
        "options": [
          "Blume",
          "Blumen"
        ]
      },
      "ko": {
        "sentence": "길가에 ___이 많이 피어 있어요.",
        "en": "There are lots of flowers beside the street.",
        "answer": "꽃",
        "options": [
          "꽃",
          "나무"
        ]
      }
    },
    "build": {
      "es": {
        "en": "The red car is on the street.",
        "tokens": [
          "El",
          "coche",
          "rojo",
          "está",
          "en",
          "la",
          "calle."
        ]
      },
      "fr": {
        "en": "The red car is in the street.",
        "tokens": [
          "La",
          "voiture",
          "rouge",
          "est",
          "dans",
          "la",
          "rue."
        ]
      },
      "de": {
        "en": "The red car is on the street.",
        "tokens": [
          "Das",
          "rote",
          "Auto",
          "steht",
          "auf",
          "der",
          "Straße."
        ]
      },
      "ko": {
        "en": "The red car is on the street.",
        "tokens": [
          "빨간",
          "차가",
          "길",
          "위에",
          "있어요."
        ]
      }
    },
    "journal": {
      "es": {
        "title": "Una calle con flores",
        "body": "Hoy subí una calle muy bonita. Había flores por todas partes y un coche rojo bajaba despacio. ¡Quiero vivir en una de esas casas!"
      },
      "fr": {
        "title": "Une rue fleurie",
        "body": "Aujourd’hui, j’ai monté une jolie rue à pied. Il y avait des fleurs partout et une voiture rouge descendait lentement. Je voudrais vivre dans une de ces maisons."
      },
      "de": {
        "title": "Eine Straße voller Blumen",
        "body": "Heute bin ich eine wunderschöne Straße hochgelaufen. Überall waren Blumen und ein rotes Auto fuhr langsam vorbei. Ich möchte in einem dieser Häuser wohnen!"
      },
      "ko": {
        "title": "꽃이 핀 언덕길",
        "body": "오늘 아주 예쁜 길을 걸어 올라갔어요. 곳곳에 꽃이 피어 있었고 빨간 차가 천천히 내려왔어요. 이런 집에 살고 싶어요!"
      }
    }
  },
  {
    "id": "golden-gate-bridge",
    "photo": "/photos/golden-gate-bridge.jpg",
    "title": "Across the bay",
    "place": "San Francisco",
    "width": 1570,
    "height": 1047,
    "alt": "The red Golden Gate Bridge crossing blue water, with cars on the deck and wooded hills and houses behind",
    "words": [
      {
        "id": "bridge",
        "en": "bridge",
        "x": 60,
        "y": 61,
        "es": {
          "word": "el puente",
          "gender": "masculine",
          "ipa": "ˈpwente"
        },
        "fr": {
          "word": "le pont",
          "gender": "masculine",
          "ipa": "pɔ̃"
        },
        "de": {
          "word": "die Brücke",
          "gender": "feminine",
          "ipa": "ˈbʁʏkə"
        },
        "ko": {
          "word": "다리",
          "gender": "none",
          "ipa": "ta.ɾi"
        }
      },
      {
        "id": "tower",
        "en": "tower",
        "x": 95,
        "y": 30,
        "es": {
          "word": "la torre",
          "gender": "feminine",
          "ipa": "ˈtore"
        },
        "fr": {
          "word": "la tour",
          "gender": "feminine",
          "ipa": "tuʁ"
        },
        "de": {
          "word": "der Turm",
          "gender": "masculine",
          "ipa": "tʊʁm"
        },
        "ko": {
          "word": "탑",
          "gender": "none",
          "ipa": "tʰap̚"
        }
      },
      {
        "id": "car",
        "en": "car",
        "x": 19,
        "y": 70,
        "es": {
          "word": "el coche",
          "gender": "masculine",
          "ipa": "ˈkotʃe"
        },
        "fr": {
          "word": "la voiture",
          "gender": "feminine",
          "ipa": "vwatyʁ"
        },
        "de": {
          "word": "das Auto",
          "gender": "neuter",
          "ipa": "ˈaʊ̯to"
        },
        "ko": {
          "word": "차",
          "gender": "none",
          "ipa": "tɕʰa"
        }
      },
      {
        "id": "sea",
        "en": "sea",
        "x": 65,
        "y": 84,
        "es": {
          "word": "el mar",
          "gender": "masculine",
          "ipa": "maɾ"
        },
        "fr": {
          "word": "la mer",
          "gender": "feminine",
          "ipa": "mɛʁ"
        },
        "de": {
          "word": "das Meer",
          "gender": "neuter",
          "ipa": "meːɐ̯"
        },
        "ko": {
          "word": "바다",
          "gender": "none",
          "ipa": "pa.da"
        }
      },
      {
        "id": "hill",
        "en": "hill",
        "x": 45,
        "y": 22,
        "es": {
          "word": "la colina",
          "gender": "feminine",
          "ipa": "koˈlina"
        },
        "fr": {
          "word": "la colline",
          "gender": "feminine",
          "ipa": "kɔlin"
        },
        "de": {
          "word": "der Hügel",
          "gender": "masculine",
          "ipa": "ˈhyːɡl̩"
        },
        "ko": {
          "word": "언덕",
          "gender": "none",
          "ipa": "ʌn.dʌk̚"
        }
      }
    ],
    "ispy": {
      "es": {
        "clue": "Veo, veo… algo que es azul y está debajo del puente.",
        "clueEn": "I spy… something that is blue and is under the bridge.",
        "answer": "el mar",
        "choices": [
          "el coche",
          "la torre",
          "el mar",
          "la colina"
        ]
      },
      "fr": {
        "clue": "Je vois, je vois… quelque chose qui est bleu et qui est sous le pont.",
        "clueEn": "I spy… something that is blue and is under the bridge.",
        "answer": "la mer",
        "choices": [
          "la colline",
          "la mer",
          "la voiture",
          "la tour"
        ]
      },
      "de": {
        "clue": "Ich sehe was, was du nicht siehst: etwas, das blau ist und unter der Brücke liegt.",
        "clueEn": "I spy… something that is blue and is under the bridge.",
        "answer": "das Meer",
        "choices": [
          "das Auto",
          "der Turm",
          "das Meer",
          "der Hügel"
        ]
      },
      "ko": {
        "clue": "파란색이고 다리 아래에 있는 것이 보여요.",
        "clueEn": "I spy… something that is blue and is under the bridge.",
        "answer": "바다",
        "choices": [
          "언덕",
          "바다",
          "차",
          "탑"
        ]
      }
    },
    "blankWordId": "car",
    "blank": {
      "es": {
        "sentence": "Hay muchos ___ en el puente.",
        "en": "There are lots of cars on the bridge.",
        "answer": "coches",
        "options": [
          "coche",
          "coches"
        ]
      },
      "fr": {
        "sentence": "Il y a beaucoup de ___ sur le pont.",
        "en": "There are lots of cars on the bridge.",
        "answer": "voitures",
        "options": [
          "voitures",
          "voiture"
        ]
      },
      "de": {
        "sentence": "Es fahren viele ___ über die Brücke.",
        "en": "There are lots of cars on the bridge.",
        "answer": "Autos",
        "options": [
          "Autos",
          "Auto"
        ]
      },
      "ko": {
        "sentence": "다리 위에 많은 ___가 있어요.",
        "en": "There are lots of cars on the bridge.",
        "answer": "차",
        "options": [
          "차",
          "바다"
        ]
      }
    },
    "build": {
      "es": {
        "en": "The red bridge is over the sea.",
        "tokens": [
          "El",
          "puente",
          "rojo",
          "está",
          "sobre",
          "el",
          "mar."
        ]
      },
      "fr": {
        "en": "The red bridge is above the sea.",
        "tokens": [
          "Le",
          "pont",
          "rouge",
          "est",
          "au-dessus",
          "de",
          "la",
          "mer."
        ]
      },
      "de": {
        "en": "The red bridge is over the sea.",
        "tokens": [
          "Die",
          "rote",
          "Brücke",
          "liegt",
          "über",
          "dem",
          "Meer."
        ]
      },
      "ko": {
        "en": "The red bridge is over the sea.",
        "tokens": [
          "빨간",
          "다리가",
          "바다",
          "위에",
          "있어요."
        ]
      }
    },
    "journal": {
      "es": {
        "title": "El puente rojo",
        "body": "Hoy crucé el puente en coche. Desde el puente vi el mar azul y las colinas verdes. ¡La torre roja es enorme!"
      },
      "fr": {
        "title": "Le pont rouge",
        "body": "Aujourd’hui, j’ai traversé le pont en voiture. Depuis le pont, j’ai vu la mer bleue et les collines vertes. La tour rouge est vraiment immense."
      },
      "de": {
        "title": "Die rote Brücke",
        "body": "Heute bin ich mit dem Auto über die Brücke gefahren. Von der Brücke aus sah ich das blaue Meer und die grünen Hügel. Der rote Turm ist riesig!"
      },
      "ko": {
        "title": "붉은 다리 건너기",
        "body": "오늘 차를 타고 다리를 건넜어요. 다리 위에서 푸른 바다와 초록빛 언덕을 보았어요. 붉은 탑이 정말 거대했어요!"
      }
    }
  },
  {
    "id": "cafe-interior",
    "photo": "/photos/cafe-interior.jpg",
    "title": "Café morning",
    "place": "A city café",
    "width": 1900,
    "height": 710,
    "alt": "Sunlit café seen from above, with bar stools at a long counter, a wooden coffee table, leather sofas and a tall grandfather clock",
    "words": [
      {
        "id": "stool",
        "en": "stool",
        "x": 32,
        "y": 60,
        "es": {
          "word": "el taburete",
          "gender": "masculine",
          "ipa": "tabuˈɾete"
        },
        "fr": {
          "word": "le tabouret",
          "gender": "masculine",
          "ipa": "tabuʁɛ"
        },
        "de": {
          "word": "der Hocker",
          "gender": "masculine",
          "ipa": "ˈhɔkɐ"
        },
        "ko": {
          "word": "스툴",
          "gender": "none",
          "ipa": "sɯ.tʰul"
        }
      },
      {
        "id": "table",
        "en": "table",
        "x": 45,
        "y": 78,
        "es": {
          "word": "la mesa",
          "gender": "feminine",
          "ipa": "ˈmesa"
        },
        "fr": {
          "word": "la table",
          "gender": "feminine",
          "ipa": "tabl"
        },
        "de": {
          "word": "der Tisch",
          "gender": "masculine",
          "ipa": "tɪʃ"
        },
        "ko": {
          "word": "탁자",
          "gender": "none",
          "ipa": "tʰak̚.tɕa"
        }
      },
      {
        "id": "sofa",
        "en": "sofa",
        "x": 81,
        "y": 78,
        "es": {
          "word": "el sofá",
          "gender": "masculine",
          "ipa": "soˈfa"
        },
        "fr": {
          "word": "le canapé",
          "gender": "masculine",
          "ipa": "kanape"
        },
        "de": {
          "word": "das Sofa",
          "gender": "neuter",
          "ipa": "ˈzoːfa"
        },
        "ko": {
          "word": "소파",
          "gender": "none",
          "ipa": "so.pʰa"
        }
      },
      {
        "id": "lamp",
        "en": "lamp",
        "x": 76,
        "y": 60,
        "es": {
          "word": "la lámpara",
          "gender": "feminine",
          "ipa": "ˈlampaɾa"
        },
        "fr": {
          "word": "la lampe",
          "gender": "feminine",
          "ipa": "lɑ̃p"
        },
        "de": {
          "word": "die Lampe",
          "gender": "feminine",
          "ipa": "ˈlampə"
        },
        "ko": {
          "word": "램프",
          "gender": "none",
          "ipa": "ɾɛm.pʰɯ"
        }
      },
      {
        "id": "clock",
        "en": "clock",
        "x": 86,
        "y": 30,
        "es": {
          "word": "el reloj",
          "gender": "masculine",
          "ipa": "reˈlox"
        },
        "fr": {
          "word": "l’horloge",
          "gender": "feminine",
          "ipa": "ɔʁlɔʒ"
        },
        "de": {
          "word": "die Uhr",
          "gender": "feminine",
          "ipa": "uːɐ̯"
        },
        "ko": {
          "word": "시계",
          "gender": "none",
          "ipa": "ɕi.ɡje"
        }
      }
    ],
    "ispy": {
      "es": {
        "clue": "Veo, veo… algo que es alto y marca la hora.",
        "clueEn": "I spy… something that is tall and tells the time.",
        "answer": "el reloj",
        "choices": [
          "el sofá",
          "la lámpara",
          "el taburete",
          "el reloj"
        ]
      },
      "fr": {
        "clue": "Je vois, je vois… quelque chose qui est grand et qui donne l’heure.",
        "clueEn": "I spy… something that is tall and tells the time.",
        "answer": "l’horloge",
        "choices": [
          "le canapé",
          "l’horloge",
          "la lampe",
          "le tabouret"
        ]
      },
      "de": {
        "clue": "Ich sehe was, was du nicht siehst: etwas, das groß ist und die Zeit anzeigt.",
        "clueEn": "I spy… something that is tall and tells the time.",
        "answer": "die Uhr",
        "choices": [
          "das Sofa",
          "die Lampe",
          "der Hocker",
          "die Uhr"
        ]
      },
      "ko": {
        "clue": "키가 크고 시간을 알려주는 것이 보여요.",
        "clueEn": "I spy… something that is tall and tells the time.",
        "answer": "시계",
        "choices": [
          "소파",
          "시계",
          "램프",
          "스툴"
        ]
      }
    },
    "blankWordId": "sofa",
    "blank": {
      "es": {
        "sentence": "Los ___ son marrones.",
        "en": "The sofas are brown.",
        "answer": "sofás",
        "options": [
          "sofás",
          "sofá"
        ]
      },
      "fr": {
        "sentence": "Les ___ sont marron.",
        "en": "The sofas are brown.",
        "answer": "canapés",
        "options": [
          "canapé",
          "canapés"
        ]
      },
      "de": {
        "sentence": "Die ___ sind braun.",
        "en": "The sofas are brown.",
        "answer": "Sofas",
        "options": [
          "Sofas",
          "Sofa"
        ]
      },
      "ko": {
        "sentence": "___가 갈색이에요.",
        "en": "The sofas are brown.",
        "answer": "소파",
        "options": [
          "소파",
          "탁자"
        ]
      }
    },
    "build": {
      "es": {
        "en": "I have a coffee on the sofa.",
        "tokens": [
          "Tomo",
          "un",
          "café",
          "en",
          "el",
          "sofá."
        ]
      },
      "fr": {
        "en": "I drink a coffee on the sofa.",
        "tokens": [
          "Je",
          "bois",
          "un",
          "café",
          "sur",
          "le",
          "canapé."
        ]
      },
      "de": {
        "en": "I drink a coffee on the sofa.",
        "tokens": [
          "Ich",
          "trinke",
          "einen",
          "Kaffee",
          "auf",
          "dem",
          "Sofa."
        ]
      },
      "ko": {
        "en": "I drink a coffee on the sofa.",
        "tokens": [
          "소파에",
          "앉아",
          "커피를",
          "마셔요."
        ]
      }
    },
    "journal": {
      "es": {
        "title": "Una mañana en la cafetería",
        "body": "Esta mañana tomé un té en una cafetería preciosa. Leí un libro en un sofá de piel, cerca de una mesa de madera. Un reloj muy alto marcaba las diez."
      },
      "fr": {
        "title": "Un matin au café",
        "body": "Ce matin, j’ai pris un thé dans un joli café. J’ai lu un livre sur un canapé en cuir, près d’une table en bois. Une grande horloge indiquait dix heures."
      },
      "de": {
        "title": "Ein Morgen im Café",
        "body": "Heute Morgen habe ich in einem gemütlichen Café Tee getrunken. Ich habe auf einem Ledersofa neben einem Holztisch ein Buch gelesen. Eine große Uhr schlug zehn."
      },
      "ko": {
        "title": "카페에서의 아침",
        "body": "오늘 아침 분위기 좋은 카페에서 차를 마셨어요. 나무 탁자 옆 가죽 소파에 앉아 책을 읽었어요. 커다란 시계가 10시를 가리키고 있었어요."
      }
    }
  },
  {
    "id": "desk-flatlay",
    "photo": "/photos/desk-flatlay.jpg",
    "title": "Study day",
    "place": "A home office",
    "width": 1900,
    "height": 1267,
    "alt": "White desk seen from above with an open notebook, a yellow pencil, a pair of glasses, a smartphone, a laptop and a potted plant",
    "words": [
      {
        "id": "notebook",
        "en": "notebook",
        "x": 38,
        "y": 52,
        "es": {
          "word": "la libreta",
          "gender": "feminine",
          "ipa": "liˈbɾeta"
        },
        "fr": {
          "word": "le cahier",
          "gender": "masculine",
          "ipa": "kaje"
        },
        "de": {
          "word": "das Notizbuch",
          "gender": "neuter",
          "ipa": "noˈtiːtsˌbuːx"
        },
        "ko": {
          "word": "공책",
          "gender": "none",
          "ipa": "koŋ.tɕʰɛk̚"
        }
      },
      {
        "id": "pencil",
        "en": "pencil",
        "x": 76,
        "y": 60,
        "es": {
          "word": "el lápiz",
          "gender": "masculine",
          "ipa": "ˈlapiθ"
        },
        "fr": {
          "word": "le crayon",
          "gender": "masculine",
          "ipa": "kʁɛjɔ̃"
        },
        "de": {
          "word": "der Bleistift",
          "gender": "masculine",
          "ipa": "ˈblaɪ̯ˌʃtɪft"
        },
        "ko": {
          "word": "연필",
          "gender": "none",
          "ipa": "jʌn.pʰil"
        }
      },
      {
        "id": "laptop",
        "en": "laptop",
        "x": 90,
        "y": 24,
        "es": {
          "word": "el portátil",
          "gender": "masculine",
          "ipa": "poɾˈtatil"
        },
        "fr": {
          "word": "l’ordinateur",
          "gender": "masculine",
          "ipa": "ɔʁdinatœʁ"
        },
        "de": {
          "word": "der Laptop",
          "gender": "masculine",
          "ipa": "ˈlɛpˌtɔp"
        },
        "ko": {
          "word": "노트북",
          "gender": "none",
          "ipa": "no.tʰɯ.puk̚"
        }
      },
      {
        "id": "phone",
        "en": "phone",
        "x": 11,
        "y": 65,
        "es": {
          "word": "el móvil",
          "gender": "masculine",
          "ipa": "ˈmobil"
        },
        "fr": {
          "word": "le téléphone",
          "gender": "masculine",
          "ipa": "telefɔn"
        },
        "de": {
          "word": "das Handy",
          "gender": "neuter",
          "ipa": "ˈhɛndi"
        },
        "ko": {
          "word": "휴대폰",
          "gender": "none",
          "ipa": "hju.dɛ.pʰon"
        }
      },
      {
        "id": "plant",
        "en": "plant",
        "x": 17,
        "y": 10,
        "es": {
          "word": "la planta",
          "gender": "feminine",
          "ipa": "ˈplanta"
        },
        "fr": {
          "word": "la plante",
          "gender": "feminine",
          "ipa": "plɑ̃t"
        },
        "de": {
          "word": "die Pflanze",
          "gender": "feminine",
          "ipa": "ˈpflantsə"
        },
        "ko": {
          "word": "식물",
          "gender": "none",
          "ipa": "ɕiŋ.mul"
        }
      },
      {
        "id": "page",
        "en": "page",
        "x": 59,
        "y": 65,
        "es": {
          "word": "la página",
          "gender": "feminine",
          "ipa": "ˈpaxina"
        },
        "fr": {
          "word": "la page",
          "gender": "feminine",
          "ipa": "paʒ"
        },
        "de": {
          "word": "die Seite",
          "gender": "feminine",
          "ipa": "ˈzaɪ̯tə"
        },
        "ko": {
          "word": "페이지",
          "gender": "none",
          "ipa": "pʰe.i.dʑi"
        }
      }
    ],
    "ispy": {
      "es": {
        "clue": "Veo, veo… algo que es amarillo y sirve para escribir.",
        "clueEn": "I spy… something that is yellow and is used for writing.",
        "answer": "el lápiz",
        "choices": [
          "el lápiz",
          "el móvil",
          "la libreta",
          "la planta"
        ]
      },
      "fr": {
        "clue": "Je vois, je vois… quelque chose qui est jaune et qui sert à écrire.",
        "clueEn": "I spy… something that is yellow and is used for writing.",
        "answer": "le crayon",
        "choices": [
          "la plante",
          "le téléphone",
          "le crayon",
          "le cahier"
        ]
      },
      "de": {
        "clue": "Ich sehe was, was du nicht siehst: etwas, das gelb ist und zum Schreiben dient.",
        "clueEn": "I spy… something that is yellow and is used for writing.",
        "answer": "der Bleistift",
        "choices": [
          "der Bleistift",
          "das Handy",
          "das Notizbuch",
          "die Pflanze"
        ]
      },
      "ko": {
        "clue": "노란색이고 글을 쓸 때 사용하는 것이 보여요.",
        "clueEn": "I spy… something that is yellow and is used for writing.",
        "answer": "연필",
        "choices": [
          "연필",
          "휴대폰",
          "공책",
          "식물"
        ]
      }
    },
    "blankWordId": "page",
    "blank": {
      "es": {
        "sentence": "La libreta tiene dos ___ blancas.",
        "en": "The notebook has two white pages.",
        "answer": "páginas",
        "options": [
          "página",
          "páginas"
        ]
      },
      "fr": {
        "sentence": "Le cahier a deux ___ blanches.",
        "en": "The notebook has two white pages.",
        "answer": "pages",
        "options": [
          "pages",
          "page"
        ]
      },
      "de": {
        "sentence": "Das Notizbuch hat zwei weiße ___.",
        "en": "The notebook has two white pages.",
        "answer": "Seiten",
        "options": [
          "Seite",
          "Seiten"
        ]
      },
      "ko": {
        "sentence": "공책에 두 장의 흰 ___가 있어요.",
        "en": "The notebook has two white pages.",
        "answer": "페이지",
        "options": [
          "페이지",
          "공책"
        ]
      }
    },
    "build": {
      "es": {
        "en": "I write in my new notebook.",
        "tokens": [
          "Escribo",
          "en",
          "mi",
          "libreta",
          "nueva."
        ]
      },
      "fr": {
        "en": "I write in my new notebook.",
        "tokens": [
          "J’écris",
          "dans",
          "mon",
          "nouveau",
          "cahier."
        ]
      },
      "de": {
        "en": "I write in my new notebook.",
        "tokens": [
          "Ich",
          "schreibe",
          "in",
          "mein",
          "neues",
          "Notizbuch."
        ]
      },
      "ko": {
        "en": "I write in my new notebook.",
        "tokens": [
          "새",
          "공책에",
          "글을",
          "써요."
        ]
      }
    },
    "journal": {
      "es": {
        "title": "Un día de estudio",
        "body": "Hoy estudié en casa toda la mañana. Escribí diez palabras nuevas en mi libreta con un lápiz amarillo. Después puse el móvil en silencio y regué la planta."
      },
      "fr": {
        "title": "Une matinée d’étude",
        "body": "Aujourd’hui, j’ai étudié chez moi toute la matinée. J’ai écrit dix nouveaux mots dans mon cahier avec un crayon jaune. Ensuite, j’ai mis mon téléphone en silencieux et j’ai arrosé la plante."
      },
      "de": {
        "title": "Ein Tag zum Lernen",
        "body": "Heute habe ich den ganzen Vormittag zu Hause gelernt. Mit einem gelben Bleistift habe ich zehn neue Wörter in mein Notizbuch geschrieben. Danach habe ich mein Handy stumm geschaltet und die Pflanze gegossen."
      },
      "ko": {
        "title": "공부하는 하루",
        "body": "오늘 오전 내내 집에서 공부했어요. 노란 연필로 새 공책에 열 개의 새 단어를 적었어요. 그런 다음 휴대폰을 무음으로 해두고 식물에 물을 주었어요."
      }
    }
  },
  {
    "id": "paris-rooftops",
    "photo": "/photos/paris-rooftops.jpg",
    "title": "Paris at dusk",
    "place": "Paris",
    "width": 1440,
    "height": 642,
    "alt": "Stone gargoyle looking out over Paris rooftops at dusk, with the Seine, a bridge and the lit Eiffel Tower on the horizon",
    "words": [
      {
        "id": "statue",
        "en": "statue",
        "x": 15,
        "y": 52,
        "es": {
          "word": "la estatua",
          "gender": "feminine",
          "ipa": "esˈtatwa"
        },
        "fr": {
          "word": "la statue",
          "gender": "feminine",
          "ipa": "staty"
        },
        "de": {
          "word": "die Statue",
          "gender": "feminine",
          "ipa": "ˈʃtaːtu̯ə"
        },
        "ko": {
          "word": "조각상",
          "gender": "none",
          "ipa": "tɕo.ɡak̚.saŋ"
        }
      },
      {
        "id": "tower",
        "en": "tower",
        "x": 61,
        "y": 30,
        "es": {
          "word": "la torre",
          "gender": "feminine",
          "ipa": "ˈtore"
        },
        "fr": {
          "word": "la tour",
          "gender": "feminine",
          "ipa": "tuʁ"
        },
        "de": {
          "word": "der Turm",
          "gender": "masculine",
          "ipa": "tʊʁm"
        },
        "ko": {
          "word": "탑",
          "gender": "none",
          "ipa": "tʰap̚"
        }
      },
      {
        "id": "bridge",
        "en": "bridge",
        "x": 73,
        "y": 59,
        "es": {
          "word": "el puente",
          "gender": "masculine",
          "ipa": "ˈpwente"
        },
        "fr": {
          "word": "le pont",
          "gender": "masculine",
          "ipa": "pɔ̃"
        },
        "de": {
          "word": "die Brücke",
          "gender": "feminine",
          "ipa": "ˈbʁʏkə"
        },
        "ko": {
          "word": "다리",
          "gender": "none",
          "ipa": "ta.ɾi"
        }
      },
      {
        "id": "river",
        "en": "river",
        "x": 67,
        "y": 76,
        "es": {
          "word": "el río",
          "gender": "masculine",
          "ipa": "ˈrio"
        },
        "fr": {
          "word": "le fleuve",
          "gender": "masculine",
          "ipa": "flœv"
        },
        "de": {
          "word": "der Fluss",
          "gender": "masculine",
          "ipa": "flʊs"
        },
        "ko": {
          "word": "강",
          "gender": "none",
          "ipa": "kaŋ"
        }
      },
      {
        "id": "building",
        "en": "building",
        "x": 90,
        "y": 72,
        "es": {
          "word": "el edificio",
          "gender": "masculine",
          "ipa": "ediˈfiθjo"
        },
        "fr": {
          "word": "le bâtiment",
          "gender": "masculine",
          "ipa": "batimɑ̃"
        },
        "de": {
          "word": "das Gebäude",
          "gender": "neuter",
          "ipa": "ɡəˈbɔɪ̯də"
        },
        "ko": {
          "word": "건물",
          "gender": "none",
          "ipa": "kʌn.mul"
        }
      }
    ],
    "ispy": {
      "es": {
        "clue": "Veo, veo… algo que es de piedra y mira la ciudad.",
        "clueEn": "I spy… something that is made of stone and looks out over the city.",
        "answer": "la estatua",
        "choices": [
          "el puente",
          "la estatua",
          "la torre",
          "el río"
        ]
      },
      "fr": {
        "clue": "Je vois, je vois… quelque chose qui est en pierre et qui regarde la ville.",
        "clueEn": "I spy… something that is made of stone and looks out over the city.",
        "answer": "la statue",
        "choices": [
          "le fleuve",
          "le pont",
          "la statue",
          "la tour"
        ]
      },
      "de": {
        "clue": "Ich sehe was, was du nicht siehst: etwas, das aus Stein ist und auf die Stadt blickt.",
        "clueEn": "I spy… something that is made of stone and looks out over the city.",
        "answer": "die Statue",
        "choices": [
          "die Brücke",
          "die Statue",
          "der Turm",
          "der Fluss"
        ]
      },
      "ko": {
        "clue": "돌로 만들어졌고 도시를 내려다보는 것이 보여요.",
        "clueEn": "I spy… something that is made of stone and looks out over the city.",
        "answer": "조각상",
        "choices": [
          "강",
          "다리",
          "조각상",
          "탑"
        ]
      }
    },
    "blankWordId": "bridge",
    "blank": {
      "es": {
        "sentence": "Dos ___ cruzan el río.",
        "en": "Two bridges cross the river.",
        "answer": "puentes",
        "options": [
          "puentes",
          "puente"
        ]
      },
      "fr": {
        "sentence": "Deux ___ traversent le fleuve.",
        "en": "Two bridges cross the river.",
        "answer": "ponts",
        "options": [
          "pont",
          "ponts"
        ]
      },
      "de": {
        "sentence": "Zwei ___ überqueren den Fluss.",
        "en": "Two bridges cross the river.",
        "answer": "Brücken",
        "options": [
          "Brücke",
          "Brücken"
        ]
      },
      "ko": {
        "sentence": "두 개의 ___가 강을 건너요.",
        "en": "Two bridges cross the river.",
        "answer": "다리",
        "options": [
          "다리",
          "강"
        ]
      }
    },
    "build": {
      "es": {
        "en": "The Eiffel Tower shines at night.",
        "tokens": [
          "La",
          "torre",
          "Eiffel",
          "brilla",
          "por",
          "la",
          "noche."
        ]
      },
      "fr": {
        "en": "The Eiffel Tower shines in the evening.",
        "tokens": [
          "La",
          "tour",
          "Eiffel",
          "brille",
          "le",
          "soir."
        ]
      },
      "de": {
        "en": "The Eiffel Tower shines in the evening.",
        "tokens": [
          "Der",
          "Eiffelturm",
          "leuchtet",
          "am",
          "Abend."
        ]
      },
      "ko": {
        "en": "The Eiffel Tower shines in the evening.",
        "tokens": [
          "에펠탑이",
          "저녁에",
          "빛나요."
        ]
      }
    },
    "journal": {
      "es": {
        "title": "Una tarde en París",
        "body": "Esta tarde subí a lo alto de una catedral. Una estatua muy rara miraba la ciudad. Desde arriba vi el río, un puente y la torre Eiffel iluminada."
      },
      "fr": {
        "title": "Un soir à Paris",
        "body": "Ce soir, j’ai grimpé en haut d’une cathédrale. Une drôle de statue regardait la ville. D’en haut, j’ai vu le fleuve, un pont et la tour Eiffel qui brillait."
      },
      "de": {
        "title": "Ein Abend in Paris",
        "body": "Heute Abend bin ich auf das Dach einer Kathedrale gestiegen. Eine seltsame Statue blickte über die Stadt. Von oben sah ich den Fluss, eine Brücke und den erleuchteten Eiffelturm."
      },
      "ko": {
        "title": "파리의 저녁",
        "body": "오늘 저녁 대성당 꼭대기에 올라갔어요. 특이한 조각상이 도시를 내려다보고 있었어요. 위에서 강과 다리, 그리고 불을 밝힌 에펠탑이 보였어요."
      }
    }
  },
  {
    "id": "alpine-castle",
    "photo": "/photos/alpine-castle.jpg",
    "title": "Fairy-tale castle",
    "place": "Bavaria",
    "width": 2000,
    "height": 1335,
    "alt": "White fairy-tale castle on a forested ridge above green fields and a lake, under a cloudy sky",
    "words": [
      {
        "id": "castle",
        "en": "castle",
        "x": 35,
        "y": 48,
        "es": {
          "word": "el castillo",
          "gender": "masculine",
          "ipa": "kasˈtiʎo"
        },
        "fr": {
          "word": "le château",
          "gender": "masculine",
          "ipa": "ʃato"
        },
        "de": {
          "word": "das Schloss",
          "gender": "neuter",
          "ipa": "ʃlɔs"
        },
        "ko": {
          "word": "성",
          "gender": "none",
          "ipa": "sʌŋ"
        }
      },
      {
        "id": "lake",
        "en": "lake",
        "x": 14,
        "y": 51,
        "es": {
          "word": "el lago",
          "gender": "masculine",
          "ipa": "ˈlaɡo"
        },
        "fr": {
          "word": "le lac",
          "gender": "masculine",
          "ipa": "lak"
        },
        "de": {
          "word": "der See",
          "gender": "masculine",
          "ipa": "zeː"
        },
        "ko": {
          "word": "호수",
          "gender": "none",
          "ipa": "ho.su"
        }
      },
      {
        "id": "forest",
        "en": "forest",
        "x": 50,
        "y": 80,
        "es": {
          "word": "el bosque",
          "gender": "masculine",
          "ipa": "ˈboske"
        },
        "fr": {
          "word": "la forêt",
          "gender": "feminine",
          "ipa": "fɔʁɛ"
        },
        "de": {
          "word": "der Wald",
          "gender": "masculine",
          "ipa": "valt"
        },
        "ko": {
          "word": "숲",
          "gender": "none",
          "ipa": "sup̚"
        }
      },
      {
        "id": "mountain",
        "en": "mountain",
        "x": 91,
        "y": 45,
        "es": {
          "word": "la montaña",
          "gender": "feminine",
          "ipa": "monˈtaɲa"
        },
        "fr": {
          "word": "la montagne",
          "gender": "feminine",
          "ipa": "mɔ̃taɲ"
        },
        "de": {
          "word": "der Berg",
          "gender": "masculine",
          "ipa": "bɛʁk"
        },
        "ko": {
          "word": "산",
          "gender": "none",
          "ipa": "san"
        }
      },
      {
        "id": "cloud",
        "en": "cloud",
        "x": 70,
        "y": 18,
        "es": {
          "word": "la nube",
          "gender": "feminine",
          "ipa": "ˈnube"
        },
        "fr": {
          "word": "le nuage",
          "gender": "masculine",
          "ipa": "nɥaʒ"
        },
        "de": {
          "word": "die Wolke",
          "gender": "feminine",
          "ipa": "ˈvɔlkə"
        },
        "ko": {
          "word": "구름",
          "gender": "none",
          "ipa": "ku.ɾɯm"
        }
      },
      {
        "id": "tower",
        "en": "tower",
        "x": 31.5,
        "y": 31,
        "es": {
          "word": "la torre",
          "gender": "feminine",
          "ipa": "ˈtore"
        },
        "fr": {
          "word": "la tour",
          "gender": "feminine",
          "ipa": "tuʁ"
        },
        "de": {
          "word": "der Turm",
          "gender": "masculine",
          "ipa": "tʊʁm"
        },
        "ko": {
          "word": "탑",
          "gender": "none",
          "ipa": "tʰap̚"
        }
      }
    ],
    "ispy": {
      "es": {
        "clue": "Veo, veo… algo que es azul y está a la izquierda del castillo.",
        "clueEn": "I spy… something that is blue and is to the left of the castle.",
        "answer": "el lago",
        "choices": [
          "el bosque",
          "la nube",
          "la montaña",
          "el lago"
        ]
      },
      "fr": {
        "clue": "Je vois, je vois… quelque chose qui est bleu et qui est à gauche du château.",
        "clueEn": "I spy… something that is blue and is to the left of the castle.",
        "answer": "le lac",
        "choices": [
          "la forêt",
          "le lac",
          "la montagne",
          "le nuage"
        ]
      },
      "de": {
        "clue": "Ich sehe was, was du nicht siehst: etwas, das blau ist und links vom Schloss liegt.",
        "clueEn": "I spy… something that is blue and is to the left of the castle.",
        "answer": "der See",
        "choices": [
          "der Wald",
          "die Wolke",
          "der Berg",
          "der See"
        ]
      },
      "ko": {
        "clue": "파란색이고 성 왼쪽에 있는 것이 보여요.",
        "clueEn": "I spy… something that is blue and is to the left of the castle.",
        "answer": "호수",
        "choices": [
          "숲",
          "호수",
          "산",
          "구름"
        ]
      }
    },
    "blankWordId": "tower",
    "blank": {
      "es": {
        "sentence": "El castillo tiene muchas ___.",
        "en": "The castle has lots of towers.",
        "answer": "torres",
        "options": [
          "torre",
          "torres"
        ]
      },
      "fr": {
        "sentence": "Le château a beaucoup de ___.",
        "en": "The castle has lots of towers.",
        "answer": "tours",
        "options": [
          "tours",
          "tour"
        ]
      },
      "de": {
        "sentence": "Das Schloss hat viele ___.",
        "en": "The castle has lots of towers.",
        "answer": "Türme",
        "options": [
          "Turm",
          "Türme"
        ]
      },
      "ko": {
        "sentence": "성에 ___이 많이 있어요.",
        "en": "The castle has lots of towers.",
        "answer": "탑",
        "options": [
          "탑",
          "성"
        ]
      }
    },
    "build": {
      "es": {
        "en": "The white castle is in the forest.",
        "tokens": [
          "El",
          "castillo",
          "blanco",
          "está",
          "en",
          "el",
          "bosque."
        ]
      },
      "fr": {
        "en": "The white castle is in the forest.",
        "tokens": [
          "Le",
          "château",
          "blanc",
          "est",
          "dans",
          "la",
          "forêt."
        ]
      },
      "de": {
        "en": "The white castle is in the forest.",
        "tokens": [
          "Das",
          "weiße",
          "Schloss",
          "steht",
          "im",
          "Wald."
        ]
      },
      "ko": {
        "en": "The white castle is in the forest.",
        "tokens": [
          "하얀",
          "성이",
          "숲속에",
          "있어요."
        ]
      }
    },
    "journal": {
      "es": {
        "title": "Un castillo de cuento",
        "body": "Hoy caminé por el bosque hasta un castillo blanco. Parecía sacado de un cuento. Desde arriba vi un lago azul y muchas nubes."
      },
      "fr": {
        "title": "Un château magique",
        "body": "Aujourd’hui, j’ai marché dans la forêt jusqu’à un château blanc. C’était comme dans un conte de fées. D’en haut, j’ai vu un lac bleu et beaucoup de nuages."
      },
      "de": {
        "title": "Ein Märchenschloss",
        "body": "Heute bin ich durch den Wald zu einem weißen Schloss gewandert. Es sah aus wie im Märchen. Von oben sah ich einen blauen See und viele Wolken."
      },
      "ko": {
        "title": "동화 속 성",
        "body": "오늘 숲을 지나 하얀 성까지 걸어갔어요. 동화 속 한 장면 같았어요. 위에서 푸른 호수와 많은 구름을 보았어요."
      }
    }
  },
  {
    "id": "sunlit-promenade",
    "photo": "/photos/sunlit-promenade.jpg",
    "title": "Golden hour walk",
    "place": "A sunny city square",
    "width": 1950,
    "height": 1300,
    "alt": "City square at golden hour with ornate street lamps, palm trees, fountain mist and people walking in silhouette",
    "words": [
      {
        "id": "street-lamp",
        "en": "street lamp",
        "x": 29,
        "y": 24,
        "es": {
          "word": "la farola",
          "gender": "feminine",
          "ipa": "faˈɾola"
        },
        "fr": {
          "word": "le lampadaire",
          "gender": "masculine",
          "ipa": "lɑ̃padɛʁ"
        },
        "de": {
          "word": "die Laterne",
          "gender": "feminine",
          "ipa": "laˈtɛʁnə"
        },
        "ko": {
          "word": "가로등",
          "gender": "none",
          "ipa": "ka.ɾo.dɯŋ"
        }
      },
      {
        "id": "palm-tree",
        "en": "palm tree",
        "x": 62,
        "y": 27,
        "es": {
          "word": "la palmera",
          "gender": "feminine",
          "ipa": "palˈmeɾa"
        },
        "fr": {
          "word": "le palmier",
          "gender": "masculine",
          "ipa": "palmje"
        },
        "de": {
          "word": "die Palme",
          "gender": "feminine",
          "ipa": "ˈpalmə"
        },
        "ko": {
          "word": "야자수",
          "gender": "none",
          "ipa": "ja.dʑa.su"
        }
      },
      {
        "id": "sun",
        "en": "sun",
        "x": 53,
        "y": 12,
        "es": {
          "word": "el sol",
          "gender": "masculine",
          "ipa": "sol"
        },
        "fr": {
          "word": "le soleil",
          "gender": "masculine",
          "ipa": "sɔlɛj"
        },
        "de": {
          "word": "die Sonne",
          "gender": "feminine",
          "ipa": "ˈzɔnə"
        },
        "ko": {
          "word": "태양",
          "gender": "none",
          "ipa": "tʰɛ.jaŋ"
        }
      },
      {
        "id": "tree",
        "en": "tree",
        "x": 40,
        "y": 38,
        "es": {
          "word": "el árbol",
          "gender": "masculine",
          "ipa": "ˈaɾbol"
        },
        "fr": {
          "word": "l’arbre",
          "gender": "masculine",
          "ipa": "aʁbʁ"
        },
        "de": {
          "word": "der Baum",
          "gender": "masculine",
          "ipa": "baʊ̯m"
        },
        "ko": {
          "word": "나무",
          "gender": "none",
          "ipa": "na.mu"
        }
      },
      {
        "id": "shadow",
        "en": "shadow",
        "x": 80,
        "y": 82,
        "es": {
          "word": "la sombra",
          "gender": "feminine",
          "ipa": "ˈsombɾa"
        },
        "fr": {
          "word": "l’ombre",
          "gender": "feminine",
          "ipa": "ɔ̃bʁ"
        },
        "de": {
          "word": "der Schatten",
          "gender": "masculine",
          "ipa": "ˈʃatn̩"
        },
        "ko": {
          "word": "그림자",
          "gender": "none",
          "ipa": "kɯ.ɾim.dʑa"
        }
      }
    ],
    "ispy": {
      "es": {
        "clue": "Veo, veo… algo que es alto, negro y da luz por la noche.",
        "clueEn": "I spy… something that is tall and black and gives light at night.",
        "answer": "la farola",
        "choices": [
          "la palmera",
          "el sol",
          "la farola",
          "la sombra"
        ]
      },
      "fr": {
        "clue": "Je vois, je vois… quelque chose qui est grand, noir et qui éclaire la nuit.",
        "clueEn": "I spy… something that is tall and black and gives light at night.",
        "answer": "le lampadaire",
        "choices": [
          "le lampadaire",
          "le soleil",
          "l’ombre",
          "le palmier"
        ]
      },
      "de": {
        "clue": "Ich sehe was, was du nicht siehst: etwas, das hoch und schwarz ist und nachts Licht spendet.",
        "clueEn": "I spy… something that is tall and black and gives light at night.",
        "answer": "die Laterne",
        "choices": [
          "die Palme",
          "die Sonne",
          "die Laterne",
          "der Schatten"
        ]
      },
      "ko": {
        "clue": "키가 크고 검은색이며 밤에 불을 밝혀주는 것이 보여요.",
        "clueEn": "I spy… something that is tall and black and gives light at night.",
        "answer": "가로등",
        "choices": [
          "가로등",
          "태양",
          "그림자",
          "야자수"
        ]
      }
    },
    "blankWordId": "palm-tree",
    "blank": {
      "es": {
        "sentence": "Hay dos ___ altas.",
        "en": "There are two tall palm trees.",
        "answer": "palmeras",
        "options": [
          "palmeras",
          "palmera"
        ]
      },
      "fr": {
        "sentence": "Il y a deux grands ___.",
        "en": "There are two tall palm trees.",
        "answer": "palmiers",
        "options": [
          "palmier",
          "palmiers"
        ]
      },
      "de": {
        "sentence": "Es gibt zwei hohe ___.",
        "en": "There are two tall palm trees.",
        "answer": "Palmen",
        "options": [
          "Palme",
          "Palmen"
        ]
      },
      "ko": {
        "sentence": "두 그루의 키 큰 ___가 있어요.",
        "en": "There are two tall palm trees.",
        "answer": "야자수",
        "options": [
          "야자수",
          "나무"
        ]
      }
    },
    "build": {
      "es": {
        "en": "The sun shines behind the trees.",
        "tokens": [
          "El",
          "sol",
          "brilla",
          "detrás",
          "de",
          "los",
          "árboles."
        ]
      },
      "fr": {
        "en": "The sun shines behind the trees.",
        "tokens": [
          "Le",
          "soleil",
          "brille",
          "derrière",
          "les",
          "arbres."
        ]
      },
      "de": {
        "en": "The sun shines behind the trees.",
        "tokens": [
          "Die",
          "Sonne",
          "scheint",
          "hinter",
          "den",
          "Bäumen."
        ]
      },
      "ko": {
        "en": "The sun shines behind the trees.",
        "tokens": [
          "나무",
          "뒤로",
          "해가",
          "빛나요."
        ]
      }
    },
    "journal": {
      "es": {
        "title": "Un paseo al atardecer",
        "body": "Al atardecer paseé por la plaza con mis amigos. El sol brillaba entre las palmeras y nuestras sombras eran muy largas. Luego nos sentamos cerca de una farola antigua."
      },
      "fr": {
        "title": "Balade au soleil couchant",
        "body": "Ce soir, j’ai fait une balade sur la place avec mes amis. Le soleil brillait entre les palmiers et nos ombres étaient très longues. Ensuite, on s’est assis près d’un vieux lampadaire."
      },
      "de": {
        "title": "Spaziergang im Abendlicht",
        "body": "Am Abend bin ich mit meinen Freunden über den Platz spaziert. Die Sonne schien durch die Palmen und unsere Schatten waren sehr lang. Danach haben wir uns an eine alte Laterne gesetzt."
      },
      "ko": {
        "title": "노을 속 산책",
        "body": "오늘 저녁 친구들과 광장을 산책했어요. 야자수 사이로 해가 비쳤고 우리의 그림자가 길게 드리워졌어요. 그 후 우리는 오래된 가로등 근처에 앉았어요."
      }
    }
  },
  {
    "id": "mountain-chalet",
    "photo": "/photos/mountain-chalet.jpg",
    "title": "Mountain weekend",
    "place": "Somewhere in the Alps",
    "width": 1200,
    "height": 800,
    "alt": "Wooden chalet with a cantilevered swimming pool among pine trees, a village church spire and forested mountains beyond",
    "words": [
      {
        "id": "house",
        "en": "house",
        "x": 70,
        "y": 29,
        "es": {
          "word": "la casa",
          "gender": "feminine",
          "ipa": "ˈkasa"
        },
        "fr": {
          "word": "la maison",
          "gender": "feminine",
          "ipa": "mɛzɔ̃"
        },
        "de": {
          "word": "das Haus",
          "gender": "neuter",
          "ipa": "haʊ̯s"
        },
        "ko": {
          "word": "집",
          "gender": "none",
          "ipa": "tɕip"
        }
      },
      {
        "id": "balcony",
        "en": "balcony",
        "x": 70,
        "y": 42,
        "es": {
          "word": "el balcón",
          "gender": "masculine",
          "ipa": "balˈkon"
        },
        "fr": {
          "word": "le balcon",
          "gender": "masculine",
          "ipa": "balkɔ̃"
        },
        "de": {
          "word": "der Balkon",
          "gender": "masculine",
          "ipa": "balˈkɔŋ"
        },
        "ko": {
          "word": "발코니",
          "gender": "none",
          "ipa": "pal.kʰo.ni"
        }
      },
      {
        "id": "pool",
        "en": "pool",
        "x": 52,
        "y": 59,
        "es": {
          "word": "la piscina",
          "gender": "feminine",
          "ipa": "pisˈθina"
        },
        "fr": {
          "word": "la piscine",
          "gender": "feminine",
          "ipa": "pisin"
        },
        "de": {
          "word": "der Pool",
          "gender": "masculine",
          "ipa": "puːl"
        },
        "ko": {
          "word": "수영장",
          "gender": "none",
          "ipa": "su.jʌŋ.dʑaŋ"
        }
      },
      {
        "id": "church",
        "en": "church",
        "x": 16,
        "y": 42,
        "es": {
          "word": "la iglesia",
          "gender": "feminine",
          "ipa": "iˈɡlesja"
        },
        "fr": {
          "word": "l’église",
          "gender": "feminine",
          "ipa": "eɡliz"
        },
        "de": {
          "word": "die Kirche",
          "gender": "feminine",
          "ipa": "ˈkɪʁçə"
        },
        "ko": {
          "word": "교회",
          "gender": "none",
          "ipa": "kjo.hø"
        }
      },
      {
        "id": "tree",
        "en": "tree",
        "x": 88,
        "y": 55,
        "es": {
          "word": "el árbol",
          "gender": "masculine",
          "ipa": "ˈaɾbol"
        },
        "fr": {
          "word": "l’arbre",
          "gender": "masculine",
          "ipa": "aʁbʁ"
        },
        "de": {
          "word": "der Baum",
          "gender": "masculine",
          "ipa": "baʊ̯m"
        },
        "ko": {
          "word": "나무",
          "gender": "none",
          "ipa": "na.mu"
        }
      }
    ],
    "ispy": {
      "es": {
        "clue": "Veo, veo… algo que es blanco y tiene una torre muy alta.",
        "clueEn": "I spy… something that is white and has a very tall tower.",
        "answer": "la iglesia",
        "choices": [
          "la iglesia",
          "el árbol",
          "la piscina",
          "la casa"
        ]
      },
      "fr": {
        "clue": "Je vois, je vois… quelque chose qui est blanc et qui a un clocher pointu.",
        "clueEn": "I spy… something that is white and has a pointed bell tower.",
        "answer": "l’église",
        "choices": [
          "la maison",
          "la piscine",
          "l’arbre",
          "l’église"
        ]
      },
      "de": {
        "clue": "Ich sehe was, was du nicht siehst: etwas, das weiß ist und einen spitzen Turm hat.",
        "clueEn": "I spy… something that is white and has a very tall tower.",
        "answer": "die Kirche",
        "choices": [
          "die Kirche",
          "der Baum",
          "der Pool",
          "das Haus"
        ]
      },
      "ko": {
        "clue": "하얀색이고 뾰족한 탑이 있는 것이 보여요.",
        "clueEn": "I spy… something that is white and has a very tall tower.",
        "answer": "교회",
        "choices": [
          "집",
          "수영장",
          "나무",
          "교회"
        ]
      }
    },
    "blankWordId": "tree",
    "blank": {
      "es": {
        "sentence": "Los ___ son muy altos.",
        "en": "The trees are very tall.",
        "answer": "árboles",
        "options": [
          "árbol",
          "árboles"
        ]
      },
      "fr": {
        "sentence": "Les ___ sont très hauts.",
        "en": "The trees are very tall.",
        "answer": "arbres",
        "options": [
          "arbres",
          "arbre"
        ]
      },
      "de": {
        "sentence": "Die ___ sind sehr hoch.",
        "en": "The trees are very tall.",
        "answer": "Bäume",
        "options": [
          "Baum",
          "Bäume"
        ]
      },
      "ko": {
        "sentence": "___가 아주 높아요.",
        "en": "The trees are very tall.",
        "answer": "나무",
        "options": [
          "나무",
          "집"
        ]
      }
    },
    "build": {
      "es": {
        "en": "The house has a big pool.",
        "tokens": [
          "La",
          "casa",
          "tiene",
          "una",
          "piscina",
          "grande."
        ]
      },
      "fr": {
        "en": "The house has a big pool.",
        "tokens": [
          "La",
          "maison",
          "a",
          "une",
          "grande",
          "piscine."
        ]
      },
      "de": {
        "en": "The house has a big pool.",
        "tokens": [
          "Das",
          "Haus",
          "hat",
          "einen",
          "großen",
          "Pool."
        ]
      },
      "ko": {
        "en": "The house has a big pool.",
        "tokens": [
          "집에",
          "큰",
          "수영장이",
          "있어요."
        ]
      }
    },
    "journal": {
      "es": {
        "title": "Días en la montaña",
        "body": "Este fin de semana dormí en una casa de madera. Por la mañana nadé en la piscina y, desde el balcón, vi la iglesia del pueblo."
      },
      "fr": {
        "title": "Un week-end à la montagne",
        "body": "Ce week-end, j’ai dormi dans une maison en bois. Le matin, j’ai nagé dans la piscine et, depuis le balcon, j’ai vu l’église du village."
      },
      "de": {
        "title": "Tage in den Bergen",
        "body": "Dieses Wochenende habe ich in einem Holzhaus geschlafen. Am Morgen bin ich im Pool geschwommen und habe vom Balkon aus die Dorfkirche gesehen."
      },
      "ko": {
        "title": "산에서의 주말",
        "body": "이번 주말 통나무집에서 묵었어요. 아침에 수영장에서 수영을 하고 발코니에서 마을 교회를 바라보았어요."
      }
    }
  }
];

export function getScene(id: string): Scene | undefined {
  return scenes.find(scene => scene.id === id);
}
