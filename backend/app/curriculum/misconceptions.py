"""
Misconception / expectation map for the abstraction-first QSE curriculum (F6).

Dual use:
  1. Peer-Reasoner input. For the current exercise, Sol is given the EXPECTATIONS
     (what a correct understanding looks like) and a short list of likely
     MISCONCEPTIONS, each with an observable SIGNATURE (detectable from the
     student's functional-model source, their last run distribution, and the
     recent dialogue) and a Socratic PEER_MOVE that surfaces the misconception
     WITHOUT handing over the fix. This is expectation-misconception tailored
     (EMT) dialogue in the AutoTutor tradition, adapted to a peer stance.
  2. Concept-inventory seed. Each expectation maps to a correct-answer / probe
     item; each misconception's `inventory_seed` is a ready-made distractor.
     The pre-registration's QSE concept inventory is built from these.

Stance handling (study integrity): the EXPECTATIONS and misconception SIGNATURES
are *capability/content* and are shared across the peer and oracle arms (so the
arms differ in stance, not in what the tutor knows). The PEER_MOVE (Socratic,
answer-free) is applied under the peer stance; under the oracle stance the same
misconception knowledge informs a direct explanation. The control arm runs no
reasoner, so this map is never consulted there.

The withholding governance gate still runs after the reasoner regardless, so a
peer_move that drifts toward a solution is caught deterministically downstream.

Data shape:
    CONCEPT[exercise_id] = {
        "concept": <one-line concept name>,
        "module":  <1|2|3>,
        "expectations": [ <correct-understanding statements> ],
        "misconceptions": [
            {
              "id":        <stable id>,
              "belief":    <the wrong idea, in the student's terms>,
              "signature": <how it shows up here: code pattern / wrong
                            distribution / verbal cue the reasoner can match>,
              "peer_move": <Socratic move: a prediction/observation prompt,
                            never the answer>,
              "inventory_seed": <distractor phrasing for the concept inventory>,
            }, ...
        ],
    }

CROSS_CUTTING holds Concept 3 (abstraction + debugging-by-specification) items
that apply to every exercise; `for_exercise()` merges them in.
"""
from __future__ import annotations

from typing import Dict, List, TypedDict


class Misconception(TypedDict):
    id: str
    belief: str
    signature: str
    peer_move: str
    inventory_seed: str


class ConceptEntry(TypedDict):
    concept: str
    module: int
    expectations: List[str]
    misconceptions: List[Misconception]


# ── Concept 1 — Superposition & single-qubit intent (Module 1) ───────────────
_SUPERPOSE: ConceptEntry = {
    "concept": "Superposition and single-qubit intent",
    "module": 1,
    "expectations": [
        "An equal superposition is a definite prepared state that yields 0 or 1 "
        "with equal probability over repeated measurement (50/50), not a hidden "
        "value we happen not to know.",
        "A measurement returns one of the basis outcomes (0 or 1); the outcome "
        "distribution (the bars) is what you read over many shots.",
        "At the abstraction layer you state intent (\"put q0 in equal "
        "superposition\") and the platform realizes it; you reason about the "
        "outcome distribution, not gate mechanics.",
    ],
    "misconceptions": [
        {
            "id": "M1.1-classical-ignorance",
            "belief": "The qubit is really 0 or 1 already and we just don't know "
                      "which (a coin under a cup).",
            "signature": "Student talks about the qubit's \"real\"/\"actual\" value, "
                         "or is confused/annoyed that re-running gives different "
                         "outcomes for the same program.",
            "peer_move": "Ask what they'd expect if they measured this same prepared "
                         "state many times versus measuring a qubit they had "
                         "definitely flipped to 1 — and whether \"don't know yet\" "
                         "and \"50/50 by preparation\" would look different in the bars.",
            "inventory_seed": "The qubit already has a definite value (0 or 1); "
                              "superposition just means we don't know it yet.",
        },
        {
            "id": "M1.2-halfway-value",
            "belief": "A superposed qubit holds an in-between value like 0.5, and "
                      "measuring returns that middle value.",
            "signature": "Student expects a measurement to read out 0.5 or a "
                         "fractional value, or is surprised the bars sit only on "
                         "0 and 1.",
            "peer_move": "Ask what values a single measurement can actually return, "
                         "then where the \"50\" they're picturing should live — in the "
                         "readout, or in how often each outcome shows up.",
            "inventory_seed": "Measuring a qubit in equal superposition returns 0.5.",
        },
        {
            "id": "M1.3-double-superpose",
            "belief": "Applying superpose twice makes the qubit \"more\" superposed "
                      "or more random.",
            "signature": "Source applies `superpose q0` twice (or repeatedly) to the "
                         "same qubit; student expects it to stay or become 50/50, "
                         "but the run shows a definite 0.",
            "peer_move": "Before they run it, ask them to predict the distribution "
                         "after applying the same operation to q0 twice — then have "
                         "them run it and reconcile what they see with what they "
                         "expected.",
            "inventory_seed": "Applying an equal-superposition operation twice to the "
                              "same qubit leaves it in equal superposition.",
        },
        {
            "id": "M1.4-measurement-cosmetic",
            "belief": "`measure all` is just a print/output line; one run gives the "
                      "answer.",
            "signature": "Student treats a single run as deterministic, ignores the "
                         "distribution, or omits/misreads `measure all`.",
            "peer_move": "Ask what a single run tells them versus what the bars across "
                         "many runs tell them, and which one the goal is actually "
                         "stated over.",
            "inventory_seed": "A quantum program's correctness is judged from a single "
                              "run's outcome.",
        },
    ],
}

# ── Concept 2 — Entanglement & multi-qubit structure (Module 2) ──────────────
_BELL: ConceptEntry = {
    "concept": "Entanglement and multi-qubit structure (Bell pair)",
    "module": 2,
    "expectations": [
        "Entanglement is a correlation that links qubits' outcomes; a Bell pair "
        "yields only 00 and 11 (never 01 or 10), each about 50%.",
        "Entanglement is created by an operation that links qubits (entangle / a "
        "controlled operation) acting on a qubit that is already in superposition "
        "— not by superposing each qubit separately.",
        "Operation order matters: the superposition must exist before the linking "
        "operation for the correlation to be nontrivial.",
    ],
    "misconceptions": [
        {
            "id": "M2.1-superpose-both-is-entangle",
            "belief": "Putting each qubit in superposition entangles them.",
            "signature": "For a correlated target (e.g., Bell), source applies "
                         "`superpose` to both q0 and q1 (or `superpose all`) with no "
                         "`entangle`; the run shows all four outcomes ~25% each "
                         "instead of only 00/11.",
            "peer_move": "Have them read their four roughly-equal bars and ask whether "
                         "the qubits are actually linked — what in their program "
                         "connects q0 to q1 so the two always agree? (This is exactly "
                         "the independence-vs-entanglement contrast.)",
            "inventory_seed": "Putting two qubits each in equal superposition makes "
                              "them entangled.",
        },
        {
            "id": "M2.2-entangle-is-copy",
            "belief": "Entangle just copies one qubit's value to the other "
                      "(classical fan-out), so it always makes them equal.",
            "signature": "Source applies `entangle q0 q1` with no preceding "
                         "`superpose` and expects a random-but-equal result; the run "
                         "shows a definite 00.",
            "peer_move": "Ask them to predict the distribution for entangle WITHOUT a "
                         "superposition first, then WITH one — and what that "
                         "difference says about where the randomness has to come from.",
            "inventory_seed": "Entangling two qubits copies the first qubit's value "
                              "onto the second.",
        },
        {
            "id": "M2.3-order-irrelevant",
            "belief": "The order of operations doesn't matter.",
            "signature": "Source applies `entangle q0 q1` before `superpose q0` (or "
                         "superposes the wrong qubit after entangling); the run is not "
                         "the Bell distribution (e.g., 00/10 instead of 00/11).",
            "peer_move": "Ask them to trace what state exists at the moment the "
                         "entangle runs in their current order, and whether that's the "
                         "state they meant to link.",
            "inventory_seed": "Reordering the operations in a functional model does not "
                              "change the resulting outcome distribution.",
        },
        {
            "id": "M2.4-independent-measurement",
            "belief": "Each qubit is measured independently even when entangled, so "
                      "01 and 10 should sometimes appear in a Bell pair.",
            "signature": "Student expects to occasionally see 01 or 10 in a correct "
                         "Bell pair, or is surprised those outcomes are absent.",
            "peer_move": "Point at the missing 01/10 bars and ask what their absence "
                         "implies about whether the two measurements are independent.",
            "inventory_seed": "In a Bell pair, each qubit is measured independently, so "
                              "all four outcomes can occur.",
        },
    ],
}

_UNIFORM2: ConceptEntry = {
    "concept": "Independence versus entanglement",
    "module": 2,
    "expectations": [
        "Two qubits each in superposition but not linked are independent: all four "
        "outcomes (00, 01, 10, 11) occur about equally (25% each).",
        "Independence (a product state) and entanglement (a correlated state) are "
        "different structures, readable from which outcomes appear.",
        "This is the deliberate contrast to the Bell pair: same superpositions, but "
        "no linking operation.",
    ],
    "misconceptions": [
        {
            "id": "M2.5-uniform-needs-entangle",
            "belief": "Getting all four outcomes equally requires entangling the "
                      "qubits.",
            "signature": "For the independence target, student adds `entangle` and is "
                         "surprised the four outcomes collapse to a correlated pair.",
            "peer_move": "Ask whether \"all four equally likely\" sounds like the "
                         "qubits agreeing or acting on their own — and which operation "
                         "would make them agree.",
            "inventory_seed": "Producing all four two-qubit outcomes equally requires "
                              "entanglement.",
        },
        {
            "id": "M2.6-uniform-is-entangled",
            "belief": "All four outcomes appearing means the qubits are entangled.",
            "signature": "Student describes the 25%-each result as \"entangled\" or "
                         "\"correlated.\"",
            "peer_move": "Ask whether knowing q0's outcome tells them anything about "
                         "q1's here — and how that compares to the Bell case where it "
                         "tells them everything.",
            "inventory_seed": "If all four two-qubit outcomes are equally likely, the "
                              "qubits are entangled.",
        },
    ],
}

_GHZ: ConceptEntry = {
    "concept": "Scaling entanglement (GHZ state)",
    "module": 2,
    "expectations": [
        "A GHZ state extends the Bell idea to three qubits: only 000 and 111, each "
        "about 50%.",
        "The correlation spreads from one superposed qubit out to the others "
        "through chained linking operations.",
    ],
    "misconceptions": [
        {
            "id": "M2.7-ghz-superpose-all",
            "belief": "Scaling up just means superposing all three qubits.",
            "signature": "Source applies `superpose all` (or superposes each qubit) "
                         "for the GHZ target; the run shows eight outcomes ~equal "
                         "instead of only 000/111.",
            "peer_move": "Recall what made the Bell pair agree, and ask how to spread "
                         "that same link from q0 out to q1 AND q2 — one qubit "
                         "superposed, the rest pulled along.",
            "inventory_seed": "A three-qubit GHZ state is made by putting all three "
                              "qubits in superposition.",
        },
        {
            "id": "M2.8-ghz-disconnected-links",
            "belief": "Linking the wrong pairs (or only one pair) still spreads the "
                      "correlation to all three.",
            "signature": "Source entangles a pair that leaves a qubit disconnected "
                         "(e.g., only `entangle q0 q1` for a 3-qubit target); the "
                         "third qubit stays 0.",
            "peer_move": "Ask which qubits are actually linked in their current chain, "
                         "and whether the third one is reached by any operation.",
            "inventory_seed": "Entangling one pair of qubits in a three-qubit register "
                              "correlates all three.",
        },
    ],
}

# ── Concept 3 — Specification → synthesized algorithm (Module 3; cross-cutting)
CROSS_CUTTING: ConceptEntry = {
    "concept": "From specification to synthesized algorithm (abstraction + "
               "debugging by specification)",
    "module": 3,
    "expectations": [
        "A functional model expresses intent and constraints; the platform "
        "synthesizes and optimizes the executable circuit. You reason about the "
        "specification, not a hand-tuned gate sequence.",
        "Correctness means the outcome distribution matches the target; debugging "
        "means reasoning from the mismatch between the distribution you got and "
        "the one you wanted.",
        "The same intent can be synthesized to different backends; the abstraction "
        "is portable.",
    ],
    "misconceptions": [
        {
            "id": "M3.1-literal-gates",
            "belief": "The functional model is a literal list of gates I must "
                      "micromanage, not an intent the compiler realizes.",
            "signature": "Student over-specifies or resists the abstraction, asking "
                         "how to control exact gate placement rather than stating the "
                         "intended state.",
            "peer_move": "Invite them to describe the destination they want (the "
                         "outcome distribution) and let the synthesis find the route, "
                         "rather than steering every step.",
            "inventory_seed": "A functional model is executed as the exact, "
                              "unoptimized sequence of operations the author writes.",
        },
        {
            "id": "M3.2-random-edits",
            "belief": "Debugging means changing operations until the check passes.",
            "signature": "Repeated submissions with small unprincipled edits and no "
                         "stated hypothesis (a repeated-error span with little change "
                         "in the distribution).",
            "peer_move": "Ask what the distribution they GOT tells them their program "
                         "is actually preparing, and what single difference from the "
                         "target that points to — one hypothesis, then one test.",
            "inventory_seed": "The best way to fix a failing quantum program is to try "
                              "changing operations until the output matches.",
        },
        {
            "id": "M3.3-looks-right",
            "belief": "If the code looks reasonable, it's correct.",
            "signature": "Student is confused when a plausible-looking program fails "
                         "the goal check (distance to target above tolerance).",
            "peer_move": "Anchor on the target distribution as the ground truth and "
                         "ask where their run's distribution departs from it.",
            "inventory_seed": "A quantum program is correct if its operations look "
                              "reasonable, regardless of the outcome distribution.",
        },
    ],
}


# ── registry + accessor ──────────────────────────────────────────────────────
CONCEPT: Dict[str, ConceptEntry] = {
    "superpose": _SUPERPOSE,
    "bell": _BELL,
    "uniform2": _UNIFORM2,
    "ghz": _GHZ,
}


def for_exercise(exercise_id: str) -> ConceptEntry:
    """Merged map for a turn: the exercise's own concept plus the cross-cutting
    abstraction/debugging items (Concept 3), which apply everywhere.

    Returns an empty-but-valid entry for unknown exercise ids so callers never
    need to special-case missing keys.
    """
    base = CONCEPT.get(exercise_id)
    if base is None:
        return {
            "concept": "(unknown exercise)",
            "module": 0,
            "expectations": list(CROSS_CUTTING["expectations"]),
            "misconceptions": list(CROSS_CUTTING["misconceptions"]),
        }
    return {
        "concept": base["concept"],
        "module": base["module"],
        "expectations": list(base["expectations"]) + list(CROSS_CUTTING["expectations"]),
        "misconceptions": list(base["misconceptions"]) + list(CROSS_CUTTING["misconceptions"]),
    }


def all_inventory_seeds() -> List[dict]:
    """Flatten every expectation (correct) and misconception distractor into
    concept-inventory item stubs, tagged by concept and exercise. Used to seed
    the QSE concept inventory referenced in the pre-registration."""
    items: List[dict] = []
    for ex_id, entry in {**CONCEPT, "_cross_cutting": CROSS_CUTTING}.items():
        for e in entry["expectations"]:
            items.append({"exercise": ex_id, "concept": entry["concept"],
                          "kind": "correct", "text": e})
        for m in entry["misconceptions"]:
            items.append({"exercise": ex_id, "concept": entry["concept"],
                          "kind": "distractor", "misconception_id": m["id"],
                          "text": m["inventory_seed"]})
    return items
