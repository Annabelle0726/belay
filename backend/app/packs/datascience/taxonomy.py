"""
Data-science concept taxonomy (v0).

~65 concepts across seven strata, with prerequisite edges (concept -> concept)
that the persistent learner model's spaced-revisit machinery consumes through the
`Taxonomy` interface (Taxonomy.relevant_concepts walks Concept.prereqs).

FUTURE ANCHOR: this file is the intended anchor point for textbook-grounded
knowledge bases — each concept id is a stable key a `KnowledgeBase` can attach
cited passages to (see core.domain.KnowledgeBase; no retrieval is built yet).

Strata (id prefix is informational only; ids are globally unique):
  1 data-foundations      2 wrangling-eda            3 probability-inference
  4 regression-classification                        5 model-evaluation
  6 optimization-nn-fundamentals                     7 advanced-neural-networks
"""
from __future__ import annotations

from ...core.domain import Concept, Taxonomy

# (id, label, (prereq concept ids,))
_CONCEPTS: list[tuple[str, str, tuple[str, ...]]] = [
    # ── 1. data foundations ──────────────────────────────────────────────────
    ("data-types", "Data types (numeric, categorical, ordinal, datetime)", ()),
    ("tabular-structure", "Tabular data: rows as observations, columns as variables", ("data-types",)),
    ("tidy-data", "Tidy data principles", ("tabular-structure",)),
    ("missing-data", "Missing data and NA semantics", ("tabular-structure",)),
    ("data-io", "Reading and writing data (CSV, etc.)", ("tabular-structure",)),
    ("indexing-selection", "Indexing and selection", ("tabular-structure",)),
    ("summary-statistics", "Summary statistics (mean, median, std)", ("data-types",)),
    ("data-provenance", "Data provenance, units, and measurement", ("tabular-structure",)),
    # ── 2. wrangling & EDA ───────────────────────────────────────────────────
    ("filtering", "Filtering rows by condition", ("indexing-selection",)),
    ("grouping-aggregation", "Group-by and aggregation", ("filtering", "summary-statistics")),
    ("joins-merge", "Joining and merging tables", ("tabular-structure",)),
    ("reshaping", "Reshaping (pivot/melt, long vs wide)", ("tidy-data",)),
    ("vectorization", "Vectorized operations over arrays/columns", ("data-types",)),
    ("broadcasting", "Broadcasting and shape alignment", ("vectorization",)),
    ("apply-map", "Apply/map vs vectorization", ("vectorization",)),
    ("eda-visual", "Exploratory data visualization", ("summary-statistics",)),
    ("outliers", "Outlier detection and handling", ("summary-statistics",)),
    ("feature-engineering", "Feature engineering basics", ("grouping-aggregation",)),
    # ── 3. probability & statistical inference ───────────────────────────────
    ("random-variables", "Random variables and distributions", ("summary-statistics",)),
    ("expectation-variance", "Expectation and variance", ("random-variables",)),
    ("common-distributions", "Common distributions (normal, binomial)", ("random-variables",)),
    ("sampling", "Sampling and sampling distributions", ("random-variables",)),
    ("clt", "Central limit theorem", ("sampling", "expectation-variance")),
    ("confidence-intervals", "Confidence intervals", ("clt",)),
    ("hypothesis-testing", "Hypothesis testing and p-values", ("sampling",)),
    ("correlation-causation", "Correlation vs causation", ("expectation-variance",)),
    ("bayes-rule", "Conditional probability and Bayes' rule", ("random-variables",)),
    # ── 4. regression & classification ───────────────────────────────────────
    ("linear-regression", "Linear regression", ("expectation-variance", "vectorization")),
    ("least-squares", "Least squares / cost minimization", ("linear-regression",)),
    ("logistic-regression", "Logistic regression", ("linear-regression",)),
    ("classification-basics", "Classification fundamentals", ("logistic-regression",)),
    ("decision-boundaries", "Decision boundaries", ("classification-basics",)),
    ("regularization", "Regularization (L1/L2)", ("least-squares",)),
    ("feature-scaling", "Feature scaling and normalization", ("linear-regression", "broadcasting")),
    ("knn", "k-Nearest Neighbors", ("classification-basics",)),
    ("decision-trees", "Decision trees", ("classification-basics",)),
    # ── 5. model evaluation & generalization ─────────────────────────────────
    ("train-test-split", "Train/test split", ("classification-basics",)),
    ("data-leakage", "Data leakage (train/test contamination)", ("train-test-split",)),
    ("cross-validation", "Cross-validation", ("train-test-split",)),
    ("overfitting-underfitting", "Overfitting vs underfitting", ("train-test-split",)),
    ("bias-variance", "Bias-variance tradeoff", ("overfitting-underfitting",)),
    ("classification-metrics", "Classification metrics (precision/recall/F1)", ("classification-basics",)),
    ("imbalanced-classes", "Accuracy on imbalanced classes", ("classification-metrics",)),
    ("regression-metrics", "Regression metrics (MSE, R^2)", ("linear-regression",)),
    ("roc-auc", "ROC and AUC", ("classification-metrics",)),
    ("generalization", "Generalization and held-out evaluation", ("train-test-split",)),
    # ── 6. optimization & NN fundamentals ────────────────────────────────────
    ("gradient-descent", "Gradient descent", ("least-squares",)),
    ("learning-rate", "Learning-rate intuition", ("gradient-descent",)),
    ("loss-functions", "Loss functions (MSE, cross-entropy)", ("gradient-descent",)),
    ("backpropagation", "Backpropagation and the chain rule", ("gradient-descent",)),
    ("perceptron", "Perceptron / linear unit", ("logistic-regression",)),
    ("activation-functions", "Activation functions (ReLU, sigmoid)", ("perceptron",)),
    ("mlp", "Multilayer perceptron", ("perceptron", "backpropagation")),
    ("weight-initialization", "Weight initialization", ("mlp",)),
    ("minibatching", "Mini-batch / stochastic gradient descent", ("gradient-descent",)),
    ("epochs-convergence", "Epochs and convergence", ("gradient-descent",)),
    # ── 7. advanced neural networks ──────────────────────────────────────────
    ("convolution", "Convolution and CNNs", ("mlp",)),
    ("pooling", "Pooling layers", ("convolution",)),
    ("sequence-models", "Sequence models (RNNs)", ("mlp",)),
    ("attention", "Attention mechanism", ("sequence-models",)),
    ("transformers", "Transformer architecture", ("attention",)),
    ("embeddings", "Embeddings", ("mlp",)),
    ("regularization-nn", "Neural-net regularization (dropout, weight decay)", ("mlp", "regularization")),
    ("transfer-learning", "Transfer learning", ("mlp",)),
    ("batchnorm", "Normalization layers (batch/layer norm)", ("mlp", "feature-scaling")),
]

# Human label map (the former CONCEPTS dict shape, for callers that want it).
CONCEPTS: dict[str, str] = {cid: label for cid, label, _ in _CONCEPTS}

# exercise_id -> primary concept id
EXERCISE_CONCEPT: dict[str, str] = {
    "ds-foundations": "grouping-aggregation",
    "ds-regression": "linear-regression",
    "ds-mlp": "mlp",
}

# misconception_id -> concept id
MISCONCEPTION_CONCEPT: dict[str, str] = {
    "DS-corr-causation": "correlation-causation",
    "DS-pvalue-ph0": "hypothesis-testing",
    "DS-train-test-leakage": "data-leakage",
    "DS-data-snooping": "data-leakage",
    "DS-accuracy-imbalanced": "imbalanced-classes",
    "DS-overfit-underfit": "overfitting-underfitting",
    "DS-normalization-skip": "feature-scaling",
    "DS-broadcasting-shape": "broadcasting",
    "DS-learning-rate": "learning-rate",
    "DS-mean-vs-median": "summary-statistics",
    "DS-missing-drop": "missing-data",
    "DS-groupby-reset": "grouping-aggregation",
    "DS-apply-loop": "apply-map",
    "DS-r2-meaning": "regression-metrics",
    "DS-threshold-fixed": "classification-metrics",
    "DS-gd-local-minima": "gradient-descent",
    "DS-relu-dead": "activation-functions",
    "DS-sample-population": "sampling",
}

# exercise_id -> prerequisite exercise ids (curriculum order edges)
EXERCISE_PREREQS: dict[str, list[str]] = {
    "ds-foundations": [],
    "ds-regression": ["ds-foundations"],
    "ds-mlp": ["ds-regression"],
}


def build_taxonomy() -> Taxonomy:
    concepts = [Concept(id=cid, label=label, prereqs=tuple(prereqs))
                for cid, label, prereqs in _CONCEPTS]
    return Taxonomy(
        concepts,
        exercise_concept=EXERCISE_CONCEPT,
        misconception_concept=MISCONCEPTION_CONCEPT,
        exercise_prereqs=EXERCISE_PREREQS,
    )
