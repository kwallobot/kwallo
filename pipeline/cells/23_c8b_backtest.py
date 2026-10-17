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

def weeks_of(df):
    w = week_start(df["Date"])
    return sorted(pd.Timestamp(d) for d in w.unique() if last_done <= pd.Timestamp(d) < this_week + pd.Timedelta(days=7))

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
        for w in weeks_of(test):
            games = test[(test["Date"] >= w) & (test["Date"] < w + pd.Timedelta(days=7))].copy()
            t = predict_league(src[src["Date"] < w], games, half_life=info["half_life"], totals=False, quiet=True, adjust=bt_adjust_for(info["group"]))
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
else:
    bt_scored, bt_table, bt_comp = None, None, None
    print("Backtest switched off in Settings (RUN_BACKTEST = False).")
