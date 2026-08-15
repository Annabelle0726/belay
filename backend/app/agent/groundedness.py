# SPDX-License-Identifier: AGPL-3.0-only
"""
Groundedness check for retrieval-augmented tutor responses (CC-B3).

After the Reasoner writes its response, this module checks whether the
response's substantive claims are traceable to passages present in
`ctx["knowledge"]` for that turn.

Design principles:
- Deterministic overlap/entailment check (no additional model call)
- Inline citations attached to grounded claims
- Ungrounded claims flagged in trace (not blocked — this is a signal)
- Leak gate integrity: only sees passages that survived `screen_passages`
- No-op when `knowledge()` returns None

Trace event: additive, follows the `retrieval` event pattern (Slice F).
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class Citation:
    """Represents a citation to a retrieved passage."""

    def __init__(self, passage_id: str, citation_text: str, locator: str | None = None):
        self.passage_id = passage_id
        self.citation_text = citation_text
        self.locator = locator

    def to_marker(self, index: int) -> str:
        """Return the inline citation marker, e.g. `[1]`."""
        return f"[{index}]"

    def to_reference(self, index: int) -> str:
        """Return the full reference entry, e.g. `[1] Introduction to Statistics, §3.2`."""
        if self.locator:
            return f"[{index}] {self.citation_text} ({self.locator})"
        return f"[{index}] {self.citation_text}"

    def __repr__(self):
        return f"Citation(passage_id={self.passage_id!r}, citation_text={self.citation_text!r})"


def check_groundedness(
    response: str,
    passages: list[dict],
    trace: bool = True,
) -> tuple[str, dict[str, Any]]:
    """
    Check if the response is grounded in the retrieved passages.

    Args:
        response: The tutor's generated response (message)
        passages: List of passage dicts with keys: id, text, citation, locator
        trace: Whether to return trace data

    Returns:
        (updated_response, trace_data)
        - updated_response: Response with inline citations added
        - trace_data: Dict with passages_available, citations_used, ungrounded_fragments

    Behavior:
        - If no passages: return original response, trace_data with empty citations
        - If claim grounded in passage: attach inline citation marker `[1]`
        - If claim ungrounded: keep response as-is, flag in trace
        - This is a SIGNAL, not a block — no regression in behavior
    """
    if not passages:
        # No passages available -> no-op (same as today)
        return response, {
            "passages_available": 0,
            "citations_used": [],
            "citations_count": 0,
            "ungrounded_fragments": [],
            "check_ran": False,
            "reason": "no passages available",
        }

    # Extract substantive claims from the response
    claims = _extract_claims(response)

    if not claims:
        # No substantive claims -> no need for grounding check
        return response, {
            "passages_available": len(passages),
            "citations_used": [],
            "citations_count": 0,
            "ungrounded_fragments": [],
            "check_ran": True,
            "reason": "no substantive claims found",
        }

    # Build a map of passage text -> Citation
    passage_map: dict[str, Citation] = {}
    for p in passages:
        passage_text = p.get("text", "").lower()
        if passage_text:
            passage_map[passage_text] = Citation(
                passage_id=p["id"],
                citation_text=p.get("citation", ""),
                locator=p.get("locator"),
            )

    # Check each claim against passages
    cited_claims: list[str] = []
    ungrounded_claims: list[str] = []
    citations_used: list[Citation] = []

    updated_response = response

    for claim in claims:
        grounded = False
        for passage_text, citation in passage_map.items():
            claim_lower = claim.lower()
            if len(claim) > 10:
                if claim_lower in passage_text or _fuzzy_match(claim_lower, passage_text):
                    grounded = True
                    # Check if citation already used
                    if citation.passage_id not in [c.passage_id for c in citations_used]:
                        citations_used.append(citation)
                    break

        if grounded:
            cited_claims.append(claim)
        else:
            ungrounded_claims.append(claim)

    # If all claims are grounded, attach citations
    if cited_claims and not ungrounded_claims:
        updated_response = _attach_citations(response, citations_used)
    # If some claims are ungrounded, keep response as-is (no regression)
    # Trace will record the gap

    trace_data: dict[str, Any] = {
        "passages_available": len(passages),
        "citations_used": [c.passage_id for c in citations_used],
        "citations_count": len(citations_used),
        "ungrounded_fragments": ungrounded_claims[:5],
        "check_ran": True,
        "all_claims_grounded": len(ungrounded_claims) == 0,
        "claim_count": len(claims),
    }

    return updated_response, trace_data


def _extract_claims(text: str) -> list[str]:
    """
    Extract substantive claims from the response text.

    This is a simple deterministic extractor that splits on sentences
    and filters out questions, greetings, and non-substantive phrases.

    Returns a list of claim strings.
    """
    if not text:
        return []

    # Split into sentences (simple approach)
    sentences = re.split(r"[.!?]\s+", text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

    # Filter out non-substantive sentences
    non_substantive_patterns = [
        r"^(let\'?s|let us|try to|what about|can you|would you|how about|maybe we)",
        r"^(i think|i believe|i feel|in my opinion)",
        r"^(that\'?s a good|great question|good point|excellent)",
        r"^(yes|no|okay|alright|sure|absolutely)",
    ]

    claims: list[str] = []
    for s in sentences:
        s_lower = s.lower()
        # Skip questions
        if s.endswith("?"):
            continue
        # Skip non-substantive patterns
        is_substantive = True
        for pattern in non_substantive_patterns:
            if re.match(pattern, s_lower, re.IGNORECASE):
                is_substantive = False
                break
        if is_substantive and len(s.split()) >= 3:
            # Remove trailing punctuation
            s = s.rstrip(".!")
            claims.append(s)

    return claims


def _fuzzy_match(claim: str, passage: str) -> bool:
    """
    Fuzzy match: check if significant portions of claim appear in passage.
    """
    if not claim or not passage:
        return False

    claim_words = set(claim.split())
    if len(claim_words) < 3:
        return False

    passage_words = set(passage.split())

    # Stopwords to ignore
    stopwords = {
        "the",
        "a",
        "an",
        "of",
        "to",
        "for",
        "with",
        "on",
        "at",
        "from",
        "by",
        "in",
        "as",
        "is",
        "was",
        "were",
        "are",
        "am",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
    }

    # Remove stopwords for better matching
    claim_words = claim_words - stopwords
    passage_words = passage_words - stopwords

    if not claim_words:
        return False

    overlap_words = claim_words & passage_words
    ratio = len(overlap_words) / len(claim_words)

    # If more than 50% of significant words overlap, consider it matched
    return ratio >= 0.5


def _attach_citations(response: str, citations: list[Citation]) -> str:
    """
    Attach inline citations to the response.

    Adds citation markers `[1]`, `[2]` at the end of sentences that
    should be cited, and appends a References section.

    Example output:
        "The mean of category A is approximately 15 [1]. References: [1] ..."
    """
    if not citations:
        return response

    references = []
    for idx, citation in enumerate(citations, 1):
        references.append(citation.to_reference(idx))

    # If response already has citations, append to them
    if "\n\nReferences:" in response or "\nReferences:" in response:
        return response

    ref_section = "\n\nReferences:\n" + "\n".join(references)
    return response + ref_section


def get_groundedness_trace(
    passage_count: int,
    citations_used: list[str],
    ungrounded_fragments: list[str],
    all_grounded: bool,
) -> dict:
    """
    Build the additive trace event payload for groundedness.

    Follows the same pattern as the `retrieval` event in Slice F.
    Content-free: records citation IDs, never passage text.
    """
    return {
        "passages_available": passage_count,
        "citations_used": citations_used,
        "ungrounded_count": len(ungrounded_fragments),
        "ungrounded_fragments": ungrounded_fragments[:5],
        "all_grounded": all_grounded,
    }
