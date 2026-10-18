export type WordClass = "noun" | "verb" | "adjective" | "adverb" | "pronoun" | "preposition" | "conjunction" | "interjection" | "determiner" | "phrase" | "other";
export type VocabStatus = "new" | "learning" | "mastered";
export type Gender = "la" | "el" | "le" | "l'" | "der" | "die" | "das" | null;
/** Definite articles accepted as noun gender values. */
export const GENDER_ARTICLES: ReadonlySet<string> = new Set([
  "la", "el", "le", "l'", "der", "die", "das",
]);

export type LanguageItem = {
  id: string;
  word: string;
  translation: string;
  wordClass: WordClass;
  gender: Gender;
  marker: number;
  /** marker position on the scene, in percent of width/height */
  x: number;
  y: number;
  example: string;
  exampleTranslation: string;
  attributes?: Record<string, string>;
};

export type Scene = {
  sessionId?: string;
  isUploaded?: boolean;
  imageUrl: string | null;
  mediaAssetId: string;
  languageCode: string;
  id: string;
  title: string;
  blurb: string;
  language: string;
  items: LanguageItem[];
};

export type SceneSummary = Pick<Scene, "id" | "mediaAssetId" | "imageUrl" | "title" | "blurb">;

export type ScenarioProgress = {
  sceneId: string;
  sessionId: string;
  mediaAssetId: string;
  title: string;
  status: "in-progress" | "completed" | "mastered";
  completedTaskCount: number;
  totalTaskCount: number;
  level: string;
};

export type VocabularyScene = {
  mediaAssetId: string;
  title: string;
  sceneId: string | null;
};

export type VocabRecord = {
  id: string;
  word: string;
  translation: string;
  wordClass: WordClass;
  gender: Gender;
  status: VocabStatus;
  firstLearnedAt: string | null;
  topic: string;
  sceneId: string;
  example: string;
  phoneticText?: string | null;
  scenes?: VocabularyScene[];
};

export type JournalEntry = {
  photos: { mediaAssetId: string; displayOrder: number; imageUrl: string | null }[];
  imageUrl: string | null;
  languageProfileId: string;
  id: string;
  date: string;
  title: string;
  mediaAssetId: string | null;
  body: string;
  wordsUsed: string[];
};

export type LeaderboardRow = {
  rank: number;
  name: string;
  xp: number;
  isYou?: boolean;
};

export type StreakDay = {
  date: string;
  active: boolean;
};

export type Streak = {
  current: number;
  days: StreakDay[];
};

export interface OwnershipChoice {
  sceneObjectId: string;
  pretend: boolean;
}

export interface PreferenceChoice {
  sceneObjectIds: string[];
  chosenObjectId: string | null;
  reaction: "like" | "dislike" | "skip" | null;
}

export interface MissionChoices {
  ownership?: OwnershipChoice | null;
  preference?: PreferenceChoice | null;
}

export interface TaughtChunk {
  text: string;
  translation: string;
}

export interface A0MissionSnapshot {
  missionId: "M04" | "M05";
  level: "A0";
  situation: "lostAndFound" | "everydayChoice";
  taughtChunks: TaughtChunk[];
  ownedObjectId?: string | null;
  pretend?: boolean | null;
  preferenceObjectIds?: string[] | null;
  chosenObjectId?: string | null;
  reaction?: "like" | "dislike" | null;
}

export interface MissionDialogueTurn {
  speaker: "server" | "linguini" | "learner";
  text: string;
  translation?: string | null;
}

export interface MissionQuestionOutcome {
  text: string;
  kind: "returned" | "basket" | "leftBehind";
  sceneObjectId: string;
}

export interface MissionQuestionFields {
  gapType?: "chunkChoice" | "pictureToBlank" | "audioGap" | "dialogueGap" | "typedGap" | null;
  dialogue?: MissionDialogueTurn[] | null;
  optionObjectIds?: Record<string, string> | null;
  optionIcons?: Record<string, "belongs" | "likes" | "like" | "dislike"> | null;
  completeTranslation?: string | null;
  outcome?: MissionQuestionOutcome | null;
  correctNote?: string | null;
  typedAllowed?: boolean | null;
}
