import assert from "node:assert/strict";
import test from "node:test";
import { joinChunks } from "../src/lib/joinChunks.ts";

test("joins chunks according to each chunk's join instruction", () => {
  assert.equal(joinChunks([
    { chunkId: "a", text: "Es", join: "space" },
    { chunkId: "b", text: "una", join: "space" },
    { chunkId: "c", text: "taza", join: "space" },
    { chunkId: "d", text: ".", join: "none" },
  ]), "Es una taza.");
  assert.equal(joinChunks([
    { chunkId: "one", text: "컵", join: "space" },
    { chunkId: "two", text: "입니다", join: "none" },
  ]), "컵입니다");
});

test("joining an empty chunk list returns an empty preview", () => {
  assert.equal(joinChunks([]), "");
});
