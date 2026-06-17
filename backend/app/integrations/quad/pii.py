"""
PII boundary for the Quad sidecar (privacy is the hard constraint).

The ONLY identity the sidecar accepts is a pseudonymous host id — the host's
numeric user id namespaced by provider, e.g. ``gh:12345``. Any payload carrying
names, SIS identifiers, or plaintext email is REFUSED at the boundary with a clear
error. This mirrors the EduCloud privacy posture: real names and SIS IDs never
reach the server; the tutor sees a pseudonymous id + submission content only.
"""

from __future__ import annotations

import re

# pseudo_id := <provider>:<numeric host user id>, e.g. gh:12345, gl:9, host:42.
PSEUDO_ID_RE = re.compile(r"^[a-z0-9_]+:[0-9]+$")

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Field keys that may not appear anywhere in a Quad payload (normalized: lowercased,
# non-alphanumerics stripped). Names, SIS ids, and contact identifiers.
_NAME_KEYS = {
    "name",
    "firstname",
    "lastname",
    "fullname",
    "realname",
    "displayname",
    "givenname",
    "surname",
    "fname",
    "lname",
    "preferredname",
}

# Keys whose pedagogical content legitimately may contain '@' or names and is NOT
# scanned for email patterns (student code / dialogue / their own message).
_CONTENT_KEYS = {"source"}


def _norm(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _forbidden_key(key: str) -> bool:
    n = _norm(key)
    if n in _NAME_KEYS:
        return True
    # SIS / student identifiers, email, SSN, phone (substring on normalized key).
    return any(t in n for t in ("sis", "student", "email", "ssn", "phone", "mail"))


def pii_reason(payload: dict) -> str | None:
    """Return a human-readable reason if the payload carries PII, else None.

    Checks, recursively over the whole payload:
      1. forbidden identity field keys (name / SIS / student id / email / ssn / phone);
      2. plaintext email patterns in any value except the pedagogical `source`;
    and that ``pseudo_id`` (if present) is a bare pseudonymous host id.
    """
    pid = payload.get("pseudo_id")
    if pid is not None and not PSEUDO_ID_RE.match(str(pid)):
        return (
            f"pseudo_id must be a pseudonymous host id like 'gh:12345' "
            f"(provider:numeric-id); got {pid!r}"
        )

    def walk(node, under_content: bool) -> str | None:
        if isinstance(node, dict):
            for k, v in node.items():
                if _forbidden_key(k):
                    return f"forbidden PII field {k!r}: names, SIS/student ids, email, ssn, and phone are not accepted"
                r = walk(v, under_content or _norm(k) in _CONTENT_KEYS)
                if r:
                    return r
        elif isinstance(node, list):
            for item in node:
                r = walk(item, under_content)
                if r:
                    return r
        elif isinstance(node, str):
            if not under_content and _EMAIL_RE.search(node):
                return "plaintext email detected; the sidecar accepts pseudonymous ids only"
        return None

    return walk(payload, under_content=False)


class PIIRejected(ValueError):
    """Raised when a Quad payload carries PII (rejected at the boundary)."""


def assert_no_pii(payload: dict) -> None:
    reason = pii_reason(payload)
    if reason:
        raise PIIRejected(reason)
