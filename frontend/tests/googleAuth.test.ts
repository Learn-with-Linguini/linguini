import assert from "node:assert/strict";
import test from "node:test";
import { signInWithGoogleIdToken } from "../src/lib/googleAuth.ts";

test("Google credentials are exchanged for a Supabase session", async () => {
  const calls: unknown[] = [];
  const client = {
    auth: {
      async signInWithIdToken(credentials: unknown) {
        calls.push(credentials);
        return { error: null };
      },
    },
  };

  const result = await signInWithGoogleIdToken(client, "signed-google-id-token");

  assert.equal(result.error, null);
  assert.deepEqual(calls, [{ provider: "google", token: "signed-google-id-token" }]);
});

test("empty Google credentials are rejected before contacting Supabase", async () => {
  let called = false;
  const client = {
    auth: {
      async signInWithIdToken() {
        called = true;
        return { error: null };
      },
    },
  };

  await assert.rejects(() => signInWithGoogleIdToken(client, "  "), /did not return/);
  assert.equal(called, false);
});
