import type { MissionChoices } from "../data/types";
import type { GrammarLessonQuestion } from "./api";

export interface MissionChoiceDraft {
  ownedObjectId: string | null;
  ownershipPretend: boolean;
  preferenceObjectIds: string[];
  chosenObjectId: string | null;
  reaction: "like" | "dislike" | "skip" | null;
}

export function fillMissionGap(template: string, answer: string): string {
  return template.replace("___", answer);
}

export function serializeMissionChoices(
  draft: MissionChoiceDraft,
  selectedObjectIds?: ReadonlySet<string>,
): MissionChoices | undefined {
  const isSelected = (id: string) => !selectedObjectIds || selectedObjectIds.has(id);
  const ownership = draft.ownedObjectId && isSelected(draft.ownedObjectId)
    ? { sceneObjectId: draft.ownedObjectId, pretend: draft.ownershipPretend }
    : undefined;
  const compared = [...new Set(draft.preferenceObjectIds)].filter(isSelected).slice(0, 2);
  const preference = compared.length === 2
    && draft.chosenObjectId
    && compared.includes(draft.chosenObjectId)
    ? {
      sceneObjectIds: compared,
      chosenObjectId: draft.chosenObjectId,
      reaction: "like" as const,
    }
    : compared.length === 1 && draft.reaction
      ? {
        sceneObjectIds: compared,
        chosenObjectId: null,
        reaction: draft.reaction,
      }
      : undefined;
  if (!ownership && !preference) return undefined;
  return {
    ...(ownership ? { ownership } : {}),
    ...(preference ? { preference } : {}),
  };
}

/**
 * What a situation question says aloud once the learner lands on the right answer: the
 * completed sentence, or else the sentence they listened to. Questions without either
 * (photo markers, "Like"/"Don't like") stay silent rather than reading a marker number
 * or an English label in the target-language voice.
 */
export function situationPhrase(
  question: Pick<GrammarLessonQuestion, "completeChunk" | "slotTemplate" | "audioText">,
  answer: string,
): string | null {
  if (question.completeChunk) return question.completeChunk;
  if (question.slotTemplate && answer) return fillMissionGap(question.slotTemplate, answer);
  return question.audioText ?? null;
}
