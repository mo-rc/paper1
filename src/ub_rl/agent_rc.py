"""Isolated F1 R-C dual-penalty variant; not registered with the harness.

The A5 environment reward remains R1. This variant substitutes R1-lambda*c only
for the terminal reward passed into the inherited n-step builder.
"""
import logging
import math
from numbers import Integral, Real

import numpy as np

from .agents import F1Agent
from .envs import F1Env


logger = logging.getLogger(__name__)


class RCF1Env(F1Env):
    """F1 environment wrapper exposing accepted-design cost from its checker record."""

    def accepted_cost(self):
        if not self.done:
            raise RuntimeError("accepted-design cost is available only after episode termination")
        if self.i not in self.visited:
            raise RuntimeError("accepted design has no verified checker record")
        # This replaces the plan's "last element of info" rule: read the accepted
        # section directly, so explicit accept immediately after reset is covered.
        _, utilisation = self.visited[self.i]
        return max(0.0, float(np.max(utilisation)) - 1.0)


class RCF1Agent(F1Agent):
    """F1 agent with episodic dual updates and a terminal-only replay penalty.

    ``lambda_init``, ``eta`` and ``update_cadence`` are intentionally required
    keyword arguments: the P12b amendment must freeze them before any run.
    """

    def __init__(self, cfg, env, *, lambda_init, eta, update_cadence):
        if not isinstance(env, RCF1Env):
            raise TypeError("RCF1Agent requires an RCF1Env")
        if isinstance(lambda_init, bool) or not isinstance(lambda_init, Real):
            raise ValueError("lambda_init must be a finite nonnegative number")
        if not math.isfinite(float(lambda_init)) or lambda_init < 0:
            raise ValueError("lambda_init must be a finite nonnegative number")
        if isinstance(eta, bool) or not isinstance(eta, Real):
            raise ValueError("eta must be a finite nonnegative number")
        if not math.isfinite(float(eta)) or eta < 0:
            raise ValueError("eta must be a finite nonnegative number")
        if (isinstance(update_cadence, bool) or not isinstance(update_cadence, Integral)
                or update_cadence <= 0):
            raise ValueError("update_cadence must be a positive integer number of episodes")

        super().__init__(cfg, env)
        self.rc_env = env
        self.lambda_value = float(lambda_init)
        self.eta = float(eta)
        self.update_cadence = int(update_cadence)
        self.completed_episodes = 0
        self._block_costs = []
        self.lambda_history = []
        self.mean_c_history = []
        self.terminal_records = []

    def observe(self, obs, action, reward, done, info):
        """Keep env reward R1; alter only the terminal transition sent to replay."""
        training_reward = float(reward)
        if done:
            c = self.rc_env.accepted_cost()
            # Snapshot before the dual update: this is lambda at episode end and
            # the multiplier applied to every n-step window flushed at terminal.
            lambda_at_end = self.lambda_value
            training_reward -= lambda_at_end * c
            self.terminal_records.append({
                "episode": self.completed_episodes + 1,
                "accepted_index": self.rc_env.i,
                "r1_reward": float(reward),
                "c": c,
                "lambda_at_end": lambda_at_end,
                "training_terminal_reward": training_reward,
            })

        # NStepBuilder receives ordinary rewards for nonterminal transitions and
        # R1-lambda*c only on the terminal transition; RCF1Env's reward is untouched.
        super().observe(obs, action, training_reward, done, info)

        if done:
            self.completed_episodes += 1
            self._block_costs.append(c)
            if self.completed_episodes % self.update_cadence == 0:
                mean_c = float(np.mean(self._block_costs))
                self.lambda_value = max(0.0, self.lambda_value + self.eta * mean_c)
                self.lambda_history.append(self.lambda_value)
                self.mean_c_history.append(mean_c)
                logger.info("R-C dual update episodes=%d lambda=%.12g mean_c=%.12g",
                            self.completed_episodes, self.lambda_value, mean_c)
                self._block_costs.clear()

    def checkpoint_state(self):
        state = super().checkpoint_state()
        state["rc"] = {
            "lambda_value": self.lambda_value,
            "eta": self.eta,
            "update_cadence": self.update_cadence,
            "completed_episodes": self.completed_episodes,
            "block_costs": list(self._block_costs),
            "lambda_history": list(self.lambda_history),
            "mean_c_history": list(self.mean_c_history),
            "terminal_records": [dict(row) for row in self.terminal_records],
        }
        return state

    def load_state(self, state):
        super().load_state(state)
        rc = state["rc"]
        self.lambda_value = float(rc["lambda_value"])
        self.completed_episodes = int(rc["completed_episodes"])
        self._block_costs = list(rc["block_costs"])
        self.lambda_history = list(rc["lambda_history"])
        self.mean_c_history = list(rc["mean_c_history"])
        self.terminal_records = [dict(row) for row in rc["terminal_records"]]

