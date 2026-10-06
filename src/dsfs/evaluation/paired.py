"""Trajectory-level paired uncertainty for correlated rolling forecasts."""
from collections import defaultdict
import numpy as np
from dsfs.forecast.harness import paired_origins

def trajectory_lift_ci(baseline, enhanced, *, seed=42, n_resamples=1000, metric="mase"):
    left, right = paired_origins(baseline, enhanced)
    groups = defaultdict(list)
    for a,b in zip(left,right):
        if metric == "mase":
            if a.mase_scale is None or a.mase_scale <= 0:
                continue
            scale = a.mase_scale
        else:
            scale = 1.0
        groups[a.entity_key].append((abs(a.actual-a.predicted)/scale, abs(b.actual-b.predicted)/scale))
    arrays = [np.asarray(v) for v in groups.values()]
    if not arrays:
        return {"metric":metric,"point":None,"ci_low":None,"ci_high":None,"n_accounts":0}
    def lift(values):
        means = np.concatenate(values).mean(axis=0)
        return float((means[0]-means[1])/means[0]) if means[0] > 0 else 0.0
    rng = np.random.default_rng(seed)
    boot = [lift([arrays[i] for i in rng.integers(0,len(arrays),len(arrays))]) for _ in range(n_resamples)]
    lo,hi = np.percentile(boot,[2.5,97.5])
    return {"metric":metric,"point":lift(arrays),"ci_low":float(lo),"ci_high":float(hi),
            "n_accounts":len(arrays),"method":"paired account trajectory bootstrap","seed":seed}
