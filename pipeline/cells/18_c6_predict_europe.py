# ===================== 5. PREDICT: Champions League and Europa League =====================
pred_eu = pd.DataFrame()
up = euro_up[(euro_up["Date"] >= TODAY) & (euro_up["Date"] < TODAY + pd.Timedelta(days=PREDICT_DAYS))] if len(euro_up) else pd.DataFrame()
if len(up) == 0:
    print(f"No European fixtures in the next {PREDICT_DAYS} days (or no current-season files in Drive).")
else:
    print("Fitting the cross-league model (takes a minute)...")
    def euro_live_adjust(df):
        if not (PLAYER_MODEL and EURO_PLAYER_ADJUST) or coefs_live is None or len(up_feats) == 0 or "event_id" not in df:
            return np.ones(len(df)), np.ones(len(df))
        f = df[["event_id"]].merge(up_feats.drop_duplicates("event_id"), on="event_id", how="left")
        return multipliers(f, coefs_live)
    pred_eu = predict_europe(domestic_x, euro, up, adjust=euro_live_adjust)
    if len(pred_eu):
        pred_eu[["pH", "pD", "pA"]] = outsider_adjust(pred_eu[["pH", "pD", "pA"]].values)
    pred_eu = add_blend(pred_eu, "Europe")
    absent_eu = up[["event_id"]].merge(up_feats.drop_duplicates("event_id"), on="event_id", how="left") if len(up_feats) and "event_id" in up else None
    if absent_eu is not None and "h_missing_names" in absent_eu:
        pred_eu["Absent"] = ["Likely missing, " + "; ".join(x for x in [f"home: {h_}" if isinstance(h_, str) and h_ else "", f"away: {a_}" if isinstance(a_, str) and a_ else ""] if x)
                             if ((isinstance(h_, str) and h_) or (isinstance(a_, str) and a_)) else "" for h_, a_ in zip(absent_eu["h_missing_names"], absent_eu["a_missing_names"])]
    # v35: corners and yellow cards for the cups, from each side's last 10 matches in every competition (football-data.co.uk,
    #      then ESPN's team statistics), blended 70/30 toward the cups' own average; spread estimated from the cups' matches
    _tc = []
    for fr_ in [all_matches] + ([TS_EXTRA] if "TS_EXTRA" in globals() and len(TS_EXTRA) else []):
        if all(c_ in fr_ for c_ in ("HC", "AC", "HY", "AY")):
            _tc.append(fr_[["Date", "HomeTeam", "AwayTeam", "HC", "AC", "HY", "AY"]].assign(cup=fr_["Comp"].isin(list(EURO_CODES.values())) if "Comp" in fr_ else False))
    if _tc and len(pred_eu):
        tc_ = pd.concat(_tc, ignore_index=True)
        tc_["Date"] = pd.to_datetime(tc_["Date"]).dt.normalize()
        for c_ in ("HC", "AC", "HY", "AY"):
            tc_[c_] = pd.to_numeric(tc_[c_], errors="coerce")
        tc_ = tc_[tc_["Date"] < TODAY].drop_duplicates(["Date", "HomeTeam", "AwayTeam"])
        long_ = pd.concat([pd.DataFrame({"Team": tc_["HomeTeam"], "Date": tc_["Date"], "cf": tc_["HC"], "ca": tc_["AC"], "yf": tc_["HY"], "ya": tc_["AY"]}),
                           pd.DataFrame({"Team": tc_["AwayTeam"], "Date": tc_["Date"], "cf": tc_["AC"], "ca": tc_["HC"], "yf": tc_["AY"], "ya": tc_["HY"]})]).sort_values("Date")
        cup_ = tc_[tc_["cup"]]
        def _avg(team_, f_, a_):
            d_ = long_[long_["Team"] == team_].dropna(subset=[f_, a_]).tail(10)
            return (float(d_[f_].mean()), float(d_[a_].mean())) if len(d_) >= 4 else None
        for stat_, f_, a_, line_, base_ in (("corners", "cf", "ca", 9.5, 10.0), ("cards", "yf", "ya", 4.5, 4.0)):
            tot_ = (cup_[["HC", "AC"]] if stat_ == "corners" else cup_[["HY", "AY"]]).dropna().sum(axis=1)
            mean_ = float(tot_.mean()) if len(tot_) >= 30 else base_
            k_ = float(np.clip(tot_.var() / max(tot_.mean(), 1e-9), 1.0, 3.0)) if len(tot_) >= 30 else 1.3
            eh_, ea_, n_ = [], [], 0
            for r_ in pred_eu.itertuples():
                h_, a2_ = _avg(r_.Home, f_, a_), _avg(r_.Away, f_, a_)
                if h_ and a2_:
                    eh_.append(0.7 * (h_[0] + a2_[1]) / 2 + 0.3 * mean_ / 2); ea_.append(0.7 * (a2_[0] + h_[1]) / 2 + 0.3 * mean_ / 2); n_ += 1
                else:
                    eh_.append(np.nan); ea_.append(np.nan)
            eh_, ea_ = np.array(eh_), np.array(ea_)
            mu_ = eh_ + ea_
            p_ = np.array([over_prob(m_, k_, line_) if np.isfinite(m_) else np.nan for m_ in mu_])
            if stat_ == "corners":
                pred_eu["ExpCorners"], pred_eu["pOverCorners"] = mu_, p_
            else:
                pred_eu["ExpCards"], pred_eu["pOverCards"], pred_eu["ExpCardsH"], pred_eu["ExpCardsA"] = mu_, p_, eh_, ea_
            print(f"European {stat_}: priced for {n_} of {len(pred_eu)} matches (cups' average {mean_:.1f} a match).")
    print(f"European model: '{EURO_CHOSEN['preset']}' settings, calibration {EURO_CHOSEN.get('temperature', 1.0):.2f}, player adjustment {'on' if EURO_PLAYER_ADJUST and PLAYER_MODEL else 'off'}.")
    show = pred_eu.reindex(columns=["Competition", "Date", "Home", "Away"]).copy()
    show[["Home %", "Draw %", "Away %"]] = (pred_eu.reindex(columns=["pH", "pD", "pA"]) * 100).round(0).values
    _pe = pred_eu.reindex(columns=["ExpHome", "ExpAway", "Note"])
    show["Exp home goals"], show["Exp away goals"], show["Note"] = _pe["ExpHome"].round(2), _pe["ExpAway"].round(2), _pe["Note"]
    display(show.sort_values("Date").reset_index(drop=True))
