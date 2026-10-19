import assert from "node:assert/strict";
import test from "node:test";

function isSurveyMilestone(completedLessonsCount: number): boolean {
  return (
    completedLessonsCount === 1 ||
    (completedLessonsCount > 1 && (completedLessonsCount - 1) % 5 === 0)
  );
}

test("survey milestones prompt after lesson 1 and every 5 lessons afterwards", () => {
  assert.equal(isSurveyMilestone(0), false);
  assert.equal(isSurveyMilestone(1), true);
  assert.equal(isSurveyMilestone(2), false);
  assert.equal(isSurveyMilestone(3), false);
  assert.equal(isSurveyMilestone(4), false);
  assert.equal(isSurveyMilestone(5), false);
  assert.equal(isSurveyMilestone(6), true);
  assert.equal(isSurveyMilestone(7), false);
  assert.equal(isSurveyMilestone(10), false);
  assert.equal(isSurveyMilestone(11), true);
  assert.equal(isSurveyMilestone(15), false);
  assert.equal(isSurveyMilestone(16), true);
  assert.equal(isSurveyMilestone(21), true);
});

test("survey rating options have valid rating scores 1 to 5", () => {
  const ratings = [
    { value: 1, label: "Angry", src: "/ratings/rating-1.png" },
    { value: 2, label: "Sad", src: "/ratings/rating-2.png" },
    { value: 3, label: "Neutral", src: "/ratings/rating-3.png" },
    { value: 4, label: "Happy", src: "/ratings/rating-4.png" },
    { value: 5, label: "Loved it", src: "/ratings/rating-5.png" },
  ];

  assert.equal(ratings.length, 5);
  for (let i = 0; i < ratings.length; i++) {
    assert.equal(ratings[i].value, i + 1);
    assert.equal(ratings[i].src, `/ratings/rating-${i + 1}.png`);
  }
});
