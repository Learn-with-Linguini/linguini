import { GENDER_ARTICLES } from "../data/types.ts";
import type { Gender, LeaderboardRow, ScenarioProgress, Streak, VocabRecord, VocabularyScene, VocabStatus, WordClass } from "../data/types";
import type { Scene, SceneSummary } from "../data/types";
import type { JournalEntry } from "../data/types";
import { getAccessToken } from "./supabase.ts";

// The Node test runner has no import.meta.env; read process.env there.
const envBaseUrl = import.meta.env?.VITE_API_BASE_URL
  ?? (globalThis as { process?: { env?: { VITE_API_BASE_URL?: string } } }).process?.env?.VITE_API_BASE_URL;
const apiBaseUrl = envBaseUrl?.replace(/\/+$/, "");

export interface UploadedImage {
  id: string;
  signedUrl: string;
  mimeType: string;
  width: number;
  height: number;
}

export function mediaImageUrl(assetId: string, width: 320 | 640 | 1280): string {
  return `${apiBaseUrl ?? ""}/api/v1/media/${encodeURIComponent(assetId)}/image?width=${width}`;
}

const MAX_UPLOAD_EDGE = 1600;

export function shouldDownscale(bytes: number, width: number, height: number): boolean {
  return bytes > 600_000 || Math.max(width, height) > MAX_UPLOAD_EDGE;
}

async function downscale(file: File): Promise<File> {
  try {
    if (typeof createImageBitmap !== "function" || typeof document === "undefined") return file;
    const canvas = document.createElement("canvas");
    if (typeof canvas.getContext !== "function") return file;
    // from-image keeps phone EXIF rotation instead of baking a sideways bitmap.
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    try {
      if (!shouldDownscale(file.size, bitmap.width, bitmap.height)) return file;
      const scale = MAX_UPLOAD_EDGE / Math.max(bitmap.width, bitmap.height);
      canvas.width = Math.max(1, Math.round(bitmap.width * Math.min(1, scale)));
      canvas.height = Math.max(1, Math.round(bitmap.height * Math.min(1, scale)));
      const context = canvas.getContext("2d");
      if (!context) return file;
      context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    } finally {
      bitmap.close();
    }
    const toBlob = (type: string, quality: number) =>
      new Promise<Blob | null>(resolve => canvas.toBlob(resolve, type, quality));
    const webp = await toBlob("image/webp", 0.82);
    const blob = webp ?? (await toBlob("image/jpeg", 0.85));
    const type = webp ? "image/webp" : "image/jpeg";
    if (!blob || blob.size >= file.size) return file;
    return new File([blob], file.name, { type });
  } catch {
    // A failed optimisation must never break the upload itself.
    return file;
  }
}

export async function uploadImage(file: File, source: "camera" | "userUpload", onPhase: (phase: string) => void): Promise<UploadedImage> {
  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) throw new Error("Choose a JPEG, PNG or WebP image.");
  if (!file.size || file.size > 10 * 1024 * 1024) throw new Error("Choose an image between 1 byte and 10 MB.");
  onPhase("Optimising image…");
  const prepared = await downscale(file);
  onPhase("Preparing upload…");
  const upload = await write<{ assetId: string; storageKey: string; uploadUrl: string }>("/api/v1/media/upload-url", "POST", {
    fileName: file.name, fileSize: prepared.size, mimeType: prepared.type, source,
  });
  onPhase("Uploading image…");
  const response = await fetch(upload.uploadUrl, {
    method: "PUT", headers: { "Content-Type": prepared.type, "x-upsert": "false" }, body: prepared,
  });
  if (!response.ok) throw new Error("Image upload failed. Please try again.");
  onPhase("Checking image…");
  // Confirmation is idempotent; retry once if the server committed but its response was lost.
  const confirm = () => write<UploadedImage>("/api/v1/media/confirm-upload", "POST", {
    assetId: upload.assetId, storageKey: upload.storageKey, source,
  });
  try { return await confirm(); } catch (error) {
    if (error instanceof Error && /HTTP 4\d\d/.test(error.message)) throw error;
    return confirm();
  }
}

// Matches the camelCase User response from GET /api/v1/me.
export interface User {
  learningGoal: string;
  microphoneEnabled: boolean;
  cameraEnabled: boolean;
  id: string;
  createdAt: string;
  updatedAt: string;
  authProviderId: string;
  displayName: string;
  email: string | null;
  timezone: string;
  onboardingCompleted: boolean;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly activeSessionId: string | null;
  constructor(message: string, status: number, code: string | null, activeSessionId: string | null) {
    super(message);
    this.status = status;
    this.code = code;
    this.activeSessionId = activeSessionId;
  }
}

async function request<T>(path: string, signal?: AbortSignal, options?: RequestInit): Promise<T> {
  if (!apiBaseUrl) {
    throw new Error("The app is still being set up. Please try again in a moment.");
  }

  let response: Response;
  try {
    const headers = new Headers(options?.headers);
    const token = await getAccessToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    response = await fetch(`${apiBaseUrl}${path}`, { ...options, headers, signal });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new Error("We couldn't connect right now. Please check your connection and try again.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message = typeof body?.detail?.message === "string" ? body.detail.message : "Request failed.";
    const code = typeof body?.detail?.code === "string" ? body.detail.code : null;
    const activeSessionId = typeof body?.detail?.activeSessionId === "string" ? body.detail.activeSessionId : null;
    throw new ApiError(message, response.status, code, activeSessionId);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function getCurrentUser(signal?: AbortSignal): Promise<User> {
  return request<User>("/api/v1/me", signal);
}

export interface LanguageProfile {
  id: string;
  userId: string;
  sourceLanguageCode: string;
  targetLanguageCode: string;
  proficiencyLevel: "A1" | "A2" | "B1" | "B2" | "C1" | "C2";
  isActive: boolean;
  dailyGoalMinutes: number | null;
  preferredInputMode: "speech" | "text" | "both";
}

export type UserPatch = Partial<Pick<User, "displayName" | "timezone" | "onboardingCompleted" | "learningGoal" | "microphoneEnabled" | "cameraEnabled">>;
export type LanguageProfilePatch = Partial<Pick<LanguageProfile, "proficiencyLevel" | "isActive" | "dailyGoalMinutes" | "preferredInputMode">>;

function write<T>(path: string, method: string, body: unknown): Promise<T> {
  return request(path, undefined, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

export const getLanguageProfiles = (signal?: AbortSignal) => request<LanguageProfile[]>("/api/v1/me/language-profiles", signal);
export const updateUser = (patch: UserPatch) => write<User>("/api/v1/me", "PATCH", patch);
export const updateLanguageProfile = (id: string, patch: LanguageProfilePatch) => write<LanguageProfile>(`/api/v1/me/language-profiles/${id}`, "PATCH", patch);
export const createLanguageProfile = (code: string, minutes = 10) => write<LanguageProfile>("/api/v1/me/language-profiles", "POST", {
  sourceLanguageCode: "en", targetLanguageCode: code, proficiencyLevel: "A1", dailyGoalMinutes: minutes,
});

export interface ProgressResponse {
  xp: number;
  scenarios: ScenarioProgress[];
  leaderboard: LeaderboardRow[];
  streak: Streak;
}

interface DailyVocabularyItem {
  vocabulary: {
    id: string;
    displayText: string;
    partOfSpeech: WordClass;
    gender: string | null;
    exampleSentence: string | null;
    phoneticText?: string | null;
  };
  translation: { translatedText: string } | null;
  progress: { status: VocabStatus; firstLearnedAt?: string | null } | null;
  sceneId: string | null;
  topic: string | null;
  scenes?: VocabularyScene[];
}

export function getProgress(signal?: AbortSignal): Promise<ProgressResponse> {
  return request<ProgressResponse>("/api/v1/me/progress", signal);
}

interface PreloadedScene {
  imageUrl?: string | null;
  mediaAsset: { id: string };
  languageCode: string;
  sceneId: string;
  title: string;
  description: string | null;
  language: string;
}

function sceneSummary(row: PreloadedScene): SceneSummary {
  return { id: row.sceneId, mediaAssetId: row.mediaAsset.id, imageUrl: row.imageUrl ?? null, title: row.title, blurb: row.description ?? "", language: row.language, languageCode: row.languageCode };
}

export async function getScenes(signal?: AbortSignal): Promise<SceneSummary[]> {
  const rows = await request<PreloadedScene[]>("/api/v1/preloaded-scenes", signal);
  return rows.map(sceneSummary);
}

export async function getSceneDetail(id: string, signal?: AbortSignal): Promise<Scene> {
  const row = await request<PreloadedScene & Pick<Scene, "items">>(
    `/api/v1/preloaded-scenes/${encodeURIComponent(id)}`, signal,
  );
  return { ...sceneSummary(row), items: row.items };
}

export async function getVocabulary(signal?: AbortSignal): Promise<VocabRecord[]> {
  const items: DailyVocabularyItem[] = [];
  let cursor: string | null = null;
  do {
    const query = cursor ? `?limit=500&cursor=${encodeURIComponent(cursor)}` : "?limit=500";
    const page: { items: DailyVocabularyItem[]; nextCursor: string | null } =
      await request(`/api/v1/me/vocabulary${query}`, signal);
    items.push(...page.items);
    cursor = page.nextCursor;
  } while (cursor);
  return items.map((item) => ({
    id: item.vocabulary.id,
    word: item.vocabulary.displayText,
    translation: item.translation?.translatedText ?? "Translation unavailable",
    wordClass: item.vocabulary.partOfSpeech,
    gender: item.vocabulary.gender != null && GENDER_ARTICLES.has(item.vocabulary.gender) ? item.vocabulary.gender as Gender : null,
    status: item.progress?.status ?? "new",
    firstLearnedAt: item.progress?.firstLearnedAt ?? null,
    topic: item.topic ?? "Uncategorised",
    sceneId: item.sceneId ?? "",
    scenes: item.scenes ?? [],
    example: item.vocabulary.exampleSentence ?? "",
    phoneticText: item.vocabulary.phoneticText ?? null,
  }));
}

interface JournalRecord {
  id: string; languageProfileId: string; localDate: string; title: string;
  selectedWords: string[]; currentRevisionId: string | null;
}
interface JournalDetail {
  media: { mediaAssetId: string; displayOrder: number }[];
  imageUrl?: string | null;
  imageUrls?: Record<string, string | null>;
  journal: JournalRecord;
  revisions: { id: string; content: string }[];
}
function journalEntry(detail: JournalDetail): JournalEntry {
  const row = detail.journal;
  const media = [...detail.media].sort((a, b) => a.displayOrder - b.displayOrder);
  return { id: row.id, languageProfileId: row.languageProfileId, date: row.localDate,
    photos: media.map((photo, index) => ({ ...photo, imageUrl: detail.imageUrls?.[photo.mediaAssetId] ?? (index === 0 ? detail.imageUrl ?? null : null) })),
    title: row.title, mediaAssetId: [...detail.media].sort((a, b) => a.displayOrder - b.displayOrder)[0]?.mediaAssetId ?? null, imageUrl: detail.imageUrl ?? null, wordsUsed: row.selectedWords,
    body: detail.revisions.find((revision) => revision.id === row.currentRevisionId)?.content ?? "" };
}
export async function getJournals(signal?: AbortSignal): Promise<JournalEntry[]> {
  return (await request<JournalDetail[]>("/api/v1/journals", signal)).map(journalEntry);
}
export async function getJournal(id: string, signal?: AbortSignal): Promise<JournalEntry> {
  return journalEntry(await request<JournalDetail>(`/api/v1/journals/${id}`, signal));
}
export interface JournalPhotoOption {
  mediaAssetId: string;
  imageUrl: string | null;
  sessionId: string;
  completedAt: string;
}
export async function getJournalContext(date?: string, signal?: AbortSignal) {
  const context = await request<{ localDate: string; journal: JournalRecord | null; eligiblePhotos: JournalPhotoOption[]; suggestedWords: string[] }>(`/api/v1/journal/${date ?? "today"}/context`, signal);
  return {
    date: context.localDate,
    entry: context.journal ? await getJournal(context.journal.id, signal) : null,
    photoOptions: context.eligiblePhotos,
    wordSuggestions: context.suggestedWords ?? [],
  };
}
export type JournalDraft = Pick<JournalEntry, "title" | "mediaAssetId" | "body" | "wordsUsed"> & { photoAssetIds?: string[] };
export async function saveJournal(draft: JournalDraft, profileId: string, id?: string, date?: string) {
  const body = { title: draft.title, ...(draft.photoAssetIds === undefined ? { mediaAssetId: draft.mediaAssetId } : {}), content: draft.body, selectedWords: draft.wordsUsed };
  const row = id ? await write<JournalRecord>(`/api/v1/journals/${id}`, "PATCH", body)
    : await write<JournalRecord>(`/api/v1/journal/${date ?? "today"}`, "PUT", { ...body, languageProfileId: profileId });
  if (draft.photoAssetIds !== undefined) {
    const desired = [...new Set(draft.photoAssetIds)];
    const current = await getJournal(row.id);
    // Remove changed positions first; the API requires unique positions and asset IDs.
    // Reading persisted attachments on every retry also recovers from a partial save.
    let touched = false;
    for (const photo of current.photos) {
      if (desired[photo.displayOrder] !== photo.mediaAssetId) {
        await request<void>(`/api/v1/journals/${row.id}/media/${photo.mediaAssetId}`, undefined, { method: "DELETE" });
        touched = true;
      }
    }
    for (const [displayOrder, mediaAssetId] of desired.entries()) {
      if (!current.photos.some(photo => photo.mediaAssetId === mediaAssetId && photo.displayOrder === displayOrder)) {
        await write(`/api/v1/journals/${row.id}/media`, "POST", { mediaAssetId, displayOrder });
        touched = true;
      }
    }
    if (!touched) return current;
  }
  return getJournal(row.id);
}

export type TaskContent =
  | { kind: "vocabularyIntroduction"; title: string; words: VocabularyLearningWord[]; questions: VocabularyQuestion[]; allowTypingPractice: boolean; targetText?: string | null; translation?: string | null; partOfSpeech?: WordClass | null; exampleSentence?: string | null }
  | { kind: "grammarLesson"; focus: string; title: string; explanation: string; questions: GrammarLessonQuestion[] }
  | { kind: "grammarExplanation"; title: string; explanation: string; examples: string[] }
  | { kind: "grammarPractice"; prompt: string; options: string[] }
  | { kind: "syntaxExplanation"; title: string; sentencePattern: string; explanation: string; examples: string[] }
  | { kind: "sentenceBuilding"; prompt: string; sourceText: string | null; tokenBank: string[] }
  | { kind: "ispyRound"; clue: string; clueTranslation?: string | null; encouragement?: string | null; options: { optionId: string; label: string; sceneObjectId: string }[] }
  | { kind: "reflection"; prompt: string };
export interface SessionTask {
  id: string; kind: TaskContent["kind"]; phase: "learning" | "ispy";
  status: "pending" | "inProgress" | "completed" | "skipped";
  isSkippable: true; orderIndex: number; publicContent: TaskContent;
  vocabularyItemId: string | null; sceneObjectId: string | null;
}
export interface SessionProgress {
  completedTaskCount: number; skippedTaskCount: number; terminalTaskCount: number; totalTaskCount: number;
}
export type SessionStatus = "created" | "analyzingScene" | "awaitingObjectReview" | "generatingTasks" | "ready" | "inProgress" | "completed" | "abandoned" | "failed";
export interface PracticeDetail {
  session: { id: string; status: SessionStatus; sceneMediaAssetId: string; sessionTitle: string | null; sessionSummary: string | null; failureCode: "imageUploadFailed" | "sceneAnalysisFailed" | "imageModerationFailed" | "noValidObjects" | "vocabularyMappingFailed" | "taskGenerationFailed" | null };
  mediaAsset: { id: string; source: "preloaded" | "camera" | "userUpload" };
  sceneId: string | null; title: string;
  analysisMode: "placeholder" | null;
  sceneObjects: SceneObject[];
  sceneObjectRelations: SceneObjectRelation[];
  vocabulary: { id: string; displayText: string; partOfSpeech: WordClass; gender: string | null; exampleSentence: string | null; languageCode: string }[];
  translations: { vocabularyItemId: string; translatedText: string }[];
  translationPreview: {
    objects: TranslatedTerm[];
    attributes: TranslatedTerm[];
    relationships: TranslatedTerm[];
  } | null;
  tasks: SessionTask[]; nextTaskId: string | null; progress: SessionProgress;
}
interface TranslatedTerm { key: string; source: string; translation: string }
export interface SceneObject {
  id: string; sessionId: string; label: string; vocabularyItemId: string | null;
  boundingBox: { x: number | string; y: number | string; width: number | string; height: number | string } | null;
  anchorPoint: { x: number | string; y: number | string } | null;
  attributes: Record<string, unknown> | null; confidenceScore: number | string | null; sourceObjectKey: string | null;
}
export interface SceneObjectRelation {
  id: string; subjectSceneObjectId: string; relation: string;
  referenceSceneObjectId: string; sourceRelationKey: string | null;
}
export interface VocabularyLearningWord {
  learningKey: string | null; termType: "object" | "attribute" | "relationship";
  vocabularyItemId: string | null; sceneObjectId: string | null; targetText: string; translation: string;
  partOfSpeech: WordClass; gender: string | null; pluralForm: string | null; phoneticText: string | null;
  pronunciationAudioAssetId: string | null; exampleSentence: string | null;
}
export interface VocabularyQuestion { questionId: string; prompt: string; options: { optionId: string; label: string }[]; correctOptionId?: string | null }
export interface GrammarLessonQuestion {
  questionId: string;
  prompt: string;
  interactionType: "multipleChoice" | "sentenceBuilding";
  options: { optionId: string; label: string }[];
  tokenBank: string[];
  translation?: string | null;
}
export type TaskAnswer = { inputMode: "text"; text: string } | { inputMode: "multipleChoice"; optionId: string } | { inputMode: "objectSelection"; sceneObjectId: string } | { inputMode: "vocabularyReview"; answers: Record<string, string>; typedAnswers: Record<string, string> };
export interface TaskActionResult {
  task: SessionTask; nextTaskId: string | null; sessionProgress: SessionProgress;
  attempt: { id: string; isCorrect: boolean | null; feedback: { message?: string } | null; evaluationDetails?: { questionResults?: Record<string, boolean>; correctAnswers?: Record<string, string>; guessedObjectKey?: string | null; ambiguous?: boolean } | null } | null;
}
export const analyzePractice = (id: string) => write<PracticeDetail>(`/api/v1/sessions/${id}/analyze`, "POST", {});
export interface PracticeReview {
  sceneTitle?: string;
  acceptedObjectIds: string[];
  relations: SceneObjectRelation[];
  addedObjects: { id: string; label: string; x: number; y: number }[];
  objectAttributes: Record<string, Record<string, string>>;
  repositionedObjects: { id: string; anchorPoint: { x: number; y: number } }[];
}
export const reviewPractice = (id: string, review: PracticeReview) => write<PracticeDetail>(`/api/v1/sessions/${id}/review`, "PUT", review);
export const getPractice = (id: string) => request<PracticeDetail>(`/api/v1/sessions/${id}`);
export const getActivePractice = () => request<PracticeDetail | null>("/api/v1/sessions/active");
export const createPractice = (profileId: string, assetId: string, key: string) => write<PracticeDetail>("/api/v1/sessions", "POST", {
  languageProfileId: profileId, mediaAssetId: assetId, idempotencyKey: key,
});
export const taskAction = (id: string, action: "start" | "complete" | "skip" | "attempts", body: unknown = {}) => write<TaskActionResult>(`/api/v1/tasks/${id}/${action}`, "POST", body);
export const checkVocabularyAnswer = (id: string, questionId: string, optionId: string) =>
  write<{ questionId: string; isCorrect: boolean; correctOptionId: string }>(`/api/v1/tasks/${id}/check-vocabulary-answer`, "POST", { questionId, optionId });
export const completePractice = (id: string) => write<{ id: string; status: string }>(`/api/v1/sessions/${id}/complete`, "POST", {});
export const abandonPractice = (id: string) => write<{ id: string; status: string }>(`/api/v1/sessions/${id}/abandon`, "POST", {});
export const getPracticeSummary = (id: string) => request<{ progress: SessionProgress; learnedVocabularyIds: string[]; xpEarned: number; ispyCorrectCount: number; ispyAttemptCount: number }>(`/api/v1/sessions/${id}/summary`);

export const checkPracticeWord = (id: string, label: string) => request<{ available: boolean }>(`/api/v1/sessions/${id}/review-word?label=${encodeURIComponent(label)}`);
