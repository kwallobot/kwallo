# ===================== 7. SIMULATE THE WEEKEND (optional) =====================
N_SIMS = 10000
rng = np.random.default_rng()

preds = pd.concat([x for x in [pred_dom, pred_eu] if len(x)], ignore_index=True) if (len(pred_dom) or len(pred_eu)) else pd.DataFrame(columns=["Date"])
preds["Date"] = pd.to_datetime(preds["Date"])
weekend = preds[preds["Date"].dt.weekday >= 5].reset_index(drop=True)   # Saturday and Sunday only
print(f"Simulating {len(weekend)} weekend matches, {N_SIMS:,} times each...\n")

def score_grid(h, a, pH, pD, pA, maxg=10):
    g = np.outer(poisson.pmf(range(maxg + 1), h), poisson.pmf(range(maxg + 1), a))
    home, draw, away = np.tril(g, -1), np.diag(np.diag(g)), np.triu(g, 1)
    return home / home.sum() * pH + draw / draw.sum() * pD + away / away.sum() * pA

sims_h, sims_a, rows = [], [], []
for _, m in weekend.iterrows():
    g = score_grid(m["ExpHome"], m["ExpAway"], m["pH"], m["pD"], m["pA"])
    flat = g.ravel() / g.sum()
    draws = rng.choice(len(flat), size=N_SIMS, p=flat)
    hg, ag = draws // g.shape[1], draws % g.shape[1]
    sims_h.append(hg); sims_a.append(ag)
    top = np.argsort(flat)[::-1][:3]
    one = rng.integers(N_SIMS)
    rows.append({"Competition": m["Competition"], "Date": m["Date"].date(), "Home": m["Home"], "Away": m["Away"],
                 "Home win %": 100 * (hg > ag).mean(), "Draw %": 100 * (hg == ag).mean(), "Away win %": 100 * (hg < ag).mean(),
                 "Likely scores": ", ".join(f"{i // g.shape[1]}-{i % g.shape[1]} ({100 * flat[i]:.0f}%)" for i in top),
                 "One simulated result": f"{hg[one]}-{ag[one]}"})
sim_table = pd.DataFrame(rows)
sim_summary = {}
if len(weekend):
    display(sim_table.round(0))
    H, A = np.array(sims_h), np.array(sims_a)            # shape: matches x simulations
    fav = weekend[["pH", "pD", "pA"]].values.argmax(axis=1)
    res = np.where(H > A, 0, np.where(H == A, 1, 2))
    fav_wins = (res == fav[:, None]).sum(axis=0)
    total_goals = (H + A).sum(axis=0)
    sim_summary = {"matches": len(weekend), "home": (H > A).sum(axis=0).mean(), "draws": (H == A).sum(axis=0).mean(),
                   "away": (H < A).sum(axis=0).mean(), "goals": total_goals.mean(),
                   "goals_lo": np.percentile(total_goals, 5), "goals_hi": np.percentile(total_goals, 95),
                   "fav_wins": fav_wins.mean(), "top": []}
    print("\nAcross the whole weekend (per simulated weekend):")
    print(f"  Home wins: {sim_summary['home']:.1f} on average   Draws: {sim_summary['draws']:.1f}   Away wins: {sim_summary['away']:.1f}")
    print(f"  Total goals: {sim_summary['goals']:.0f} on average (90% of simulations between {sim_summary['goals_lo']:.0f} and {sim_summary['goals_hi']:.0f})")
    print(f"  Model's favourite wins in {sim_summary['fav_wins']:.1f} of {len(weekend)} matches on average")
    # v35: how often the 2, 3, 5 and 10 strongest favourites ALL win (an accumulator of the safest picks); the old
    #      "all favourites win" line was always 0.000% (with 100+ matches it's about 1 in 10^37)
    for k in [2, 3, 5, 10]:
        if len(weekend) >= k:
            top_k = weekend[["pH", "pD", "pA"]].max(axis=1).nlargest(k).index.values
            chance = 100 * (res[top_k] == fav[top_k][:, None]).all(axis=0).mean()
            names = list(weekend.loc[top_k, "Home"] + " v " + weekend.loc[top_k, "Away"])
            sim_summary["top"].append({"k": k, "chance": chance, "matches": names})
            print(f"  Chance the {k} strongest favourites all win: {chance:.1f}%  ({', '.join(names)})")
else:
    print("No Saturday or Sunday fixtures to simulate yet.")
