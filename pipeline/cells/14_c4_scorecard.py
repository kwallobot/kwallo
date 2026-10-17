# ===================== 3. SCORECARD: how did past predictions do? =====================
LOG_PATH = f"{SAVE_DIR}/prediction_log.csv"

# "Always guess the usual side" baseline for over/under, from each league's earlier seasons
_hist = all_matches[all_matches["Season"] != SEASONS[-1]]
NAIVE_OVER = {
    "pOver25": (_hist["FTHG"] + _hist["FTAG"] > 2.5).groupby(_hist["League"]).mean().to_dict(),
    "pOverCorners": (_hist["HC"] + _hist["AC"] > 9.5).groupby(_hist["League"]).mean().to_dict(),
    "pOverCards": (_hist["HY"] + _hist["AY"] > 4.5).groupby(_hist["League"]).mean().to_dict(),
}

def results_table():
    d = all_matches.assign(Competition=all_matches["League"], TotalCorners=all_matches["HC"] + all_matches["AC"],
                           TotalCards=all_matches["HY"] + all_matches["AY"])
    m = pd.concat([info["data"].assign(Competition=lg_name) for lg_name, info in SOLO.items()], ignore_index=True)
    m = m.assign(TotalCorners=np.nan, TotalCards=np.nan)
    for c in ODDS:
        if c not in m:
            m[c] = np.nan
    e = euro.assign(TotalCorners=np.nan, TotalCards=np.nan)
    for c in ODDS:
        if c not in e:
            e[c] = np.nan
    cols = ["Competition", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "TotalCorners", "TotalCards"] + ODDS
    r = pd.concat([d[cols], m[cols], e[cols]], ignore_index=True)
    return r.rename(columns={"HomeTeam": "Home", "AwayTeam": "Away", "Date": "ResultDate"})

def scorecard(log):
    log = log.copy()
    log["Date"] = pd.to_datetime(log["Date"])
    res = results_table()
    s = log.merge(res, on=["Competition", "Home", "Away"], how="inner")
    s = s[(s["ResultDate"] - s["Date"]).abs() <= pd.Timedelta(days=3)]
    s = s.drop_duplicates(subset=["Competition", "Date", "Home", "Away"])
    if s.empty:
        return s, None
    p = s[["pH", "pD", "pA"]].values
    o = outcome(s)
    s["Model LL"] = -np.log(p[np.arange(len(s)), o])
    s["Blend LL"] = np.nan
    if "pBH" in s:
        pb = s[["pBH", "pBD", "pBA"]].values
        okb = np.isfinite(pb).all(axis=1)
        s.loc[okb, "Blend LL"] = -np.log(pb[okb][np.arange(okb.sum()), o[okb]])
    s["Top pick right"] = p.argmax(axis=1) == o
    has_odds = s[ODDS].notna().all(axis=1).values
    s["Bookie LL"] = np.nan
    if has_odds.any():
        bp = book_probs(s[has_odds])
        s.loc[has_odds, "Bookie LL"] = -np.log(bp[np.arange(len(bp)), o[has_odds]])
    for col, actual, line in [("pOver25", s["FTHG"] + s["FTAG"], 2.5), ("pOverCorners", s["TotalCorners"], 9.5),
                              ("pOverCards", s["TotalCards"], 4.5)]:
        if col not in s:
            s[col] = np.nan
        ok = s[col].notna() & actual.notna()
        s[col + " right"] = np.where(ok, (s[col] > 0.5) == (actual > line), np.nan)
        naive_over = s["Competition"].map(NAIVE_OVER[col]) > 0.5
        s[col + " naive"] = np.where(ok, naive_over == (actual > line), np.nan)
    s["Week of"] = (s["Date"] - pd.to_timedelta(s["Date"].dt.weekday, unit="D")).dt.date

    def summarise(g):
        o_ = g["Bookie LL"].notna()
        return pd.Series({
            "Matches": len(g),
            "Model log loss": g["Model LL"].mean(),
            "Blend log loss": g["Blend LL"].mean() if g["Blend LL"].notna().any() else np.nan,
            "Bookie log loss": g.loc[o_, "Bookie LL"].mean() if o_.any() else np.nan,
            "Gap to bookie": (g.loc[o_, "Model LL"] - g.loc[o_, "Bookie LL"]).mean() if o_.any() else np.nan,
            "Top pick %": 100 * g["Top pick right"].mean(),
            "Over 2.5 %": 100 * g["pOver25 right"].mean(),
            "Corners 9.5 %": 100 * g["pOverCorners right"].mean(),
            "Cards 4.5 %": 100 * g["pOverCards right"].mean(),
            "Over 2.5 naive %": 100 * g["pOver25 naive"].mean(),
            "Corners naive %": 100 * g["pOverCorners naive"].mean(),
            "Cards naive %": 100 * g["pOverCards naive"].mean(),
        })
    weekly = s.groupby(["Week of", "Group"]).apply(summarise)
    total = s.groupby("Group").apply(summarise)
    total.index = pd.MultiIndex.from_tuples([("ALL WEEKS", g) for g in total.index], names=["Week of", "Group"])
    return s, pd.concat([weekly, total]).round(3)

table, scored = None, None
if os.path.exists(LOG_PATH):
    log = pd.read_csv(LOG_PATH)
    scored, table = scorecard(log)
    if table is None:
        print(f"{len(log)} predictions logged, none played yet. Check back after the next matchday.")
    else:
        print(f"{len(scored)} of {len(log)} logged predictions have results.\n")
        print("Lower log loss is better. 'Gap to bookie' is model minus bookie (on matches with odds).")
        print("'%' columns: how often the model's favoured side / over-under side was right. 'naive %' columns: how often")
        print("simply guessing each league's usual side (over or under) was right. The model only adds value where it beats that.\n")
        display(table)
        table.to_csv(f"{SAVE_DIR}/scorecard.csv")
        last_week = scored["Week of"].max()
        print(f"\nMatch by match, week of {last_week}:")
        detail = scored[scored["Week of"] == last_week].copy()
        detail["Score"] = detail["FTHG"].astype(int).astype(str) + "-" + detail["FTAG"].astype(int).astype(str)
        detail[["Home %", "Draw %", "Away %"]] = (detail[["pH", "pD", "pA"]] * 100).round(0)
        display(detail[["Competition", "Home", "Away", "Score", "Home %", "Draw %", "Away %", "Model LL", "Bookie LL"]]
                .sort_values("Model LL", ascending=False).round(2).reset_index(drop=True))
else:
    print("No prediction log yet. It will be created when you run the prediction cells below.")

analyst_score = {}
AP = f"{SAVE_DIR}/analyst_log.csv"
if os.path.exists(AP) and os.path.exists(LOG_PATH):
    a = pd.read_csv(AP)
    sc, _ = scorecard(pd.read_csv(LOG_PATH))
    if len(sc):
        sc["Date"] = sc["Date"].dt.strftime("%Y-%m-%d")
        both = sc.merge(a, on=["Competition", "Date", "Home", "Away"])
        if len(both):
            o = outcome(both)
            pa = both[["aH", "aD", "aA"]].values
            a_ll = -np.log(np.clip(pa[np.arange(len(both)), o], 1e-9, 1))
            analyst_score = {"matches": int(len(both)), "model": float(both["Model LL"].mean()), "analyst": float(a_ll.mean()),
                             "book": float(both["Bookie LL"].mean()) if both["Bookie LL"].notna().any() else None}
            print(f"\nAnalyst picks scored: {len(both)} matches. Log loss, model {analyst_score['model']:.3f} vs analyst {analyst_score['analyst']:.3f}"
                  + (f" (bookmakers {analyst_score['book']:.3f})" if analyst_score['book'] is not None else "") + ". Lower is better.")

DASH["table"], DASH["scored"] = table, scored
