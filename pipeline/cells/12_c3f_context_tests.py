# ===================== 2f. CONTEXT TESTS: weather, derbies, referees, team home advantage, motivation =====================
# Each factor is learned on matches BEFORE this season and tested on this season's matches (honest week-by-week
# predictions), and is switched on only if it helps in at least 95% of reshuffles. Decisions are saved to Drive.
CTX2_PATH = f"{SAVE_DIR}/context2.json"
CTX2 = json.load(open(CTX2_PATH)) if os.path.exists(CTX2_PATH) else {}
ctx2_report = []

def league_avg_cards(league, before, days=365):
    f_ = league_frame(league)
    f_ = f_[(f_["Date"] < before) & (f_["Date"] >= before - pd.Timedelta(days=days))]
    v_ = (pd.to_numeric(f_.get("HY"), errors="coerce") + pd.to_numeric(f_.get("AY"), errors="coerce")).dropna()
    return float(v_.mean()) if len(v_) >= 30 else np.nan

def referee_dev(ctx_rows, card_hist):
    """log(referee's shrunk yellow cards per match / league average), using only matches before each one."""
    out_ = np.zeros(len(ctx_rows))
    if card_hist.empty:
        return out_
    by_ref = {r_: g_.sort_values("Date") for r_, g_ in card_hist.dropna(subset=["referee_id"]).groupby("referee_id")}
    for i_, (r_, d_, lg_) in enumerate(zip(ctx_rows["referee_id"], ctx_rows["Date"], ctx_rows["League"])):
        if pd.isna(r_) or r_ not in by_ref:
            continue
        h_ = by_ref[r_]
        h_ = h_[h_["Date"] < d_]
        la_ = league_avg_cards(lg_, d_)
        if len(h_) == 0 or not np.isfinite(la_):
            continue
        k_ = 10.0                                              # shrinkage: 10 matches of "league-average referee"
        rate_ = (h_["cards"].sum() + k_ * la_) / (len(h_) + k_)
        out_[i_] = np.log(rate_ / la_)
    return out_

def table_features(df_rows):
    """Late-season stakes from the league table before each match: nothing to play for / relegation fight / title race."""
    feats_ = {k: np.zeros(len(df_rows)) for k in ["h_dead", "h_releg", "h_title", "a_dead", "a_releg", "a_title"]}
    for lg_, idx_ in df_rows.groupby("League").groups.items():
        fr_ = league_frame(lg_).sort_values("Date")
        for i_ in idx_:
            r_ = df_rows.loc[i_]
            seas_ = fr_[(fr_["Season"] == r_.get("Season", league_season(lg_))) & (fr_["Date"] < r_["Date"])] if "Season" in fr_ else fr_
            teams_ = sorted(set(seas_["HomeTeam"]) | set(seas_["AwayTeam"]))
            if len(teams_) < 10 or len(seas_) < 50:
                continue
            pts, played = {t: 0 for t in teams_}, {t: 0 for t in teams_}
            for h, a, gh, ga in zip(seas_["HomeTeam"], seas_["AwayTeam"], seas_["FTHG"], seas_["FTAG"]):
                pts[h] += 3 if gh > ga else (1 if gh == ga else 0); pts[a] += 3 if ga > gh else (1 if gh == ga else 0)
                played[h] += 1; played[a] += 1
            n_ = len(teams_); total_games = 2 * (n_ - 1)
            table_ = sorted(teams_, key=lambda t: -pts[t])
            drop_line = pts[table_[-3]] if n_ >= 18 else pts[table_[-2]]
            top_pts = pts[table_[0]]
            for side_, t_ in [("h", r_["HomeTeam"]), ("a", r_["AwayTeam"])]:
                if t_ not in pts:
                    continue
                left_ = total_games - played[t_]
                if left_ > 8:
                    continue                                   # only late in the season
                p_ = pts[t_]
                releg = p_ - drop_line <= 6
                title = top_pts - p_ <= 6
                dead = (not releg) and (not title) and (p_ - drop_line > 3 * left_) and (top_pts - p_ > 3 * left_)
                feats_[f"{side_}_releg"][df_rows.index.get_loc(i_)] = float(releg)
                feats_[f"{side_}_title"][df_rows.index.get_loc(i_)] = float(title)
                feats_[f"{side_}_dead"][df_rows.index.get_loc(i_)] = float(dead)
    return feats_

def ctx_lookup(games):
    g_ = games[["League", "Date", "HomeTeam", "AwayTeam"]].copy()
    g_["Date"] = pd.to_datetime(g_["Date"]).dt.normalize()
    if not len(CTX_MATCH):
        return g_.assign(derby=False, wind=np.nan, temp=np.nan, wcode=np.nan, referee_id=np.nan)
    c_ = CTX_MATCH.drop_duplicates(["League", "Date", "HomeTeam", "AwayTeam"])
    return g_.merge(c_, on=["League", "Date", "HomeTeam", "AwayTeam"], how="left")

def weather_x(c_):
    wind_ = pd.to_numeric(c_["wind"], errors="coerce")
    temp_ = pd.to_numeric(c_["temp"], errors="coerce")
    code_ = pd.to_numeric(c_["wcode"], errors="coerce")
    return {"windy": (wind_ >= wind_.quantile(0.85) if wind_.notna().sum() > 50 else wind_ > 9e9).fillna(False).astype(float).values,
            "wet": code_.isin(list(range(51, 68)) + list(range(80, 83)) + list(range(95, 100))).astype(float).values,
            "cold_or_hot": ((temp_ < 3) | (temp_ > 28)).fillna(False).astype(float).values}

def team_hfa(rows_before):
    """Each team's home goals-for and goals-against vs the model, shrunk (40 home games = half weight)."""
    out_ = {}
    for t_, g_ in rows_before.groupby("HomeTeam"):
        n_ = len(g_)
        w_ = n_ / (n_ + 40)
        att = np.log(max(g_["FTHG"].sum(), 0.5) / max(g_["ExpHome"].sum(), 0.5))
        dfn = np.log(max(g_["FTAG"].sum(), 0.5) / max(g_["ExpAway"].sum(), 0.5))
        out_[t_] = (float(w_ * att), float(w_ * dfn))
    return out_

if "base" in globals() and len(base) and TEST_GOAL_LEVEL_AND_REST:
    rng_x2 = np.random.default_rng(5)
    share2 = lambda d_: 100 * (np.array([rng_x2.choice(d_, len(d_)).mean() for _ in range(2000)]) < 0).mean()
    bb = base.dropna(subset=["ExpHome", "ExpAway", "rho"]).sort_values("Date").reset_index(drop=True)
    season_start = all_matches.loc[all_matches["Season"] == SEASONS[-1], "Date"].min()
    te_ = (bb["Date"] >= season_start).values
    o_ = outcome(bb)
    def probs_rho3(h, a):
        p = np.zeros((len(bb), 3))
        for r_v in np.unique(bb["rho"].values):
            i_ = np.where(bb["rho"].values == r_v)[0]
            p[i_] = outcome_probs(h[i_], a[i_], r_v)
        return p
    ll0 = -np.log(np.clip(probs_rho3(bb["ExpHome"].values, bb["ExpAway"].values)[np.arange(len(bb)), o_], 1e-9, 1))
    def try_goal_feature(name, xh, xa, labels):
        """Fit goal effects on earlier seasons (Poisson with the model's prediction as offset), test on this season."""
        L_ = pd.concat([pd.DataFrame({"g": bb["FTHG"], "off": np.log(bb["ExpHome"]), **{k: v for k, v in xh.items()}, "D": bb["Date"]}),
                        pd.DataFrame({"g": bb["FTAG"], "off": np.log(bb["ExpAway"]), **{k: v for k, v in xa.items()}, "D": bb["Date"]})], ignore_index=True)
        cols = list(xh.keys())
        tr = L_[L_["D"] < season_start]
        if len(tr) < 500 or tr[cols].abs().sum().min() < 15 or te_.sum() < 100:
            ctx2_report.append({"Factor": name, "Result": "not enough data yet"}); return None
        prm = sm.GLM(tr["g"], tr[cols], family=sm.families.Poisson(), offset=tr["off"]).fit().params
        fh_ = np.exp(sum(prm[c] * xh[c] for c in cols)); fa_ = np.exp(sum(prm[c] * xa[c] for c in cols))
        ll1 = -np.log(np.clip(probs_rho3(bb["ExpHome"].values * fh_, bb["ExpAway"].values * fa_)[np.arange(len(bb)), o_], 1e-9, 1))
        d_ = (ll1 - ll0)[te_]
        pct = share2(d_)
        adopt = bool(pct >= 95 and d_.mean() < 0)
        ctx2_report.append({"Factor": name, "Change in log loss": float(d_.mean()), "Better in % of reshuffles": float(pct), "Result": "ON" if adopt else "off",
                            "Effects": ", ".join(f"{labels.get(c, c)} {100 * (np.exp(prm[c]) - 1):+.1f}%" for c in cols)})
        return {c: float(prm[c]) for c in cols} if adopt else None

    cx = ctx_lookup(bb)
    # derbies: does the home side lose some of its advantage?
    dz = cx["derby"].fillna(False).astype(float).values
    CTX2["derby"] = try_goal_feature("Derbies (goals)", {"derby_home": dz, "derby_away": np.zeros(len(bb))}, {"derby_home": np.zeros(len(bb)), "derby_away": dz},
                                     {"derby_home": "home side's goals", "derby_away": "away side's goals"})
    # weather: wind, rain/snow, extreme temperatures (same effect on both sides)
    wx = weather_x(cx)
    CTX2["weather"] = try_goal_feature("Weather (goals)", wx, wx, {"windy": "windy", "wet": "rain or snow", "cold_or_hot": "very cold or hot"})
    # team-specific home advantage: learned before this season, applied to this season's home matches
    hf = team_hfa(bb[~te_])
    att_ = np.array([hf.get(t_, (0, 0))[0] for t_ in bb["HomeTeam"]]); dfn_ = np.array([hf.get(t_, (0, 0))[1] for t_ in bb["HomeTeam"]])
    ll1 = -np.log(np.clip(probs_rho3(bb["ExpHome"].values * np.exp(att_), bb["ExpAway"].values * np.exp(dfn_))[np.arange(len(bb)), o_], 1e-9, 1))
    d_ = (ll1 - ll0)[te_]
    pct = share2(d_) if te_.sum() >= 100 else 0
    CTX2["team_hfa"] = bool(pct >= 95 and d_.mean() < 0)
    ctx2_report.append({"Factor": "Team-specific home advantage", "Change in log loss": float(d_.mean()) if te_.sum() else np.nan,
                        "Better in % of reshuffles": float(pct), "Result": "ON" if CTX2["team_hfa"] else "off"})
    # motivation: late-season stakes, tested on last season's run-in (earlier half of the run-in vs later half)
    late = bb[(bb["Date"] < season_start) & (bb["Date"] >= season_start - pd.Timedelta(days=150))]
    lab_ = pd.concat([league_frame(l_)[["League", "Date", "HomeTeam", "AwayTeam", "Season"]] for l_ in late["League"].unique()], ignore_index=True)
    late = late.drop(columns=[c_ for c_ in ["Season"] if c_ in late]).merge(lab_, on=["League", "Date", "HomeTeam", "AwayTeam"], how="left")   # v22 fix
    if len(late) >= 300:
        tf = table_features(late.reset_index(drop=True))
        late = late.reset_index(drop=True)
        Lm = pd.concat([pd.DataFrame({"g": late["FTHG"], "off": np.log(late["ExpHome"]), "own_dead": tf["h_dead"], "own_releg": tf["h_releg"], "own_title": tf["h_title"],
                                      "opp_dead": tf["a_dead"], "D": late["Date"]}),
                        pd.DataFrame({"g": late["FTAG"], "off": np.log(late["ExpAway"]), "own_dead": tf["a_dead"], "own_releg": tf["a_releg"], "own_title": tf["a_title"],
                                      "opp_dead": tf["h_dead"], "D": late["Date"]})], ignore_index=True)
        cols_m = ["own_dead", "own_releg", "own_title", "opp_dead"]
        mid_ = Lm["D"].quantile(0.5)
        tr_m, ts_m = Lm[Lm["D"] < mid_], Lm[Lm["D"] >= mid_]
        if tr_m[cols_m].sum().min() >= 10:
            prm = sm.GLM(tr_m["g"], tr_m[cols_m], family=sm.families.Poisson(), offset=tr_m["off"]).fit().params
            from scipy.stats import poisson as _po
            l0 = -_po.logpmf(ts_m["g"], np.exp(ts_m["off"])); l1 = -_po.logpmf(ts_m["g"], np.exp(ts_m["off"] + ts_m[cols_m].values @ prm[cols_m].values))
            pct = share2(np.asarray(l1 - l0))
            CTX2["motivation"] = {c: float(prm[c]) for c in cols_m} if (pct >= 95 and (l1 - l0).mean() < 0) else None
            ctx2_report.append({"Factor": "Motivation (last season's run-in)", "Change in log loss": float((l1 - l0).mean()), "Better in % of reshuffles": float(pct),
                                "Result": "ON (applies in the last 8 games)" if CTX2["motivation"] else "off",
                                "Effects": ", ".join(f"{c.replace('_', ' ')} {100 * (np.exp(prm[c]) - 1):+.1f}%" for c in cols_m)})
        else:
            ctx2_report.append({"Factor": "Motivation", "Result": "not enough run-in matches yet"})
    # referees and derbies on cards: baseline = the league's average yellow cards (time-aware)
    card_hist = pd.DataFrame()
    if len(CTX_MATCH):
        cm_ = CTX_MATCH.merge(all_matches[["League", "Date", "HomeTeam", "AwayTeam", "HY", "AY"]], on=["League", "Date", "HomeTeam", "AwayTeam"], how="inner")
        cm_["cards"] = pd.to_numeric(cm_["HY"], errors="coerce") + pd.to_numeric(cm_["AY"], errors="coerce")
        card_hist = cm_.dropna(subset=["cards"]).sort_values("Date").reset_index(drop=True)
    if len(card_hist) >= 400:
        card_hist["la"] = [league_avg_cards(l_, d_) for l_, d_ in zip(card_hist["League"], card_hist["Date"])]
        card_hist = card_hist.dropna(subset=["la"]).reset_index(drop=True)
        card_hist["ref_dev"] = referee_dev(card_hist, card_hist)
        card_hist["derby_f"] = card_hist["derby"].fillna(False).astype(float)
        mid_ = card_hist["Date"].quantile(0.5)
        tr_c, ts_c = card_hist[card_hist["Date"] < mid_], card_hist[card_hist["Date"] >= mid_]
        prm = sm.GLM(tr_c["cards"], tr_c[["ref_dev", "derby_f"]], family=sm.families.Poisson(), offset=np.log(tr_c["la"])).fit().params
        from scipy.stats import poisson as _po
        l0 = -_po.logpmf(ts_c["cards"], ts_c["la"]); l1 = -_po.logpmf(ts_c["cards"], ts_c["la"] * np.exp(ts_c[["ref_dev", "derby_f"]].values @ prm.values))
        pct = share2(np.asarray(l1 - l0))
        CTX2["cards"] = {"ref_dev": float(prm["ref_dev"]), "derby_f": float(prm["derby_f"])} if (pct >= 95 and (l1 - l0).mean() < 0) else None
        ctx2_report.append({"Factor": "Referees and derbies (cards)", "Change in log loss": float((l1 - l0).mean()), "Better in % of reshuffles": float(pct),
                            "Result": "ON" if CTX2["cards"] else "off", "Effects": f"referee strictness x{np.exp(prm['ref_dev']):.2f} per unit, derby {100 * (np.exp(prm['derby_f']) - 1):+.1f}% cards"})
        REF_HIST = card_hist
    else:
        ctx2_report.append({"Factor": "Referees and derbies (cards)", "Result": f"not enough matched matches with referees yet ({len(card_hist)})"})
    CTX2["team_hfa_values"] = {k: list(v) for k, v in team_hfa(bb).items()} if CTX2.get("team_hfa") else {}
    json.dump(CTX2, open(CTX2_PATH, "w"))
    print("Context tests (learned before this season, tested on this season; 95% rule):")
    display(pd.DataFrame(ctx2_report).round(4))

def ctx2_multipliers(games):
    """Goal multipliers from the context factors that passed their tests."""
    n_ = len(games)
    fh, fa = np.ones(n_), np.ones(n_)
    if not n_ or not any(CTX2.get(k) for k in ["derby", "weather", "team_hfa", "motivation"]):
        return fh, fa
    cx_ = ctx_lookup(games)
    if CTX2.get("derby"):
        dz_ = cx_["derby"].fillna(False).astype(float).values
        fh *= np.exp(CTX2["derby"]["derby_home"] * dz_); fa *= np.exp(CTX2["derby"]["derby_away"] * dz_)
    if CTX2.get("weather"):
        wx_ = weather_x(cx_)
        f_ = np.exp(sum(CTX2["weather"][k] * wx_[k] for k in CTX2["weather"]))
        fh *= f_; fa *= f_
    if CTX2.get("team_hfa") and CTX2.get("team_hfa_values"):
        tv = CTX2["team_hfa_values"]
        fh *= np.exp([tv.get(t_, [0, 0])[0] for t_ in games["HomeTeam"]]); fa *= np.exp([tv.get(t_, [0, 0])[1] for t_ in games["HomeTeam"]])
    if CTX2.get("motivation"):
        tf_ = table_features(games.reset_index(drop=True).assign(Date=pd.to_datetime(games["Date"].values)))
        m_ = CTX2["motivation"]
        fh *= np.exp(m_["own_dead"] * tf_["h_dead"] + m_["own_releg"] * tf_["h_releg"] + m_["own_title"] * tf_["h_title"] + m_["opp_dead"] * tf_["a_dead"])
        fa *= np.exp(m_["own_dead"] * tf_["a_dead"] + m_["own_releg"] * tf_["a_releg"] + m_["own_title"] * tf_["a_title"] + m_["opp_dead"] * tf_["h_dead"])
    return fh, fa

def cards_multipliers(games):
    """Card multipliers for appointed referees and derbies, if that test passed. Also says whether the referee is known."""
    n_ = len(games)
    if not n_ or not CTX2.get("cards") or "REF_HIST" not in globals():
        return np.ones(n_)
    cx_ = ctx_lookup(games)
    cx_["League"] = games["League"].values
    dev_ = referee_dev(cx_, REF_HIST)
    return np.exp(CTX2["cards"]["ref_dev"] * dev_ + CTX2["cards"]["derby_f"] * cx_["derby"].fillna(False).astype(float).values)
health("Context factors", True, ", ".join(f"{k} {'on' if CTX2.get(k) else 'off'}" for k in ["derby", "weather", "team_hfa", "motivation", "cards"]))
