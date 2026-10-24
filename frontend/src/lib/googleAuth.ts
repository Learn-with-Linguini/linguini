type GoogleIdTokenClient = {
  auth: {
    signInWithIdToken: (credentials: {
      provider: "google";
      token: string;
    }) => Promise<{ error: { message: string } | null }>;
  };
};

export async function signInWithGoogleIdToken(client: GoogleIdTokenClient, credential: string) {
  if (!credential.trim()) throw new Error("Google did not return a sign-in credential.");
  return client.auth.signInWithIdToken({
    provider: "google",
    token: credential,
  });
}
