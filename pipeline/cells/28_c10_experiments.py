# ===================== 9. EXPERIMENTS: what's worth switching on? =====================
# Each experiment is scored on matches the model hadn't seen, against the bookmakers. Nothing here changes predictions.
from statsmodels.miscmodels.ordinal_model import OrderedModel
rng_x = np.random.default_rng(0)

def probs_from(df):
    """Home/draw/away probabilities from expected goals and each row's Dixon-Coles rho."""
    p = np.zeros((len(df), 3))
    for r_, idx in df.groupby("rho").groups.items():
        pos = df.index.get_indexer(idx)
        p[pos] = outcome_probs(df.loc[idx, "ExpHome"].values, df.loc[idx, "ExpAway"].values, r_)
    return p

def ll(p, o):
    return -np.log(np.clip(p[np.arange(len(p)), o], 1e-9, 1))

def reshuffle(diff):
    boots = np.array([rng_x.choice(diff, len(diff)).mean() for _ in range(2000)])
    return 100 * (boots < 0).mean()

def report(name, rows):
    t = pd.DataFrame(rows).set_index("Version")
    print(f"\n=== {name} ===")
    display(t.round(4))

exp_summary = []
EXTRA_TABLES = list(globals().get("EXTRA_TABLES_EARLY", []))
if RUN_EXPERIMENTS:
    season_start = all_matches.loc[all_matches["Season"] == SEASONS[-1], "Date"].min()

    # ---------- E2: ClubElo as a second opinion ----------
    if USE_CLUBELO and len(elo_snap) and "base" in globals() and len(base):
        dom = base[base["League"].isin(LEAGUES.values())].dropna(subset=ODDS).reset_index(drop=True)
        dom = elo_lookup(dom.assign(HomeLeague=dom["League"], AwayLeague=dom["League"])).dropna(subset=["EloH", "EloA"]).reset_index(drop=True)
        tr, te = dom[dom["Date"] < season_start].reset_index(drop=True), dom[dom["Date"] >= season_start].reset_index(drop=True)
        if len(tr) > 300 and len(te) > 50:
            om = OrderedModel(2 - outcome(tr), ((tr["EloH"] - tr["EloA"]) / 100).to_frame("d"), distr="logit").fit(method="bfgs", disp=False)
            elo_p = lambda df: om.model.predict(om.params, exog=((df["EloH"] - df["EloA"]) / 100).to_frame("d").values)[:, ::-1]
            p_tr, e_tr = probs_from(tr), elo_p(tr)
            weights = np.round(np.arange(0, 1.01, 0.05), 2)
            w = weights[np.argmin([ll(wt * p_tr + (1 - wt) * e_tr, outcome(tr)).mean() for wt in weights])]
            o = outcome(te)
            p_te, e_te = probs_from(te), elo_p(te)
            ours, elo_, blend, book = ll(p_te, o), ll(e_te, o), ll(w * p_te + (1 - w) * e_te, o), ll(book_probs(te), o)
            report(f"E2a. ClubElo on {len(te)} domestic matches this season (blend weight learned on earlier matches: {w:.2f} ours / {1 - w:.2f} ClubElo)", [
                {"Version": "Our model", "Log loss": ours.mean(), "Gap to bookie": (ours - book).mean()},
                {"Version": "ClubElo", "Log loss": elo_.mean(), "Gap to bookie": (elo_ - book).mean()},
                {"Version": "Blend", "Log loss": blend.mean(), "Gap to bookie": (blend - book).mean()},
                {"Version": "Bookmaker", "Log loss": book.mean(), "Gap to bookie": 0.0}])
            pct = reshuffle(blend - ours)
            print(f"Blend beat our model in {pct:.0f}% of reshuffles.")
            exp_summary.append({"Experiment": "ClubElo blend, domestic", "Change in log loss": (blend - ours).mean(),
                                "Helped in % of reshuffles": pct, "Matches": len(te)})

            # same blend in Europe, where ClubElo knows clubs from every country
            if RUN_BACKTEST and "rho" in backtest:
                be = backtest[backtest["Group"] == "Europe"].copy()
                be["Date"] = pd.to_datetime(be["Date"])
                e_ = euro.rename(columns={"HomeTeam": "Home", "AwayTeam": "Away"})
                be = be.drop(columns=[c for c in ODDS if c in be]).merge(
                    e_[["Competition", "Date", "Home", "Away", "HomeLeague", "AwayLeague", "FTHG", "FTAG"] + ODDS],
                    on=["Competition", "Date", "Home", "Away"]).dropna(subset=ODDS)
                be = elo_lookup(be.rename(columns={"Home": "HomeTeam", "Away": "AwayTeam"})).dropna(subset=["EloH", "EloA"]).reset_index(drop=True)
                if len(be) >= 20:
                    o = outcome(be)
                    p_b, e_b = probs_from(be), elo_p(be)
                    ours, elo_, blend, book = ll(p_b, o), ll(e_b, o), ll(w * p_b + (1 - w) * e_b, o), ll(book_probs(be), o)
                    other = ((be["HomeLeague"] == "Other") | (be["AwayLeague"] == "Other")).values
                    report(f"E2b. ClubElo on {len(be)} European matches this season ({other.sum()} involving clubs from other countries)", [
                        {"Version": "Our model", "Log loss": ours.mean(), "Other-country matches": ours[other].mean() if other.any() else np.nan},
                        {"Version": "ClubElo", "Log loss": elo_.mean(), "Other-country matches": elo_[other].mean() if other.any() else np.nan},
                        {"Version": "Blend", "Log loss": blend.mean(), "Other-country matches": blend[other].mean() if other.any() else np.nan},
                        {"Version": "Bookmaker", "Log loss": book.mean(), "Other-country matches": book[other].mean() if other.any() else np.nan}])
                    pct = reshuffle(blend - ours)
                    print(f"Blend beat our model in {pct:.0f}% of reshuffles.")
                    exp_summary.append({"Experiment": "ClubElo blend, Europe", "Change in log loss": (blend - ours).mean(),
                                        "Helped in % of reshuffles": pct, "Matches": len(be)})

    # ---------- E3: expected goals (Understat) in the team ratings, big five leagues ----------
    if USE_UNDERSTAT and len(xg) and "base" in globals() and len(base):
        def xg_walk(lg, start, lam, half_life=365):
            lg = lg.copy()
            lg["YH"] = (1 - lam) * lg["FTHG"] + lam * lg["xGH"].fillna(lg["FTHG"])
            lg["YA"] = (1 - lam) * lg["FTAG"] + lam * lg["xGA"].fillna(lg["FTAG"])
            out = []
            wk = (lg["Date"] - pd.to_timedelta(lg["Date"].dt.weekday, unit="D")).dt.normalize()
            this_week_ = TODAY - pd.Timedelta(days=TODAY.weekday())
            for w_ in sorted(wk[(lg["Date"] >= start) & (lg["Date"] < this_week_)].unique()):
                w_ = pd.Timestamp(w_)
                train, games = lg[lg["Date"] < w_], lg[(lg["Date"] >= w_) & (lg["Date"] < w_ + pd.Timedelta(days=7))]
                counts = pd.concat([train["HomeTeam"], train["AwayTeam"]]).value_counts()
                known = set(counts[counts >= 5].index)
                games = games[games["HomeTeam"].isin(known) & games["AwayTeam"].isin(known)]
                if games.empty:
                    continue
                m = fit_weighted(train, "YH", "YA", 0.01, half_life)
                rho = estimate_rho_ha(*shrunk_means(m, train), train)
                h, a = shrunk_means(m, games)
                out.append(games[["League", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"] + ODDS].assign(ExpHome=h, ExpAway=a, rho=rho))
            return out
        rows_ = []
        for lam in [0.5, 1.0]:
            path = f"{SAVE_DIR}/xg_walk_{lam}.csv"
            prev = pd.read_csv(path, parse_dates=["Date"]) if os.path.exists(path) else pd.DataFrame()
            parts = []
            for league in UNDERSTAT_LEAGUES:
                lg = all_matches[all_matches["League"] == league].merge(
                    xg[["League", "Season", "HomeTeam", "AwayTeam", "xGH", "xGA"]].drop_duplicates(["League", "Season", "HomeTeam", "AwayTeam"]),
                    on=["League", "Season", "HomeTeam", "AwayTeam"], how="left")
                done_to = prev.loc[prev["League"] == league, "Date"].max() if len(prev) else pd.NaT
                start = (done_to + pd.Timedelta(days=1)) if pd.notna(done_to) else base.loc[base["League"] == league, "Date"].min()
                if pd.isna(start):
                    continue
                start = start - pd.Timedelta(days=start.weekday())
                parts += xg_walk(lg, start, lam)
            allp = pd.concat([prev] + parts, ignore_index=True).drop_duplicates(["League", "Date", "HomeTeam", "AwayTeam"], keep="last") if (parts or len(prev)) else prev
            allp.to_csv(path, index=False)
            rows_.append((lam, allp))
            print(f"  expected-goals blend {lam:.1f}: {len(allp)} matches predicted")
        key = ["League", "Date", "HomeTeam", "AwayTeam"]
        b5 = base[base["League"].isin(UNDERSTAT_LEAGUES)].dropna(subset=ODDS)
        res_rows, diffs = [], {}
        for lam, allp in rows_:
            m = b5.merge(allp[key + ["ExpHome", "ExpAway", "rho"]], on=key, suffixes=("_g", "")).reset_index(drop=True)
            o = outcome(m)
            goals_ll = ll(probs_from(m.assign(ExpHome=m["ExpHome_g"], ExpAway=m["ExpAway_g"], rho=m["rho_g"])), o)
            xg_ll, book = ll(probs_from(m), o), ll(book_probs(m), o)
            if not res_rows:
                res_rows.append({"Version": "Goals only (current)", "Log loss": goals_ll.mean(), "Gap to bookie": (goals_ll - book).mean(), "Matches": len(m)})
            res_rows.append({"Version": f"{int(lam * 100)}% expected goals", "Log loss": xg_ll.mean(), "Gap to bookie": (xg_ll - book).mean(), "Matches": len(m)})
            diffs[lam] = (xg_ll - goals_ll, len(m))
        res_rows.append({"Version": "Bookmaker", "Log loss": book.mean(), "Gap to bookie": 0.0, "Matches": len(m)})
        report("E3. Expected goals in the team ratings (big five leagues, 2025/26 and 2026/27)", res_rows)
        for lam, (d_, n_) in diffs.items():
            pct = reshuffle(d_)
            print(f"{int(lam * 100)}% expected goals beat goals-only in {pct:.0f}% of reshuffles.")
            exp_summary.append({"Experiment": f"{int(lam * 100)}% expected goals (big five)", "Change in log loss": d_.mean(),
                                "Helped in % of reshuffles": pct, "Matches": n_})

    # ---------- second divisions for promoted teams (decision used from the next run) ----------
    if len(div2) and TEST_GOAL_LEVEL_AND_REST:
        rows_ = []
        for code, (top, name) in DIV2.items():
            lg_ = all_matches[all_matches["League"] == top]
            d2_ = div2[div2["League"] == name]
            for s_ in SEASONS[-2:]:
                cur = lg_[lg_["Season"] == s_]
                prev_teams = set(lg_.loc[lg_["Season"] == SEASONS[SEASONS.index(s_) - 1], "HomeTeam"]) if SEASONS.index(s_) > 0 else set()
                if cur.empty or not prev_teams:
                    continue
                new_teams = set(cur["HomeTeam"]) - prev_teams
                start_ = cur["Date"].min()
                early = cur[(cur["Date"] < start_ + pd.Timedelta(days=60)) & (cur["HomeTeam"].isin(new_teams) | cur["AwayTeam"].isin(new_teams))]
                wk_ = (early["Date"] - pd.to_timedelta(early["Date"].dt.weekday, unit="D")).dt.normalize()
                for w_ in sorted(wk_.unique()):
                    w_ = pd.Timestamp(w_)
                    games = early[(early["Date"] >= w_) & (early["Date"] < w_ + pd.Timedelta(days=7))]
                    tr_top, tr_d2 = lg_[lg_["Date"] < w_], d2_[d2_["Date"] < w_]
                    t_cur = predict_league(tr_top, games, half_life=365, totals=False, quiet=True)
                    m2 = fit_two_div(tr_top, tr_d2)
                    rho_ = estimate_rho_ha(*shrunk_means(fit_weighted(tr_top, "FTHG", "FTAG", 0.01, 365), tr_top), tr_top)
                    h2, a2 = two_div_means(m2, games)
                    p2 = outcome_probs(h2, a2, rho_)
                    o_ = outcome(games)
                    rows_.append(pd.DataFrame({"league": top, "ll_cur": -np.log(t_cur[["pH", "pD", "pA"]].values[np.arange(len(games)), o_]),
                                               "ll_new": -np.log(p2[np.arange(len(games)), o_])}))
        if rows_:
            r_ = pd.concat(rows_, ignore_index=True)
            d_ = (r_["ll_new"] - r_["ll_cur"]).values
            rng_d = np.random.default_rng(0)
            pct = 100 * (np.array([rng_d.choice(d_, len(d_)).mean() for _ in range(2000)]) < 0).mean()
            print(f"Second divisions, tested on {len(r_)} early-season matches involving promoted teams: log loss {d_.mean():+.4f}, "
                  f"better in {pct:.0f}% of reshuffles (current method {r_['ll_cur'].mean():.3f}, with second divisions {r_['ll_new'].mean():.3f}).")
            SECOND_DIV = {"on": bool(pct >= 95 and d_.mean() < 0), "pct": float(pct), "tested": int(len(r_))}
            json.dump(SECOND_DIV, open(D2_PATH, "w"))

    # ---------- E3b: expected goals (PitchAPI) for leagues Understat doesn't cover ----------
    if "xg_walk" in globals() and len(xg) and "base" in globals() and len(base):
        path = f"{SAVE_DIR}/xg_walk_extra_0.5.csv"
        prev = pd.read_csv(path, parse_dates=["Date"]) if os.path.exists(path) else pd.DataFrame(columns=["League", "Date"])
        tested, parts, cov_note = [], [], []
        for league in PA_XG_LEAGUES:
            b_ = base[base["League"] == league]
            if b_.empty:
                continue
            lg = league_frame(league).merge(xg[["League", "Season", "HomeTeam", "AwayTeam", "xGH", "xGA"]].drop_duplicates(["League", "Season", "HomeTeam", "AwayTeam"]),
                                            on=["League", "Season", "HomeTeam", "AwayTeam"], how="left")
            window = lg[lg["Date"] >= b_["Date"].min() - pd.Timedelta(days=365)]
            cov = window["xGH"].notna().mean() if len(window) else 0
            cov_note.append(f"{league} {100 * cov:.0f}%")
            if cov < 0.8:
                continue                                       # wait until the history has expected goals
            tested.append(league)
            done_to = prev.loc[prev["League"] == league, "Date"].max() if len(prev) else pd.NaT
            start = (done_to + pd.Timedelta(days=1)) if pd.notna(done_to) else b_["Date"].min()
            parts += xg_walk(lg, start - pd.Timedelta(days=start.weekday()), 0.5, half_life=SOLO.get(league, {}).get("half_life", 365))
        allp = pd.concat([prev] + parts, ignore_index=True).drop_duplicates(["League", "Date", "HomeTeam", "AwayTeam"], keep="last") if parts else prev
        if parts:
            allp.to_csv(path, index=False)
        print(f"\nE3b. Expected-goals coverage of the extra leagues (needs 80% to be tested): {', '.join(cov_note)}")
        if tested and len(allp):
            key = ["League", "Date", "HomeTeam", "AwayTeam"]
            m = base[base["League"].isin(tested)].merge(allp[key + ["ExpHome", "ExpAway", "rho"]], on=key, suffixes=("_g", "")).reset_index(drop=True)
            if len(m) >= 200:
                o = outcome(m)
                g_ll = ll(probs_from(m.assign(ExpHome=m["ExpHome_g"], ExpAway=m["ExpAway_g"], rho=m["rho_g"])), o)
                x_ll = ll(probs_from(m), o)
                pct = reshuffle(x_ll - g_ll)
                by_lg = m.assign(d=x_ll - g_ll).groupby("League")["d"].agg(["mean", "size"]).round(4)
                print(f"   50% expected goals vs goals only, {len(m)} matches in {', '.join(tested)}: log loss {np.mean(x_ll - g_ll):+.4f}, better in {pct:.0f}% of reshuffles.")
                display(by_lg)
                adopt = pct >= 95 and np.mean(x_ll - g_ll) < 0
                json.dump({"leagues": tested if adopt else []}, open(XGL_PATH, "w"))
                print(f"   -> expected goals {'switched ON' if adopt else 'not adopted'} for these leagues (from the next run).")
                exp_summary.append({"Experiment": "50% expected goals (extra leagues)", "Change in log loss": float(np.mean(x_ll - g_ll)),
                                    "Helped in % of reshuffles": pct, "Matches": len(m)})

    # ---------- E6: market-anchored lineups: do confirmed lineups add to the market's own price? ----------
    if RUN_BACKTEST and bt_scored is not None and len(bt_scored) and "mf" in globals() and "h_act_reg" in mf:
        cols_ = ["League", "Date", "HomeTeam", "AwayTeam", "h_act_reg", "a_act_reg", "h_act_att", "a_act_att"]
        ma = bt_scored[bt_scored["Group"] == "Domestic"].merge(mf[cols_].rename(columns={"League": "Competition", "HomeTeam": "Home", "AwayTeam": "Away"}),
                                                                on=["Competition", "Date", "Home", "Away"], how="inner")
        ma = ma.merge(all_matches[["League", "Date", "HomeTeam", "AwayTeam", "B365CH", "B365CD", "B365CA"]].rename(columns={"League": "Competition", "HomeTeam": "Home", "AwayTeam": "Away"}),
                      on=["Competition", "Date", "Home", "Away"], how="left")
        ma = ma.dropna(subset=ODDS + ["B365CH", "B365CD", "B365CA", "h_act_reg", "a_act_reg"]).sort_values("Date").reset_index(drop=True)
        if len(ma) >= 300:
            from scipy.optimize import minimize
            o_m = outcome(ma)
            def mkt(cols3):
                p_ = 1 / ma[cols3].values
                return p_ / p_.sum(axis=1, keepdims=True)
            early, close_ = mkt(ODDS), mkt(["B365CH", "B365CD", "B365CA"])
            dreg = (ma["a_act_reg"] - ma["h_act_reg"]).values           # positive = the away side is missing more of its regulars
            datt = (ma["a_act_att"] - ma["h_act_att"]).fillna(0).values
            def shifted(p_, b):
                lp = np.log(np.clip(p_, 1e-9, 1))
                lp[:, 0] += b[0] * dreg + b[1] * datt
                lp[:, 2] -= b[0] * dreg + b[1] * datt
                q = np.exp(lp)
                return q / q.sum(axis=1, keepdims=True)
            lossf = lambda p_, rows: -np.log(np.clip(p_[rows][np.arange(rows.sum()), o_m[rows]], 1e-9, 1))
            first, later = (ma["Date"] < ma["Date"].quantile(0.5)).values, (ma["Date"] >= ma["Date"].quantile(0.5)).values
            res_tab = []
            for label_, base_p in [("Early odds", early), ("Closing odds", close_)]:
                b_fit = minimize(lambda b: lossf(shifted(base_p, b), first).mean(), x0=[0.0, 0.0], method="Nelder-Mead").x
                l0, l1 = lossf(base_p, later), lossf(shifted(base_p, b_fit), later)
                pct = reshuffle(l1 - l0)
                res_tab.append({"Starting point": label_, "Market alone": float(l0.mean()), "Market + confirmed lineups": float(l1.mean()),
                                "Change": float((l1 - l0).mean()), "Better in % of reshuffles": float(pct)})
            print(f"\nE6. Market-anchored lineups ({len(ma)} domestic matches; learned on the earlier half, tested on the later half):")
            display(pd.DataFrame(res_tab).set_index("Starting point").round(4))
            e_, c_ = res_tab[0], res_tab[1]
            if c_["Better in % of reshuffles"] >= 95 and c_["Change"] < 0:
                verdict = "Confirmed lineups improve even the CLOSING price: the market under-reacts to team news, so there may be a real edge at lineup time."
            elif e_["Better in % of reshuffles"] >= 95 and e_["Change"] < 0:
                verdict = ("Lineups improve the EARLY price but not the closing one: the market catches up by kickoff, so any edge needs "
                           "acting fast when lineups are announced, before prices move.")
            else:
                verdict = "No measurable value from lineups on top of the market's price (with the lineup data we have)."
            print("   " + verdict)
            EXTRA_TABLES.append({"title": "Market-anchored lineups", "hint": verdict + " Lower log loss is better.", "rows": res_tab})

    # ---------- E7: outsider check: does the model rate underdogs too highly? ----------
    if RUN_BACKTEST and bt_scored is not None and len(bt_scored):
        ob = bt_scored.dropna(subset=ODDS).sort_values("Date").reset_index(drop=True)
        if len(ob) >= 300:
            Pm = ob[["pH", "pD", "pA"]].values
            Bm = book_probs(ob)
            Om = np.zeros_like(Pm); Om[np.arange(len(ob)), outcome(ob)] = 1
            bands = [(0, 0.2), (0.2, 0.35), (0.35, 0.5), (0.5, 1.01)]
            tab = []
            for lo, hi in bands:
                sel = (Pm >= lo) & (Pm < hi)
                if sel.sum() >= 30:
                    tab.append({"Model's chance": f"{int(100 * lo)}-{min(100, int(100 * hi))}%", "Cases": int(sel.sum()), "Model said %": float(100 * Pm[sel].mean()),
                                "Market said %": float(100 * Bm[sel].mean()), "Actually happened %": float(100 * Om[sel].mean())})
            print("\nE7. Outsider check (all outcomes, this season's replayed matches with odds):")
            display(pd.DataFrame(tab).round(1))
            o_o = outcome(ob)
            first, later = (ob["Date"] < ob["Date"].quantile(0.5)).values, (ob["Date"] >= ob["Date"].quantile(0.5)).values
            llf = lambda p_, rows: -np.log(np.clip(p_[rows][np.arange(rows.sum()), o_o[rows]], 1e-9, 1))
            grid = np.round(np.arange(0.7, 1.001, 0.05), 2)
            s_best = grid[int(np.argmin([llf(outsider_adjust(Pm, g_), first).mean() for g_ in grid]))]
            if s_best < 1.0:
                d_ = llf(outsider_adjust(Pm, s_best), later) - llf(Pm, later)
                pct = reshuffle(d_)
                adopt = pct >= 95 and d_.mean() < 0
                print(f"   Scaling chances under 35% by {s_best:.2f} (chosen on the earlier half): later half log loss {d_.mean():+.4f}, "
                      f"better in {pct:.0f}% of reshuffles -> {'switched ON from the next run' if adopt else 'not adopted'}.")
                json.dump({"s": float(s_best) if adopt else 1.0}, open(OUTSIDER_PATH, "w"))
                verdict = f"Scaling outsiders by {s_best:.2f}: better in {pct:.0f}% of reshuffles on the later half, {'switched on' if adopt else 'not adopted'}."
            else:
                json.dump({"s": 1.0}, open(OUTSIDER_PATH, "w"))
                verdict = "No outsider adjustment helped on the earlier half."
                print("   " + verdict)
            EXTRA_TABLES.append({"title": "Outsider check", "hint": "When the model gives a low chance, does it happen as often as the model says, or as the market says? " + verdict, "rows": tab})

    if exp_summary:
        print("\n=== SUMMARY (negative change = better; 95%+ of reshuffles = confidently real) ===")
        display(pd.DataFrame(exp_summary).round(4))
else:
    print("Experiments switched off in Settings (RUN_EXPERIMENTS = False).")
