# SPDX-License-Identifier: AGPL-3.0-only
"""Provisional local bounds; saving requires an explicit approved institution policy."""

from __future__ import annotations

from dataclasses import dataclass, fields

from fastapi import HTTPException


@dataclass(frozen=True)
class Policy:
    enabled: bool = False
    policy_id: str = ""
    retention_seconds: int = 0
    backup_max_age_seconds: int = 0
    deletion_ledger_file: str = ""
    max_body_bytes: int = 65536
    max_message_bytes: int = 8192
    max_messages: int = 200
    max_stored_bytes: int = 524288
    max_attempts: int = 5
    page_messages: int = 40
    page_bytes: int = 65536
    context_tokens: int = 16384
    model_tokens: int = 32768
    response_tokens: int = 1024
    pending_seconds: int = 120

    @classmethod
    def from_settings(cls, settings) -> Policy:
        return cls(**{f.name: getattr(settings, "dialogue_" + f.name) for f in fields(cls)})

    def require(self) -> None:
        if not self.enabled:
            raise HTTPException(
                409, "dialogue saving is disabled; ordinary tutoring remains available"
            )
        if self.configuration_errors():
            raise HTTPException(503, "dialogue saving policy is not configured")

    def configuration_errors(self) -> list[str]:
        """Operator diagnostics without disclosing configured values to HTTP clients."""
        errors = []
        if not self.policy_id:
            errors.append("DIALOGUE_POLICY_ID must be set")
        elif len(self.policy_id) > 128:
            errors.append("DIALOGUE_POLICY_ID must contain at most 128 characters")
        if not self.deletion_ledger_file:
            errors.append("DIALOGUE_DELETION_LEDGER_FILE must be set")
        for name in (
            "retention_seconds",
            "backup_max_age_seconds",
            "max_body_bytes",
            "max_message_bytes",
            "max_messages",
            "max_stored_bytes",
            "max_attempts",
            "page_messages",
            "page_bytes",
            "context_tokens",
            "response_tokens",
            "model_tokens",
            "pending_seconds",
        ):
            if getattr(self, name) <= 0:
                errors.append(f"DIALOGUE_{name.upper()} must be a positive integer")
        if self.page_bytes < self.max_message_bytes * 6 + 1024:
            errors.append("DIALOGUE_PAGE_BYTES must be >= 6 * DIALOGUE_MAX_MESSAGE_BYTES + 1024")
        if self.max_stored_bytes < self.max_message_bytes * 8 + 1024:
            errors.append(
                "DIALOGUE_MAX_STORED_BYTES must be >= 8 * DIALOGUE_MAX_MESSAGE_BYTES + 1024"
            )
        if self.context_tokens <= self.response_tokens:
            errors.append("DIALOGUE_CONTEXT_TOKENS must be > DIALOGUE_RESPONSE_TOKENS")
        if self.model_tokens <= self.context_tokens + 256:
            errors.append("DIALOGUE_MODEL_TOKENS must be > DIALOGUE_CONTEXT_TOKENS + 256")
        return errors
