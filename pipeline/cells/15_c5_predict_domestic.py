# ===================== 4. PREDICT: domestic leagues, MLS and the Saudi Pro League =====================
FIXTURE_WARNINGS = []
def get_fixtures():
    parts = []
    try:
        f = clean_cols(pd.read_csv(f"{DATA_URL}/fixtures.csv", encoding="latin-1"))
        div_names_ = {**LEAGUES, **({c_: n_ for c_, n_ in LOWER_PREDICTED.items() if n_ in SOLO} if "LOWER_PREDICTED" in globals() else {})}   # v36: second tiers
        f = f[f["Div"].isin(div_names_.keys())].copy()
        f["League"] = f["Div"].map(div_names_)
        parts.append(f.reindex(columns=["League", "Date", "HomeTeam", "AwayTeam"] + ODDS).assign(src=3))
    except Exception as e:
        print("Could not load fixtures.csv:", e)
    try:
        nf = clean_cols(pd.read_csv(f"{DATA_URL}/new_league_fixtures.csv", encoding="latin-1"))
        country_ = {"USA": "MLS", **{c_: n_ for c_, n_ in (FD_COUNTRY_LEAGUE.items() if "FD_COUNTRY_LEAGUE" in globals() else []) if n_ in SOLO}}   # v36
        nf["League"] = nf["Country"].astype(str).str.strip().map(country_)
        nf = nf[nf["League"].notna()].rename(columns={"Home": "HomeTeam", "Away": "AwayTeam", "AvgH": "B365H", "AvgD": "B365D", "AvgA": "B365A"})
        parts.append(nf.reindex(columns=["League", "Date", "HomeTeam", "AwayTeam"] + ODDS).assign(src=3))
    except Exception:
        pass
    if "EXTRA_FIXTURES" in globals() and len(EXTRA_FIXTURES):                 # v29: fixtures from PitchAPI (Egypt)
        parts.append(EXTRA_FIXTURES.reindex(columns=["League", "Date", "HomeTeam", "AwayTeam"] + ODDS).assign(src=2))
    if MANUAL_FIXTURES:
        parts.append(pd.DataFrame(MANUAL_FIXTURES, columns=["League", "Date", "HomeTeam", "AwayTeam"]).reindex(
            columns=["League", "Date", "HomeTeam", "AwayTeam"] + ODDS).assign(src=2))
    cols = ["League", "Date", "HomeTeam", "AwayTeam"] + ODDS + ["src"]
    fx = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=cols)
    fx["Date"] = pd.to_datetime(fx["Date"], dayfirst=True, format="mixed")
    for c in ODDS:
        fx[c] = pd.to_numeric(fx[c], errors="coerce")
    fx = fx[(fx["Date"] >= TODAY) & (fx["Date"] < TODAY + pd.Timedelta(days=PREDICT_DAYS))]
    fx = fx.drop_duplicates(subset=["League", "HomeTeam", "AwayTeam"])
    if len(espn_fx):
        key = ["League", "HomeTeam", "AwayTeam"]
        e = espn_fx.rename(columns={"Date": "Date_es", "EspnH": "B365H_es", "EspnD": "B365D_es", "EspnA": "B365A_es"})
        fx = fx.merge(e[key + ["Date_es", "event_id", "home_id", "away_id", "B365H_es", "B365D_es", "B365A_es"]], on=key, how="outer")
        fx["Date"] = fx["Date"].fillna(fx["Date_es"])
        for c in ODDS:
            fx[c] = fx[c].fillna(fx[c + "_es"])
        fx = fx.drop(columns=["Date_es", "B365H_es", "B365D_es", "B365A_es"])
    fx["src"] = fx["src"].fillna(1)                    # 3 football-data.co.uk, 2 added by you (MANUAL_FIXTURES), 1 ESPN only
    # sanity check (v17): a team can't play twice within 2 days in the same league. Keep football-data's fixture,
    # drop the ESPN-only one; if both come from the same source, drop both and say so.
    fx = fx.reset_index(drop=True)
    long_ = pd.concat([fx[["League", "Date", "HomeTeam"]].rename(columns={"HomeTeam": "Team"}).assign(i=fx.index),
                       fx[["League", "Date", "AwayTeam"]].rename(columns={"AwayTeam": "Team"}).assign(i=fx.index)])
    drop = set()
    for (lg_, t_), g_ in long_.groupby(["League", "Team"]):
        g_ = g_.sort_values("Date")
        for a_, b_ in zip(g_.itertuples(), list(g_.itertuples())[1:]):
            if (b_.Date - a_.Date).days <= 1:                  # v30: same day or next day (two days apart happens: Christmas, Liga MX)
                sa_, sb_ = fx.loc[a_.i, "src"], fx.loc[b_.i, "src"]
                bad = [b_.i] if sa_ > sb_ else ([a_.i] if sb_ > sa_ else [a_.i, b_.i])     # the more trusted source wins
                for i_ in bad:
                    if i_ not in drop:
                        FIXTURE_WARNINGS.append(f"{lg_}: {fx.loc[i_, 'HomeTeam']} v {fx.loc[i_, 'AwayTeam']} ({fx.loc[i_, 'Date']:%d %b}) dropped: "
                                                f"{t_} would play twice within a day, so a team name is probably mis-linked")
                drop.update(bad)
    fx = fx.drop(index=list(drop))
    return fx.reset_index(drop=True)

def promoted_factors():
    """How a newly promoted side typically does in its first 10 matches, relative to an average team."""
    gf, ga, avg = [], [], []
    for lg, g in all_matches.groupby("League"):
        seasons = sorted(g["Season"].unique())
        for prev, cur in zip(seasons, seasons[1:]):
            c = g[g["Season"] == cur]
            mean_goals = (c["FTHG"].mean() + c["FTAG"].mean()) / 2
            for t in set(c["HomeTeam"]) - set(g.loc[g["Season"] == prev, "HomeTeam"]):
                tm = c[(c["HomeTeam"] == t) | (c["AwayTeam"] == t)].sort_values("Date").head(10)
                gf.append(np.where(tm["HomeTeam"] == t, tm["FTHG"], tm["FTAG"]).sum())
                ga.append(np.where(tm["HomeTeam"] == t, tm["FTAG"], tm["FTHG"]).sum())
                avg.append(mean_goals * len(tm))
    if sum(avg) == 0:
        return 0.8, 1.2
    return sum(gf) / sum(avg), sum(ga) / sum(avg)

PROMO_ATT, PROMO_DEF = promoted_factors()
print(f"Newly promoted sides score {100 * PROMO_ATT:.0f}% and concede {100 * PROMO_DEF:.0f}% of an average team's goals in their first 10 games.")

def no_adjust(games):
    return np.ones(len(games)), np.ones(len(games)), [""] * len(games)

def live_adjust(games):
    """Player adjustment for upcoming fixtures (needs ESPN event ids)."""
    if coefs_live is None or len(up_feats) == 0 or "event_id" not in games:
        return no_adjust(games)
    f = games[["event_id"]].merge(up_feats.drop_duplicates("event_id"), on="event_id", how="left")
    fh, fa = multipliers(f, coefs_live)
    notes = []
    for hn, an in zip(f.get("h_missing_names", pd.Series([""] * len(f))).fillna(""),
                      f.get("a_missing_names", pd.Series([""] * len(f))).fillna("")):
        parts = [f"home: {hn}" if hn else "", f"away: {an}" if an else ""]
        notes.append("Likely missing, " + "; ".join(x for x in parts if x) if (hn or an) else "")
    return fh, fa, notes

def predict_league(lg_data, games, half_life, totals=True, quiet=False, adjust=no_adjust):
    games = games.reset_index(drop=True)
    if games.empty:
        return None
    counts = pd.concat([lg_data["HomeTeam"], lg_data["AwayTeam"]]).value_counts()
    known = set(counts[counts >= 5].index)
    new_h, new_a = ~games["HomeTeam"].isin(known).values, ~games["AwayTeam"].isin(known).values
    g2 = games.copy()
    g2.loc[new_h, "HomeTeam"], g2.loc[new_a, "AwayTeam"] = "__new__", "__new__"
    promo_h = np.where(new_h, PROMO_ATT, 1.0) * np.where(new_a, PROMO_DEF, 1.0)   # scale for home goals
    promo_a = np.where(new_a, PROMO_ATT, 1.0) * np.where(new_h, PROMO_DEF, 1.0)   # scale for away goals
    if not quiet:
        for name in sorted(set(games.loc[new_h, "HomeTeam"]) | set(games.loc[new_a, "AwayTeam"])):
            print(f"  {name} ({games['League'].iloc[0]}): new to the data, rated as a typical promoted side. If this is a known club, check the spelling.")
    fh, fa, absent = adjust(games)
    league_ = games["League"].iloc[0]
    if XG_WEIGHT > 0 and len(xg) and (league_ in UNDERSTAT_LEAGUES or league_ in XG_EXTRA_LEAGUES):
        lx = lg_data.merge(xg[["League", "Season", "HomeTeam", "AwayTeam", "xGH", "xGA"]].drop_duplicates(["League", "Season", "HomeTeam", "AwayTeam"]),
                           on=["League", "Season", "HomeTeam", "AwayTeam"], how="left")
        lx["YH"] = (1 - XG_WEIGHT) * lx["FTHG"] + XG_WEIGHT * lx["xGH"].fillna(lx["FTHG"])
        lx["YA"] = (1 - XG_WEIGHT) * lx["FTAG"] + XG_WEIGHT * lx["xGA"].fillna(lx["FTAG"])
        gm = fit_weighted(lx, "YH", "YA", 0.01, half_life)
    else:
        gm = fit_weighted(lg_data, "FTHG", "FTAG", 0.01, half_life)
    rho = estimate_rho_ha(*shrunk_means(gm, lg_data), lg_data)
    h, a = shrunk_means(gm, g2)
    ch, ca = context_multipliers(games)          # goal level and rest days, if they passed their tests
    ih, ia = impact_multipliers(games) if "impact_multipliers" in globals() else (1.0, 1.0)   # squad quality, if it passed
    xh, xa = ctx2_multipliers(games) if "ctx2_multipliers" in globals() else (1.0, 1.0)      # derbies, weather, home advantage, motivation
    fh, fa = fh * ch * ih * xh, fa * ca * ia * xa
    new_any = new_h | new_a
    top2 = {top: name for top, name in DIV2.values()} if "DIV2" in globals() else {}
    from_top = np.zeros(len(games), dtype=bool)
    if SECOND_DIV.get("on") and league_ in top2 and new_any.any() and len(div2):
        # promoted teams: rating carried over from the second division instead of a "typical promoted side"
        d2_ = div2[(div2["League"] == top2[league_]) & (div2["Date"] < pd.to_datetime(games["Date"]).min())]
        h2, a2 = two_div_means(fit_two_div(lg_data, d2_, half_life), games)
        h, a = np.where(new_any, h2, h * promo_h), np.where(new_any, a2, a * promo_a)
        h, a = h * fh, a * fa
    elif league_ in (LOWER_TOP if "LOWER_TOP" in globals() else {}) and new_any.any():
        # v36: in a second tier, a club just relegated from the division above keeps its rating from there (both divisions on one
        #      scale, this one at its own level); a club promoted from below is still rated as a typical promoted side
        top_ = league_frame(LOWER_TOP[league_])
        top_ = top_[top_["Date"] < pd.to_datetime(games["Date"]).min()]
        known_top = set(top_["HomeTeam"]) | set(top_["AwayTeam"])
        from_top = new_any & np.where(new_h, games["HomeTeam"].isin(known_top), True) & np.where(new_a, games["AwayTeam"].isin(known_top), True)
        if from_top.any():
            h2, a2 = two_div_means(fit_two_div(top_, lg_data, half_life), games, level=1.0)
            h, a = np.where(from_top, h2, h * promo_h), np.where(from_top, a2, a * promo_a)
            h, a = h * fh, a * fa
        else:
            h, a = h * promo_h * fh, a * promo_a * fa
    else:
        h, a = h * promo_h * fh, a * promo_a * fa
    p = outcome_probs(h, a, rho)
    note = np.where(new_h | new_a, ("New to the league: rated from its second-division results" if (SECOND_DIV.get("on") and league_ in top2)
                                     else "New to the league: rated as a typical promoted side"), "")
    note = np.where(from_top, "New to the league: rated from its results in the division above", note)
    t = pd.DataFrame({"Competition": games["League"].values, "Date": pd.to_datetime(games["Date"]).dt.strftime("%Y-%m-%d").values,
                      "Home": games["HomeTeam"].values, "Away": games["AwayTeam"].values,
                      "pH": p[:, 0], "pD": p[:, 1], "pA": p[:, 2], "ExpHome": h, "ExpAway": a, "rho": rho,
                      "Note": note, "Absent": absent, "AdjHome": fh, "AdjAway": fa})
    if games[ODDS].notna().all(axis=1).any():
        bp = np.full((len(games), 3), np.nan)
        has = games[ODDS].notna().all(axis=1).values
        bp[has] = book_probs(games[has])
        t["bookH"], t["bookD"], t["bookA"] = bp[:, 0], bp[:, 1], bp[:, 2]
    if totals:
        gm2, k2 = fit_total(lg_data, "FTHG", "FTAG", 0.1)
        h2, a2 = shrunk_means(gm2, g2)
        mu = h2 * promo_h * fh + a2 * promo_a * fa
        t["ExpGoals"], t["pOver25"] = mu, over_prob(mu, k2, 2.5)
        lyc = lg_data.dropna(subset=["HY", "AY"])                # v36: only matches with card counts (all of them in the main leagues)
        if len(lyc) >= 200:
            cm_, kc = fit_total(lyc, "HY", "AY", 0.1)
            ch_, ca_ = shrunk_means(cm_, g2)
            if "cards_multipliers" in globals():
                cmul_ = cards_multipliers(games)                    # appointed referee and derbies, if that test passed
                ch_, ca_ = ch_ * cmul_, ca_ * cmul_
            mu = ch_ + ca_
            t["ExpCards"], t["pOverCards"] = mu, over_prob(mu, kc, 4.5)
            t["ExpCardsH"], t["ExpCardsA"] = ch_, ca_               # v23: each side's expected yellow cards
        lc = lg_data.dropna(subset=["HC", "AC", "HS", "AS"])
        if len(lc) >= 200:                                          # v36: a league without corner and shot counts skips corners
            mc, ms = fit_weighted(lc, "HC", "AC", 1.0), fit_weighted(lc, "HS", "AS", 1.0)
            ratio = (lc["HC"] + lc["AC"]).sum() / (lc["HS"] + lc["AS"]).sum()
            blend = lambda d: (sum(shrunk_means(mc, d)) + sum(shrunk_means(ms, d)) * ratio) / 2
            y = (lc["HC"] + lc["AC"]).values
            kcorn = np.mean((y - blend(lc)) ** 2) / np.mean(blend(lc))
            t["ExpCorners"], t["pOverCorners"] = blend(g2), over_prob(blend(g2), kcorn, 9.5)
    return t

fixtures = get_fixtures()
print(f"{len(fixtures)} domestic, MLS and Saudi fixtures in the next {PREDICT_DAYS} days.")
for w_ in FIXTURE_WARNINGS:
    print("  WARNING:", w_)
health("Fixture sanity check", not FIXTURE_WARNINGS, f"{len(FIXTURE_WARNINGS)} doubtful fixtures dropped" if FIXTURE_WARNINGS else "no team plays twice within a day")
dom_preds = []
CAL_PATH = f"{SAVE_DIR}/calibration.json"
CALIBRATION = json.load(open(CAL_PATH)) if os.path.exists(CAL_PATH) else {}
for league in list(LEAGUES.values()) + list(SOLO):
    games = fixtures[fixtures["League"] == league]
    if games.empty:
        continue
    if league in SOLO:
        t = predict_league(SOLO[league]["data"], games, half_life=SOLO[league]["half_life"], totals=SOLO[league].get("totals", False), adjust=live_adjust)
    else:
        t = predict_league(all_matches[all_matches["League"] == league], games, half_life=365, adjust=live_adjust)
    if t is not None:
        t["Group"] = SOLO[league]["group"] if league in SOLO else "Domestic"
        if "ML" in globals() and ML is not None and t["Group"].iloc[0] != "Europe":
            try:
                t[["pH", "pD", "pA"]] = ml_apply(t.assign(League=league))          # the machine-learning layer passed its test
                t["Note"] = (t["Note"].astype(str) + " [ML layer]").str.strip()
            except Exception as ex_:
                print("  machine-learning layer skipped:", str(ex_)[:80])
        cal = CALIBRATION.get(t["Group"].iloc[0], {})
        if (cal.get("T", 1.0) != 1.0 or cal.get("draw", 1.0) != 1.0) and not ("ML" in globals() and ML is not None):
            t[["pH", "pD", "pA"]] = calibrate_full(t[["pH", "pD", "pA"]].values, cal.get("T", 1.0), cal.get("draw", 1.0))
        t[["pH", "pD", "pA"]] = outsider_adjust(t[["pH", "pD", "pA"]].values)
        dom_preds.append(add_blend(t, t["Group"].iloc[0]))
if CALIBRATION:
    print("Calibration in use (learned on earlier matches, tested on later ones):",
          ", ".join(f"{g}: {v.get('T', 1):.2f} / draws x{v.get('draw', 1):.2f}" for g, v in CALIBRATION.items()))
pred_dom = pd.concat(dom_preds, ignore_index=True) if dom_preds else pd.DataFrame()

# v36: the league gate. A new league's predictions are published (site, channel, bot, track record) only once its replay of this
#      season has passed (section 8 decides, so a decision made in one run applies from the next); until then they're held back.
GATE_PATH = f"{SAVE_DIR}/league_gate.json"
LEAGUE_GATE = json.load(open(GATE_PATH)) if os.path.exists(GATE_PATH) else {}
GATE_HIDDEN = {lg_ for lg_ in (NEW_LEAGUES_V36 if "NEW_LEAGUES_V36" in globals() else set()) if not LEAGUE_GATE.get(lg_, {}).get("pass")}
if len(pred_dom) and GATE_HIDDEN:
    held_ = pred_dom[pred_dom["Competition"].isin(GATE_HIDDEN)]
    pred_dom = pred_dom[~pred_dom["Competition"].isin(GATE_HIDDEN)].reset_index(drop=True)
    if len(held_):
        print(f"League gate: {len(held_)} fixtures held back in {held_['Competition'].nunique()} new leagues until their backtest passes "
              f"({', '.join(sorted(held_['Competition'].unique()))}).")
passed_ = sorted(lg_ for lg_ in (NEW_LEAGUES_V36 if "NEW_LEAGUES_V36" in globals() else set()) if LEAGUE_GATE.get(lg_, {}).get("pass"))
health("League gate (v36 leagues)", True, f"{len(passed_)} published" + (f": {', '.join(passed_)}" if passed_ else "") + f"; {len(GATE_HIDDEN)} waiting")

if len(pred_dom):
    show = pred_dom[["Competition", "Date", "Home", "Away"]].copy()
    show[["Home %", "Draw %", "Away %"]] = (pred_dom[["pH", "pD", "pA"]] * 100).round(0).values
    for c, label in [("bookH", "Book H %"), ("bookD", "Book D %"), ("bookA", "Book A %")]:
        if c in pred_dom:
            show[label] = (pred_dom[c] * 100).round(0)
    for c, label in [("ExpGoals", "Exp goals"), ("pOver25", "Over 2.5 %"), ("ExpCorners", "Exp corners"),
                     ("pOverCorners", "Over 9.5 corners %"), ("ExpCards", "Exp cards"), ("pOverCards", "Over 4.5 cards %")]:
        if c in pred_dom:
            show[label] = (pred_dom[c] * (100 if "%" in label else 1)).round(0 if "%" in label else 1)
    if "Absent" in pred_dom:
        show["Likely missing"] = pred_dom["Absent"].fillna("")
    display(show)
else:
    print("No domestic fixtures found. The fixtures file may not be updated yet, or add some to MANUAL_FIXTURES.")
