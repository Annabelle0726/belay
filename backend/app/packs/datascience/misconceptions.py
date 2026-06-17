# SPDX-License-Identifier: AGPL-3.0-only
"""
DS misconception / expectation library (v0) — EMT dialogue input for the
Peer-Reasoner, in the same shape the context layer consumes for quantum.

~18 canonical data-science misconceptions, each tagged to a taxonomy node (see
taxonomy.MISCONCEPTION_CONCEPT) with an observable SIGNATURE and a Socratic
PEER_MOVE that surfaces it without handing over the fix. ``for_exercise`` merges
an exercise's own misconceptions with the cross-cutting set (leakage, p-values,
over/underfitting, …) that apply everywhere.
"""

from __future__ import annotations

from typing import TypedDict


class Misconception(TypedDict):
    id: str
    belief: str
    signature: str
    peer_move: str
    inventory_seed: str


class ConceptEntry(TypedDict):
    concept: str
    expectations: list[str]
    misconceptions: list[Misconception]


_FOUNDATIONS: ConceptEntry = {
    "concept": "Group-by and aggregation",
    "expectations": [
        "Group-by partitions rows by a key, then aggregates each group to one value.",
        "An aggregation (mean/sum/count) collapses many rows per group into a single number.",
        "The grouping key becomes the index/label of the result, not a value to average.",
    ],
    "misconceptions": [
        {
            "id": "DS-groupby-reset",
            "belief": "After grouping you still have all the original rows; aggregation is optional.",
            "signature": "Student groups but never aggregates, or expects per-row output from a group-by.",
            "peer_move": "Ask how many numbers they expect per category in the result, and what operation turns a category's many rows into that one number.",
            "inventory_seed": "group-by returns the same number of rows as the input.",
        },
        {
            "id": "DS-apply-loop",
            "belief": "You must loop over rows in Python to compute per-group summaries.",
            "signature": "Student writes an explicit for-loop over rows instead of group-by/vectorized aggregation.",
            "peer_move": "Ask what a single group-by + mean would replace in their loop, and what that buys in clarity and speed.",
            "inventory_seed": "the only way to summarize groups is a Python for-loop over rows.",
        },
        {
            "id": "DS-mean-vs-median",
            "belief": "Mean and median are interchangeable summaries.",
            "signature": "Student swaps mean/median freely or is surprised an outlier moves the mean.",
            "peer_move": "Ask what would happen to each summary if one amount in a category were 10x larger.",
            "inventory_seed": "mean and median always give the same value.",
        },
        {
            "id": "DS-missing-drop",
            "belief": "Missing values can be ignored; they don't affect a mean.",
            "signature": "Student assumes NA rows silently drop or count as zero in an aggregation.",
            "peer_move": "Ask what their aggregation does with a missing amount — skip it, error, or treat it as zero?",
            "inventory_seed": "missing values are treated as zero when computing a mean.",
        },
    ],
}

_REGRESSION: ConceptEntry = {
    "concept": "Linear regression with held-out evaluation",
    "expectations": [
        "Fit parameters on the TRAIN split only; estimate generalization on the held-out TEST split.",
        "R^2 measures variance explained on data the model did not see during fitting.",
        "A linear fit needs an intercept term unless the data is centered.",
    ],
    "misconceptions": [
        {
            "id": "DS-r2-meaning",
            "belief": "R^2 measures how well the model fits the training data.",
            "signature": "Student reports training R^2 as the result or expects test R^2 ≈ train R^2 always.",
            "peer_move": "Ask which split the score should be computed on if the question is 'will it generalize'.",
            "inventory_seed": "a high training R^2 means the model will generalize.",
        },
        {
            "id": "DS-normalization-skip",
            "belief": "Feature scaling never matters for linear models.",
            "signature": "Student is surprised by coefficient magnitudes or unstable fits on unscaled features.",
            "peer_move": "Ask whether features on very different scales would make the coefficients comparable, and when scaling would change the prediction.",
            "inventory_seed": "feature scaling has no effect on any model.",
        },
        {
            "id": "DS-broadcasting-shape",
            "belief": "Array shapes line up automatically; shape errors are random.",
            "signature": "ValueError on shape mismatch (e.g., (n,) vs (n,1)) in the design matrix or prediction.",
            "peer_move": "Ask them to print the shapes of X_test and their prediction, and where the dimensions should match.",
            "inventory_seed": "numpy operations ignore array shapes.",
        },
        {
            "id": "DS-corr-causation",
            "belief": "A strong fit / correlation means one variable causes the other.",
            "signature": "Student interprets a regression coefficient as a causal effect.",
            "peer_move": "Ask what else could explain the association besides X causing y.",
            "inventory_seed": "a strong correlation proves causation.",
        },
    ],
}

_MLP: ConceptEntry = {
    "concept": "MLP trained with gradient descent",
    "expectations": [
        "A loss measures error; gradient descent steps parameters downhill to reduce it.",
        "The learning rate sets step size: too big diverges, too small crawls.",
        "Nonlinear activations let an MLP fit non-linearly-separable data (e.g., XOR).",
    ],
    "misconceptions": [
        {
            "id": "DS-learning-rate",
            "belief": "A bigger learning rate always trains faster.",
            "signature": "Loss explodes / NaNs, or oscillates without decreasing.",
            "peer_move": "Ask what their loss curve looks like across epochs, and whether it is descending or bouncing.",
            "inventory_seed": "increasing the learning rate always speeds up convergence.",
        },
        {
            "id": "DS-gd-local-minima",
            "belief": "Gradient descent always reaches the global minimum.",
            "signature": "Student is confused when the same code with a different seed reaches a different loss.",
            "peer_move": "Ask whether the starting weights might change where descent ends up, and what that says about a single run.",
            "inventory_seed": "gradient descent always finds the global minimum.",
        },
        {
            "id": "DS-relu-dead",
            "belief": "More layers / units always help; activations are interchangeable.",
            "signature": "Student stacks units but the network can't separate XOR, or uses no nonlinearity.",
            "peer_move": "Ask whether a network with no nonlinear activation can ever bend a straight decision boundary.",
            "inventory_seed": "a network of only linear layers can solve XOR.",
        },
    ],
}

# Apply to every exercise (the generalization/inference habits of mind).
CROSS_CUTTING: ConceptEntry = {
    "concept": "Generalization and honest evaluation (cross-cutting)",
    "expectations": [
        "Decisions are judged on held-out data, not the data used to build the model.",
        "A metric is only meaningful relative to a baseline and the data it was measured on.",
    ],
    "misconceptions": [
        {
            "id": "DS-train-test-leakage",
            "belief": "It's fine to fit preprocessing or the model using the test set.",
            "signature": "Student fits/scales on the full dataset before splitting, or peeks at test labels.",
            "peer_move": "Ask what the test set is standing in for, and whether the model is allowed to have seen it.",
            "inventory_seed": "scaling on the whole dataset before splitting is harmless.",
        },
        {
            "id": "DS-data-snooping",
            "belief": "Tuning until the test score is highest is good practice.",
            "signature": "Student repeatedly edits to maximize the reported test metric.",
            "peer_move": "Ask what the test score still estimates after you've optimized against it many times.",
            "inventory_seed": "optimizing directly against the test score gives an honest estimate.",
        },
        {
            "id": "DS-overfit-underfit",
            "belief": "Lower training error is always better.",
            "signature": "Student drives training error to zero and is surprised test error rises.",
            "peer_move": "Ask what the gap between train and test error tells them about the model's complexity.",
            "inventory_seed": "the model with the lowest training error generalizes best.",
        },
        {
            "id": "DS-accuracy-imbalanced",
            "belief": "Accuracy is always the right metric.",
            "signature": "Student reports 95% accuracy on a 95/5 imbalanced problem as success.",
            "peer_move": "Ask what accuracy a model that always predicts the majority class would get here.",
            "inventory_seed": "high accuracy always means a good classifier.",
        },
        {
            "id": "DS-pvalue-ph0",
            "belief": "A p-value is the probability the null hypothesis is true.",
            "signature": "Student says 'p=0.04 means 4% chance H0 is true'.",
            "peer_move": "Ask what is being held fixed when a p-value is computed — the hypothesis, or the data.",
            "inventory_seed": "the p-value is the probability that the null hypothesis is true.",
        },
        {
            "id": "DS-threshold-fixed",
            "belief": "0.5 is always the right classification threshold.",
            "signature": "Student never considers moving the decision threshold for an imbalanced/asymmetric cost task.",
            "peer_move": "Ask what changes if false positives and false negatives cost very different amounts.",
            "inventory_seed": "the classification threshold should always be 0.5.",
        },
        {
            "id": "DS-sample-population",
            "belief": "A sample statistic equals the population value.",
            "signature": "Student treats one sample's mean as the exact truth, ignoring sampling variation.",
            "peer_move": "Ask how much the mean might move if they drew a different sample of the same size.",
            "inventory_seed": "a sample mean equals the population mean exactly.",
        },
    ],
}


_BY_EXERCISE: dict[str, ConceptEntry] = {
    "ds-foundations": _FOUNDATIONS,
    "ds-regression": _REGRESSION,
    "ds-mlp": _MLP,
}


def for_exercise(exercise_id: str) -> dict:
    """Merged map for a turn: the exercise's own concept items + cross-cutting."""
    base = _BY_EXERCISE.get(exercise_id)
    if base is None:
        return {
            "concept": "(unknown exercise)",
            "expectations": list(CROSS_CUTTING["expectations"]),
            "misconceptions": [dict(m) for m in CROSS_CUTTING["misconceptions"]],
        }
    return {
        "concept": base["concept"],
        "expectations": list(base["expectations"]) + list(CROSS_CUTTING["expectations"]),
        "misconceptions": [dict(m) for m in base["misconceptions"]]
        + [dict(m) for m in CROSS_CUTTING["misconceptions"]],
    }


def all_inventory_seeds() -> list[dict]:
    items: list[dict] = []
    for ex_id, entry in {**_BY_EXERCISE, "_cross_cutting": CROSS_CUTTING}.items():
        for e in entry["expectations"]:
            items.append(
                {"exercise": ex_id, "concept": entry["concept"], "kind": "correct", "text": e}
            )
        for m in entry["misconceptions"]:
            items.append(
                {
                    "exercise": ex_id,
                    "concept": entry["concept"],
                    "kind": "distractor",
                    "misconception_id": m["id"],
                    "text": m["inventory_seed"],
                }
            )
    return items
