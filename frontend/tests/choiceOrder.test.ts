import assert from "node:assert/strict";
import test from "node:test";
import { choiceOrder } from "../src/lib/practiceTasks.ts";

test("choice order is stable for one question and varies with its seed", () => {
  const options = ["one", "two", "three", "four"];
  const first = choiceOrder(options, "task-a:question-a", option => option);

  assert.deepEqual(choiceOrder(options, "task-a:question-a", option => option), first);
  assert.deepEqual([...first].sort(), [...options].sort());
  assert.notDeepEqual(choiceOrder(options, "task-b:question-b", option => option), first);
});
