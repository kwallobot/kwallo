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
    print(f"European model: '{EURO_CHOSEN['preset']}' settings, calibration {EURO_CHOSEN.get('temperature', 1.0):.2f}, player adjustment {'on' if EURO_PLAYER_ADJUST and PLAYER_MODEL else 'off'}.")
    show = pred_eu.reindex(columns=["Competition", "Date", "Home", "Away"]).copy()
    show[["Home %", "Draw %", "Away %"]] = (pred_eu.reindex(columns=["pH", "pD", "pA"]) * 100).round(0).values
    _pe = pred_eu.reindex(columns=["ExpHome", "ExpAway", "Note"])
    show["Exp home goals"], show["Exp away goals"], show["Note"] = _pe["ExpHome"].round(2), _pe["ExpAway"].round(2), _pe["Note"]
    display(show.sort_values("Date").reset_index(drop=True))
