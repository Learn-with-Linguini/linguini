import assert from "node:assert/strict";
import test from "node:test";
import { ApiError, descriptionEvaluation, reviewDetails, ISPY_DESCRIPTION_EVALUATION_VERSION } from "../src/lib/api.ts";
import type { ISpyDescriptionEvaluation, SessionTask, TaskAttemptResult, TaskContent } from "../src/lib/api.ts";
import { finishesWithoutISpy, isMissionSession, MISSION_PHOTO_NOT_READY, taskTitle } from "../src/lib/practiceTasks.ts";
import { friendlyError } from "../src/lib/queryKeys.ts";

const lesson: TaskContent = {
  kind: "grammarLesson", focus: "genderNumberAgreement", title: "Describe the cup", explanation: "Colours agree.",
  questions: [{ questionId: "colour", prompt: "Choose", interactionType: "multipleChoice", options: [{ optionId: "roja", label: "roja" }, { optionId: "rojo", label: "rojo" }], tokenBank: [] }],
};
const task = (publicContent: TaskContent): SessionTask => ({
  id: "task", kind: publicContent.kind, phase: "learning", status: "pending", isSkippable: true, orderIndex: 0,
  publicContent, vocabularyItemId: null, sceneObjectId: null,
});
const attempt = (evaluationDetails: TaskAttemptResult["evaluationDetails"]): TaskAttemptResult => ({
  id: "attempt", attemptNumber: 1, isCorrect: false, feedback: null, evaluationDetails,
});

test("tasks with and without mission metadata are the same task", () => {
  const mission = task({ ...lesson, missionId: "M01", practiceLevel: "A1", contentVersion: 1 });
  assert.equal(taskTitle(mission), taskTitle(task(lesson)));
  assert.equal(mission.publicContent.missionId, "M01");
  assert.equal(task(lesson).publicContent.missionId, undefined);
});

test("structured outcomes extend grouped review details", () => {
  const legacy = { questionResults: { colour: false }, correctAnswers: { colour: "roja" } };
  assert.deepEqual(reviewDetails(attempt(legacy)), legacy);
  const details = reviewDetails(attempt({
    ...legacy,
    questionOutcomes: [{
      questionId: "colour", outcome: "incorrect", objectiveId: "identify-describe-object", targetIds: ["describe-colour"],
      evidenceType: "recognition", assistance: ["hint"], assistanceUsed: true,
      mistakes: [{ mistake: "wrongGender", answer: "rojo", correction: "La taza es roja.", explanation: null }],
    }],
  }));
  assert.equal(details?.questionResults.colour, false);
  assert.equal(details?.questionOutcomes?.[0].mistakes[0].correction, "La taza es roja.");
  assert.equal(descriptionEvaluation(attempt(details)), null);
});

test("standalone I-Spy evaluations are not read as grouped review details", () => {
  const evaluation: ISpyDescriptionEvaluation = {
    version: ISPY_DESCRIPTION_EVALUATION_VERSION, outcome: "clearMatch", guessedObjectKey: "cup", ambiguous: false,
    alternativeObjectKeys: [], matchedEvidenceKeys: [], contradictedEvidenceKeys: [], targetAmongAlternatives: false,
  };
  assert.equal(reviewDetails(attempt(evaluation)), null);
  assert.deepEqual(descriptionEvaluation(attempt(evaluation)), evaluation);
});

test("only mission sessions without I-Spy finish from the last learning task", () => {
  const mission = task({ ...lesson, missionId: "M01", practiceLevel: "A1", contentVersion: 1 });
  const clue = task({ kind: "ispyRound", clue: "Veo algo rojo.", options: [] });
  assert.equal(finishesWithoutISpy([mission]), true);
  assert.equal(finishesWithoutISpy([mission, clue]), false);
  assert.equal(finishesWithoutISpy([task(lesson)]), false);
  assert.equal(isMissionSession([mission, clue]), true);
  assert.equal(isMissionSession([task(lesson), clue]), false);
  const where = task({ ...lesson, title: "Ask where it is", missionId: "M02", practiceLevel: "A1", contentVersion: 1 });
  assert.equal(finishesWithoutISpy([mission, where]), true);
  assert.equal(finishesWithoutISpy([mission, where, clue]), false);
});

test("a photo that is not ready for the mission keeps the server's reasons", () => {
  const reason = `${MISSION_PHOTO_NOT_READY} Confirm the colour of at least one object.`;
  assert.equal(friendlyError(new ApiError(reason, 409, "mission_photo_not_ready", null)), reason);
  assert.notEqual(friendlyError(new ApiError("Session changed.", 409, "practice_conflict", null)), "Session changed.");
});
