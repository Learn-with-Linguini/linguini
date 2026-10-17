import assert from "node:assert/strict";
import test from "node:test";
import { countError, countGroups, initialCounts, objectCounts, savedCounts, suggestedCount } from "../src/lib/countGroups.ts";

test("matching names form one group whose count matches its pointers", () => {
  const groups = countGroups([
    { id: "a", label: "book", attributes: null },
    { id: "b", label: "Book ", attributes: { quantity: "three" } },
    { id: "c", label: "cup", attributes: { quantity: "many" } },
  ]);
  assert.deepEqual(groups, [
    { key: "book", label: "book", objectIds: ["a", "b"], suggested: 2 },
    { key: "cup", label: "cup", objectIds: ["c"], suggested: 1 },
  ]);
});

test("only a 1 to 10 quantity is suggested", () => {
  assert.deepEqual(["3", "ten", "0", "11", "several", ""].map(suggestedCount), [3, 10, null, null, null, null]);
  assert.equal(suggestedCount(4), null);
});

test("counts outside 1 to 10 are explained and never sent", () => {
  assert.equal(countError("11"), "Counts go from 1 to 10.");
  assert.equal(countError("0"), "Counts go from 1 to 10.");
  assert.equal(countError("2.5"), "Counts go from 1 to 10.");
  assert.equal(countError(""), null);
  assert.equal(countError("10"), null);
  const groups = countGroups([{ id: "a", label: "book" }, { id: "b", label: "cup" }, { id: "c", label: "pen" }]);
  assert.deepEqual(objectCounts(groups, { book: "3", cup: "12", pen: "" }), { a: 3 });
});

test("saved counts restore by group name", () => {
  assert.deepEqual(savedCounts([{ sceneObjectIds: ["a"], label: "Book", quantity: 4, suggestedQuantity: null, source: "entered" }]), { book: "4" });
  assert.deepEqual(savedCounts(undefined), {});
});

test("counts start from analysis suggestions and saved learner values win", () => {
  assert.deepEqual(initialCounts([
    { id: "a", label: "book", attributes: { quantity: "3" } },
    { id: "b", label: "cup" },
  ], [{ sceneObjectIds: ["a"], label: "Book", quantity: 2, suggestedQuantity: 1, source: "corrected" }]), {
    book: "2",
    cup: "1",
  });
});
