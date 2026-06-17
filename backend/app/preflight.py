"""
Preflight doctor — verify config, store reachability, and provider endpoint
reachability BEFORE serving.

    python -m app.preflight            # all checks (exit non-zero on any failure)
    python -m app.preflight --skip-provider

Operators run this before/at bring-up; the container CMD runs it informationally.
"""

from __future__ import annotations

import argparse
import urllib.request

from .config import settings


def check_config() -> tuple[bool, str]:
    issues = []
    from .agent.llm import provider_class

    try:
        provider_class(settings.provider)
    except Exception as e:  # noqa: BLE001
        issues.append(str(e))
    if settings.store_backend not in ("sql", "memory"):
        issues.append(f"STORE_BACKEND must be sql|memory, got {settings.store_backend!r}")
    pack_id = None
    try:
        from .core.registry import get_active_pack

        pack_id = get_active_pack().id
    except Exception as e:  # noqa: BLE001
        issues.append(f"TUTOR_PACK unresolvable: {e}")
    if issues:
        return False, "; ".join(issues)
    return True, (
        f"provider={settings.provider} pack={pack_id} "
        f"store={settings.store_backend} db={settings.database_url}"
    )


def check_store() -> tuple[bool, str]:
    try:
        from sqlalchemy import text

        from .store.db import engine

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        kind = "postgres" if settings.store_is_postgres else "sqlite"
        return True, f"store reachable ({kind}): {settings.database_url}"
    except Exception as e:  # noqa: BLE001
        return False, f"store unreachable: {e}"


def check_provider(timeout: float = 3.0) -> tuple[bool, str]:
    if settings.provider == "openai_compatible":
        url = settings.openai_base_url.rstrip("/") + "/models"
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {settings.openai_api_key}"}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return True, f"openai_compatible endpoint reachable: {url} (HTTP {resp.status})"
        except Exception as e:  # noqa: BLE001
            return False, f"openai_compatible endpoint unreachable: {url} ({e})"
    if settings.provider == "anthropic":
        ok = bool(settings.anthropic_api_key)
        return ok, ("ANTHROPIC_API_KEY is set" if ok else "ANTHROPIC_API_KEY not set")
    if settings.provider == "bedrock":
        return True, "bedrock is a documented stub (not live)"
    return False, f"unknown provider {settings.provider!r}"


def run(probe_provider: bool = True) -> list[tuple[str, tuple[bool, str]]]:
    checks: list[tuple[str, tuple[bool, str]]] = [
        ("config", check_config()),
        ("store", check_store()),
    ]
    if probe_provider:
        checks.append(("provider", check_provider()))
    return checks


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="app.preflight", description="Preflight doctor")
    p.add_argument(
        "--skip-provider", action="store_true", help="skip the provider-endpoint reachability probe"
    )
    args = p.parse_args(argv)

    all_ok = True
    for name, (ok, msg) in run(probe_provider=not args.skip_provider):
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {msg}")
        all_ok = all_ok and ok
    # Slice H/G visibility: a half-armed distress opt-in is a WARN, not a hard FAIL
    # (it renders the safe generic frame). Surface it in deployment testing.
    from .agent import distress as _distress

    if _distress.warn_if_misconfigured(settings):
        print(
            "[WARN] distress: DISTRESS_ROUTING_ENABLED is on but support/escalation are "
            "unset ([FILL-IN]); the safe generic frame will render. Set them before go-live."
        )
    print("preflight: OK" if all_ok else "preflight: FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
