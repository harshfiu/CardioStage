"""
Logistic regression written from scratch with only numpy, as a learning extra.

scikit-learn's LogisticRegression does all of this in one line. Writing it by
hand shows what "training a model" actually means: start with a guess, measure
how wrong it is, nudge the weights to be less wrong, repeat.

We then check that our version learns the SAME weights as scikit-learn.

Run:  python -m cardiostage.from_scratch
"""

import numpy as np


def sigmoid(z):
    """
    Squash any number into the range (0, 1) so it can act as a probability.

        z = -5  -> 0.007   (very unlikely)
        z =  0  -> 0.5     (coin flip)
        z = +5  -> 0.993   (very likely)

    np.clip guards against overflow: exp(1000) is too big for a computer.
    """
    z = np.clip(z, -500, 500)
    return 1.0 / (1.0 + np.exp(-z))


class ScratchLogisticRegression:
    """
    The model:   probability of disease = sigmoid(w1*x1 + w2*x2 + ... + b)

    - Each feature x gets a weight w. A positive weight means "a higher value of
      this feature raises the risk"; negative means it lowers the risk.
    - b (the bias/intercept) is the baseline before any feature is considered.

    Training = finding the w and b that make the predicted probabilities match
    the real outcomes as closely as possible.

    C works exactly like scikit-learn's C: it controls regularisation, a
    penalty on large weights that stops the model from over-trusting any single
    feature. Smaller C = stronger penalty = simpler, more cautious model.
    """

    def __init__(self, C=1.0, learning_rate=0.5, n_iterations=200_000, tol=1e-14):
        self.C = C
        self.learning_rate = learning_rate
        self.n_iterations = n_iterations
        self.tol = tol  # stop early once the loss stops improving

    def _loss(self, X, y):
        """
        Log loss (a.k.a. binary cross-entropy): how wrong are we, on average?

        For a sick patient (y=1) the cost is -log(p): predicting p=0.9 costs
        0.11, but a confident wrong p=0.1 costs 2.30. Confident mistakes are
        punished hard, which pushes the model toward honest probabilities.

        The second term is the regularisation penalty on large weights.
        """
        n = len(y)
        p = np.clip(sigmoid(X @ self.weights + self.bias), 1e-15, 1 - 1e-15)
        log_loss = -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))
        penalty = (self.weights @ self.weights) / (2 * self.C * n)
        return log_loss + penalty

    def fit(self, X, y):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        n_samples, n_features = X.shape

        # Step 1: start knowing nothing. All weights 0, so every patient gets
        # sigmoid(0) = 0.5.
        self.weights = np.zeros(n_features)
        self.bias = 0.0
        self.loss_history = [self._loss(X, y)]

        for _ in range(self.n_iterations):
            # Step 2: predict with the current weights.
            p = sigmoid(X @ self.weights + self.bias)

            # Step 3: compute the GRADIENT, i.e. for each weight, which
            # direction (and how strongly) changing it would increase the loss.
            # Calculus gives a remarkably simple result for log loss:
            #   error = p - y            (how far off each prediction is)
            #   gradient for w = average of (error * feature value)
            # A feature that is large exactly when we under-predict sick
            # patients gets a gradient telling us to raise its weight.
            error = p - y
            grad_w = X.T @ error / n_samples + self.weights / (self.C * n_samples)
            grad_b = error.mean()

            # Step 4: GRADIENT DESCENT. Step a little in the opposite
            # direction of the gradient (downhill on the loss).
            self.weights -= self.learning_rate * grad_w
            self.bias -= self.learning_rate * grad_b

            # Step 5: repeat until the loss stops shrinking.
            self.loss_history.append(self._loss(X, y))
            if abs(self.loss_history[-2] - self.loss_history[-1]) < self.tol:
                break
        return self

    def predict_proba(self, X):
        """Probability of disease for each patient."""
        return sigmoid(np.asarray(X, dtype=float) @ self.weights + self.bias)

    def predict(self, X, threshold=0.5):
        """Turn probabilities into yes/no using a threshold (0.5 by default)."""
        return (self.predict_proba(X) >= threshold).astype(int)


def main():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score

    from cardiostage import config
    from cardiostage.data import get_features_and_target, load_clean, split_cleveland
    from cardiostage.preprocessing import build_preprocessor

    train, _ = split_cleveland(load_clean())
    X_raw, y = get_features_and_target(train, stage=3)
    X = build_preprocessor(3).fit_transform(X_raw)  # same preparation as the real model

    C = 0.1  # the value Phase 3's grid search picked
    ours = ScratchLogisticRegression(C=C).fit(X, y)
    # tol: ask scikit-learn to converge just as precisely as ours does.
    sklearn_model = LogisticRegression(C=C, max_iter=5000, tol=1e-10).fit(X, y)

    comparison = pd.DataFrame({
        "from_scratch": ours.weights,
        "scikit_learn": sklearn_model.coef_[0],
    }, index=X.columns).sort_values("from_scratch")
    print(f"Converged after {len(ours.loss_history) - 1} steps\n")
    print("Learned weights (negative = lowers risk, positive = raises risk):")
    print(comparison.round(4).to_string())
    print(f"\nIntercept: scratch {ours.bias:.4f}  vs  sklearn {sklearn_model.intercept_[0]:.4f}")
    print(f"Largest weight difference: {np.abs(comparison.diff(axis=1).iloc[:, 1]).max():.6f}")
    print(f"Training ROC-AUC: scratch {roc_auc_score(y, ours.predict_proba(X)):.4f}  vs  "
          f"sklearn {roc_auc_score(y, sklearn_model.predict_proba(X)[:, 1]):.4f}")

    # Loss curve: watch the model learn.
    fig, ax = plt.subplots(figsize=(7, 3.4))
    # A log scale can't show step 0, so number steps from 1 (1 = starting guess).
    steps = np.arange(1, len(ours.loss_history) + 1)
    ax.plot(steps, ours.loss_history, color="#2a78d6", linewidth=2)
    ax.annotate("start: every patient 50%\n(loss = 0.693)", xy=(1, ours.loss_history[0]),
                xytext=(3, 0.66), color="#52514e", fontsize=9,
                arrowprops={"arrowstyle": "->", "color": "#52514e"})
    ax.set_xscale("log")
    ax.set_xlabel("Gradient-descent step (log scale, 1 = starting guess)")
    ax.set_ylabel("Loss (lower = better)")
    ax.set_title("Logistic regression from scratch: the loss falls as it learns",
                 fontweight="bold")
    ax.grid(color="#ebeae6")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    path = config.FIGURES_DIR / "06_scratch_loss_curve.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\nsaved {path.relative_to(config.PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
