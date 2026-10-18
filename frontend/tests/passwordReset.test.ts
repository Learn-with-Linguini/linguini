import assert from "node:assert/strict";
import test from "node:test";
import {
  authenticationMessage,
  parseRecoveryUrlError,
  validatePasswordReset,
} from "../src/lib/authMessages.ts";

test("authenticationMessage handles password reset and rate limiting errors gracefully", () => {
  assert.equal(
    authenticationMessage("For security purposes, you can only request this after 60 seconds."),
    "Please wait a moment before trying again."
  );
  assert.equal(
    authenticationMessage("over_email_send_rate_limit"),
    "Please wait a moment before trying again."
  );
  assert.equal(
    authenticationMessage("too many requests"),
    "Please wait a moment before trying again."
  );
  assert.equal(
    authenticationMessage("User not found"),
    "No account was found with that email address."
  );
  assert.equal(
    authenticationMessage("Invalid login credentials"),
    "That email and password don't match. Try again or create an account."
  );
  assert.equal(
    authenticationMessage("Unexpected internal error"),
    "We couldn't complete that request. Please try again."
  );
});

test("validatePasswordReset enforces minimum length and matching passwords", () => {
  assert.equal(validatePasswordReset("12345", "12345"), "Password must be at least 6 characters.");
  assert.equal(validatePasswordReset("123456", "123457"), "Passwords do not match. Please re-enter them.");
  assert.equal(validatePasswordReset("correcthorse", "correcthorse"), null);
});

test("parseRecoveryUrlError detects expired or invalid single-use recovery links", () => {
  const expiredHash = "#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired&sb=";
  assert.equal(
    parseRecoveryUrlError(expiredHash, ""),
    "This password reset link has expired or has already been used. Please request a new one."
  );

  const queryError = "?error=access_denied&error_code=otp_expired";
  assert.equal(
    parseRecoveryUrlError("", queryError),
    "This password reset link has expired or has already been used. Please request a new one."
  );

  const validHash = "#access_token=test_token&refresh_token=test_refresh&type=recovery";
  assert.equal(parseRecoveryUrlError(validHash, ""), null);

  assert.equal(parseRecoveryUrlError("", ""), null);
});
