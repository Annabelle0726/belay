# SPDX-License-Identifier: AGPL-3.0-only
"""
DS curriculum v0 — one module per taxonomy stratum (thin), with three exercises
that run end to end through `run` (grade + leak paths):

  ds-foundations  — compute grouped summaries from a CSV (wrangling/EDA).
  ds-regression   — fit + evaluate a regression on a held-out split (seeded).
  ds-mlp          — train a tiny numpy MLP to a loss threshold (seeded).

Exercises carry no numeric ``target``/``tol``; grading is spec-driven
(specs/<id>.json) and executed in the sandbox runner.
"""

from __future__ import annotations

from .solutions import SOLUTIONS

EXERCISES: list[dict] = [
    {
        "id": "ds-foundations",
        "module": "wrangling-eda",
        "order": 1,
        "prereqs": [],
        "title": "01 · Grouped summaries",
        "concept": "group-by and aggregation",
        "goalText": "Compute the mean amount per category from a CSV into `result`.",
        "prompt": (
            "Read data/sales.csv and build `result` as a dict mapping each "
            "category to its mean amount."
        ),
        "starter": SOLUTIONS["ds-foundations"]["starter"],
    },
    {
        "id": "ds-regression",
        "module": "regression-classification",
        "order": 1,
        "prereqs": ["ds-foundations"],
        "title": "02 · Held-out regression",
        "concept": "linear regression with held-out evaluation",
        "goalText": "Fit on the train split; predict `y_pred` for the test split (held-out R^2 ≥ 0.8).",
        "prompt": (
            "Fit a linear model on the training split, then set `y_pred` for "
            "X_test. You are graded on held-out R^2 — do not peek at y_test."
        ),
        "starter": SOLUTIONS["ds-regression"]["starter"],
    },
    {
        "id": "ds-mlp",
        "module": "optimization-nn-fundamentals",
        "order": 1,
        "prereqs": ["ds-regression"],
        "title": "03 · Tiny MLP from scratch",
        "concept": "multilayer perceptron trained with gradient descent",
        "goalText": "Train a one-hidden-layer numpy MLP until MSE `final_loss` ≤ 0.05 (seeded).",
        "prompt": (
            "Implement and train a tiny MLP (one hidden layer, numpy only) on "
            "the provided data until the training MSE `final_loss` ≤ 0.05. Seed "
            "your RNG for determinism."
        ),
        "starter": SOLUTIONS["ds-mlp"]["starter"],
    },
]

# One module per stratum (thin v0). Exercises attach to their stratum module.
MODULES: list[dict] = [
    {
        "id": "data-foundations",
        "title": "Module 1 · Data foundations",
        "summary": "Data types, tabular structure, tidy data, summary statistics.",
    },
    {
        "id": "wrangling-eda",
        "title": "Module 2 · Wrangling & EDA",
        "summary": "Filtering, group-by/aggregation, joins, reshaping, vectorization.",
    },
    {
        "id": "probability-inference",
        "title": "Module 3 · Probability & inference",
        "summary": "Random variables, sampling, CLT, hypothesis testing, correlation vs causation.",
    },
    {
        "id": "regression-classification",
        "title": "Module 4 · Regression & classification",
        "summary": "Linear/logistic regression, regularization, scaling, kNN, trees.",
    },
    {
        "id": "model-evaluation",
        "title": "Module 5 · Model evaluation & generalization",
        "summary": "Train/test split, leakage, cross-validation, over/underfitting, metrics.",
    },
    {
        "id": "optimization-nn-fundamentals",
        "title": "Module 6 · Optimization & NN fundamentals",
        "summary": "Gradient descent, loss functions, backprop, perceptrons, MLPs.",
    },
    {
        "id": "advanced-neural-networks",
        "title": "Module 7 · Advanced neural networks",
        "summary": "CNNs, sequence models, attention, transformers, transfer learning.",
    },
]

_BY_ID: dict[str, dict] = {e["id"]: e for e in EXERCISES}


def get_exercise(exercise_id: str) -> dict:
    if exercise_id not in _BY_ID:
        raise KeyError(f"unknown exercise: {exercise_id}")
    return _BY_ID[exercise_id]


def curriculum() -> dict:
    by_module = {m["id"]: {**m, "exercises": []} for m in MODULES}
    for ex in sorted(EXERCISES, key=lambda e: (e["module"], e["order"])):
        by_module[ex["module"]]["exercises"].append(ex)
    return {"modules": [by_module[m["id"]] for m in MODULES]}
