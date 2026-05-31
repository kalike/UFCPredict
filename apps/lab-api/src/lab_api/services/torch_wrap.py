"""sklearn-style wrappers around ufc_core.models.pytorch_arch nets.

Both wrappers expose .fit(X, y) and .predict_proba(X) so the training
worker can persist them via joblib and the predict-future endpoint can
use the same predict_proba contract as the sklearn models.
"""

from __future__ import annotations

import os

# Prevent libomp duplicate-symbol crash on macOS when LightGBM is also loaded.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from ufc_core.models.pytorch_arch import DeepMLP, TabularResNet


class _DeepMLPFactory:
    """Picklable factory for DeepMLP — stores construction kwargs explicitly."""

    def __init__(self, hidden_dims: list[int], dropout: float = 0.3):
        self.hidden_dims = hidden_dims
        self.dropout = dropout

    def __call__(self, input_dim: int) -> nn.Module:
        return DeepMLP(input_dim, self.hidden_dims, dropout=self.dropout)


class _TabularResNetFactory:
    """Picklable factory for TabularResNet — stores construction kwargs explicitly."""

    def __init__(self, hidden_dim: int = 128, n_blocks: int = 3, dropout: float = 0.2):
        self.hidden_dim = hidden_dim
        self.n_blocks = n_blocks
        self.dropout = dropout

    def __call__(self, input_dim: int) -> nn.Module:
        return TabularResNet(
            input_dim,
            hidden_dim=self.hidden_dim,
            n_blocks=self.n_blocks,
            dropout=self.dropout,
        )


class _BinaryNNWrapper:
    """sklearn-style wrapper over a torch nn.Module that outputs a single logit."""

    def __init__(
        self,
        factory,
        *,
        epochs: int,
        batch_size: int,
        lr: float,
        weight_decay: float,
    ):
        self._factory = factory
        self.epochs = epochs
        self.batch_size = batch_size
        self.lr = lr
        self.weight_decay = weight_decay
        self.model: nn.Module | None = None
        self._input_dim: int | None = None
        # Imputer + scaler are computed in fit() on numpy directly to avoid
        # a heavy sklearn dependency on the predict path.
        self._mean: np.ndarray | None = None
        self._std: np.ndarray | None = None

    # ---- private helpers ----
    def _impute(self, X: np.ndarray) -> np.ndarray:
        if self._mean is None:
            # First call (fit). Median impute then standardize.
            col_median = np.nanmedian(X, axis=0)
            # Fall back to 0 for fully-NaN columns
            col_median = np.where(np.isnan(col_median), 0.0, col_median)
            X = np.where(np.isnan(X), col_median, X)
            self._mean = X.mean(axis=0)
            std = X.std(axis=0)
            self._std = np.where(std < 1e-8, 1.0, std)
            return (X - self._mean) / self._std
        # Predict path: reuse stored stats.
        # Impute NaN with 0 (after standardize, mean is 0).
        X = np.where(np.isnan(X), 0.0, X)
        return (X - self._mean) / self._std

    # ---- sklearn API ----
    def fit(self, X: np.ndarray, y: np.ndarray):
        X = np.asarray(X, dtype=np.float32)
        y = np.asarray(y, dtype=np.float32).reshape(-1)
        self._input_dim = X.shape[1]
        X_norm = self._impute(X).astype(np.float32)

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = self._factory(self._input_dim).to(device)
        opt = torch.optim.Adam(
            self.model.parameters(), lr=self.lr, weight_decay=self.weight_decay
        )
        loss_fn = nn.BCEWithLogitsLoss()

        ds = TensorDataset(torch.from_numpy(X_norm), torch.from_numpy(y))
        loader = DataLoader(ds, batch_size=self.batch_size, shuffle=True, drop_last=False)

        self.model.train()
        for _ in range(self.epochs):
            for xb, yb in loader:
                xb, yb = xb.to(device), yb.to(device)
                opt.zero_grad()
                logits = self.model(xb).squeeze(-1)
                loss = loss_fn(logits, yb)
                loss.backward()
                opt.step()

        self.model.eval()
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Model not fitted")
        X = np.asarray(X, dtype=np.float32)
        X_norm = self._impute(X).astype(np.float32)
        device = next(self.model.parameters()).device
        with torch.no_grad():
            logits = self.model(torch.from_numpy(X_norm).to(device)).squeeze(-1)
            probs = torch.sigmoid(logits).cpu().numpy()
        return np.column_stack([1.0 - probs, probs])

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


def make_deep_mlp(
    *,
    epochs: int = 40,
    batch_size: int = 64,
    lr: float = 1e-3,
    weight_decay: float = 1e-4,
    hidden_dims: tuple[int, ...] = (128, 64, 32),
    dropout: float = 0.3,
) -> _BinaryNNWrapper:
    return _BinaryNNWrapper(
        factory=_DeepMLPFactory(list(hidden_dims), dropout=dropout),
        epochs=epochs,
        batch_size=batch_size,
        lr=lr,
        weight_decay=weight_decay,
    )


def make_resnet(
    *,
    epochs: int = 40,
    batch_size: int = 64,
    lr: float = 1e-3,
    weight_decay: float = 1e-4,
    hidden_dim: int = 128,
    n_blocks: int = 3,
) -> _BinaryNNWrapper:
    return _BinaryNNWrapper(
        factory=_TabularResNetFactory(hidden_dim=hidden_dim, n_blocks=n_blocks, dropout=0.2),
        epochs=epochs,
        batch_size=batch_size,
        lr=lr,
        weight_decay=weight_decay,
    )
