# ===================== 9c. MACHINE-LEARNING LAYER (v23): learn only corrections on top of the model =====================
# Starts from the model's own probabilities exactly as they are (as an offset) and learns small adjustments from every signal
# (rest, derbies, weather, managers, style, pressing), with ridge shrinkage on the adjustments only. Learned on the earlier half of
# this season's replayed matches, tested on the later half; kept (used from the next run) only if better in 95%+ of reshuffles.
from scipy.optimize import minimize as _min
ml_report = []
ML_JSON = f"{SAVE_DIR}/ml_layer.json"
def _softmax3(lh, la):
    z = np.stack([lh, np.zeros_like(lh), la], axis=1)
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)
if RUN_BACKTEST and bt_scored is not None and len(bt_scored):
    md_ = bt_scored[bt_scored["Group"] != "Europe"].dropna(subset=["pH", "pD", "pA", "ExpHome", "ExpAway"]).sort_values("Date").reset_index(drop=True)
    if len(md_) >= 600:
        Xm = ml_features(md_)
        ym = outcome(md_)
        lh0, la0 = Xm["lp_h"].values, Xm["lp_a"].values
        feats_ml = [c_ for c_ in Xm.columns if c_ not in ("lp_h", "lp_a", "exp_h", "exp_a") and Xm[c_].notna().mean() >= 0.05]
        mid_ = md_["Date"].quantile(0.5)
        tr_, te_ = (md_["Date"] < mid_).values, (md_["Date"] >= mid_).values
        mu_, sd_ = Xm.loc[tr_, feats_ml].mean(), Xm.loc[tr_, feats_ml].std().replace(0, 1).fillna(1)
        Z = ((Xm[feats_ml] - mu_) / sd_).fillna(0).values
        k_ = len(feats_ml)
        def nll(w, rows, lam):
            W = w.reshape(2, k_)
            p_ = _softmax3(lh0[rows] + Z[rows] @ W[0], la0[rows] + Z[rows] @ W[1])
            return -np.log(np.clip(p_[np.arange(rows.sum()), ym[rows]], 1e-9, 1)).mean() + lam * (w ** 2).sum()
        base_ll = -np.log(np.clip(md_[["pH", "pD", "pA"]].values[np.arange(len(md_)), ym], 1e-9, 1))
        rng_m = np.random.default_rng(9)
        best_ = None
        for lam_ in [0.05, 0.01, 0.002]:
            w_ = _min(nll, np.zeros(2 * k_), args=(tr_, lam_), method="L-BFGS-B").x
            W = w_.reshape(2, k_)
            p_ = _softmax3(lh0[te_] + Z[te_] @ W[0], la0[te_] + Z[te_] @ W[1])
            ll_ = -np.log(np.clip(p_[np.arange(te_.sum()), ym[te_]], 1e-9, 1))
            d_ = ll_ - base_ll[te_]
            pct = 100 * (np.array([rng_m.choice(d_, len(d_)).mean() for _ in range(2000)]) < 0).mean()
            ml_report.append({"Shrinkage": lam_, "Model log loss (later half)": float(base_ll[te_].mean()), "With corrections": float(ll_.mean()),
                              "Change": float(d_.mean()), "Better in % of reshuffles": float(pct)})
            if pct >= 95 and d_.mean() < 0 and (best_ is None or d_.mean() < best_[1]):
                best_ = (lam_, d_.mean())
        print(f"Machine-learning layer (corrections on top of the model), {len(md_)} replayed matches, {k_} signals:")
        display(pd.DataFrame(ml_report).round(4))
        if best_:
            Zall = ((Xm[feats_ml] - Xm[feats_ml].mean()) / Xm[feats_ml].std().replace(0, 1).fillna(1)).fillna(0).values
            Z = Zall
            w_ = _min(nll, np.zeros(2 * k_), args=(np.ones(len(md_), bool), best_[0]), method="L-BFGS-B").x
            json.dump({"kind": "offset", "features": feats_ml, "mu": Xm[feats_ml].mean().fillna(0).tolist(),
                       "sd": Xm[feats_ml].std().replace(0, 1).fillna(1).tolist(), "W": w_.reshape(2, k_).tolist()}, open(ML_JSON, "w"))
            top_ = sorted(zip(feats_ml, np.abs(w_.reshape(2, k_)).sum(0)), key=lambda x: -x[1])[:5]
            print(f"-> passed (shrinkage {best_[0]}): used from the next run. Strongest signals: " + ", ".join(f"{n_}" for n_, _ in top_))
        else:
            for p_ in [ML_JSON, f"{SAVE_DIR}/ml_layer.joblib"]:
                if os.path.exists(p_):
                    os.remove(p_)
            print("-> no version beat the model clearly enough: predictions stay as they are.")
        EXTRA_TABLES.append({"title": "Machine-learning layer (corrections on top of the model)",
                             "hint": "Learned on the earlier half of this season, tested on the later half; used only if better in 95%+ of reshuffles.", "rows": ml_report})
    else:
        print(f"Machine-learning layer: only {len(md_)} replayed matches so far; it needs 600.")
