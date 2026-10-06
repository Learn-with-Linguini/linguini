"""Load, validate and resolve secrets for :class:`AiConfig` without network I/O."""

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.ai.config.models import (
    ADAPTERS,
    FEATURE_CAPABILITIES,
    AiConfig,
    AiConfigurationError,
    AiFeature,
    AiProvider,
)


def _describe(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in error['loc']) or 'config'}: {error['msg']}"
        for error in exc.errors(include_url=False, include_input=False, include_context=False)
    )


def parse_ai_config(data: Mapping[str, Any]) -> AiConfig:
    """Validate parsed TOML data; error messages never echo input values."""
    try:
        config = AiConfig.model_validate(data)
    except ValidationError as exc:
        raise AiConfigurationError(f"Invalid AI configuration: {_describe(exc)}") from None
    validate_ai_config(config)
    return config


def load_ai_config_file(path: str | Path) -> AiConfig:
    path = Path(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise AiConfigurationError(f"AI config file not found: {path}") from None
    except tomllib.TOMLDecodeError as exc:
        raise AiConfigurationError(f"Invalid TOML in AI config file {path}: {exc}") from None
    return parse_ai_config(data)


def validate_ai_config(config: AiConfig) -> None:
    """Check references, adapter support and feature capabilities."""
    problems: list[str] = []

    for credential_id, credential in config.credentials.items():
        if credential.adapter not in ADAPTERS:
            problems.append(
                f"credentials.{credential_id}: unsupported adapter {credential.adapter.value!r}"
            )

    for deployment_id, deployment in config.deployments.items():
        where = f"deployments.{deployment_id}"
        spec = ADAPTERS.get(deployment.adapter)
        if spec is None:
            problems.append(f"{where}: unsupported adapter {deployment.adapter.value!r}")
            continue
        if deployment.api not in spec.apis:
            problems.append(
                f"{where}: adapter {deployment.adapter.value!r} does not support api "
                f"{deployment.api.value!r}"
            )
        unsupported = deployment.capabilities - spec.capabilities
        if unsupported:
            problems.append(
                f"{where}: adapter {deployment.adapter.value!r} does not support "
                f"{', '.join(sorted(unsupported))}"
            )
        if deployment.adapter is AiProvider.OPENROUTER:
            if deployment.upstream_fallback is None:
                problems.append(
                    f"{where}: OpenRouter deployments need upstream_fallback "
                    "(set allow_fallbacks explicitly)"
                )
        elif deployment.upstream_fallback is not None:
            problems.append(f"{where}: upstream_fallback is only supported for openrouter")
        for credential_id in deployment.credentials:
            credential = config.credentials.get(credential_id)
            if credential is None:
                problems.append(f"{where}: unknown credential {credential_id!r}")
            elif credential.adapter is not deployment.adapter:
                problems.append(
                    f"{where}: credential {credential_id!r} is for adapter "
                    f"{credential.adapter.value!r}, not {deployment.adapter.value!r}"
                )

    for feature in AiFeature:
        route = config.routes.get(feature)
        where = f"routes.{feature.value}"
        if route is None:
            problems.append(f"{where}: missing route (set enabled = false to turn it off)")
            continue
        if len(set(route.deployments)) != len(route.deployments):
            problems.append(f"{where}: deployments are listed more than once")
        known = [d for d in route.deployments if d in config.deployments]
        for deployment_id in route.deployments:
            if deployment_id not in config.deployments:
                problems.append(f"{where}: unknown deployment {deployment_id!r}")
        if not route.enabled:
            continue
        if not route.deployments:
            problems.append(f"{where}: an enabled route needs at least one deployment")
        if route.deadline_seconds is None:
            problems.append(f"{where}: an enabled route needs deadline_seconds")
        if route.max_model_calls is None:
            problems.append(f"{where}: an enabled route needs max_model_calls")
        for deployment_id in known:
            missing = FEATURE_CAPABILITIES[feature] - config.deployments[deployment_id].capabilities
            if missing:
                problems.append(
                    f"{where}: deployment {deployment_id!r} lacks {', '.join(sorted(missing))}"
                )
        if route.deployments and route.deployments[0] in config.deployments:
            defaults = config.deployments[route.deployments[0]].defaults
            deadline = route.deadline_seconds
            if deadline is not None and deadline < defaults.timeout_seconds:
                problems.append(
                    f"{where}: deadline_seconds is shorter than the primary deployment's "
                    "timeout_seconds"
                )
            attempts = 1 + min(defaults.max_retries, 1)
            if route.max_model_calls is not None and route.max_model_calls < attempts:
                problems.append(
                    f"{where}: max_model_calls is below the primary deployment's "
                    f"{attempts} attempt(s)"
                )

    if problems:
        raise AiConfigurationError("Invalid AI configuration: " + "; ".join(problems))


def resolve_credential_secrets(config: AiConfig, env: Mapping[str, str]) -> dict[str, str]:
    """Map each credential ID to the first non-empty value among its env vars."""
    secrets: dict[str, str] = {}
    for credential_id, credential in config.credentials.items():
        for name in credential.env:
            value = (env.get(name) or "").strip()
            if value:
                secrets[credential_id] = value
                break
    return secrets


def select_credential(
    config: AiConfig, deployment_credentials: tuple[str, ...], secrets: Mapping[str, str]
) -> str:
    """The first eligible credential with a secret, else the first eligible one."""
    for credential_id in deployment_credentials:
        if secrets.get(credential_id):
            return credential_id
    return deployment_credentials[0]


def missing_secret_problems(config: AiConfig, secrets: Mapping[str, str]) -> list[str]:
    problems: list[str] = []
    for feature in AiFeature:
        primary = config.primary_deployment(feature)
        if primary is None:
            continue
        _, deployment = primary
        if any(secrets.get(c) for c in deployment.credentials):
            continue
        names = [n for c in deployment.credentials for n in config.credentials[c].env]
        problems.append(
            f"{feature.value}: no secret for credential(s) "
            f"{', '.join(deployment.credentials)} (set {' or '.join(names)})"
        )
    return problems
