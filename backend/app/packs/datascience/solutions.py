"""
Reference solutions, starters, and prose-leak answer tokens, per exercise.

The reference solutions are validated end-to-end through `grader.grade` in the
pack's tests (they must pass run + grade). They are ALSO what the pack "knows" for
the prose-leak heuristic: ``solution_ops`` (essential operation tokens) and
``answer_values`` (literal answers) are the disclosure signals the prose check
looks for (EXTRACTION_PLAN §(f)).
"""
from __future__ import annotations

from typing import Dict, List, TypedDict


class _Solution(TypedDict):
    source: str
    starter: str
    solution_ops: List[str]    # essential operation tokens (whole-word match)
    answer_values: List[str]   # literal answer tokens (strong disclosure signal)


_FOUNDATIONS_REF = '''\
import pandas as pd
df = pd.read_csv("data/sales.csv")
result = df.groupby("category")["amount"].mean().to_dict()
print(result)
'''

_FOUNDATIONS_STARTER = '''\
import pandas as pd
df = pd.read_csv("data/sales.csv")
# Goal: build `result` = {category: mean amount} for each category.
result = {}
print(result)
'''

_REGRESSION_REF = '''\
import numpy as np
X_train = np.loadtxt("data/X_train.csv", delimiter=",")
y_train = np.loadtxt("data/y_train.csv", delimiter=",")
X_test = np.loadtxt("data/X_test.csv", delimiter=",")
A = np.c_[X_train, np.ones_like(X_train)]
coef, *_ = np.linalg.lstsq(A, y_train, rcond=None)
y_pred = np.c_[X_test, np.ones_like(X_test)] @ coef
'''

_REGRESSION_STARTER = '''\
import numpy as np
X_train = np.loadtxt("data/X_train.csv", delimiter=",")
y_train = np.loadtxt("data/y_train.csv", delimiter=",")
X_test = np.loadtxt("data/X_test.csv", delimiter=",")
# Goal: fit a linear model on the TRAIN split, then set `y_pred` for X_test.
# It is graded by held-out R^2 on the test split (>= 0.8). Do not peek at y_test.
y_pred = None
'''

_MLP_REF = '''\
import numpy as np
X = np.loadtxt("data/X.csv", delimiter=",")
y = np.loadtxt("data/y.csv", delimiter=",").reshape(-1, 1)
rng = np.random.default_rng(0)
H = 8
W1 = rng.normal(0, 1, (2, H)); b1 = np.zeros(H)
W2 = rng.normal(0, 1, (H, 1)); b2 = np.zeros(1)
lr = 0.5
for _ in range(4000):
    z1 = X @ W1 + b1; a1 = np.tanh(z1)
    z2 = a1 @ W2 + b2; out = 1 / (1 + np.exp(-z2))
    loss = np.mean((out - y) ** 2)
    d2 = (out - y) * out * (1 - out) / len(X)
    dW2 = a1.T @ d2; db2 = d2.sum(0)
    d1 = (d2 @ W2.T) * (1 - a1 ** 2)
    dW1 = X.T @ d1; db1 = d1.sum(0)
    W1 -= lr * dW1; b1 -= lr * db1; W2 -= lr * dW2; b2 -= lr * db2
final_loss = float(loss)
print("final_loss", final_loss)
'''

_MLP_STARTER = '''\
import numpy as np
X = np.loadtxt("data/X.csv", delimiter=",")
y = np.loadtxt("data/y.csv", delimiter=",").reshape(-1, 1)
# Goal: train a tiny MLP (one hidden layer) with numpy until MSE `final_loss` <= 0.05.
# Seed your RNG for determinism. Set `final_loss` to the final training loss.
final_loss = 1.0
'''


SOLUTIONS: Dict[str, _Solution] = {
    "ds-foundations": {
        "source": _FOUNDATIONS_REF,
        "starter": _FOUNDATIONS_STARTER,
        "solution_ops": ["groupby", "mean"],
        "answer_values": ["15", "40", "100"],
    },
    "ds-regression": {
        "source": _REGRESSION_REF,
        "starter": _REGRESSION_STARTER,
        "solution_ops": ["lstsq", "linalg", "coef"],
        "answer_values": [],
    },
    "ds-mlp": {
        "source": _MLP_REF,
        "starter": _MLP_STARTER,
        "solution_ops": ["tanh", "sigmoid", "backprop", "gradient"],
        "answer_values": [],
    },
}
