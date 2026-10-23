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

    # ---------- v37c: the two seasons before this one, for the new leagues (for the league gate) ----------
    # Replayed week by week like this season (only results from before each week), once per league and season, and kept, so later
    # runs skip them. The full run only; a run that hits the time limit continues the next week. No player adjustment here: the
    # lineup data for these leagues starts this season, so the older replays are, if anything, a little harsh on the model.
    PAST_REPLAY_MINUTES = 40
    BT_PAST_PATH = f"{SAVE_DIR}/backtest_past_v36leagues.csv"
    past_bt = pd.read_csv(BT_PAST_PATH) if os.path.exists(BT_PAST_PATH) else pd.DataFrame(columns=["Competition", "ReplaySeason"])
    past_done = set(zip(past_bt["Competition"], past_bt["ReplaySeason"].astype(str))) if len(past_bt) else set()
    t_past, past_new = time.time(), []
    for lg_ in sorted(NEW_LEAGUES_V36 if "NEW_LEAGUES_V36" in globals() else []):
        info_ = SOLO.get(lg_)
        if info_ is None or PAST_REPLAY_MINUTES <= 0:
            continue
        src_ = info_["data"]
        seasons_ = sorted(s for s in src_["Season"].astype(str).unique() if s < str(info_["season"]))[-2:]
        for s_ in seasons_:
            if (lg_, s_) in past_done:
                continue
            if time.time() - t_past > PAST_REPLAY_MINUTES * 60:
                break
            test_ = src_[src_["Season"].astype(str) == s_]
            rows_ = []
            for w in sorted(pd.Timestamp(d) for d in week_start(test_["Date"]).unique()):
                hist_ = src_[src_["Date"] < w]
                if len(hist_) < 200:                                     # too little earlier data for a fair prediction
                    continue
                games = test_[(test_["Date"] >= w) & (test_["Date"] < w + pd.Timedelta(days=7))].copy()
                t = predict_league(hist_, games, half_life=info_["half_life"], totals=info_.get("totals", False), quiet=True, adjust=no_adjust)
                if t is not None:
                    rows_.append(t.assign(Group=info_["group"], Week=w.strftime("%Y-%m-%d"), ReplaySeason=s_))
            if rows_:
                past_new += rows_
            else:                                                        # nothing replayable (no earlier data): don't try again
                past_new.append(pd.DataFrame({"Competition": [lg_], "ReplaySeason": [s_]}))
            print(f"  past-season replay: {lg_} {s_}, {sum(len(r) for r in rows_)} matches")
    if past_new:
        past_bt = pd.concat([past_bt] + past_new, ignore_index=True)
        past_bt.to_csv(BT_PAST_PATH, index=False)

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
        # v37c: each new league's replay of this season AND the two before it (about 1,000 matches instead of 50-200, so luck matters
        # far less). Where the league has bookmaker odds (40+ replayed matches with them), it passes by coming within 0.03 of the
        # bookmakers: the harder test, and a fair one in very even leagues, where a naive guess can look good by luck. The five leagues
        # without odds take the naive test (beat their usual home / draw / away split by 0.01). 60+ matches either way. Checked every
        # run; a league can drop out.
        past_scored = scorecard(past_bt.dropna(subset=["pH"]))[0] if len(past_bt) and "pH" in past_bt and past_bt["pH"].notna().any() else pd.DataFrame()
        gate_rows = []
        for lg_ in sorted(NEW_LEAGUES_V36 if "NEW_LEAGUES_V36" in globals() else []):
            info_ = SOLO.get(lg_)
            if info_ is None:
                continue
            cur_ = bt_scored[bt_scored["Competition"] == lg_].assign(ReplaySeason=str(info_["season"]))
            old_ = past_scored[past_scored["Competition"] == lg_] if len(past_scored) else pd.DataFrame()
            g_ = pd.concat([cur_, old_], ignore_index=True) if len(old_) else cur_
            # naive guess for each match: the league's home / draw / away split in the seasons before that match's season
            nv_ = pd.Series(np.nan, index=g_.index)
            data_ = info_["data"]
            for s_, gs_ in (g_.groupby(g_["ReplaySeason"].astype(str)) if len(g_) else []):
                before_ = data_[data_["Season"].astype(str) < s_]
                if len(before_) >= 100:
                    freq_ = np.bincount(outcome(before_), minlength=3) / len(before_)
                    nv_.loc[gs_.index] = -np.log(np.clip(freq_[outcome(gs_)], 1e-9, 1))
            okn_ = nv_.notna()
            naive_ = float(nv_[okn_].mean()) if okn_.any() else np.nan
            model_n_ = float(g_.loc[okn_, "Model LL"].mean()) if okn_.any() else np.nan     # the model on the same matches
            o_ = g_["Bookie LL"].notna() if len(g_) else pd.Series(dtype=bool)
            model_ = float(g_["Model LL"].mean()) if len(g_) else np.nan
            gap_ = float((g_.loc[o_, "Model LL"] - g_.loc[o_, "Bookie LL"]).mean()) if len(g_) and o_.sum() >= 40 else np.nan
            by_book_ = lg_ not in CHANCES_ONLY and np.isfinite(gap_)
            if len(g_) < 60:
                ok_, why_ = False, "fewer than 60 replayed matches"
            elif by_book_:
                ok_ = gap_ <= 0.03
                why_ = "passed" if ok_ else "too far behind the bookmakers"
            elif not np.isfinite(naive_):
                ok_, why_ = False, "no earlier season to compare with"
            else:
                ok_ = model_n_ <= naive_ - 0.01
                why_ = "passed" if ok_ else "not clearly better than the naive guess"
            fin_ = lambda x: float(x) if np.isfinite(x) else None
            LEAGUE_GATE[lg_] = {"pass": bool(ok_), "matches": int(len(g_)), "this_season": int(len(cur_)), "model": fin_(model_), "naive": fin_(naive_),
                                "gap": fin_(gap_), "test": "bookmakers" if by_book_ else "naive", "why": why_, "checked": TODAY.strftime("%Y-%m-%d")}
            gate_rows.append({"League": lg_, "Matches": len(g_), "This season": len(cur_), "Model log loss": model_, "Naive log loss": naive_,
                              "Gap to bookie": gap_, "Verdict": why_})
        if gate_rows:
            json.dump(LEAGUE_GATE, open(GATE_PATH, "w"))
            print("\nLeague gate for the v36 leagues: this season and the two before (decisions apply from the next run):")
            display(pd.DataFrame(gate_rows).set_index("League").round(3))
            EXTRA_TABLES_EARLY = list(globals().get("EXTRA_TABLES_EARLY", [])) + [{"title": "League gate (new leagues)", "hint": "Each new league's replay of this "
                                 "season and the two before it: published once it comes within 0.03 of the bookmakers (leagues without odds: beats a naive guess by "
                                 "0.01), with 60+ matches (log loss, lower is better). Until then its matches show without Kwallo's chances.",
                                 "rows": json.loads(pd.DataFrame(gate_rows).to_json(orient="records"))}]
else:
    bt_scored, bt_table, bt_comp = None, None, None
    print("Backtest switched off in Settings (RUN_BACKTEST = False).")
