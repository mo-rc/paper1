"""Preliminary landscape diagnostics. EXPLORATORY: uses a simplified, unverified checker
(class-aware bending, shear, deflection only; no web bearing, shear buckling or interaction).
Not used for any claim. Replaced by verified results once Gate 2 is accepted.
Usage: python scripts/prelim_diagnostics.py [path-to-xlsx]"""
import sys, math, time
import numpy as np, openpyxl
from scipy.stats import spearmanr

XLSX = sys.argv[1] if len(sys.argv) > 1 else "data/raw/UB-secpropsdimsprops-EC3UKNA-UK-10-16-2026.xlsx"
PHI = 27 / 56.7675


def load():
    ws = openpyxl.load_workbook(XLSX, data_only=True).active
    rows, ser = [], None
    for r in ws.iter_rows(min_row=11, max_row=117, values_only=True):
        if r[0]:
            ser = r[0]
        rows.append(dict(n=(ser + " " + r[1]).replace("  ", " ").replace("+", "").strip(),
                         plus="+" in (str(r[0]) + str(r[1]) + str(r[2])), m=float(r[3]), h=float(r[4]),
                         b=float(r[5]), tw=float(r[6]), tf=float(r[7]), r=float(r[8]), cw=float(r[10]),
                         cf=float(r[11]), Iy=float(r[17]), Wel=float(r[21]), Wpl=float(r[23]), A=float(r[29]) * 100))
    return rows


ROWS = load()


def prep(sel):
    S = sorted([s for s in ROWS if sel(s)], key=lambda s: (s["m"], s["h"]))
    A = {k: np.array([s[k] for s in S]) for k in ("m", "h", "b", "tw", "tf", "r", "cw", "cf", "Iy", "Wel", "Wpl", "A")}
    t = np.maximum(A["tf"], A["tw"])
    fy = np.where(t <= 16, 355, np.where(t <= 40, 345, np.where(t <= 63, 335, 325.0)))
    e = np.sqrt(235 / fy)
    cf = np.where(A["cf"] <= 9 * e, 1, np.where(A["cf"] <= 10 * e, 2, np.where(A["cf"] <= 14 * e, 3, 4)))
    cw = np.where(A["cw"] <= 72 * e, 1, np.where(A["cw"] <= 83 * e, 2, np.where(A["cw"] <= 124 * e, 3, 4)))
    cls = np.maximum(cf, cw)
    Av = np.maximum(A["A"] - 2 * A["b"] * A["tf"] + (A["tw"] + 2 * A["r"]) * A["tf"], (A["h"] - 2 * A["tf"]) * A["tw"])
    W = np.where(cls <= 2, A["Wpl"], A["Wel"]) * 1e3
    A.update(fy=fy, cls=cls, Mrd=W * fy / 1e6, Vrd=Av * fy / 3 ** 0.5 / 1e3, names=[s["n"] for s in S])
    return A


def util(A, L, w, phi=None, lim=None, mode="var"):
    n = len(L)
    phi = np.full(n, PHI) if phi is None else phi
    lim = np.full(n, 360.0) if lim is None else lim
    L, w, phi, lim = L[:, None], w[:, None], phi[:, None], lim[:, None]
    g = A["m"][None, :] * 9.80665e-3
    wt = w + 1.35 * g
    ub = wt * L * L / 8 / A["Mrd"][None, :]
    uv = wt * L / 2 / A["Vrd"][None, :]
    Qk = phi * w / 1.5
    q = Qk if mode == "var" else Qk + (1 - phi) * w / 1.35 + g
    d = 5 * q * (L * 1e3) ** 4 / (384 * 210000 * A["Iy"][None, :] * 1e4)
    ud = d / (L * 1e3 / lim)
    return ub, uv, ud, (ub <= 1) & (uv <= 1) & (ud <= 1) & (A["cls"][None, :] <= 3)


def trial_idx(A, L, w):
    need = (w * L * L / 8) * 1e6 / 355 / 1e3
    S = len(A["m"])
    return np.array([np.argmax(A["Wpl"] >= x) if (A["Wpl"] >= x).any() else S - 1 for x in need])


def heuristic(ok, trial):
    S = ok.shape[1]; ex = []; ev = []; found = []
    for i in range(len(ok)):
        j = trial[i]; e = 1
        while not ok[i, j] and j < S - 1:
            j += 1; e += 1
        if ok[i, j]:
            while j > 0:
                e += 1
                if ok[i, j - 1]: j -= 1
                else: break
        found.append(j if ok[i, j] else -1); ev.append(e)
    return np.array(found), np.array(ev)


def main():
    rng = np.random.default_rng(0)
    for name, sel in (("C91", lambda s: not s["plus"]), ("C107", lambda s: True)):
        A = prep(sel); S = len(A["m"]); m = A["m"]
        print(f"== {name}: {S} sections; class counts {{1,2,3,4}} = {[int((A['cls']==c).sum()) for c in (1,2,3,4)]}")
        print(f"  Spearman mass~Wpl {spearmanr(m, A['Wpl'])[0]:.3f}, mass~Iy {spearmanr(m, A['Iy'])[0]:.3f}; adjacent decreases Wpl {np.mean(np.diff(A['Wpl'])<0):.3f}, Iy {np.mean(np.diff(A['Iy'])<0):.3f}; mass ties {S-len(set(m))}")
        a, b = np.meshgrid(np.linspace(9, 15, 100), np.linspace(56, 100, 100)); L, w = a.ravel(), b.ravel()
        ub, uv, ud, ok = util(A, L, w); feas = ok.any(1); opt = np.argmax(ok, 1); ar = np.arange(len(L))
        print(f"  grid 100x100: infeasible {int((~feas).sum())}; distinct optima {len(set(opt[feas]))}; scan cost (rank of optimum) mean {np.mean(opt[feas]+1):.1f} max {int((opt[feas]+1).max())}")
        print(f"  governing at optimum: bending {np.mean(ub[ar,opt]>=np.maximum(uv[ar,opt],ud[ar,opt])):.3f}, deflection {np.mean(ud[ar,opt]>=np.maximum(ub[ar,opt],uv[ar,opt])):.3f}")
        for tol in (0.02, 0.05):
            cnt = np.array([(ok[i] & (m <= m[opt[i]] * (1 + tol))).sum() for i in range(len(L))])
            print(f"  alternatives within {int(tol*100)}% of optimal mass: >=2 in {np.mean(cnt>=2):.3f} of contexts, >=3 in {np.mean(cnt>=3):.3f}")
        tr = trial_idx(A, L, w); d = opt - tr
        print(f"  trial section (required Wpl): equals optimum {np.mean(d==0):.3f}; feasible {np.mean(ok[ar,tr]):.3f}; index distance to optimum max {int(d.max())}; m_opt/m_trial max {np.max(m[opt]/m[tr]):.2f}; m_max/m_trial max {np.max(m[-1]/m[tr]):.1f}")
        r_all = m[None, :] / m[tr][:, None]
        for beta in (10, 20, 40):
            Rf = np.exp(-beta * r_all)
            print(f"  v1.1 R3 beta={beta}: feasible sections with R<1e-6 (the infeasible reward): {np.mean(((Rf<1e-6)&ok).sum(1)/np.maximum(ok.sum(1),1)):.3f}; optimum R<1e-6 in {np.mean(Rf[ar,opt][feas]<1e-6):.3f} of contexts")
        fnd, ev = heuristic(ok, tr)
        print(f"  heuristic iteration (trial, up until feasible, down while feasible): exact {np.mean(fnd==opt):.3f}; mean checker calls {ev.mean():.1f}")
        for nm, (Lr, wr) in {"E1": ((15.01, 18), (56, 100)), "E2": ((9, 15), (100.01, 130)), "E3": ((15.01, 18), (100.01, 130))}.items():
            a2, b2 = np.meshgrid(np.linspace(*Lr, 40), np.linspace(*wr, 40)); print(f"  {nm} infeasible fraction {1-util(A, a2.ravel(), b2.ravel())[3].any(1).mean():.3f}")
        _, _, _, ok2 = util(A, L, w, mode="tot"); f2 = ok2.any(1); o2 = np.argmax(ok2, 1)
        print(f"  sensitivity total load L/250: optimum differs from primary in {np.mean(o2[f2]!=opt[f2]):.3f} of contexts; distinct optima {len(set(o2[f2]))}")
        ubr, uvr, udr, okr = util(A, np.array([9.0]), np.array([56.7675])); i = int(np.argmax(okr[0]))
        print(f"  reference case optimum: {A['names'][i]} ({m[i]} kg/m); utilisation bending {ubr[0,i]:.3f} shear {uvr[0,i]:.3f} deflection {udr[0,i]:.3f}")
        if name == "C91":
            def samp(n): return rng.uniform(9, 15, n), rng.uniform(56, 100, n)
            Lt, wt = samp(2197); ot = np.argmax(util(A, Lt, wt)[3], 1); Lh, wh = samp(2000); okh = util(A, Lh, wh)[3]; oh = np.argmax(okh, 1)
            X = np.c_[(Lt-9)/6, (wt-56)/44]; Y = np.c_[(Lh-9)/6, (wh-56)/44]; nn = ot[((Y[:, None]-X[None])**2).sum(2).argmin(1)]
            print(f"  diagnostic nearest-label lookup, 2197 labels: exact {np.mean(nn==oh):.3f}, feasible {okh[np.arange(2000),nn].mean():.3f}")
            Lb, wb = samp(10000); t = time.perf_counter(); util(A, Lb, wb); dt = time.perf_counter() - t
            print(f"  timing (this machine, numpy): {dt/10000*1e6:.2f} us per context ({dt/10000/S*1e6:.3f} us per section evaluation), vectorised over 10,000 contexts")
    print("== minimum attainable exact two-sided p: paired sign-flip n=5 seeds %.4f, n=10 %.5f; unpaired 5 vs 5 %.4f" % (2/2**5, 2/2**10, 2/math.comb(10, 5)))
    A = prep(lambda s: not s["plus"]); m = A["m"]; rng2 = np.random.default_rng(1)
    def samp_g(n, dim):
        return (rng2.uniform(9, 15, n), rng2.uniform(56, 100, n), rng2.uniform(.2, .8, n) if dim >= 3 else np.full(n, PHI), rng2.uniform(200, 500, n) if dim >= 4 else np.full(n, 360.))
    print("== context dimension (C91): deflection limit varies in 4-D")
    for tag, dim in (("2-D", 2), ("3-D (+variable share)", 3), ("4-D (+deflection limit)", 4)):
        for mode in ("var", "tot"):
            Lh, wh, ph, lh = samp_g(4000, dim); ub, uv, ud, ok = util(A, Lh, wh, ph, lh, mode); feas = ok.any(1); opt = np.argmax(ok, 1); ar = np.arange(len(Lh))
            fnd, ev = heuristic(ok, trial_idx(A, Lh, wh))
            Lt, wt, pt, lt = samp_g(2197, dim); ot = np.argmax(util(A, Lt, wt, pt, lt, mode)[3], 1)
            sc = lambda L, w, p, l: np.c_[(L-9)/6, (w-56)/44, (p-.2)/.6 if dim >= 3 else 0*L, (l-200)/300 if dim >= 4 else 0*L]
            nn = ot[((sc(Lh, wh, ph, lh)[:, None]-sc(Lt, wt, pt, lt)[None])**2).sum(2).argmin(1)]
            print(f"  {tag}, {'variable-load' if mode=='var' else 'total-load'}: distinct optima {len(set(opt[feas]))}; deflection governs {np.mean(ud[ar,opt]>=np.maximum(ub[ar,opt],uv[ar,opt])):.3f}; heuristic exact {np.mean(fnd[feas]==opt[feas]):.3f}, mean calls {ev.mean():.1f}; nearest-label exact {np.mean(nn==opt):.3f}, feasible {ok[ar,nn].mean():.3f}")
    print("== depth cap h <= h_max as an extra context (C91, 4-D plus cap)")
    h = A["h"]; rng3 = np.random.default_rng(2)
    for hmin in (350, 450, 550):
        N = 4000; Lh, wh, ph, lh = samp_g(N, 4); hm = rng3.uniform(hmin, 1000, N)
        ok = util(A, Lh, wh, ph, lh)[3] & (h[None, :] <= hm[:, None]); feas = ok.any(1); opt = np.argmax(ok, 1)
        fnd, ev = heuristic(ok, trial_idx(A, Lh, wh))
        print(f"  h_max~U({hmin},1000): infeasible contexts {1-feas.mean():.3f}; distinct optima {len(set(opt[feas]))}; heuristic exact (feasible contexts) {np.mean(fnd[feas]==opt[feas]):.3f}")


if __name__ == "__main__":
    main()
