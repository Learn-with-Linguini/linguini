import type { Scene } from "./types";

/**
 * Demo scenes for the landing page's "try it" session. Marker positions are
 * percentages of the photo and were checked against annotated renders.
 * IPA is a broad transcription of the noun without its article
 * (Spain Spanish with θ; standard Parisian French).
 */
export const scenes: Scene[] = [
  {
    id: "hillside-street",
    photo: "/photos/hillside-street.jpg",
    title: "Hillside drive",
    place: "A steep city street",
    width: 1570,
    height: 1047,
    alt: "Winding red-brick street lined with flowering hydrangea hedges, pastel hillside houses and a red car in warm evening light",
    words: [
      {
        id: "car",
        en: "car",
        x: 47,
        y: 62,
        es: { word: "el coche", gender: "masculine", ipa: "ˈkotʃe" },
        fr: { word: "la voiture", gender: "feminine", ipa: "vwatyʁ" },
      },
      {
        id: "house",
        en: "house",
        x: 58,
        y: 33,
        es: { word: "la casa", gender: "feminine", ipa: "ˈkasa" },
        fr: { word: "la maison", gender: "feminine", ipa: "mɛzɔ̃" },
      },
      {
        id: "tree",
        en: "tree",
        x: 84,
        y: 52,
        es: { word: "el árbol", gender: "masculine", ipa: "ˈaɾbol" },
        fr: { word: "l’arbre", gender: "masculine", ipa: "aʁbʁ" },
      },
      {
        id: "flower",
        en: "flower",
        x: 18,
        y: 66,
        es: { word: "la flor", gender: "feminine", ipa: "floɾ" },
        fr: { word: "la fleur", gender: "feminine", ipa: "flœʁ" },
      },
      {
        id: "street",
        en: "street",
        x: 50,
        y: 86,
        es: { word: "la calle", gender: "feminine", ipa: "ˈkaʎe" },
        fr: { word: "la rue", gender: "feminine", ipa: "ʁy" },
      },
    ],
    ispy: {
      es: {
        clue: "Veo, veo… algo que es rojo y tiene cuatro ruedas.",
        clueEn: "I spy… something that is red and has four wheels.",
        answer: "el coche",
        choices: ["la casa", "el coche", "el árbol", "la calle"],
      },
      fr: {
        clue: "Je vois, je vois… quelque chose qui est rouge et qui a quatre roues.",
        clueEn: "I spy… something that is red and has four wheels.",
        answer: "la voiture",
        choices: ["la maison", "l’arbre", "la voiture", "la rue"],
      },
    },
    blank: {
      es: {
        sentence: "Hay muchas ___ al lado de la calle.",
        en: "There are lots of flowers beside the street.",
        answer: "flores",
        options: ["flor", "flores"],
      },
      fr: {
        sentence: "Il y a beaucoup de ___ au bord de la rue.",
        en: "There are lots of flowers along the street.",
        answer: "fleurs",
        options: ["fleurs", "fleur"],
      },
    },
    build: {
      es: {
        en: "The red car is on the street.",
        tokens: ["El", "coche", "rojo", "está", "en", "la", "calle."],
      },
      fr: {
        en: "The red car is in the street.",
        tokens: ["La", "voiture", "rouge", "est", "dans", "la", "rue."],
      },
    },
    journal: {
      es: {
        title: "Una calle con flores",
        body: "Hoy subí una calle muy bonita. Había flores por todas partes y un coche rojo bajaba despacio. ¡Quiero vivir en una de esas casas!",
      },
      fr: {
        title: "Une rue fleurie",
        body: "Aujourd’hui, j’ai monté une jolie rue à pied. Il y avait des fleurs partout et une voiture rouge descendait lentement. Je voudrais vivre dans une de ces maisons.",
      },
    },
  },
  {
    id: "golden-gate-bridge",
    photo: "/photos/golden-gate-bridge.jpg",
    title: "Across the bay",
    place: "San Francisco",
    width: 1570,
    height: 1047,
    alt: "The red Golden Gate Bridge crossing blue water, with cars on the deck and wooded hills and houses behind",
    words: [
      {
        id: "bridge",
        en: "bridge",
        x: 60,
        y: 61,
        es: { word: "el puente", gender: "masculine", ipa: "ˈpwente" },
        fr: { word: "le pont", gender: "masculine", ipa: "pɔ̃" },
      },
      {
        id: "tower",
        en: "tower",
        x: 95,
        y: 30,
        es: { word: "la torre", gender: "feminine", ipa: "ˈtore" },
        fr: { word: "la tour", gender: "feminine", ipa: "tuʁ" },
      },
      {
        id: "car",
        en: "car",
        x: 19,
        y: 70,
        es: { word: "el coche", gender: "masculine", ipa: "ˈkotʃe" },
        fr: { word: "la voiture", gender: "feminine", ipa: "vwatyʁ" },
      },
      {
        id: "sea",
        en: "sea",
        x: 65,
        y: 84,
        es: { word: "el mar", gender: "masculine", ipa: "maɾ" },
        fr: { word: "la mer", gender: "feminine", ipa: "mɛʁ" },
      },
      {
        id: "hill",
        en: "hill",
        x: 45,
        y: 22,
        es: { word: "la colina", gender: "feminine", ipa: "koˈlina" },
        fr: { word: "la colline", gender: "feminine", ipa: "kɔlin" },
      },
    ],
    ispy: {
      es: {
        clue: "Veo, veo… algo que es azul y está debajo del puente.",
        clueEn: "I spy… something that is blue and is under the bridge.",
        answer: "el mar",
        choices: ["el coche", "la torre", "el mar", "la colina"],
      },
      fr: {
        clue: "Je vois, je vois… quelque chose qui est bleu et qui est sous le pont.",
        clueEn: "I spy… something that is blue and is under the bridge.",
        answer: "la mer",
        choices: ["la colline", "la mer", "la voiture", "la tour"],
      },
    },
    blank: {
      es: {
        sentence: "Hay muchos ___ en el puente.",
        en: "There are lots of cars on the bridge.",
        answer: "coches",
        options: ["coche", "coches"],
      },
      fr: {
        sentence: "Il y a beaucoup de ___ sur le pont.",
        en: "There are lots of cars on the bridge.",
        answer: "voitures",
        options: ["voitures", "voiture"],
      },
    },
    build: {
      es: {
        en: "The red bridge is over the sea.",
        tokens: ["El", "puente", "rojo", "está", "sobre", "el", "mar."],
      },
      fr: {
        en: "The red bridge is above the sea.",
        tokens: ["Le", "pont", "rouge", "est", "au-dessus", "de", "la", "mer."],
      },
    },
    journal: {
      es: {
        title: "El puente rojo",
        body: "Hoy crucé el puente en coche. Desde el puente vi el mar azul y las colinas verdes. ¡La torre roja es enorme!",
      },
      fr: {
        title: "Le pont rouge",
        body: "Aujourd’hui, j’ai traversé le pont en voiture. Depuis le pont, j’ai vu la mer bleue et les collines vertes. La tour rouge est vraiment immense.",
      },
    },
  },
  {
    id: "cafe-interior",
    photo: "/photos/cafe-interior.jpg",
    title: "Café morning",
    place: "A city café",
    width: 1900,
    height: 710,
    alt: "Sunlit café seen from above, with bar stools at a long counter, a wooden coffee table, leather sofas and a tall grandfather clock",
    words: [
      {
        id: "stool",
        en: "stool",
        x: 32,
        y: 60,
        es: { word: "el taburete", gender: "masculine", ipa: "tabuˈɾete" },
        fr: { word: "le tabouret", gender: "masculine", ipa: "tabuʁɛ" },
      },
      {
        id: "table",
        en: "table",
        x: 45,
        y: 78,
        es: { word: "la mesa", gender: "feminine", ipa: "ˈmesa" },
        fr: { word: "la table", gender: "feminine", ipa: "tabl" },
      },
      {
        id: "sofa",
        en: "sofa",
        x: 81,
        y: 78,
        es: { word: "el sofá", gender: "masculine", ipa: "soˈfa" },
        fr: { word: "le canapé", gender: "masculine", ipa: "kanape" },
      },
      {
        id: "lamp",
        en: "lamp",
        x: 76,
        y: 60,
        es: { word: "la lámpara", gender: "feminine", ipa: "ˈlampaɾa" },
        fr: { word: "la lampe", gender: "feminine", ipa: "lɑ̃p" },
      },
      {
        id: "clock",
        en: "clock",
        x: 86,
        y: 30,
        es: { word: "el reloj", gender: "masculine", ipa: "reˈlox" },
        fr: { word: "l’horloge", gender: "feminine", ipa: "ɔʁlɔʒ" },
      },
    ],
    ispy: {
      es: {
        clue: "Veo, veo… algo que es alto y marca la hora.",
        clueEn: "I spy… something that is tall and tells the time.",
        answer: "el reloj",
        choices: ["el sofá", "la lámpara", "el taburete", "el reloj"],
      },
      fr: {
        clue: "Je vois, je vois… quelque chose qui est grand et qui donne l’heure.",
        clueEn: "I spy… something that is tall and tells the time.",
        answer: "l’horloge",
        choices: ["le canapé", "l’horloge", "la lampe", "le tabouret"],
      },
    },
    blank: {
      es: {
        sentence: "Los ___ son marrones.",
        en: "The sofas are brown.",
        answer: "sofás",
        options: ["sofás", "sofá"],
      },
      fr: {
        sentence: "Les ___ sont marron.",
        en: "The sofas are brown.",
        answer: "canapés",
        options: ["canapé", "canapés"],
      },
    },
    build: {
      es: {
        en: "I have a coffee on the sofa.",
        tokens: ["Tomo", "un", "café", "en", "el", "sofá."],
      },
      fr: {
        en: "I drink a coffee on the sofa.",
        tokens: ["Je", "bois", "un", "café", "sur", "le", "canapé."],
      },
    },
    journal: {
      es: {
        title: "Una mañana en la cafetería",
        body: "Esta mañana tomé un té en una cafetería preciosa. Leí un libro en un sofá de piel, cerca de una mesa de madera. Un reloj muy alto marcaba las diez.",
      },
      fr: {
        title: "Un matin au café",
        body: "Ce matin, j’ai pris un thé dans un joli café. J’ai lu un livre sur un canapé en cuir, près d’une table en bois. Une grande horloge indiquait dix heures.",
      },
    },
  },
  {
    id: "desk-flatlay",
    photo: "/photos/desk-flatlay.jpg",
    title: "Study day",
    place: "A home office",
    width: 1900,
    height: 1267,
    alt: "White desk seen from above with an open notebook, a yellow pencil, a pair of glasses, a smartphone, a laptop and a potted plant",
    words: [
      {
        id: "notebook",
        en: "notebook",
        x: 38,
        y: 52,
        es: { word: "la libreta", gender: "feminine", ipa: "liˈbɾeta" },
        fr: { word: "le cahier", gender: "masculine", ipa: "kaje" },
      },
      {
        id: "pencil",
        en: "pencil",
        x: 76,
        y: 60,
        es: { word: "el lápiz", gender: "masculine", ipa: "ˈlapiθ" },
        fr: { word: "le crayon", gender: "masculine", ipa: "kʁɛjɔ̃" },
      },
      {
        id: "laptop",
        en: "laptop",
        x: 90,
        y: 24,
        es: { word: "el portátil", gender: "masculine", ipa: "poɾˈtatil" },
        fr: { word: "l’ordinateur", gender: "masculine", ipa: "ɔʁdinatœʁ" },
      },
      {
        id: "phone",
        en: "phone",
        x: 11,
        y: 65,
        es: { word: "el móvil", gender: "masculine", ipa: "ˈmobil" },
        fr: { word: "le téléphone", gender: "masculine", ipa: "telefɔn" },
      },
      {
        id: "plant",
        en: "plant",
        x: 17,
        y: 10,
        es: { word: "la planta", gender: "feminine", ipa: "ˈplanta" },
        fr: { word: "la plante", gender: "feminine", ipa: "plɑ̃t" },
      },
    ],
    ispy: {
      es: {
        clue: "Veo, veo… algo que es amarillo y sirve para escribir.",
        clueEn: "I spy… something that is yellow and is used for writing.",
        answer: "el lápiz",
        choices: ["el lápiz", "el móvil", "la libreta", "la planta"],
      },
      fr: {
        clue: "Je vois, je vois… quelque chose qui est jaune et qui sert à écrire.",
        clueEn: "I spy… something that is yellow and is used for writing.",
        answer: "le crayon",
        choices: ["la plante", "le téléphone", "le crayon", "le cahier"],
      },
    },
    blank: {
      es: {
        sentence: "La libreta tiene dos ___ blancas.",
        en: "The notebook has two white pages.",
        answer: "páginas",
        options: ["página", "páginas"],
      },
      fr: {
        sentence: "Le cahier a deux ___ blanches.",
        en: "The notebook has two white pages.",
        answer: "pages",
        options: ["pages", "page"],
      },
    },
    build: {
      es: {
        en: "I write in my new notebook.",
        tokens: ["Escribo", "en", "mi", "libreta", "nueva."],
      },
      fr: {
        en: "I write in my new notebook.",
        tokens: ["J’écris", "dans", "mon", "nouveau", "cahier."],
      },
    },
    journal: {
      es: {
        title: "Un día de estudio",
        body: "Hoy estudié en casa toda la mañana. Escribí diez palabras nuevas en mi libreta con un lápiz amarillo. Después puse el móvil en silencio y regué la planta.",
      },
      fr: {
        title: "Une matinée d’étude",
        body: "Aujourd’hui, j’ai étudié chez moi toute la matinée. J’ai écrit dix nouveaux mots dans mon cahier avec un crayon jaune. Ensuite, j’ai mis mon téléphone en silencieux et j’ai arrosé la plante.",
      },
    },
  },
  {
    id: "paris-rooftops",
    photo: "/photos/paris-rooftops.jpg",
    title: "Paris at dusk",
    place: "Paris",
    width: 1440,
    height: 642,
    alt: "Stone gargoyle looking out over Paris rooftops at dusk, with the Seine, a bridge and the lit Eiffel Tower on the horizon",
    words: [
      {
        id: "statue",
        en: "statue",
        x: 15,
        y: 52,
        es: { word: "la estatua", gender: "feminine", ipa: "esˈtatwa" },
        fr: { word: "la statue", gender: "feminine", ipa: "staty" },
      },
      {
        id: "tower",
        en: "tower",
        x: 61,
        y: 30,
        es: { word: "la torre", gender: "feminine", ipa: "ˈtore" },
        fr: { word: "la tour", gender: "feminine", ipa: "tuʁ" },
      },
      {
        id: "bridge",
        en: "bridge",
        x: 73,
        y: 59,
        es: { word: "el puente", gender: "masculine", ipa: "ˈpwente" },
        fr: { word: "le pont", gender: "masculine", ipa: "pɔ̃" },
      },
      {
        id: "river",
        en: "river",
        x: 67,
        y: 76,
        es: { word: "el río", gender: "masculine", ipa: "ˈrio" },
        fr: { word: "le fleuve", gender: "masculine", ipa: "flœv" },
      },
      {
        id: "building",
        en: "building",
        x: 90,
        y: 72,
        es: { word: "el edificio", gender: "masculine", ipa: "ediˈfiθjo" },
        fr: { word: "le bâtiment", gender: "masculine", ipa: "batimɑ̃" },
      },
    ],
    ispy: {
      es: {
        clue: "Veo, veo… algo que es de piedra y mira la ciudad.",
        clueEn: "I spy… something that is made of stone and looks out over the city.",
        answer: "la estatua",
        choices: ["el puente", "la estatua", "la torre", "el río"],
      },
      fr: {
        clue: "Je vois, je vois… quelque chose qui est en pierre et qui regarde la ville.",
        clueEn: "I spy… something that is made of stone and looks out over the city.",
        answer: "la statue",
        choices: ["le fleuve", "le pont", "la statue", "la tour"],
      },
    },
    blank: {
      es: {
        sentence: "Dos ___ cruzan el río.",
        en: "Two bridges cross the river.",
        answer: "puentes",
        options: ["puentes", "puente"],
      },
      fr: {
        sentence: "Deux ___ traversent le fleuve.",
        en: "Two bridges cross the river.",
        answer: "ponts",
        options: ["pont", "ponts"],
      },
    },
    build: {
      es: {
        en: "The Eiffel Tower shines at night.",
        tokens: ["La", "torre", "Eiffel", "brilla", "por", "la", "noche."],
      },
      fr: {
        en: "The Eiffel Tower shines in the evening.",
        tokens: ["La", "tour", "Eiffel", "brille", "le", "soir."],
      },
    },
    journal: {
      es: {
        title: "Una tarde en París",
        body: "Esta tarde subí a lo alto de una catedral. Una estatua muy rara miraba la ciudad. Desde arriba vi el río, un puente y la torre Eiffel iluminada.",
      },
      fr: {
        title: "Un soir à Paris",
        body: "Ce soir, j’ai grimpé en haut d’une cathédrale. Une drôle de statue regardait la ville. D’en haut, j’ai vu le fleuve, un pont et la tour Eiffel qui brillait.",
      },
    },
  },
  {
    id: "alpine-castle",
    photo: "/photos/alpine-castle.jpg",
    title: "Fairy-tale castle",
    place: "Bavaria",
    width: 2000,
    height: 1335,
    alt: "White fairy-tale castle on a forested ridge above green fields and a lake, under a cloudy sky",
    words: [
      {
        id: "castle",
        en: "castle",
        x: 35,
        y: 48,
        es: { word: "el castillo", gender: "masculine", ipa: "kasˈtiʎo" },
        fr: { word: "le château", gender: "masculine", ipa: "ʃato" },
      },
      {
        id: "lake",
        en: "lake",
        x: 14,
        y: 51,
        es: { word: "el lago", gender: "masculine", ipa: "ˈlaɡo" },
        fr: { word: "le lac", gender: "masculine", ipa: "lak" },
      },
      {
        id: "forest",
        en: "forest",
        x: 50,
        y: 80,
        es: { word: "el bosque", gender: "masculine", ipa: "ˈboske" },
        fr: { word: "la forêt", gender: "feminine", ipa: "fɔʁɛ" },
      },
      {
        id: "mountain",
        en: "mountain",
        x: 91,
        y: 45,
        es: { word: "la montaña", gender: "feminine", ipa: "monˈtaɲa" },
        fr: { word: "la montagne", gender: "feminine", ipa: "mɔ̃taɲ" },
      },
      {
        id: "cloud",
        en: "cloud",
        x: 70,
        y: 18,
        es: { word: "la nube", gender: "feminine", ipa: "ˈnube" },
        fr: { word: "le nuage", gender: "masculine", ipa: "nɥaʒ" },
      },
    ],
    ispy: {
      es: {
        clue: "Veo, veo… algo que es azul y está a la izquierda del castillo.",
        clueEn: "I spy… something that is blue and is to the left of the castle.",
        answer: "el lago",
        choices: ["el bosque", "la nube", "la montaña", "el lago"],
      },
      fr: {
        clue: "Je vois, je vois… quelque chose qui est bleu et qui est à gauche du château.",
        clueEn: "I spy… something that is blue and is to the left of the castle.",
        answer: "le lac",
        choices: ["la forêt", "le lac", "la montagne", "le nuage"],
      },
    },
    blank: {
      es: {
        sentence: "El castillo tiene muchas ___.",
        en: "The castle has lots of towers.",
        answer: "torres",
        options: ["torre", "torres"],
      },
      fr: {
        sentence: "Le château a beaucoup de ___.",
        en: "The castle has lots of towers.",
        answer: "tours",
        options: ["tours", "tour"],
      },
    },
    build: {
      es: {
        en: "The white castle is in the forest.",
        tokens: ["El", "castillo", "blanco", "está", "en", "el", "bosque."],
      },
      fr: {
        en: "The white castle is in the forest.",
        tokens: ["Le", "château", "blanc", "est", "dans", "la", "forêt."],
      },
    },
    journal: {
      es: {
        title: "Un castillo de cuento",
        body: "Hoy caminé por el bosque hasta un castillo blanco. Parecía sacado de un cuento. Desde arriba vi un lago azul y muchas nubes.",
      },
      fr: {
        title: "Un château magique",
        body: "Aujourd’hui, j’ai marché dans la forêt jusqu’à un château blanc. C’était comme dans un conte de fées. D’en haut, j’ai vu un lac bleu et beaucoup de nuages.",
      },
    },
  },
  {
    id: "sunlit-promenade",
    photo: "/photos/sunlit-promenade.jpg",
    title: "Golden hour walk",
    place: "A sunny city square",
    width: 1950,
    height: 1300,
    alt: "City square at golden hour with ornate street lamps, palm trees, fountain mist and people walking in silhouette",
    words: [
      {
        id: "street-lamp",
        en: "street lamp",
        x: 29,
        y: 24,
        es: { word: "la farola", gender: "feminine", ipa: "faˈɾola" },
        fr: { word: "le lampadaire", gender: "masculine", ipa: "lɑ̃padɛʁ" },
      },
      {
        id: "palm-tree",
        en: "palm tree",
        x: 62,
        y: 27,
        es: { word: "la palmera", gender: "feminine", ipa: "palˈmeɾa" },
        fr: { word: "le palmier", gender: "masculine", ipa: "palmje" },
      },
      {
        id: "sun",
        en: "sun",
        x: 53,
        y: 12,
        es: { word: "el sol", gender: "masculine", ipa: "sol" },
        fr: { word: "le soleil", gender: "masculine", ipa: "sɔlɛj" },
      },
      {
        id: "tree",
        en: "tree",
        x: 40,
        y: 38,
        es: { word: "el árbol", gender: "masculine", ipa: "ˈaɾbol" },
        fr: { word: "l’arbre", gender: "masculine", ipa: "aʁbʁ" },
      },
      {
        id: "shadow",
        en: "shadow",
        x: 80,
        y: 82,
        es: { word: "la sombra", gender: "feminine", ipa: "ˈsombɾa" },
        fr: { word: "l’ombre", gender: "feminine", ipa: "ɔ̃bʁ" },
      },
    ],
    ispy: {
      es: {
        clue: "Veo, veo… algo que es alto, negro y da luz por la noche.",
        clueEn: "I spy… something that is tall and black and gives light at night.",
        answer: "la farola",
        choices: ["la palmera", "el sol", "la farola", "la sombra"],
      },
      fr: {
        clue: "Je vois, je vois… quelque chose qui est grand, noir et qui éclaire la nuit.",
        clueEn: "I spy… something that is tall and black and gives light at night.",
        answer: "le lampadaire",
        choices: ["le lampadaire", "le soleil", "l’ombre", "le palmier"],
      },
    },
    blank: {
      es: {
        sentence: "Hay dos ___ altas.",
        en: "There are two tall palm trees.",
        answer: "palmeras",
        options: ["palmeras", "palmera"],
      },
      fr: {
        sentence: "Il y a deux grands ___.",
        en: "There are two tall palm trees.",
        answer: "palmiers",
        options: ["palmier", "palmiers"],
      },
    },
    build: {
      es: {
        en: "The sun shines behind the trees.",
        tokens: ["El", "sol", "brilla", "detrás", "de", "los", "árboles."],
      },
      fr: {
        en: "The sun shines behind the trees.",
        tokens: ["Le", "soleil", "brille", "derrière", "les", "arbres."],
      },
    },
    journal: {
      es: {
        title: "Un paseo al atardecer",
        body: "Al atardecer paseé por la plaza con mis amigos. El sol brillaba entre las palmeras y nuestras sombras eran muy largas. Luego nos sentamos cerca de una farola antigua.",
      },
      fr: {
        title: "Balade au soleil couchant",
        body: "Ce soir, j’ai fait une balade sur la place avec mes amis. Le soleil brillait entre les palmiers et nos ombres étaient très longues. Ensuite, on s’est assis près d’un vieux lampadaire.",
      },
    },
  },
  {
    id: "mountain-chalet",
    photo: "/photos/mountain-chalet.jpg",
    title: "Mountain weekend",
    place: "Somewhere in the Alps",
    width: 1200,
    height: 800,
    alt: "Wooden chalet with a cantilevered swimming pool among pine trees, a village church spire and forested mountains beyond",
    words: [
      {
        id: "house",
        en: "house",
        x: 70,
        y: 29,
        es: { word: "la casa", gender: "feminine", ipa: "ˈkasa" },
        fr: { word: "la maison", gender: "feminine", ipa: "mɛzɔ̃" },
      },
      {
        id: "balcony",
        en: "balcony",
        x: 70,
        y: 42,
        es: { word: "el balcón", gender: "masculine", ipa: "balˈkon" },
        fr: { word: "le balcon", gender: "masculine", ipa: "balkɔ̃" },
      },
      {
        id: "pool",
        en: "pool",
        x: 52,
        y: 59,
        es: { word: "la piscina", gender: "feminine", ipa: "pisˈθina" },
        fr: { word: "la piscine", gender: "feminine", ipa: "pisin" },
      },
      {
        id: "church",
        en: "church",
        x: 16,
        y: 42,
        es: { word: "la iglesia", gender: "feminine", ipa: "iˈɡlesja" },
        fr: { word: "l’église", gender: "feminine", ipa: "eɡliz" },
      },
      {
        id: "tree",
        en: "tree",
        x: 88,
        y: 55,
        es: { word: "el árbol", gender: "masculine", ipa: "ˈaɾbol" },
        fr: { word: "l’arbre", gender: "masculine", ipa: "aʁbʁ" },
      },
    ],
    ispy: {
      es: {
        clue: "Veo, veo… algo que es blanco y tiene una torre muy alta.",
        clueEn: "I spy… something that is white and has a very tall tower.",
        answer: "la iglesia",
        choices: ["la iglesia", "el árbol", "la piscina", "la casa"],
      },
      fr: {
        clue: "Je vois, je vois… quelque chose qui est blanc et qui a un clocher pointu.",
        clueEn: "I spy… something that is white and has a pointed bell tower.",
        answer: "l’église",
        choices: ["la maison", "la piscine", "l’arbre", "l’église"],
      },
    },
    blank: {
      es: {
        sentence: "Los ___ son muy altos.",
        en: "The trees are very tall.",
        answer: "árboles",
        options: ["árbol", "árboles"],
      },
      fr: {
        sentence: "Les ___ sont très hauts.",
        en: "The trees are very tall.",
        answer: "arbres",
        options: ["arbres", "arbre"],
      },
    },
    build: {
      es: {
        en: "The house has a big pool.",
        tokens: ["La", "casa", "tiene", "una", "piscina", "grande."],
      },
      fr: {
        en: "The house has a big pool.",
        tokens: ["La", "maison", "a", "une", "grande", "piscine."],
      },
    },
    journal: {
      es: {
        title: "Días en la montaña",
        body: "Este fin de semana dormí en una casa de madera. Por la mañana nadé en la piscina y, desde el balcón, vi la iglesia del pueblo.",
      },
      fr: {
        title: "Un week-end à la montagne",
        body: "Ce week-end, j’ai dormi dans une maison en bois. Le matin, j’ai nagé dans la piscine et, depuis le balcon, j’ai vu l’église du village.",
      },
    },
  },
];

export function getScene(id: string): Scene | undefined {
  return scenes.find(scene => scene.id === id);
}
