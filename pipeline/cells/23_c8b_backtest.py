# ===================== 8. BACKTEST: replay this season =====================
# Predicts every match played this season one week at a time, using only results from before that week,
# then scores the predictions exactly like the live log. Results are cached in Drive, so later runs only add new weeks.
BT_PATH = f"{SAVE_DIR}/backtest_{SEASONS[-1]}_v10.csv"   # v10: + rho stored, player-adjustment cap (if switched on)
week_start = lambda d: (d - pd.to_timedelta(d.dt.weekday, unit="D")).dt.normalize()

cache = pd.read_csv(BT_PATH) if os.path.exists(BT_PATH) else pd.DataFrame(columns=["Week"])
last_done = pd.Timestamp(cache["Week"].max()) if len(cache) else pd.Timestamp("1900-01-01")
cache = cache[pd.to_datetime(cache["Week"]) < last_done] if len(cache) else cache   # redo the last week, it may have been incomplete
this_week = TODAY - pd.Timedelta(days=TODAY.weekday())
new_rows = []
done_comps = set(cache["Competition"].dropna()) if len(cache) and "Competition" in cache else set()

def weeks_of(df, comp=None):
    # v36: a league not in the cache yet (a newly added one) replays its whole season, not just the weeks since the last run
    lo_ = last_done if (comp is None or comp in done_comps or not len(done_comps)) else pd.Timestamp("1900-01-01")
    w = week_start(df["Date"])
    return sorted(pd.Timestamp(d) for d in w.unique() if lo_ <= pd.Timestamp(d) < this_week + pd.Timedelta(days=7))

def bt_adjust_for(group):
    params = coefs_bt.get(group) if PLAYER_MODEL else None
    def adj(games):
        if params is None or len(mf) == 0:
            return no_adjust(games)
        cols = ["League", "Date", "HomeTeam", "AwayTeam"] + [c for c in mf.columns if c.startswith(("h_", "a_"))]
        f = games[["League", "Date", "HomeTeam", "AwayTeam"]].merge(
            mf[cols].drop_duplicates(subset=["League", "Date", "HomeTeam", "AwayTeam"]), how="left")
        fh, fa = multipliers(f, params)
        return fh, fa, [""] * len(games)
    return adj

def bt_euro_adjust(df):
    params = coefs_bt.get("Domestic") if (PLAYER_MODEL and EURO_PLAYER_ADJUST) else None
    if params is None or "event_id" not in df or "feats" not in globals():
        return np.ones(len(df)), np.ones(len(df))
    return multipliers(pair_features(feats, df[["event_id", "home_id", "away_id"]]), params)

if RUN_BACKTEST:
    print("Replaying this season week by week (the first run takes a few minutes; later runs only add new weeks)...")
    for league in LEAGUES.values():
        lg = all_matches[all_matches["League"] == league]
        test = lg[lg["Season"] == SEASONS[-1]]
        for w in weeks_of(test):
            games = test[(test["Date"] >= w) & (test["Date"] < w + pd.Timedelta(days=7))].copy()
            t = predict_league(lg[lg["Date"] < w], games, half_life=365, quiet=True, adjust=bt_adjust_for("Domestic"))
            if t is not None:
                new_rows.append(t.assign(Group="Domestic", Week=w.strftime("%Y-%m-%d")))
    for lg_name, info in SOLO.items():
        src = info["data"]
        test = src[src["Season"] == info["season"]]
        for w in weeks_of(test, lg_name):
            games = test[(test["Date"] >= w) & (test["Date"] < w + pd.Timedelta(days=7))].copy()
            t = predict_league(src[src["Date"] < w], games, half_life=info["half_life"], totals=info.get("totals", False), quiet=True, adjust=bt_adjust_for(info["group"]))
            if t is not None:
                new_rows.append(t.assign(Group=info["group"], Week=w.strftime("%Y-%m-%d")))
    test = euro[euro["Season"] == SEASONS[-1]]
    for w in weeks_of(test):
        games = test[(test["Date"] >= w) & (test["Date"] < w + pd.Timedelta(days=7))]
        t = predict_europe(domestic_x[domestic_x["Date"] < w], euro[euro["Date"] < w], games, quiet=True, adjust=bt_euro_adjust)
        new_rows.append(t.assign(Week=w.strftime("%Y-%m-%d")))
    backtest = pd.concat([cache] + new_rows, ignore_index=True) if new_rows else cache
    backtest.to_csv(BT_PATH, index=False)

    bt_scored, bt_table = scorecard(backtest)
    if bt_table is None:
        print("No finished matches this season yet.")
    else:
        print(f"\n{len(bt_scored)} matches replayed this season. Lower log loss is better; gap = model minus bookie.\n")
        display(bt_table)

        def by_comp(g):
            o_ = g["Bookie LL"].notna()
            return pd.Series({"Matches": len(g), "Model log loss": g["Model LL"].mean(),
                              "Bookie log loss": g.loc[o_, "Bookie LL"].mean() if o_.any() else np.nan,
                              "Gap to bookie": (g.loc[o_, "Model LL"] - g.loc[o_, "Bookie LL"]).mean() if o_.any() else np.nan,
                              "Top pick %": 100 * g["Top pick right"].mean(), "Over 2.5 %": 100 * g["pOver25 right"].mean(),
                              "Corners 9.5 %": 100 * g["pOverCorners right"].mean(), "Cards 4.5 %": 100 * g["pOverCards right"].mean(),
                              "Over 2.5 naive %": 100 * g["pOver25 naive"].mean(), "Corners naive %": 100 * g["pOverCorners naive"].mean(),
                              "Cards naive %": 100 * g["pOverCards naive"].mean()})
        bt_comp = bt_scored.groupby("Competition").apply(by_comp).sort_values("Gap to bookie", ascending=False).round(3)
        print("\nBy competition, weakest first:")
        display(bt_comp)

        # ---------- v36: the league gate (applied in section 4 from the next run) ----------
        # Each new league's replay of this season against a naive guess (its usual home / draw / away split in earlier seasons) and,
        # where odds exist, the bookmakers. It passes with 60+ replayed matches, beating the naive guess by 0.01 or more and coming
        # within 0.03 of the bookmakers (the five leagues without odds: the naive test only). Checked every run; a league can drop out.
        gate_rows = []
        for lg_ in sorted(NEW_LEAGUES_V36 if "NEW_LEAGUES_V36" in globals() else []):
            g_ = bt_scored[bt_scored["Competition"] == lg_]
            info_ = SOLO.get(lg_)
            if info_ is None:
                continue
            past_ = info_["data"][info_["data"]["Season"] != info_["season"]]
            if len(g_) and len(past_) >= 100:
                freq_ = np.bincount(outcome(past_), minlength=3) / len(past_)
                naive_ = float(-np.log(np.clip(freq_[outcome(g_)], 1e-9, 1)).mean())
            else:
                naive_ = np.nan
            o_ = g_["Bookie LL"].notna() if len(g_) else pd.Series(dtype=bool)
            model_ = float(g_["Model LL"].mean()) if len(g_) else np.nan
            gap_ = float((g_.loc[o_, "Model LL"] - g_.loc[o_, "Bookie LL"]).mean()) if len(g_) and o_.sum() >= 40 else np.nan
            ok_ = (len(g_) >= 60 and np.isfinite(naive_) and model_ <= naive_ - 0.01
                   and (lg_ in CHANCES_ONLY or (np.isfinite(gap_) and gap_ <= 0.03)))
            why_ = ("passed" if ok_ else "fewer than 60 replayed matches" if len(g_) < 60 else "no earlier season to compare with" if not np.isfinite(naive_)
                    else "not clearly better than the naive guess" if model_ > naive_ - 0.01 else "too few matches with odds" if not np.isfinite(gap_)
                    else "too far behind the bookmakers")
            fin_ = lambda x: float(x) if np.isfinite(x) else None
            LEAGUE_GATE[lg_] = {"pass": bool(ok_), "matches": int(len(g_)), "model": fin_(model_), "naive": fin_(naive_), "gap": fin_(gap_), "why": why_,
                                "checked": TODAY.strftime("%Y-%m-%d")}
            gate_rows.append({"League": lg_, "Matches": len(g_), "Model log loss": model_, "Naive log loss": naive_, "Gap to bookie": gap_, "Verdict": why_})
        if gate_rows:
            json.dump(LEAGUE_GATE, open(GATE_PATH, "w"))
            print("\nLeague gate for the v36 leagues (decisions apply from the next run):")
            display(pd.DataFrame(gate_rows).set_index("League").round(3))
            EXTRA_TABLES_EARLY = list(globals().get("EXTRA_TABLES_EARLY", [])) + [{"title": "League gate (new leagues)", "hint": "Each new league's replay of this "
                                 "season: published once it beats a naive guess by 0.01 and comes within 0.03 of the bookmakers (log loss, lower is better), with 60+ matches.",
                                 "rows": json.loads(pd.DataFrame(gate_rows).to_json(orient="records"))}]
else:
    bt_scored, bt_table, bt_comp = None, None, None
    print("Backtest switched off in Settings (RUN_BACKTEST = False).")
