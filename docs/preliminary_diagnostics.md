# Preliminary diagnostics

**All results below come from a simplified, unverified checker** (class-aware bending, shear, deflection only; no web bearing, shear buckling or interaction). They support no claim. They are replaced by verified results at Gate 3.

Source: `scripts/prelim_diagnostics.py` on the catalogue of spec section 4 (SHA-256 recorded there).

Primary set C (91 sections), span 9-15 m, w 56-100 kN/m, 100x100 grid, primary deflection rule:
- Mass and Wpl rank correlation 0.998; 34% of adjacent pairs in mass order have decreasing Wpl.
- All 10,000 contexts feasible; no infeasible contexts in the extrapolation ranges E1-E3 under these checks.
- 17 distinct optimal sections. Bending governs the optimum in every context; deflection in none.
- The trial section from the required modulus equals the optimum in 61% of contexts and is at most 3 steps (mass order) from it.
- Heuristic iteration (trial section, move up until feasible, then down while feasible) finds the optimum in all contexts with a mean of 2.6 checker calls. Ordered scan needs a mean of 53.0.
- Alternatives within 5% of optimal mass: at least 2 in 51.9% of contexts, at least 3 in 13.5%.
- Reference case: 457 x 191 x 74; bending utilisation 0.998, shear 0.291, deflection 0.880.
- Nearest-label lookup (diagnostic only, not a baseline) with 2,197 labels: 92.3% exact, 97.1% feasible.
- Vectorised enumeration: 1.87 microseconds per context on the development machine.

Context dimension (variable-load rule): with variable share and deflection limit varied, heuristic iteration stays exact (3.3 to 3.4 mean calls); nearest-label lookup falls to 57.4% exact and 79.8% feasible in four dimensions. With a depth cap h <= h_max added, heuristic iteration stays exact on feasible contexts; 17% to 42% of contexts are infeasible depending on the cap range.

Total-load span/250 rule: the optimum differs from the primary rule in every context; deflection governs.

Reward check (arithmetic, not checker output): in spec v1.1, R3 = exp(-beta*m/m_trial) with m/m_trial >= 1 for feasible sections gives R <= exp(-20) for beta = 20 and below the infeasible reward 1e-6; for beta = 10 it does so for any feasible section heavier than 1.38 m_trial. Corrected in v1.2.

Label-cost arithmetic (preliminary, equal quality assumed, tuning excluded): break-even N* = 200,000 / (c_conv - 1) tasks, using 1 verification call for a direct-choice policy: about 125,000 against heuristic iteration (c = 2.6), 3,846 against ordered scan (c = 53.0), 2,222 against enumeration (c = 91). Generating 2,197 enumeration labels is about 200,000 section evaluations, a few milliseconds here. Policy inference time is not yet measured; it is not assumed to beat the checker.

What this could change: if the verified checker confirms that heuristic iteration is exact at about 3 calls, solution-quality headroom for RL is nil and the efficiency margin is small. The study then answers a narrower question (sample efficiency, diversity, behaviour on harder context sets, cost when each call is expensive) and reports honestly if RL offers no advantage. Spec section 12 states this as the saturation rule.
