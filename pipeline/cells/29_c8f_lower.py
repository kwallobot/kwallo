# ===================== 9b. LOWER LEAGUES: is there an edge where markets are thinner? =====================
# A backtest only: the model is replayed week by week on second-tier (and English third and fourth tier) leagues,
# using football-data.co.uk's results and odds, then checked with the same tools as the main leagues:
# accuracy vs the market, the model's share in a blend, and value bets with closing-line value.
# A league is CONFIRMED only if its closing-line value is positive in the earlier half AND confirmed in the later half.
LOWER = {"E1": "Championship", "E2": "League One", "E3": "League Two", "SP2": "Segunda Division", "D2": "2. Bundesliga",
         "I2": "Serie B", "F2": "Ligue 2", "SC1": "Scottish Championship", "SC2": "Scottish League One", "SC3": "Scottish League Two"}
RUN_LOWER_LEAGUE_TEST = True
lower_rows, lower_confirmed = [], []
if RUN_LOWER_LEAGUE_TEST:
    frames_ = []
    for code_, name_ in LOWER.items():
        for season_ in SEASONS:
            try:
                df_ = pd.read_csv(f"{DATA_URL}/mmz4281/{season_}/{code_}.csv", encoding="latin-1", on_bad_lines="skip")
            except Exception:
                continue
            df_ = clean_cols(df_).reindex(columns=KEEP)
            df_["League"], df_["Season"] = name_, season_
            frames_.append(df_)
    low = pd.concat(frames_, ignore_index=True).dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"]) if frames_ else pd.DataFrame()
    if len(low):
        low["Date"] = pd.to_datetime(low["Date"], dayfirst=True, format="mixed")
        for c_ in ODDS + PRICE_COLS:
            low[c_] = pd.to_numeric(low[c_], errors="coerce")
        # replay the last two seasons week by week (cached; later runs only add new weeks)
        LP = f"{SAVE_DIR}/lower_league_walk.csv"
        prev_ = pd.read_csv(LP, parse_dates=["Date"]) if os.path.exists(LP) else pd.DataFrame(columns=["League", "Date"])
        start_all = pd.Timestamp(f"20{SEASONS[-2][:2]}-08-01")
        new_ = []
        for name_ in LOWER.values():
            lg_ = low[low["League"] == name_].sort_values("Date")
            if lg_.empty:
                continue
            done_to = prev_.loc[prev_["League"] == name_, "Date"].max() if len(prev_) else pd.NaT
            st_ = (done_to + pd.Timedelta(days=1)) if pd.notna(done_to) else start_all
            st_ = st_ - pd.Timedelta(days=st_.weekday())
            new_ += base_walk(lg_, st_, 365, end=TODAY - pd.Timedelta(days=TODAY.weekday()))
        if new_:
            print(f"Lower leagues: replayed {sum(len(x) for x in new_)} new matches.")
        walk = pd.concat([prev_] + new_, ignore_index=True).drop_duplicates(["League", "Date", "HomeTeam", "AwayTeam"], keep="last") if new_ else prev_
        walk["Date"] = pd.to_datetime(walk["Date"])
        walk.to_csv(LP, index=False)
        # prices: best before kickoff (best > average > Bet365); closing benchmark (Pinnacle > average closing > Bet365 closing)
        lw = walk.drop(columns=[c_ for c_ in ODDS if c_ in walk]).merge(low[["League", "Date", "HomeTeam", "AwayTeam"] + ODDS + PRICE_COLS],
                                                                        on=["League", "Date", "HomeTeam", "AwayTeam"], how="inner")
        def chain(df_, options):
            out_ = np.full((len(df_), 3), np.nan)
            for cols3 in options:
                if all(c_ in df_ for c_ in cols3):
                    v_ = df_[list(cols3)].values.astype(float)
                    fill = np.isnan(out_).any(axis=1) & np.isfinite(v_).all(axis=1)
                    out_[fill] = v_[fill]
            return out_
        early_ = chain(lw, [ODDS, ("AvgH", "AvgD", "AvgA")])
        best_ = chain(lw, [("MaxH", "MaxD", "MaxA"), ("AvgH", "AvgD", "AvgA"), ODDS])
        close_ = chain(lw, [("PSCH", "PSCD", "PSCA"), ("AvgCH", "AvgCD", "AvgCA"), ("B365CH", "B365CD", "B365CA")])
        ok_ = np.isfinite(early_).all(axis=1) & np.isfinite(best_).all(axis=1) & np.isfinite(close_).all(axis=1)
        lw, early_, best_, close_ = lw[ok_].reset_index(drop=True), early_[ok_], best_[ok_], close_[ok_]
        if len(lw) >= 200:
            P_ = np.zeros((len(lw), 3))
            for r_v in np.unique(lw["rho"].values):
                i_ = np.where(lw["rho"].values == r_v)[0]
                P_[i_] = outcome_probs(lw["ExpHome"].values[i_], lw["ExpAway"].values[i_], r_v)
            fair = lambda x: (1 / x) / (1 / x).sum(axis=1, keepdims=True)
            E_, C_ = fair(early_), fair(close_)
            o_ = outcome(lw)
            idx_ = np.arange(len(lw))
            ll_ = lambda p: -np.log(np.clip(p[idx_, o_], 1e-9, 1))
            ev_ = P_ * best_ - 1
            ev_[best_ > MAX_PRICE] = -1
            k_ = ev_.argmax(axis=1)
            lw["EV"], lw["Price"] = ev_[idx_, k_], best_[idx_, k_]
            lw["CLV"] = best_[idx_, k_] * C_[idx_, k_] - 1
            lw["Profit"] = np.where(o_ == k_, lw["Price"] - 1, -1.0)
            lw["llM"], lw["llE"], lw["llC"] = ll_(P_), ll_(E_), ll_(C_)
            mid_ = lw["Date"].quantile(0.5)
            rng_l = np.random.default_rng(4)
            def blend_share(rows):
                ws = np.round(np.arange(0, 1.01, 0.05), 2)
                return ws[int(np.argmin([-np.log(np.clip((w * P_[rows] + (1 - w) * E_[rows])[np.arange(rows.sum()), o_[rows]], 1e-9, 1)).mean() for w in ws]))]
            def summarise(name_, sel):
                g_ = lw[sel]
                bets = g_[(g_["EV"] >= EV_MIN) & (g_["EV"] <= MAX_PLAUSIBLE_EV)]
                d1, d2 = bets[bets["Date"] < mid_], bets[bets["Date"] >= mid_]
                verdict = "too few bets"
                if len(d1) >= 25 and len(d2) >= 25:
                    if d1["CLV"].mean() > 0 and d2["CLV"].mean() > 0:
                        pct_ = 100 * (np.array([rng_l.choice(d2["CLV"].values, len(d2)).mean() for _ in range(2000)]) > 0).mean()
                        verdict = "CONFIRMED" if pct_ >= 95 else "promising, not confirmed"
                    else:
                        verdict = "no edge"
                return {"League": name_, "Matches": len(g_), "Model log loss": g_["llM"].mean(), "Early odds": g_["llE"].mean(), "Closing odds": g_["llC"].mean(),
                        "Model share in blend": float(blend_share(sel.values & (lw["Date"] >= mid_).values)) if (sel & (lw["Date"] >= mid_)).sum() >= 50 else np.nan,
                        "Value bets": len(bets), "CLV % (earlier)": 100 * d1["CLV"].mean() if len(d1) else np.nan, "CLV % (later)": 100 * d2["CLV"].mean() if len(d2) else np.nan,
                        "ROI % (earlier)": 100 * d1["Profit"].mean() if len(d1) else np.nan, "ROI % (later)": 100 * d2["Profit"].mean() if len(d2) else np.nan, "Verdict": verdict}
            rows_ = [summarise(n_, lw["League"] == n_) for n_ in LOWER.values() if (lw["League"] == n_).sum() >= 50]
            rows_.append(summarise("All lower leagues", lw["League"].notna()))
            lower_rows = json.loads(pd.DataFrame(rows_).to_json(orient="records"))
            lower_confirmed = [r_["League"] for r_ in lower_rows if r_["Verdict"] == "CONFIRMED" and r_["League"] != "All lower leagues"]
            json.dump(lower_confirmed, open(f"{SAVE_DIR}/lower_confirmed.json", "w"))
            print(f"\nLower-league test: {len(lw)} replayed matches with odds (last two seasons). Lower log loss is better; "
                  "'Model share in blend' is learned on the later half (0 = the market alone is best).")
            display(pd.DataFrame(rows_).set_index("League").round(3))
            print("Confirmed edges in lower leagues: " + (", ".join(lower_confirmed) if lower_confirmed else "none.")
                  + " A confirmed league would be a candidate to add to live predictions and the paper ledger.")
            EXTRA_TABLES.append({"title": "Lower-league edge test", "hint": "The model replayed on second-tier and lower English leagues, with value bets checked against "
                                 "closing prices (earlier half, then confirmed on the later half). Only CONFIRMED counts; the model's share in a blend shows how much it adds to the market.",
                                 "rows": [{k_: v_ for k_, v_ in r_.items() if k_ in ("League", "Matches", "Model log loss", "Closing odds", "Model share in blend",
                                                                                      "Value bets", "CLV % (earlier)", "CLV % (later)", "Verdict")} for r_ in lower_rows]})
        else:
            print(f"Lower-league test: only {len(lw)} replayed matches with full odds so far.")
    health("Lower-league test", True, ("confirmed: " + ", ".join(lower_confirmed)) if lower_confirmed else "no confirmed edge")
