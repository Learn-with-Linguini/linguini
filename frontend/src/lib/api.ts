import { GENDER_ARTICLES } from "../data/types.ts";
import type { A0MissionSnapshot, Gender, LeaderboardRow, MissionChoices, MissionQuestionFields, ScenarioProgress, Streak, TaughtChunk, VocabRecord, VocabularyScene, VocabStatus, WordClass } from "../data/types";
import type { SceneSummary } from "../data/types";
import type { JournalEntry } from "../data/types";
import { getAccessToken, waitForAccessToken } from "./supabase.ts";

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

export function protectedMediaPath(url: string | null | undefined): string | null {
  const prefix = `${apiBaseUrl ?? ""}/api/v1/media/`;
  return apiBaseUrl && url?.startsWith(prefix) ? url.slice(apiBaseUrl.length) : null;
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

export type AccountTier = "beta" | "free" | "plus";

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
  walkthroughVersionSeen: number;
  tier: AccountTier;
  utmSource?: string | null;
  utmMedium?: string | null;
  utmCampaign?: string | null;
  utmContent?: string | null;
  utmTerm?: string | null;
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

type TokenProvider = (signal?: AbortSignal) => Promise<string | null>;

async function requestResponse(
  path: string,
  signal?: AbortSignal,
  options?: RequestInit,
  tokenProvider: TokenProvider = () => getAccessToken(),
): Promise<Response> {
  if (!apiBaseUrl) {
    throw new Error("The app is still being set up. Please try again in a moment.");
  }

  let response: Response;
  try {
    const headers = new Headers(options?.headers);
    const token = await tokenProvider(signal);
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
  return response;
}

export async function request<T>(path: string, signal?: AbortSignal, options?: RequestInit): Promise<T> {
  const response = await requestResponse(path, signal, options);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function requestBlob(path: string, signal?: AbortSignal): Promise<Blob> {
  return (await requestResponse(path, signal, { cache: "no-store" }, waitForAccessToken)).blob();
}

export function getCurrentUser(signal?: AbortSignal): Promise<User> {
  return request<User>("/api/v1/me", signal);
}

export function deleteCurrentAccount(): Promise<void> {
  return request<void>("/api/v1/me", undefined, { method: "DELETE" });
}

export interface LanguageProfile {
  id: string;
  userId: string;
  sourceLanguageCode: string;
  targetLanguageCode: string;
  proficiencyLevel: ProficiencyLevel;
  isActive: boolean;
  dailyGoalMinutes: number | null;
  preferredInputMode: "speech" | "text" | "both";
}

export type UserPatch = Partial<Pick<User, "displayName" | "timezone" | "onboardingCompleted" | "walkthroughVersionSeen" | "learningGoal" | "microphoneEnabled" | "cameraEnabled" | "utmSource" | "utmMedium" | "utmCampaign" | "utmContent" | "utmTerm">>;
export type LanguageProfilePatch = Partial<Pick<LanguageProfile, "proficiencyLevel" | "isActive" | "dailyGoalMinutes" | "preferredInputMode">>;

export type SupportIssueType = "general" | "technical" | "content" | "account";
export interface SupportAttachmentInput {
  fileName: string;
  mimeType: "image/jpeg" | "image/png" | "image/webp" | "application/pdf" | "text/plain";
  dataBase64: string;
}
export interface SupportRequestInput {
  subject: string;
  description: string;
  issueType: SupportIssueType;
  attachments: SupportAttachmentInput[];
}
export interface PublicSupportRequestInput extends SupportRequestInput {
  email: string;
}
export type LessonReportIssue = "answer_marked_incorrectly" | "solution_incorrect" | "wording_unclear" | "audio_incorrect" | "other";
export interface LessonReportInput {
  reportType: string;
  issue: LessonReportIssue;
  additionalDetails: string;
  context: Array<{ label: string; value: string }>;
}

export function write<T>(path: string, method: string, body: unknown): Promise<T> {
  return request(path, undefined, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

export const submitSupportRequest = (payload: SupportRequestInput) =>
  write<{ status: "sent" }>("/api/v1/support/requests", "POST", payload);

export const submitPublicSupportRequest = (payload: PublicSupportRequestInput) =>
  write<{ status: "sent" }>("/api/v1/support/public-requests", "POST", payload);

export const submitLessonReport = (payload: LessonReportInput) =>
  write<{ status: "sent" }>("/api/v1/support/lesson-reports", "POST", payload);

export interface SubscriptionStatus {
  tier: AccountTier;
  dailyLessonLimit: number | null;
  hasActiveSubscription: boolean;
  canUpgrade: boolean;
}

export const getPaymentConfig = (signal?: AbortSignal) =>
  request<{ publishableKey: string | null; plusPriceId: string }>("/api/v1/payments/config", signal);

export const getSubscriptionStatus = (signal?: AbortSignal) =>
  request<SubscriptionStatus>("/api/v1/payments/subscription-status", signal);

export const createCheckoutSession = (returnUrl?: string) =>
  write<{ checkoutUrl: string }>("/api/v1/payments/create-checkout-session", "POST", { returnUrl });

export const createPortalSession = (returnUrl?: string) =>
  write<{ portalUrl: string }>("/api/v1/payments/create-portal-session", "POST", { returnUrl });

export const testSetTier = (tier: AccountTier) =>
  write<{ tier: AccountTier }>("/api/v1/payments/test-set-tier", "POST", { tier });

export const getLanguageProfiles = (signal?: AbortSignal) => request<LanguageProfile[]>("/api/v1/me/language-profiles", signal);
export const updateUser = (patch: UserPatch) => write<User>("/api/v1/me", "PATCH", patch);
export const updateLanguageProfile = (id: string, patch: LanguageProfilePatch) => write<LanguageProfile>(`/api/v1/me/language-profiles/${id}`, "PATCH", patch);
export const createLanguageProfile = (code: string, minutes: number, proficiencyLevel: ProficiencyLevel) => write<LanguageProfile>("/api/v1/me/language-profiles", "POST", {
  sourceLanguageCode: "en", targetLanguageCode: code, proficiencyLevel, dailyGoalMinutes: minutes,
});

export interface PlacementQuestion {
  id: string; questionKey: string; orderIndex: number; prompt: string; promptTranslation: string; skill: string;
  difficulty: "A0" | "A1" | "A2";
  options: Array<{ value: string; label: string }>;
}
export interface PlacementTest { languageCode: string; imagePath: string; questions: PlacementQuestion[] }
export const getPlacementTest = (languageCode: string) =>
  request<PlacementTest>(`/api/v1/onboarding/placement?languageCode=${encodeURIComponent(languageCode)}`);
export const submitPlacement = (languageCode: string, pathway: "beginner" | "placement", answers: Record<string, string> = {}) =>
  write<{ proficiencyLevel: "A0" | "A1" | "A2"; message: string }>("/api/v1/onboarding/placement", "POST", { languageCode, pathway, answers });
export const checkPlacementAnswer = (questionId: string, answer: string) =>
  write<{ correct: boolean; correctOption: string }>("/api/v1/onboarding/placement/check", "POST", { questionId, answer });

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
  sceneId: string;
  title: string;
  description: string | null;
}

function sceneSummary(row: PreloadedScene): SceneSummary {
  return { id: row.sceneId, mediaAssetId: row.mediaAsset.id, imageUrl: row.imageUrl ?? null, title: row.title, blurb: row.description ?? "" };
}

export async function getScenes(signal?: AbortSignal): Promise<SceneSummary[]> {
  const rows = await request<PreloadedScene[]>("/api/v1/preloaded-scenes", signal);
  return rows.map(sceneSummary);
}

export async function getSceneDetail(id: string, signal?: AbortSignal): Promise<SceneSummary> {
  const row = await request<PreloadedScene>(`/api/v1/preloaded-scenes/${encodeURIComponent(id)}`, signal);
  return sceneSummary(row);
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

export type ProficiencyLevel = "A0" | "A1" | "A2" | "B1" | "B2" | "C1" | "C2";
export const proficiencyLabel = (level: ProficiencyLevel) => (level === "A0" ? "Pre-A1" : level);
/** Links task content to a versioned backend mission definition; absent on tasks without a mission. */
export interface MissionTaskFields { missionId?: string; practiceLevel?: ProficiencyLevel; contentVersion?: number }
export interface RoleplayFact {
  sceneObjectId: string;
  source: "assignedRoleplay";
  isFictional: true;
}
export interface MissionScenarioAlternative { sceneObjectId: string; label: string }
export interface MissionScenario {
  scenarioId: string; prompt: string; sceneObjectId: string; itemLabel: string;
  accepted: boolean; alternatives: MissionScenarioAlternative[];
}
export type TaskContent = MissionTaskFields & (
  | { kind: "vocabularyIntroduction"; title: string; words: VocabularyLearningWord[]; questions: VocabularyQuestion[]; allowTypingPractice: boolean; targetText?: string | null; translation?: string | null; partOfSpeech?: WordClass | null; exampleSentence?: string | null }
  | { kind: "grammarLesson"; focus: string; title: string; explanation?: string | null; checkEachQuestion?: boolean; prep?: LessonPrepCard[] | null; questions: GrammarLessonQuestion[]; roleplayFacts?: RoleplayFact[] | null; situation?: "lostAndFound" | "everydayChoice" | null; taughtChunks?: TaughtChunk[] | null; missionSnapshot?: A0MissionSnapshot | null; scenario?: MissionScenario | null }
  | { kind: "grammarExplanation"; title: string; explanation: string; examples: string[] }
  | { kind: "grammarPractice"; prompt: string; options: string[] }
  | { kind: "syntaxExplanation"; title: string; sentencePattern: string; explanation: string; examples: string[] }
  | { kind: "sentenceBuilding"; prompt: string; sourceText: string | null; tokenBank: string[] }
  | { kind: "ispyRound"; clue: string; clueTranslation?: string | null; encouragement?: string | null; options: { optionId: string; label: string; sceneObjectId: string }[] }
  | { kind: "reflection"; prompt: string; clueFrames?: ClueFrame[]; avoidWords?: string[] }
);
export type ClueFrameId = "name" | "colour" | "location";
export type ClueSlotId = "position" | "reference" | "colour";
export interface ClueSlotChip { text: string; meaning?: string | null; example?: string | null }
export interface ClueSlot { slotId: ClueSlotId; label: string; chips: ClueSlotChip[] }
/** `chips` are legacy complete phrases; `phrases` maps "position|reference" to composed text; `help` is shown on request. */
export interface ClueFrame {
  frameId: ClueFrameId; prefix: string; meaning: string; example: string; chips: string[];
  template?: string | null; slots?: ClueSlot[]; phrases?: Record<string, string>; help?: string[];
}
export interface ClueSlotChoice { frameId: ClueFrameId; slotId: ClueSlotId; chip: string }
export const CLUE_ASSISTANCE_VERSION = "ispy-clue-assistance.v1";
/** Support visible while writing a clue; recorded as guided practice, never as independent recall. */
export interface ClueAssistance {
  version: typeof CLUE_ASSISTANCE_VERSION; practiceMode: "guided"; targetWordShown: true;
  offeredFrameIds: ClueFrameId[]; selectedFrameIds: ClueFrameId[]; insertedChips: string[];
  selectedSlots?: ClueSlotChoice[]; revealedHelpFrameIds?: ClueFrameId[];
}
export interface SessionTask {
  id: string; kind: TaskContent["kind"]; phase: "learning" | "ispy";
  status: "pending" | "inProgress" | "completed" | "skipped";
  isSkippable: true; orderIndex: number; publicContent: TaskContent;
  vocabularyItemId: string | null; sceneObjectId: string | null;
  xpReward: number; xpBonus: number;
}
export interface SessionProgress {
  completedTaskCount: number; skippedTaskCount: number; terminalTaskCount: number; totalTaskCount: number;
}
export type SessionMode = "lesson" | "ispy";
export type SessionStatus = "created" | "analyzingScene" | "awaitingObjectReview" | "generatingTasks" | "ready" | "inProgress" | "completed" | "abandoned" | "failed";
export type PracticeFocus = "genderNumberAgreement" | "pluralNounForm" | "sceneDescription" | "chainedDescription";
export interface SessionPersonalization {
  /** Counts completed sessions; earlier practice evidence can exist when this is zero. */
  previousSessions: number;
  returningWords: { word: string; needsReview: boolean }[];
  practiceFocuses: PracticeFocus[];
}
export interface PracticeDetail {
  session: { id: string; mode: SessionMode; sourceSessionId: string | null; status: SessionStatus; sceneMediaAssetId: string; sessionTitle: string | null; sessionSummary: string | null; failureCode: "imageUploadFailed" | "sceneAnalysisFailed" | "imageModerationFailed" | "noValidObjects" | "vocabularyMappingFailed" | "taskGenerationFailed" | null };
  mediaAsset: { id: string; source: "preloaded" | "camera" | "userUpload" };
  sceneId: string | null; title: string;
  analysisMode: "placeholder" | null;
  analysisRetryable: boolean;
  sceneObjects: SceneObject[];
  /** Reviewed sessions: scene object id -> its marker number on the review screen. */
  reviewMarkers?: Record<string, number>;
  sceneObjectRelations: SceneObjectRelation[];
  sceneActionSuggestions: SceneActionSuggestion[];
  scenePriceSuggestions: ScenePriceSuggestion[];
  vocabulary: { id: string; displayText: string; partOfSpeech: WordClass; gender: string | null; exampleSentence: string | null; languageCode: string }[];
  translations: { vocabularyItemId: string; translatedText: string }[];
  translationPreview: {
    objects: TranslatedTerm[];
    attributes: TranslatedTerm[];
    relationships: TranslatedTerm[];
  } | null;
  tasks: SessionTask[]; nextTaskId: string | null; progress: SessionProgress;
  personalization?: SessionPersonalization | null;
  countedGroups?: CountedGroup[];
  missionGuidance?: string[];
  provisionalMissionPlan?: MissionTaskFields[];
  suggestedSceneObjectIds?: string[];
  missionChoices?: MissionChoices | null;
}
export interface SceneActionSuggestion {
  actionKey: string; action: string; sceneObjectIds: string[]; confidenceScore: number | string;
}
export interface ScenePriceSuggestion {
  priceKey: string; sceneObjectId: string; displayedPrice: string; confidenceScore: number | string;
}
export interface CountedGroup {
  sceneObjectIds: string[]; label: string; quantity: number;
  suggestedQuantity: number | null; source: "confirmed" | "corrected" | "entered";
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
export interface GrammarLessonQuestion extends MissionQuestionFields {
  questionId: string;
  prompt: string;
  interactionType: "multipleChoice" | "sentenceBuilding" | "textCloze";
  options: { optionId: string; label: string }[];
  tokenBank: string[];
  gapKind?: string | null;
  assistanceSteps?: ("replayAudio" | "visualDetail" | "phraseOnset" | "chunkBank" | "fullModel")[] | null;
  allowRetry?: boolean | null;
  wrongFieldTokens?: Record<string, string> | null;
  translation?: string | null;
  sceneObjectId?: string | null;
  objectLabel?: string | null;
  promptTranslation?: string | null;
  referenceObjectId?: string | null;
  referenceLabel?: string | null;
  section?: string | null;
  groupObjectIds?: string[];
  boardCounts?: Record<string, number>;
  boardObjectId?: string | null;
  quantityWord?: string | null;
  roleplayPremise?: string | null;
  /** Mission options already shuffled and saved by the backend; show them as stored. */
  keepOptionOrder?: boolean | null;
  /** Marker questions: each option's scene object, numbered as on the reviewed photo. */
  markerObjectIds?: Record<string, string> | null;
  planningFacts?: string[];
  /** A short English instruction shown above the prompt. */
  instruction?: string | null;
  /** Target-language text the learner can play aloud. */
  audioText?: string | null;
  /** Listening questions hide the written prompt until the learner reveals it. */
  listenFirst?: boolean | null;
  /** A practice board showing this many of `boardObjectId`, without a choice. */
  displayCount?: number | null;
  /** A chunk with its missing word as `___`, completed and played after grading. */
  slotTemplate?: string | null;
  completeChunk?: string | null;
}
/** A taught chunk shown with audio before a lesson's questions. */
export interface LessonPrepCard { text: string; translation?: string | null; sceneObjectId?: string | null }
export type TaskAnswer = { inputMode: "text"; text: string; assistance?: ClueAssistance } | { inputMode: "multipleChoice"; optionId: string } | { inputMode: "objectSelection"; sceneObjectId: string } | { inputMode: "vocabularyReview"; answers: Record<string, string>; typedAnswers: Record<string, string>; questionAssistance?: QuestionAssistance[] };
export type ConfirmGuessBody = { attemptId: string };
export type SupportKind = "translation" | "audio" | "example" | "wordBank" | "clueFrame" | "helpPhrase" | "hint" | "answerReveal";
export type EvidenceType = "recognition" | "objectSelection" | "construction" | "production" | "participation";
export type MistakeType = "wrongObject" | "wrongWord" | "wrongArticle" | "wrongGender" | "wrongColour" | "wrongAttribute" | "wrongPosition" | "wordOrder" | "missingWord" | "spelling" | "targetNamed" | "wrongQuantity" | "pluralForm";
/** Supports the learner opened for one grouped-lesson question. */
export interface QuestionAssistance { questionId: string; supports: SupportKind[] }
export interface MistakeDetail { mistake: MistakeType; answer: string | null; correction: string; explanation: string | null }
/** `assistanceUsed` is true only when a support counts as assistance under the mission's rules. */
export interface QuestionOutcome {
  questionId: string; outcome: "correct" | "incorrect" | "unassessed";
  objectiveId: string | null; targetIds: string[]; evidenceType: EvidenceType;
  assistance: SupportKind[]; assistanceUsed: boolean; mistakes: MistakeDetail[];
  correctNote?: string; optionNotes?: string[];
}
export interface LessonAnswerCheck {
  basilEarned?: number;
  questionId: string; answer: string; isCorrect: boolean; correctAnswer: string | null;
  outcome: QuestionOutcome; attemptsLeft?: number | null; feedback?: string | null;
  wrongField?: string | null; assistanceStepsUsed?: string[];
}
/** `questionOutcomes` is present only for tasks with mission evaluation metadata. */
export interface VocabularyReviewDetails { questionResults: Record<string, boolean>; correctAnswers: Record<string, string>; questionOutcomes?: QuestionOutcome[] }
export type ISpyDescriptionOutcome = "clearMatch" | "needsClarification" | "needsRevision" | "noMatch" | "evaluationFailed";
export const ISPY_DESCRIPTION_EVALUATION_VERSION = "ispy-description-evaluation.v1";
export interface ISpyDescriptionEvaluation {
  version: typeof ISPY_DESCRIPTION_EVALUATION_VERSION; outcome: ISpyDescriptionOutcome; guessedObjectKey: string | null; ambiguous: boolean;
  alternativeObjectKeys: string[]; matchedEvidenceKeys: string[]; contradictedEvidenceKeys: string[]; targetAmongAlternatives: boolean;
}
export interface TaskAttemptResult {
  id: string; attemptNumber: number; isCorrect: boolean | null; feedback: { message?: string } | null;
  responsePayload?: Record<string, unknown>;
  evaluationDetails?: VocabularyReviewDetails | ISpyDescriptionEvaluation | null;
}
/** The owner's latest round-two attempt, as much as is needed to restore it after a reload. */
export interface LatestClueAttempt {
  id: string; attemptNumber: number; text: string; optionId: string | null; isCorrect: boolean | null; feedback: string | null;
  evaluationDetails: ISpyDescriptionEvaluation | null; assistance: ClueAssistance | null;
  answers?: Record<string, string> | null; reviewDetails?: VocabularyReviewDetails | null;
}
export const getLatestAttempt = (taskId: string, signal?: AbortSignal) =>
  request<{ attempt: LatestClueAttempt | null }>(`/api/v1/tasks/${taskId}/latest-attempt`, signal);
export const checkLessonAnswer = (taskId: string, questionId: string, answer: string) =>
  write<LessonAnswerCheck>(`/api/v1/tasks/${taskId}/check-lesson-answer`, "POST", { questionId, answer });
export const getLessonChecks = (taskId: string, signal?: AbortSignal) =>
  request<{ checks: LessonAnswerCheck[]; assistanceSteps: Record<string, string[]> }>(
    `/api/v1/tasks/${taskId}/lesson-checks`, signal,
  );
export type LessonAssistanceStep = "replayAudio" | "visualDetail" | "phraseOnset" | "chunkBank" | "fullModel";
export const requestLessonAssistance = (
  taskId: string, questionId: string, step: LessonAssistanceStep,
) => write<{ questionId: string; step: LessonAssistanceStep; content: string }>(
  `/api/v1/tasks/${taskId}/lesson-assistance`, "POST", { questionId, step },
);
export const updateMissionScenario = (
  taskId: string, action: "accept" | "choose", sceneObjectId?: string,
) => write<{ accepted: boolean; tasks: SessionTask[] }>(
  `/api/v1/tasks/${taskId}/mission-scenario`, "POST", { action, ...(sceneObjectId ? { sceneObjectId } : {}) },
);
export interface TaskActionResult {
  basilEarned?: number;
  task: SessionTask; nextTaskId: string | null; sessionProgress: SessionProgress; attempt: TaskAttemptResult | null;
  xpEarned: number;
}
export const descriptionEvaluation = (attempt: TaskAttemptResult | null): ISpyDescriptionEvaluation | null => {
  const details = attempt?.evaluationDetails;
  return details && "version" in details && details.version === ISPY_DESCRIPTION_EVALUATION_VERSION ? details : null;
};
export const reviewDetails = (attempt: TaskAttemptResult | null): VocabularyReviewDetails | null => {
  const details = attempt?.evaluationDetails;
  return details && "questionResults" in details ? details : null;
};
export const analyzePractice = (id: string) => write<PracticeDetail>(`/api/v1/sessions/${id}/analyze`, "POST", {});
export const retryPracticeAnalysis = (id: string) => write<PracticeDetail>(`/api/v1/sessions/${id}/retry-analysis`, "POST", {});
export interface PracticeReview {
  sceneTitle?: string;
  acceptedObjectIds: string[];
  relations: SceneObjectRelation[];
  addedObjects: { id: string; label: string; x: number; y: number }[];
  objectAttributes: Record<string, Record<string, string>>;
  repositionedObjects: { id: string; anchorPoint: { x: number; y: number } }[];
  objectCounts: Record<string, number>;
  missionChoices?: MissionChoices;
}
export const reviewPractice = (id: string, review: PracticeReview) => write<PracticeDetail>(`/api/v1/sessions/${id}/review`, "PUT", review);
export const getPractice = (id: string) => request<PracticeDetail>(`/api/v1/sessions/${id}`);
export const getActivePractice = () => request<PracticeDetail | null>("/api/v1/sessions/active");
export const createPractice = (profileId: string, assetId: string, key: string) => write<PracticeDetail>("/api/v1/sessions", "POST", {
  languageProfileId: profileId, mediaAssetId: assetId, idempotencyKey: key,
});
export const taskAction = (id: string, action: "start" | "complete" | "skip" | "attempts" | "confirm-guess", body: unknown = {}) => write<TaskActionResult>(`/api/v1/tasks/${id}/${action}`, "POST", body);
export interface VocabularyAnswerCheck { questionId: string; acceptedOptionId: string; isCorrect: boolean; correctOptionId: string; basilEarned: number }
export const getVocabularyChecks = (id: string, signal?: AbortSignal) =>
  request<{ checks: VocabularyAnswerCheck[] }>(`/api/v1/tasks/${id}/vocabulary-checks`, signal);
export const checkVocabularyAnswer = (id: string, questionId: string, optionId: string) =>
  write<VocabularyAnswerCheck>(`/api/v1/tasks/${id}/check-vocabulary-answer`, "POST", { questionId, optionId });
export const checkVocabularyTyping = (id: string, learningKey: string, answer: string, reveal = false) =>
  write<{ learningKey: string; isCorrect: boolean; correctAnswer: string; revealed: boolean }>(`/api/v1/tasks/${id}/check-vocabulary-typing`, "POST", { learningKey, answer, reveal });
export const completePractice = (id: string) => write<{ id: string; status: string }>(`/api/v1/sessions/${id}/complete`, "POST", {});
export const abandonPractice = (id: string) => write<{ id: string; status: string }>(`/api/v1/sessions/${id}/abandon`, "POST", {});
export const getPracticeSummary = (id: string) => request<{
  progress: SessionProgress;
  learnedVocabularyIds: string[];
  xpEarned: number;
  basilEarned: number;
  ispyCorrectCount: number;
  ispyAttemptCount: number;
  completedLessonsCount: number;
}>(`/api/v1/sessions/${id}/summary`);

export interface SurveySubmission {
  rating: number;
  usageFrequency?: string;
  motivation?: string;
  improvements?: string;
  receiveFollowUp?: boolean;
  email?: string | null;
  triggerSource?: string;
  lessonCount?: number | null;
}

export interface SurveyResponse {
  id: string;
  rating: number;
  createdAt: string;
}

export function submitSurvey(data: SurveySubmission): Promise<SurveyResponse> {
  return write<SurveyResponse>("/api/v1/surveys", "POST", {
    rating: data.rating,
    usage_frequency: data.usageFrequency ?? "",
    motivation: data.motivation ?? "",
    improvements: data.improvements ?? "",
    receive_follow_up: Boolean(data.receiveFollowUp),
    email: data.email ? data.email.trim() : null,
    trigger_source: data.triggerSource ?? "profile",
    lesson_count: data.lessonCount ?? null,
  });
}

export interface ISpyPhoto { mediaAsset: { id: string; source: "camera" | "userUpload"; createdAt: string }; playable: boolean; confirmedAt: string | null }
export interface ISpyPhotoPage { photos: ISpyPhoto[]; nextCursor: string | null }
export const getISpyPhotos = (cursor: string | null, signal?: AbortSignal) =>
  request<ISpyPhotoPage>(`/api/v1/ispy/photos${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`, signal);
export const getActiveISpyGame = (signal?: AbortSignal) => request<PracticeDetail | null>("/api/v1/ispy/games/active", signal);
export const startISpyGame = (profileId: string, assetId: string, key: string) => write<PracticeDetail>("/api/v1/ispy/games", "POST", {
  languageProfileId: profileId, mediaAssetId: assetId, idempotencyKey: key,
});
export const checkPracticeWord = (id: string, label: string) => request<{ available: boolean }>(`/api/v1/sessions/${id}/review-word?label=${encodeURIComponent(label)}`);
