"""P8: supervised MLP baseline, variant (i) (spec section 9, kept by Amendment A5). No RL.

Labels: the first 2,197 rows of train.csv in file order that have a feasible enumeration optimum (rows whose
context has no feasible section are skipped - decided and recorded in the meta), one label per context: the
enumeration optimum section index. Costed two ways (spec section 9), both recorded: full enumeration,
n_labels * |C| = 199,927 calls; and the ordered-scan-with-certificate cost, sum over labels of
(optimum rank + 1).

Features: 12 fixed inputs - span, tributary width, dead, live, restraint ratio, one-hot deflection rule (3),
one-hot depth cap (4, including none) - z-scored with the train-label statistics (recorded in the summary).

Model: 91-way softmax MLP (softmax implicit in cross-entropy; the network returns logits), cross-entropy,
Adam, PyTorch CPU. Determinism: torch.manual_seed(seed) before init and training, torch.set_num_threads(1),
fixed data order, no shuffling. Training costs 0 checker calls - the labels are already costed.

End-to-end evaluation (spec section 9, reused): argmax output -> verify (1 call) -> if infeasible, step up in
mass order until feasible (1 counted call per step) -> abstain at the end of C. The calls are the measured
verification + repair calls; the search calls are 0 (the classifier performs no search).

Tuning selection: the same Amendment A5 rule as the GA (baselines2.select_config); the run records it in the
meta. The first drawn configuration is the default.
"""
import random
from dataclasses import dataclass

import numpy as np
import torch

from ub_rl.baselines import MethodResult, _Calls

N_LABELS = 2197  # floor(200,000 / 91), spec section 9 variant (i): enumeration labels at matched calls
DEFLECTION_RULE_INDEX = {"var360": 0, "var200": 1, "tot250": 2}
DEPTH_CAP_INDEX = {None: 0, 700: 1, 800: 2, 900: 3}
N_INPUTS = 5 + 3 + 4  # five numerics + deflection-rule one-hot + depth-cap one-hot


@dataclass(frozen=True)
class MLPConfig:
    id: int         # position in the draw order (the first drawn, id 0, is the tuning default)
    hidden: tuple   # hidden layer sizes
    lr: float       # Adam learning rate
    epochs: int
    batch: int


def mlp_config_grid():
    """The fixed parameter grid (plan section 3) in the fixed product order the draw samples from."""
    return [(h, lr, ep, b) for h in ((64,), (128,), (64, 64), (128, 128)) for lr in (1e-3, 3e-4, 1e-4)
            for ep in (20, 40, 80) for b in (32, 64)]


def draw_mlp_configs():
    """The 12 tuning configurations, drawn by a fixed seed from the fixed grid (spec section 9). Deterministic
    and asserted by a test."""
    rng = random.Random("mlp-configs-2026-11-15")
    return [MLPConfig(i, *cfg) for i, cfg in enumerate(rng.sample(mlp_config_grid(), 12))]


def context_features(ctx):
    """The 12 fixed inputs of one context (plan section 3)."""
    rule = [0, 0, 0]
    rule[DEFLECTION_RULE_INDEX[ctx.deflection_rule]] = 1
    cap = [0, 0, 0, 0]
    cap[DEPTH_CAP_INDEX[ctx.depth_cap]] = 1
    return [ctx.span, ctx.width, ctx.dead, ctx.live, ctx.restraint_ratio] + rule + cap


class MLP(torch.nn.Module):
    """91-way softmax classifier over the mass-ordered catalogue."""

    def __init__(self, n_inputs, hidden, n_out):
        super().__init__()
        layers, d = [], n_inputs
        for h in hidden:
            layers += [torch.nn.Linear(d, h), torch.nn.ReLU()]
            d = h
        layers.append(torch.nn.Linear(d, n_out))
        self.net = torch.nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


def train_mlp(labels, config, seed, n_out):
    """Train on (context, optimum index) pairs. Deterministic per seed: manual_seed, single thread, fixed data
    order, no shuffle. Returns (model, feature_mean, feature_std). Training makes no checker call."""
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    x = np.asarray([context_features(ctx) for ctx, _ in labels], dtype=np.float64)
    y = np.asarray([opt for _, opt in labels], dtype=np.int64)
    mean = x.mean(axis=0)
    std = x.std(axis=0)
    std = np.where(std == 0.0, 1.0, std)  # a one-hot feature can be constant within the labels
    xs = torch.tensor((x - mean) / std, dtype=torch.float32)
    ys = torch.from_numpy(y)
    model = MLP(xs.shape[1], config.hidden, n_out)
    opt = torch.optim.Adam(model.parameters(), lr=config.lr)
    lossf = torch.nn.CrossEntropyLoss()
    n = len(labels)
    for _ in range(config.epochs):
        for start in range(0, n, max(1, config.batch)):
            stop = min(start + config.batch, n)
            opt.zero_grad()
            loss = lossf(model(xs[start:stop]), ys[start:stop])
            loss.backward()
            opt.step()
    model.eval()
    return model, mean, std


def predict(model, mean, std, ctx):
    """Argmax class of one context under the trained model (no checker call)."""
    with torch.no_grad():
        x = torch.tensor((np.asarray(context_features(ctx), dtype=np.float64) - mean) / std,
                         dtype=torch.float32)
        return int(torch.argmax(model(x), dim=-1))


def evaluate_mlp(kc, ctx, idx):
    """Spec section 9 end-to-end: verify idx (1 call); if infeasible, step up in mass order until feasible
    (1 counted call per step); abstain at the end of C. Calls = 1 + repair steps (measured by the counter)."""
    c = _Calls(kc)
    for j in range(idx, len(kc)):
        if kc.evaluate_context(ctx, [j])["feasible"][0]:
            return MethodResult("feasible", j, c.calls())
    return MethodResult("abstain", -1, c.calls())
