# ===================== 8a. MODEL vs ACTUAL: every match this season, calibration and bias =====================
# Uses the replayed season from section 8. Any correction is learned only from EARLIER weeks and tested on LATER ones,
# and is switched on (from the next run) only if it helps in at least 95% of reshuffles.
bt_matches, calib_bands, bias_table, cal_result = pd.DataFrame(), [], pd.DataFrame(), {}
blend_curves, disagree, miss_rows, miss_totals = {}, [], [], {}
adj_check, adj_decision = [], {}
if RUN_BACKTEST and bt_scored is not None and len(bt_scored):
    s = bt_scored.copy().reset_index(drop=True)
    o = outcome(s)
    P = s[["pH", "pD", "pA"]].values
    s["pResult"] = P[np.arange(len(s)), o]
    has = s[ODDS].notna().all(axis=1).values
    BP = np.full((len(s), 3), np.nan)
    if has.any():
        BP[has] = book_probs(s[has])
    s["bookH"], s["bookD"], s["bookA"] = BP[:, 0], BP[:, 1], BP[:, 2]
    s["Score"] = s["FTHG"].astype(int).astype(str) + "-" + s["FTAG"].astype(int).astype(str)
    s["Result"] = np.array(["Home win", "Draw", "Away win"])[o]
    s["Goals"] = s["FTHG"] + s["FTAG"]
    cols = ["Date", "Competition", "Group", "Home", "Away", "Score", "Result", "pH", "pD", "pA", "bookH", "bookD", "bookA", "pResult", "pOver25", "Goals"]
    bt_matches = s.reindex(columns=cols).sort_values("Date", ascending=False)
    bt_matches.to_csv(f"{SAVE_DIR}/backtest_matches_{SEASONS[-1]}.csv", index=False)
    print(f"Every replayed match this season saved to Drive: backtest_matches_{SEASONS[-1]}.csv ({len(bt_matches)} matches).")

    # --- bias check: average prediction vs what actually happened, per group ---
    rows = []
    for grp, g in s.groupby("Group"):
        og = outcome(g)
        rows.append({"Group": grp, "Matches": len(g),
                     "Home win % (model)": 100 * g["pH"].mean(), "Home win % (actual)": 100 * (og == 0).mean(),
                     "Draw % (model)": 100 * g["pD"].mean(), "Draw % (actual)": 100 * (og == 1).mean(),
                     "Away win % (model)": 100 * g["pA"].mean(), "Away win % (actual)": 100 * (og == 2).mean(),
                     "Goals per game (model)": (g["ExpHome"] + g["ExpAway"]).mean(), "Goals per game (actual)": g["Goals"].mean()})
    bias_table = pd.DataFrame(rows).set_index("Group").round(2)
    print("\nBias check (model's average prediction vs what actually happened):")
    display(bias_table)

    # --- calibration bands: when the model says X%, how often does it happen? ---
    for k, lab in enumerate(["Home win", "Draw", "Away win"]):
        bins = np.clip((P[:, k] * 10).astype(int), 0, 9)
        for b in range(10):
            sel = bins == b
            if sel.sum() >= 15:
                calib_bands.append({"Outcome": lab, "Band": f"{10 * b}-{10 * b + 10}%", "Predicted": 100 * P[sel, k].mean(),
                                    "Actual": 100 * (o[sel] == k).mean(), "Matches": int(sel.sum())})
    ov = s["pOver25"].notna().values
    if ov.sum() >= 50:
        po, ao = s.loc[ov, "pOver25"].values, (s.loc[ov, "Goals"] > 2.5).values
        bins = np.clip((po * 10).astype(int), 0, 9)
        for b in range(10):
            sel = bins == b
            if sel.sum() >= 15:
                calib_bands.append({"Outcome": "Over 2.5", "Band": f"{10 * b}-{10 * b + 10}%", "Predicted": 100 * po[sel].mean(),
                                    "Actual": 100 * ao[sel].mean(), "Matches": int(sel.sum())})
    print("\nCalibration (a well-calibrated model has Predicted close to Actual in every band):")
    display(pd.DataFrame(calib_bands).round(1))

    # --- both teams to score: right more often than "always guess the usual answer"? calibrated? ---
    btts_edge, btts_cal = None, []
    if "btts_prob" in globals() and {"ExpHome", "ExpAway"}.issubset(s.columns):
        pb = np.array([btts_prob(r.ExpHome, r.ExpAway, r.pH, r.pD, r.pA) for r in s.itertuples()])
        yb = ((s["FTHG"] > 0) & (s["FTAG"] > 0)).values
        hit = ((pb >= 0.5) == yb).mean()
        usual = s.assign(y=yb).groupby("Competition")["y"].transform("mean").values >= 0.5      # each league's usual answer
        naive = (usual == yb).mean()
        btts_edge = float(100 * (hit - naive))
        for lo, hi in [(0, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 1.01)]:
            sel = (pb >= lo) & (pb < hi)
            if sel.sum() >= 30:
                btts_cal.append({"Model's chance": f"{int(100 * lo)}-{min(100, int(100 * hi))}%", "Matches": int(sel.sum()),
                                 "Model said %": float(100 * pb[sel].mean()), "Both scored %": float(100 * yb[sel].mean())})
        print(f"\nBoth teams to score: right {100 * hit:.1f}% of the time vs {100 * naive:.1f}% for always guessing each league's usual answer "
              f"({btts_edge:+.1f} points){' -> no proven edge' if btts_edge < 2 else ''}.")
        display(pd.DataFrame(btts_cal).round(1))
        EXTRA_TABLES_EARLY = list(globals().get("EXTRA_TABLES_EARLY", [])) + [{"title": "Both teams to score: calibration",
            "hint": f"Right {100 * hit:.1f}% of the time vs {100 * naive:.1f}% for always guessing each league's usual answer ({btts_edge:+.1f} points).", "rows": btts_cal}]

    # --- closing-line comparison: did the market move toward the model between early and closing odds? ---
    clv = {}
    cl = s[s["Group"] == "Domestic"].merge(all_matches[["League", "Date", "HomeTeam", "AwayTeam", "B365CH", "B365CD", "B365CA"]].rename(
        columns={"League": "Competition", "HomeTeam": "Home", "AwayTeam": "Away"}), on=["Competition", "Date", "Home", "Away"], how="inner")
    cl = cl.dropna(subset=ODDS + ["B365CH", "B365CD", "B365CA"])
    if len(cl) >= 50:
        po = book_probs(cl)
        pc = (1 / cl[["B365CH", "B365CD", "B365CA"]].values); pc = pc / pc.sum(axis=1, keepdims=True)
        pm = cl[["pH", "pD", "pA"]].values
        k_ = np.abs(pm - po).argmax(axis=1)                         # where the model disagreed most with the early odds
        idx = np.arange(len(cl))
        dir_model, move = np.sign(pm[idx, k_] - po[idx, k_]), pc[idx, k_] - po[idx, k_]
        moved = move != 0
        toward = (np.sign(move) == dir_model)[moved]
        oc = outcome(cl)
        clv = {"matches": int(moved.sum()), "toward_pct": float(100 * toward.mean()),
               "avg_move": float(100 * (move * dir_model)[moved].mean()),
               "ll_model": float(-np.log(pm[idx, oc]).mean()), "ll_early": float(-np.log(po[idx, oc]).mean()),
               "ll_close": float(-np.log(pc[idx, oc]).mean())}
        print(f"\nClosing-line check on {clv['matches']} domestic matches: the market moved toward the model in {clv['toward_pct']:.0f}% of them "
              f"(50% = no information), by {clv['avg_move']:+.1f} points on average. Log loss: model {clv['ll_model']:.3f}, "
              f"early odds {clv['ll_early']:.3f}, closing odds {clv['ll_close']:.3f}.")

    # --- model + market blend: weight learned on earlier weeks, tested on later weeks, per group ---
    WGRID = np.round(np.arange(0, 1.01, 0.05), 2)
    blend_curves, new_blend, rng_b = {}, {}, np.random.default_rng(1)
    for grp in sorted(set(s["Group"])):
        g = s[(s["Group"] == grp)].dropna(subset=["bookH", "bookD", "bookA"]).sort_values("Date")
        if len(g) < 60:
            continue
        Pm, Bm, Og = g[["pH", "pD", "pA"]].values, g[["bookH", "bookD", "bookA"]].values, outcome(g)
        llw = lambda Pm_, Bm_, Og_, w_: -np.log(np.clip((w_ * Pm_ + (1 - w_) * Bm_)[np.arange(len(Og_)), Og_], 1e-9, 1))
        blend_curves[grp] = [{"w": float(w_), "ll": float(llw(Pm, Bm, Og, w_).mean())} for w_ in WGRID]
        wk = (g["Date"] - pd.to_timedelta(g["Date"].dt.weekday, unit="D")).dt.normalize().values
        lm, lb, lk = [], [], []
        for w_ in sorted(set(wk)):
            prior, cur = (g["Date"].values < w_), (wk == w_)
            if prior.sum() < 100:
                continue
            best = WGRID[np.argmin([llw(Pm[prior], Bm[prior], Og[prior], x).mean() for x in WGRID])]
            lb += list(llw(Pm[cur], Bm[cur], Og[cur], best)); lm += list(llw(Pm[cur], Bm[cur], Og[cur], 1.0)); lk += list(llw(Pm[cur], Bm[cur], Og[cur], 0.0))
        w_all = float(WGRID[np.argmin([c_["ll"] for c_ in blend_curves[grp]])])
        entry = {"w": w_all, "matches": int(len(g))}
        if len(lb) >= 50:
            dd = np.array(lb) - np.array(lm)
            entry.update({"tested": len(lb), "ll_model": float(np.mean(lm)), "ll_blend": float(np.mean(lb)), "ll_book": float(np.mean(lk)),
                          "pct_vs_model": float(100 * (np.array([rng_b.choice(dd, len(dd)).mean() for _ in range(2000)]) < 0).mean())})
        new_blend[grp] = entry
    json.dump(new_blend, open(BLEND_PATH, "w"))
    print("\nModel + market blend (share of the MODEL in the blend; learned on earlier weeks, tested on later ones):")
    for grp, e_ in new_blend.items():
        extra = (f"; on later weeks: model {e_['ll_model']:.3f}, blend {e_['ll_blend']:.3f}, bookmakers {e_['ll_book']:.3f}" if "tested" in e_ else "")
        print(f"  {grp}: {100 * e_['w']:.0f}% model / {100 - 100 * e_['w']:.0f}% market{extra}")

    # --- disagreement record: when the model differed from the early odds, who was closer? ---
    disagree = []
    sb = s.dropna(subset=["bookH", "bookD", "bookA"])
    if len(sb) >= 100:
        Pm, Bm, Ob = sb[["pH", "pD", "pA"]].values, sb[["bookH", "bookD", "bookA"]].values, outcome(sb)
        happened = np.zeros_like(Pm); happened[np.arange(len(sb)), Ob] = 1
        for thr in [5, 10, 15]:
            for direction, mask in [("model higher than market", (Pm - Bm) >= thr / 100), ("model lower than market", (Bm - Pm) >= thr / 100)]:
                n_ = int(mask.sum())
                if n_ >= 10:
                    disagree.append({"Disagreement": f"{thr}+ points, {direction}", "Cases": n_, "Model said %": 100 * Pm[mask].mean(),
                                     "Market said %": 100 * Bm[mask].mean(), "Actually happened %": 100 * happened[mask].mean()})
        print("\nDisagreement record (outcomes where the model and the early odds differed; if the model's view has value,")
        print("'Actually happened' sits closer to the model than to the market):")
        display(pd.DataFrame(disagree).round(1))

    # --- miss review: why did the biggest misses happen? ---
    miss_rows, miss_totals = [], {}
    ids_ = []
    if "mf" in globals() and len(mf):
        ids_.append(mf[["League", "Date", "HomeTeam", "AwayTeam", "event_id", "home_id", "away_id"]].rename(columns={"League": "Competition", "HomeTeam": "Home", "AwayTeam": "Away"}))
    if len(euro) and "event_id" in euro:
        ids_.append(euro[["Competition", "Date", "HomeTeam", "AwayTeam", "event_id", "home_id", "away_id"]].rename(columns={"HomeTeam": "Home", "AwayTeam": "Away"}))
    if ids_ and len(lu):
        idmap = pd.concat(ids_, ignore_index=True).drop_duplicates(["Competition", "Date", "Home", "Away"])
        idmap[["event_id", "home_id", "away_id"]] = idmap[["event_id", "home_id", "away_id"]].astype(str)
        lu_t = {t_: g_.sort_values("date") for t_, g_ in lu.assign(team_id=lu["team_id"].astype(str), player_id=lu["player_id"].astype(str)).groupby("team_id")}
        reds = events_all[events_all["type"].astype(str).str.startswith("Red Card")] if "events_all" in globals() and len(events_all) else pd.DataFrame(columns=["event_id"])
        reds_by = {k_: g_ for k_, g_ in reds.groupby("event_id")} if len(reds) else {}
        id_lookup = {(c_, pd.Timestamp(dt_), h_, a_): row_ for c_, dt_, h_, a_, row_ in
                     zip(idmap["Competition"], idmap["Date"], idmap["Home"], idmap["Away"], idmap.to_dict("records"))}
        def diagnose(r_):
            causes = []
            m_ = id_lookup.get((r_["Competition"], pd.Timestamp(r_["Date"]), r_["Home"], r_["Away"]))
            if m_ is None:
                return ["no lineup data for this match"]
            if m_["event_id"] in reds_by:
                for rr in reds_by[m_["event_id"]].itertuples():
                    who = r_["Home"] if str(rr.team_id) == m_["home_id"] else r_["Away"]
                    causes.append(f"red card for {who}" + (f" ({int(rr.minute)}')" if pd.notna(rr.minute) else ""))
            for side_, tid_ in [("Home", m_["home_id"]), ("Away", m_["away_id"])]:
                g_ = lu_t.get(tid_)
                if g_ is None:
                    continue
                before = g_[(g_["date"] < r_["Date"]) & (g_["date"] >= r_["Date"] - pd.Timedelta(days=60))]
                now_ = g_[g_["event_id"].astype(str) == m_["event_id"]]
                if before.empty or now_.empty:
                    continue
                rate = before.groupby("player_id")["starter"].sum() / before["event_id"].nunique()
                regulars = set(rate[rate >= 0.5].index)
                prev_ev = before.sort_values("date")["event_id"].iloc[-1]
                prev_squad = set(before.loc[before["event_id"] == prev_ev, "player_id"])
                starters = set(now_.loc[now_["starter"], "player_id"])
                surprise = [p_ for p_ in regulars if p_ not in starters and p_ in prev_squad]
                if regulars and len(surprise) / len(regulars) >= 0.4:
                    causes.append(f"heavy rotation by {r_[side_]} ({len(surprise)} regulars didn't start)")
                elif len(surprise) >= 2:
                    names_ = now_.set_index("player_id")["player"].to_dict()
                    allnames = g_.drop_duplicates("player_id").set_index("player_id")["player"].to_dict()
                    causes.append(f"unexpected absences for {r_[side_]}: " + ", ".join(allnames.get(p_, p_) for p_ in surprise[:3]))
            return causes or ["no clear cause (probably normal variation)"]
        s["Causes"] = [diagnose(r_) for _, r_ in s.iterrows()]          # every match, so misses can be compared with the rest
        big = s[s["pResult"] < 0.25].copy()
        kind = lambda c_: ("Red card" if c_.startswith("red card") else "Rotation" if c_.startswith("heavy rotation") else
                           "Unexpected absences" if c_.startswith("unexpected absences") else "No lineup data" if c_.startswith("no lineup") else "No clear cause")
        kinds_all = s["Causes"].apply(lambda cs: {kind(c_) for c_ in cs})
        kinds_big = kinds_all[s["pResult"] < 0.25]
        for k_ in ["Unexpected absences", "Rotation", "Red card", "No clear cause", "No lineup data"]:
            n_big = int(kinds_big.apply(lambda ks: k_ in ks).sum()); n_all = int(kinds_all.apply(lambda ks: k_ in ks).sum())
            if n_big == 0:
                continue
            rate_big, rate_all = n_big / len(big), n_all / len(s)
            # does this cause show up clearly more often in the misses? (simple two-proportion test)
            p_pool = n_all / len(s)
            se = np.sqrt(p_pool * (1 - p_pool) * (1 / len(big) + 1 / len(s))) if 0 < p_pool < 1 else np.inf
            z = (rate_big - rate_all) / se if se > 0 else 0
            miss_totals[k_] = {"misses": n_big, "miss_pct": 100 * rate_big, "all_pct": 100 * rate_all,
                               "lift": rate_big / rate_all if rate_all else np.nan, "stands_out": bool(z >= 2 and k_ not in ("No clear cause", "No lineup data"))}
        latest = big[big["Date"] >= big["Date"].max() - pd.Timedelta(days=7)].sort_values("pResult")
        miss_rows = [{"Date": str(r_["Date"])[:10], "Competition": r_["Competition"], "Match": f"{r_['Home']} {r_['Score']} {r_['Away']}",
                      "Chance given": float(r_["pResult"]), "Likely cause": "; ".join(r_["Causes"])} for _, r_ in latest.iterrows()]
        print(f"\nMiss review: {len(big)} matches this season where the model gave the result under 25%.")
        print("Each cause's rate in those misses vs in ALL matches; only a cause clearly more common in the misses can explain them:")
        for k_, v_ in miss_totals.items():
            print(f"  {k_}: {v_['miss_pct']:.0f}% of misses vs {v_['all_pct']:.0f}% of all matches"
                  + (" -> stands out" if v_["stands_out"] else (" -> no more common than usual" if k_ not in ("No clear cause", "No lineup data") else "")))
        if miss_rows:
            print("Latest week's biggest misses:")
            display(pd.DataFrame(miss_rows))

    # --- player-adjustment check: are some leagues getting implausibly large adjustments? ---
    adj_check, adj_decision = [], {}
    if {"AdjHome", "AdjAway", "rho"}.issubset(s.columns) and s["rho"].notna().sum() >= 200:
        sa = s.dropna(subset=["AdjHome", "AdjAway", "rho"]).copy()
        sa["size"] = np.maximum(np.abs(np.log(sa["AdjHome"])), np.abs(np.log(sa["AdjAway"])))
        sa["large"] = (np.abs(sa["AdjHome"] - 1) >= 0.20) | (np.abs(sa["AdjAway"] - 1) >= 0.20)
        overall_large = sa["large"].mean()
        for comp_, g_ in sa.groupby("Competition"):
            adj_check.append({"Competition": comp_, "Matches": len(g_), "Typical size %": float(100 * (np.exp(g_["size"].median()) - 1)),
                              "Large (20%+) %": float(100 * g_["large"].mean()), "Stands out": bool(g_["large"].mean() >= max(3 * overall_large, 0.15) and len(g_) >= 30)})
        adj_check = sorted(adj_check, key=lambda r_: -r_["Large (20%+) %"])
        print(f"\nPlayer-adjustment check (large = 20%+ change in expected goals; overall {100 * overall_large:.0f}% of matches):")
        display(pd.DataFrame(adj_check).round(1))
        # test caps: learned on the first half of the season, checked on the second half
        sa = sa.sort_values("Date").reset_index(drop=True)
        half = sa["Date"] >= sa["Date"].quantile(0.5)
        o_a = outcome(sa)
        def ll_cap(cap, rows):
            g_ = sa[rows]
            fh, fa = g_["AdjHome"].values, g_["AdjAway"].values
            fhc, fac = (np.clip(fh, 1 - cap, 1 + cap), np.clip(fa, 1 - cap, 1 + cap)) if cap else (fh, fa)
            h_, a_ = g_["ExpHome"].values / fh * fhc, g_["ExpAway"].values / fa * fac
            p_ = np.zeros((len(g_), 3))
            for r_v in np.unique(g_["rho"].values):
                i_ = np.where(g_["rho"].values == r_v)[0]
                p_[i_] = outcome_probs(h_[i_], a_[i_], r_v)
            return -np.log(np.clip(p_[np.arange(len(g_)), o_a[rows.values]], 1e-9, 1))
        caps = [None, 0.25, 0.20, 0.15, 0.10]
        first = [ll_cap(c_, ~half).mean() for c_ in caps]
        best_cap = caps[int(np.argmin(first))]
        if best_cap is not None:
            d_ = ll_cap(best_cap, half) - ll_cap(None, half)
            rng_a = np.random.default_rng(2)
            pct = 100 * (np.array([rng_a.choice(d_, len(d_)).mean() for _ in range(2000)]) < 0).mean()
            adopt = pct >= 95 and d_.mean() < 0
            adj_decision = {"cap": best_cap if adopt else None, "tested_cap": best_cap, "change": float(d_.mean()), "pct": float(pct)}
            print(f"Capping adjustments at +/-{100 * best_cap:.0f}% (chosen on the first half of the season), checked on the second half: "
                  f"log loss {d_.mean():+.4f}, better in {pct:.0f}% of reshuffles -> {'switched ON from the next run' if adopt else 'not adopted'}.")
        else:
            adj_decision = {"cap": None, "tested_cap": None}
            print("No cap improved the first half of the season, so adjustments stay uncapped.")
        json.dump({"cap": adj_decision.get("cap")}, open(ADJ_CAP_PATH, "w"))

    # --- corrections: learned on earlier weeks, tested on later weeks ---
    TGRID, DGRID = np.round(np.arange(0.8, 1.26, 0.05), 2), np.round(np.arange(0.85, 1.21, 0.05), 2)
    def fit_cal(Pm, Om):
        best, bl = (1.0, 1.0), np.inf
        for T_ in TGRID:
            for d_ in DGRID:
                l_ = -np.log(calibrate_full(Pm, T_, d_)[np.arange(len(Om)), Om]).mean()
                if l_ < bl:
                    best, bl = (float(T_), float(d_)), l_
        return best
    rng_c = np.random.default_rng(0)
    new_cal = {}
    for grp in sorted(set(s["Group"]) - {"Europe"}):
        g = s[s["Group"] == grp].sort_values("Date")
        Pg, Og = g[["pH", "pD", "pA"]].values, outcome(g)
        wk = (g["Date"] - pd.to_timedelta(g["Date"].dt.weekday, unit="D")).dt.normalize().values
        raw, cor = [], []
        for w_ in sorted(set(wk)):
            prior, cur = (g["Date"].values < w_), (wk == w_)
            if prior.sum() < 150:
                continue
            T_, d_ = fit_cal(Pg[prior], Og[prior])
            raw += list(-np.log(Pg[cur][np.arange(cur.sum()), Og[cur]]))
            cor += list(-np.log(calibrate_full(Pg[cur], T_, d_)[np.arange(cur.sum()), Og[cur]]))
        if len(raw) < 100:
            cal_result[grp] = {"status": f"not enough matches yet ({len(raw)} testable)"}
            continue
        diff = np.array(cor) - np.array(raw)
        pct = 100 * (np.array([rng_c.choice(diff, len(diff)).mean() for _ in range(2000)]) < 0).mean()
        T_all, d_all = fit_cal(Pg, Og)
        adopt = pct >= 95 and diff.mean() < 0
        new_cal[grp] = {"T": T_all, "draw": d_all} if adopt else {"T": 1.0, "draw": 1.0}
        cal_result[grp] = {"status": "switched on" if adopt else "not needed", "change": float(diff.mean()), "pct": float(pct),
                           "tested": len(diff), "T": T_all, "draw": d_all}
    json.dump(new_cal, open(CAL_PATH, "w"))
    print("\nCorrections (learned on earlier weeks of this season, tested on later weeks):")
    for grp, r_ in cal_result.items():
        if "pct" in r_:
            print(f"  {grp}: {r_['status']} (change in log loss {r_['change']:+.4f}, better in {r_['pct']:.0f}% of reshuffles; "
                  f"cautiousness {r_['T']:.2f}, draws x{r_['draw']:.2f}){' - applies from the next run' if r_['status'] == 'switched on' else ''}")
        else:
            print(f"  {grp}: {r_['status']}")
else:
    print("Needs the backtest (RUN_BACKTEST = True).")
