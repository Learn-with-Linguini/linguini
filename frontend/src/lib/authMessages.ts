export function authenticationMessage(message: string): string {
  const normalized = message.toLowerCase();
  if (normalized.includes("invalid login") || normalized.includes("invalid credentials")) {
    return "That email and password don't match. Try again or create an account.";
  }
  if (normalized.includes("email not confirmed")) {
    return "Confirm your email first, then come back here to sign in.";
  }
  if (normalized.includes("already registered")) {
    return "An account already uses that email. Try signing in instead.";
  }
  if (
    normalized.includes("rate limit") ||
    normalized.includes("rate_limit") ||
    normalized.includes("too many") ||
    normalized.includes("security purposes")
  ) {
    return "Please wait a moment before trying again.";
  }
  if (normalized.includes("user not found")) {
    return "No account was found with that email address.";
  }
  return "We couldn't complete that request. Please try again.";
}

export function validatePasswordReset(password: string, confirmPassword: string): string | null {
  if (password.length < 6) {
    return "Password must be at least 6 characters.";
  }
  if (password !== confirmPassword) {
    return "Passwords do not match. Please re-enter them.";
  }
  return null;
}
