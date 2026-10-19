BEGIN;

ALTER TABLE public.onboarding_placement_questions
    ADD COLUMN prompt_translation TEXT;

UPDATE public.onboarding_placement_questions
SET prompt_translation = CASE question_key
    WHEN 'drink' THEN 'What is the man drinking?'
    WHEN 'cup-color' THEN 'What colour is the cup next to the book?'
    WHEN 'apple-count' THEN 'How many apples are on the table?'
    WHEN 'bag-location' THEN 'Where is the bag?'
    WHEN 'reader-action' THEN 'What is the seated woman doing?'
    WHEN 'scene-sentence' THEN 'Which sentence best describes the scene?'
END;

ALTER TABLE public.onboarding_placement_questions
    ALTER COLUMN prompt_translation SET NOT NULL;

COMMIT;
