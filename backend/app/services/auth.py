"""Supabase JWT verification, independent of HTTP and storage."""

import os
from dataclasses import dataclass

import jwt

JWKS_LIFESPAN_SECONDS = 600
ASYMMETRIC_ALGORITHMS = ("RS256", "ES256")


@dataclass(frozen=True)
class AuthSettings:
    mode: str  # "supabase" | "demo"
    supabase_url: str
    audience: str
    jwt_secret: str | None
    allow_anonymous: bool


@dataclass(frozen=True)
class AuthenticatedIdentity:
    subject: str
    email: str | None
    is_anonymous: bool


class InvalidTokenError(Exception):
    """The bearer token failed signature, claim, or lifetime checks."""


class AuthConfigurationError(Exception):
    """Required auth configuration is missing for the token's algorithm."""


def load_auth_settings() -> AuthSettings:
    mode = os.getenv("AUTH_MODE", "supabase").strip().lower()
    if mode not in {"supabase", "demo"}:
        raise AuthConfigurationError(
            f"Unsupported AUTH_MODE: {mode}. Expected 'supabase' or 'demo'."
        )
    return AuthSettings(
        mode=mode,
        supabase_url=os.getenv("SUPABASE_URL", "").strip().rstrip("/"),
        audience=os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated").strip(),
        jwt_secret=os.getenv("SUPABASE_JWT_SECRET", "").strip() or None,
        allow_anonymous=os.getenv("AUTH_ALLOW_ANONYMOUS", "false").strip().lower() == "true",
    )


class SupabaseTokenVerifier:
    def __init__(self, settings: AuthSettings) -> None:
        if not settings.supabase_url:
            raise AuthConfigurationError(
                "SUPABASE_URL is required to verify Supabase access tokens."
            )
        self.settings = settings
        self._jwks_client = jwt.PyJWKClient(
            f"{settings.supabase_url}/auth/v1/.well-known/jwks.json",
            cache_keys=True,
            lifespan=JWKS_LIFESPAN_SECONDS,
        )

    def verify(self, token: str) -> AuthenticatedIdentity:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise InvalidTokenError("The token is malformed.") from exc

        algorithm = header.get("alg", "")
        try:
            if algorithm == "HS256":
                if not self.settings.jwt_secret:
                    raise AuthConfigurationError(
                        "SUPABASE_JWT_SECRET is required to verify HS256 tokens."
                    )
                claims = self._decode(token, key=self.settings.jwt_secret, algorithms=["HS256"])
            elif algorithm in ASYMMETRIC_ALGORITHMS:
                signing_key = self._jwks_client.get_signing_key_from_jwt(token)
                claims = self._decode(token, key=signing_key.key, algorithms=[algorithm])
            else:
                raise InvalidTokenError(
                    "The token uses an unsupported signing algorithm."
                )
        except AuthConfigurationError:
            raise
        except jwt.PyJWTError as exc:
            raise InvalidTokenError("The token is invalid or expired.") from exc

        is_anonymous = bool(claims.get("is_anonymous", False))
        if is_anonymous and not self.settings.allow_anonymous:
            raise InvalidTokenError("Anonymous sessions are not accepted.")
        return AuthenticatedIdentity(
            subject=claims["sub"],
            email=claims.get("email"),
            is_anonymous=is_anonymous,
        )

    def _decode(self, token: str, *, key: str, algorithms: list[str]) -> dict:
        return jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience=self.settings.audience,
            issuer=f"{self.settings.supabase_url}/auth/v1",
            options={"require": ["exp", "sub"]},
        )
