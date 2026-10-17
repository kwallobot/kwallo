# ===================== 4b. EUROPEAN MODEL CHECK: test the candidate settings, keep the winner =====================
# Replays every European match with bookmaker odds since July 2025, one week at a time, for each candidate setting.
# A candidate replaces the current setting only if it beats it in at least 95% of reshuffles. Results are cached in Drive.
if RUN_EURO_SELECTION and len(euro) and EURO_MODEL == "auto":
    since = pd.Timestamp(f"20{SEASONS[-2][:2]}-07-01")
    this_week = TODAY - pd.Timedelta(days=TODAY.weekday())
    targets = euro[(euro["Date"] >= since) & (euro["Date"] < this_week)].dropna(subset=ODDS)
    week_of = lambda d: d - pd.to_timedelta(d.dt.weekday, unit="D")
    euro_sel_results = {}
    for name in EURO_PRESETS:
        path = f"{SAVE_DIR}/europe_walk_{name}_v2.csv"   # v2: clubs from other countries rated with their domestic leagues
        prev = pd.read_csv(path, parse_dates=["Date"]) if os.path.exists(path) else pd.DataFrame(columns=["Competition", "Date", "Home", "Away"])
        done_weeks = set(week_of(prev["Date"]).dt.normalize()) if len(prev) else set()
        weeks = sorted(set(week_of(targets["Date"]).dt.normalize()) - done_weeks)
        if weeks:
            print(f"Replaying European matches with the '{name}' setting: {len(weeks)} weeks to do (a few minutes per setting the first time)...")
        parts = []
        for w in weeks:
            games = targets[(targets["Date"] >= w) & (targets["Date"] < w + pd.Timedelta(days=7))]
            t = predict_europe(domestic_x[domestic_x["Date"] < w], euro[euro["Date"] < w], games, quiet=True, preset=name, temperature=1.0)
            parts.append(t[["Competition", "Date", "Home", "Away", "pH", "pD", "pA"]])
        allp = pd.concat([prev] + parts, ignore_index=True) if parts else prev
        allp["Date"] = pd.to_datetime(allp["Date"])
        allp = allp.drop_duplicates(["Competition", "Date", "Home", "Away"], keep="last")
        allp.to_csv(path, index=False)
        euro_sel_results[name] = allp

    ekey = ["Competition", "Date", "Home", "Away"]
    euro_truth = targets.rename(columns={"HomeTeam": "Home", "AwayTeam": "Away"})[ekey + ["FTHG", "FTAG", "Season"] + ODDS]
    euro_common = euro_truth
    for name, r in euro_sel_results.items():
        euro_common = euro_common.merge(r[ekey], on=ekey)
    o = outcome(euro_common)
    euro_book = -np.log(book_probs(euro_common)[np.arange(len(euro_common)), o])
    def ll_of(name, temperature=1.0, rows=None):
        r = euro_common[ekey].merge(euro_sel_results[name], on=ekey, how="left")
        p = calibrate(r[["pH", "pD", "pA"]].values, temperature)
        l_ = -np.log(np.clip(p[np.arange(len(r)), o], 1e-9, 1))
        return l_ if rows is None else l_[rows]
    rng_e = np.random.default_rng(0)
    share = lambda d_: 100 * (np.array([rng_e.choice(d_, len(d_)).mean() for _ in range(2000)]) < 0).mean()
    base_ll = ll_of("base")
    euro_rows = []
    for name in EURO_PRESETS:
        l_ = ll_of(name)
        euro_rows.append({"Setting": name, "Log loss": l_.mean(), "Gap to bookie": (l_ - euro_book).mean(),
                      "Beats current in % of reshuffles": np.nan if name == "base" else share(l_ - base_ll)})
    euro_sel_table = pd.DataFrame(euro_rows).set_index("Setting")
    print(f"\nEuropean model settings, replayed on {len(euro_common)} European matches with odds (July 2025 onwards):")
    display(euro_sel_table.round(4))
    euro_winners = euro_sel_table[(euro_sel_table.index != "base") & (euro_sel_table["Beats current in % of reshuffles"] >= 95)]
    euro_choice = euro_winners["Log loss"].idxmin() if len(euro_winners) else "base"

    # calibration: learn on last season, check on this season
    last_season, this_season = (euro_common["Season"] == SEASONS[-2]).values, (euro_common["Season"] == SEASONS[-1]).values
    temps = np.round(np.arange(0.6, 1.61, 0.05), 2)
    temperature = 1.0
    if last_season.sum() >= 100 and this_season.sum() >= 30:
        best_t = temps[np.argmin([ll_of(euro_choice, t, last_season).mean() for t in temps])]
        gain = ll_of(euro_choice, best_t, this_season) - ll_of(euro_choice, 1.0, this_season)
        pct = share(gain)
        print(f"Calibration learned on last season: {best_t:.2f} ({'more' if best_t > 1 else 'less'} cautious). "
              f"On this season it changes log loss by {gain.mean():+.4f}, better in {pct:.0f}% of reshuffles.")
        if pct >= 90 and best_t != 1.0:
            temperature = float(best_t)
    EURO_CHOSEN = {"preset": euro_choice, "temperature": temperature, "decided": TODAY.strftime("%Y-%m-%d")}
    json.dump(EURO_CHOSEN, open(_ecfg_path, "w"))
    print(f"\nEuropean model from now on: '{euro_choice}' settings, calibration {temperature:.2f}.")
else:
    print(f"European model: '{EURO_CHOSEN['preset']}' settings (selection check skipped).")
