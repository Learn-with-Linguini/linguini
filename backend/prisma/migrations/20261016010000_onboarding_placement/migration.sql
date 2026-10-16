BEGIN;

CREATE TABLE public.onboarding_placement_questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    language_code VARCHAR(35) NOT NULL,
    question_key VARCHAR(80) NOT NULL,
    order_index INTEGER NOT NULL,
    prompt TEXT NOT NULL,
    skill VARCHAR(32) NOT NULL,
    difficulty VARCHAR(2) NOT NULL CHECK (difficulty IN ('A0', 'A1', 'A2')),
    options JSONB NOT NULL,
    correct_option VARCHAR(40) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (language_code, question_key)
);
CREATE INDEX onboarding_questions_language_active_order_idx
    ON public.onboarding_placement_questions(language_code, is_active, order_index);

CREATE TABLE public.onboarding_placement_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    language_code VARCHAR(35) NOT NULL,
    pathway VARCHAR(16) NOT NULL CHECK (pathway IN ('beginner', 'placement')),
    answers JSONB NOT NULL DEFAULT '{}',
    correct_count INTEGER NOT NULL CHECK (correct_count >= 0),
    assigned_level VARCHAR(2) NOT NULL CHECK (assigned_level IN ('A0', 'A1', 'A2')),
    scoring_version VARCHAR(40) NOT NULL DEFAULT 'placement-v1',
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX onboarding_attempts_user_completed_idx
    ON public.onboarding_placement_attempts(user_id, completed_at);
CREATE INDEX onboarding_attempts_language_idx
    ON public.onboarding_placement_attempts(language_code);

INSERT INTO public.onboarding_placement_questions
    (language_code, question_key, order_index, prompt, skill, difficulty, options, correct_option)
VALUES
('es','drink',1,'¿Qué está bebiendo el hombre?','vocabulary','A0','[{"value":"cup","label":"Una taza"},{"value":"book","label":"Un libro"},{"value":"apple","label":"Una manzana"}]','cup'),
('es','cup-color',2,'¿De qué color es la taza junto al libro?','attribute','A0','[{"value":"blue","label":"Azul"},{"value":"red","label":"Roja"},{"value":"green","label":"Verde"}]','blue'),
('es','apple-count',3,'¿Cuántas manzanas hay en la mesa?','quantity','A1','[{"value":"two","label":"Dos"},{"value":"three","label":"Tres"},{"value":"four","label":"Cuatro"}]','three'),
('es','bag-location',4,'¿Dónde está el bolso?','relationship','A1','[{"value":"under","label":"Debajo de la silla"},{"value":"on","label":"Encima de la mesa"},{"value":"behind","label":"Detrás de la puerta"}]','under'),
('es','reader-action',5,'¿Qué está haciendo la mujer sentada?','action','A2','[{"value":"reading","label":"Está leyendo un libro"},{"value":"eating","label":"Está comiendo"},{"value":"writing","label":"Está escribiendo"}]','reading'),
('es','scene-sentence',6,'¿Qué frase describe mejor la escena?','comprehension','A2','[{"value":"best","label":"Dos personas están sentadas mientras una camarera lleva un plato"},{"value":"park","label":"Los niños juegan en un parque"},{"value":"empty","label":"El café está vacío"}]','best'),

('fr','drink',1,'Qu’est-ce que l’homme boit ?','vocabulary','A0','[{"value":"cup","label":"Une tasse"},{"value":"book","label":"Un livre"},{"value":"apple","label":"Une pomme"}]','cup'),
('fr','cup-color',2,'De quelle couleur est la tasse près du livre ?','attribute','A0','[{"value":"blue","label":"Bleue"},{"value":"red","label":"Rouge"},{"value":"green","label":"Verte"}]','blue'),
('fr','apple-count',3,'Combien de pommes y a-t-il sur la table ?','quantity','A1','[{"value":"two","label":"Deux"},{"value":"three","label":"Trois"},{"value":"four","label":"Quatre"}]','three'),
('fr','bag-location',4,'Où est le sac ?','relationship','A1','[{"value":"under","label":"Sous la chaise"},{"value":"on","label":"Sur la table"},{"value":"behind","label":"Derrière la porte"}]','under'),
('fr','reader-action',5,'Que fait la femme assise ?','action','A2','[{"value":"reading","label":"Elle lit un livre"},{"value":"eating","label":"Elle mange"},{"value":"writing","label":"Elle écrit"}]','reading'),
('fr','scene-sentence',6,'Quelle phrase décrit le mieux la scène ?','comprehension','A2','[{"value":"best","label":"Deux personnes sont assises pendant qu’une serveuse porte une assiette"},{"value":"park","label":"Des enfants jouent dans un parc"},{"value":"empty","label":"Le café est vide"}]','best'),

('de','drink',1,'Was trinkt der Mann?','vocabulary','A0','[{"value":"cup","label":"Eine Tasse"},{"value":"book","label":"Ein Buch"},{"value":"apple","label":"Einen Apfel"}]','cup'),
('de','cup-color',2,'Welche Farbe hat die Tasse neben dem Buch?','attribute','A0','[{"value":"blue","label":"Blau"},{"value":"red","label":"Rot"},{"value":"green","label":"Grün"}]','blue'),
('de','apple-count',3,'Wie viele Äpfel liegen auf dem Tisch?','quantity','A1','[{"value":"two","label":"Zwei"},{"value":"three","label":"Drei"},{"value":"four","label":"Vier"}]','three'),
('de','bag-location',4,'Wo ist die Tasche?','relationship','A1','[{"value":"under","label":"Unter dem Stuhl"},{"value":"on","label":"Auf dem Tisch"},{"value":"behind","label":"Hinter der Tür"}]','under'),
('de','reader-action',5,'Was macht die sitzende Frau?','action','A2','[{"value":"reading","label":"Sie liest ein Buch"},{"value":"eating","label":"Sie isst"},{"value":"writing","label":"Sie schreibt"}]','reading'),
('de','scene-sentence',6,'Welcher Satz beschreibt die Szene am besten?','comprehension','A2','[{"value":"best","label":"Zwei Personen sitzen, während eine Kellnerin einen Teller trägt"},{"value":"park","label":"Kinder spielen in einem Park"},{"value":"empty","label":"Das Café ist leer"}]','best'),

('ko','drink',1,'남자는 무엇을 마시고 있나요?','vocabulary','A0','[{"value":"cup","label":"컵"},{"value":"book","label":"책"},{"value":"apple","label":"사과"}]','cup'),
('ko','cup-color',2,'책 옆에 있는 컵은 무슨 색인가요?','attribute','A0','[{"value":"blue","label":"파란색"},{"value":"red","label":"빨간색"},{"value":"green","label":"초록색"}]','blue'),
('ko','apple-count',3,'테이블 위에 사과가 몇 개 있나요?','quantity','A1','[{"value":"two","label":"두 개"},{"value":"three","label":"세 개"},{"value":"four","label":"네 개"}]','three'),
('ko','bag-location',4,'가방은 어디에 있나요?','relationship','A1','[{"value":"under","label":"의자 아래에 있어요"},{"value":"on","label":"테이블 위에 있어요"},{"value":"behind","label":"문 뒤에 있어요"}]','under'),
('ko','reader-action',5,'앉아 있는 여자는 무엇을 하고 있나요?','action','A2','[{"value":"reading","label":"책을 읽고 있어요"},{"value":"eating","label":"음식을 먹고 있어요"},{"value":"writing","label":"글을 쓰고 있어요"}]','reading'),
('ko','scene-sentence',6,'이 장면을 가장 잘 설명하는 문장은 무엇인가요?','comprehension','A2','[{"value":"best","label":"두 사람이 앉아 있고 직원이 접시를 들고 있어요"},{"value":"park","label":"아이들이 공원에서 놀고 있어요"},{"value":"empty","label":"카페가 비어 있어요"}]','best');

COMMIT;
