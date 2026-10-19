# ===================== 8d. MATCH VERDICT: the model's best angles on every match, with reasons and its own track record =====================
# Built from the model's probabilities across all markets, reasons drawn from the data, and an honest evidence tag.
# Fair odds = the price at which a bet breaks even (1 / probability): anything offered ABOVE it is where the model sees value.
# Every verdict is logged before kickoff and scored afterwards. This is the model's view, not a guaranteed winner and not
# financial advice; no edge over the bookmakers has been confirmed yet.
from scipy.stats import poisson as _pv
VERDICTS, verdict_summary = {}, {}
VERDICT_LOG = f"{SAVE_DIR}/verdict_log.csv"
_edge = {}
if "bt_table" in globals() and bt_table is not None and ("ALL WEEKS", "Domestic") in bt_table.index:
    _r = bt_table.loc[("ALL WEEKS", "Domestic")]
    for lab, a_, b_ in [("over25", "Over 2.5 %", "Over 2.5 naive %"), ("corners", "Corners 9.5 %", "Corners naive %"), ("cards", "Cards 4.5 %", "Cards naive %")]:
        if pd.notna(_r.get(a_)) and pd.notna(_r.get(b_)):
            _edge[lab] = float(_r[a_] - _r[b_])
if globals().get("btts_edge") is not None:
    _edge["btts"] = float(btts_edge)
def evidence(family):
    if family in ("result", "double", "handicap"):
        return "no proven edge over the bookmakers yet (closing-line tests)"
    if family == "goals":
        return "small edge in testing (over/under 2.5)" if _edge.get("over25", 0) >= 2 else "no proven edge in testing"
    if family == "btts":
        return "no proven edge in testing" if _edge.get("btts", 0) < 2 else "small edge in testing"
    if family in ("cards", "cards_team"):
        return "no proven edge in testing" if _edge.get("cards", 0) < 2 else "small edge in testing"
    if family == "corners":
        return "no proven edge in testing" if _edge.get("corners", 0) < 2 else "small edge in testing"
    if family == "scorer":
        return "well calibrated in testing; value untested (no odds)" if scorer_calibration.get("trusted") else "experimental"
    if family in ("shots", "sot", "fouls", "halftime", "halftime_both", "timing", "penalty", "player_props", "first_scorer", "offsides", "tackles", "throwins"):
        return "well calibrated in testing; value untested (no odds)"
    if family == "assister":
        return "well calibrated in testing; value untested (no odds)" if assist_calibration.get("trusted") else "experimental"
    return "untested"

TREND_FOR = {   # which spotted streaks support which market (team role: h = home side, a = away side, any = either)
    "H": [("h", "win"), ("a", "loss")], "A": [("a", "win"), ("h", "loss")], "D": [],
    "1X": [("h", "unbeaten"), ("a", "loss")], "X2": [("a", "unbeaten"), ("h", "loss")],
    "O25": [("any", "over25")], "U25": [("any", "under25")], "O15": [("any", "over25")], "U35": [("any", "under25")],
    "BTTS": [("any", "btts"), ("h", "conceded"), ("a", "conceded")], "BTTSN": [("any", "btts_no"), ("h", "cleansheet"), ("a", "cleansheet"), ("h", "team0"), ("a", "team0")],
    "H15": [("h", "team2plus")], "A15": [("a", "team2plus")], "H05": [], "A05": [],
    "C45": [("any", "cards45")], "K95": [("any", "corners95")]}
def reasons_for(key_, m, home, away):
    out_ = []
    for role, mk in TREND_FOR.get(key_, []):
        for side_, team_ in ([("h", home), ("a", away)] if role == "any" else [(role, home if role == "h" else away)]):
            for sp in (TRENDS.get(team_, {}) or {}).get("spotted", []):
                wrong_venue = (side_ == "h" and sp["scope"] == "last 7 away") or (side_ == "a" and sp["scope"] == "last 7 home")
                if sp["market"] == mk and not wrong_venue:
                    lr_ = f", league usually {100 * sp['league_rate']:.0f}%" if sp.get("league_rate") is not None else ""
                    out_.append(f"{team_}: {sp['pattern'].lower()} in {sp['count']} of their {sp['scope']}{lr_}")
    if key_ in ("O25", "O15", "BTTS", "H15", "A15", "U25", "U35", "BTTSN"):
        for team_ in (home, away):
            st_ = (TRENDS.get(team_, {}) or {}).get("stats", {})
            ar_ = (TRENDS.get(team_, {}) or {}).get("arrows", {})
            if ar_.get("xGF") and st_.get("xGF", [None])[0] is not None:
                out_.append(f"{team_}'s chance creation is {'up' if ar_['xGF'] == 'up' else 'down'} (xG {st_['xGF'][0]:.1f} per game in the last 7, season {st_['xGF'][1]:.1f})")
    adj_h, adj_a = m.get("AdjHome"), m.get("AdjAway")
    if key_ in ("H", "A", "1X", "X2", "H15", "A15", "O25", "BTTS") and adj_h is not None and pd.notna(adj_h):
        for team_, v_ in [(home, adj_h), (away, adj_a)]:
            if v_ is not None and pd.notna(v_) and abs(v_ - 1) >= 0.08:
                out_.append(f"likely absences change {team_}'s expected goals by {100 * (v_ - 1):+.0f}%")
    return out_[:3]

def verdict_for(m):
    home, away = m["Home"], m["Away"]
    g_ = score_grid(m["ExpHome"], m["ExpAway"], m["pH"], m["pD"], m["pA"])
    gn = g_ / g_.sum()
    hh, aa = np.indices(gn.shape)
    tot = hh + aa
    cand = [("H", f"{home} to win", m["pH"], "result"), ("D", "Draw", m["pD"], "result"), ("A", f"{away} to win", m["pA"], "result"),
            ("1X", f"{home} or draw (double chance)", m["pH"] + m["pD"], "double"), ("X2", f"{away} or draw (double chance)", m["pA"] + m["pD"], "double"),
            ("O15", "Over 1.5 goals", gn[tot > 1.5].sum(), "goals"), ("O25", "Over 2.5 goals", gn[tot > 2.5].sum(), "goals"),
            ("U25", "Under 2.5 goals", gn[tot < 2.5].sum(), "goals"), ("U35", "Under 3.5 goals", gn[tot < 3.5].sum(), "goals"),
            ("BTTS", "Both teams to score", gn[(hh > 0) & (aa > 0)].sum(), "btts"), ("BTTSN", "Not both teams to score", 1 - gn[(hh > 0) & (aa > 0)].sum(), "btts"),
            ("H05", f"{home} to score", gn[hh > 0].sum(), "team_h"), ("A05", f"{away} to score", gn[aa > 0].sum(), "team_a"),
            ("H15", f"{home} to score 2+", gn[hh > 1].sum(), "team_h"), ("A15", f"{away} to score 2+", gn[aa > 1].sum(), "team_a"),
            ("HH", f"{home} to win by 2+", gn[hh - aa >= 2].sum(), "handicap"), ("AH", f"{away} to win by 2+", gn[aa - hh >= 2].sum(), "handicap")]
    if pd.notna(m.get("pOverCards", np.nan)):
        cand += [("C45", "Over 4.5 yellow cards", m["pOverCards"], "cards"), ("C45U", "Under 4.5 yellow cards", 1 - m["pOverCards"], "cards")]
        if pd.notna(m.get("ExpCardsH", np.nan)):
            cand += [("CH", f"{home} 2+ yellow cards", 1 - _pv.cdf(1, m["ExpCardsH"]), "cards_team"), ("CA", f"{away} 2+ yellow cards", 1 - _pv.cdf(1, m["ExpCardsA"]), "cards_team")]
    if pd.notna(m.get("pOverCorners", np.nan)):
        cand += [("K95", "Over 9.5 corners", m["pOverCorners"], "corners"), ("K95U", "Under 9.5 corners", 1 - m["pOverCorners"], "corners")]
    sc_ = SCORERS.get((m["Competition"], str(m["Date"])[:10], home, away), {}) if "SCORERS" in globals() else {}
    for side_, fam_, word_ in [("home", "scorer", "to score"), ("away", "scorer", "to score"), ("home_assist", "assister", "to provide an assist"), ("away_assist", "assister", "to provide an assist")]:
        for p_ in (sc_.get(side_) or [])[:1]:
            cand.append((f"{fam_.upper()[:2]}:{p_['Player']}", f"{p_['Player']} {word_}", p_["p"], fam_))
    for mk_ in (MARKETS.get((m["Competition"], str(m["Date"])[:10], home, away), []) if "MARKETS" in globals() else []):
        if mk_["trusted"] and mk_.get("code"):           # v24: only markets that passed their calibration test can become angles
            cand.append((f"MK:{mk_['code']}", mk_["Bet"], mk_["p"], mk_["family"]))
    bc_ = {b_["Bet"]: b_ for b_ in BET_CHECK.get((m["Competition"], str(m["Date"])[:10], home, away), [])} if "BET_CHECK" in globals() else {}
    price_for = {"H": bc_.get(f"{home} win"), "D": bc_.get("Draw"), "A": bc_.get(f"{away} win")}
    rows_ = []
    for key_, label_, p_, fam_ in cand:
        p_ = float(p_)
        if not (0.02 < p_ < 0.99):
            continue
        pr_ = price_for.get(key_)
        price, ev_ = (pr_["Price"], p_ * pr_["Price"] - 1) if pr_ else (None, None)
        rs_ = reasons_for(key_, m, home, away)
        score_ = p_ + 0.05 * len(rs_) + (0.1 if ev_ is not None and 0.03 <= ev_ <= 0.25 else 0) - (0.3 if ev_ is not None and (ev_ < -0.05 or ev_ > 0.25) else 0)
        rows_.append({"key": key_, "Bet": label_, "p": p_, "fair": 1 / p_, "price": price, "value": ev_, "family": fam_, "evidence": evidence(fam_),
                      "reasons": rs_, "score": score_})
    pool = sorted([r_ for r_ in rows_ if r_["p"] >= 0.55 and r_["family"] not in ("scorer", "assister")] +
                  [r_ for r_ in rows_ if r_["family"] in ("scorer", "assister") and r_["p"] >= 0.35], key=lambda r_: -r_["score"])
    best, fams = [], set()
    for r_ in pool:
        if r_["family"] in fams or (r_["value"] is not None and r_["value"] < -0.05):
            continue
        best.append(r_); fams.add(r_["family"])
        if len(best) == 3:
            break
    safer = max([r_ for r_ in rows_ if r_["p"] >= 0.70 and r_ not in best], key=lambda r_: r_["p"], default=None)
    avoid = []
    for r_ in rows_:
        if r_["value"] is not None and r_["value"] > 0.25:
            avoid.append(f"{r_['Bet']} at {r_['price']:.2f}: the model disagrees implausibly with the market (+{100 * r_['value']:.0f}%), so it's probably missing something")
    if any(r_["family"] in ("cards", "corners") for r_ in best):
        avoid.append("Cards and corners picks: no proven edge in testing, so treat them as context rather than bets")
    return {"best": best, "safer": safer, "avoid": avoid[:3]}

upc_v = pd.concat([x for x in [pred_dom, pred_eu] if len(x)], ignore_index=True) if (len(pred_dom) or len(pred_eu)) else pd.DataFrame()
for m_ in upc_v.to_dict("records"):
    VERDICTS[(m_["Competition"], str(m_["Date"])[:10], m_["Home"], m_["Away"])] = verdict_for(m_)
print(f"Match verdicts: {len(VERDICTS)} matches.")

# ---------- log the picks (first time seen, like placed bets) and score them when results arrive ----------
vlog = checked_read(VERDICT_LOG, text=("Competition", "Date", "Home", "Away", "key", "Bet", "kind"), num=("p", "fair", "price", "won"), name="verdict_log")
new_v = []
for k_, v_ in VERDICTS.items():
    for kind_, r_ in [("best", (v_["best"] or [None])[0]), ("safer", v_["safer"])]:
        if r_:
            new_v.append({"Logged": TODAY.strftime("%Y-%m-%d"), "Competition": k_[0], "Date": k_[1], "Home": k_[2], "Away": k_[3], "kind": kind_,
                          "key": r_["key"], "Bet": r_["Bet"], "p": r_["p"], "fair": r_["fair"], "price": r_["price"]})
if new_v:
    vlog = pd.concat([vlog, pd.DataFrame(new_v)], ignore_index=True).drop_duplicates(["Competition", "Date", "Home", "Away", "kind"], keep="first")
def settle(r_):
    g_ = RES[(RES["HomeTeam"] == r_["Home"]) & (RES["AwayTeam"] == r_["Away"]) & ((RES["Date"] - pd.Timestamp(r_["Date"])).abs() <= pd.Timedelta(days=1))]
    if g_.empty:
        return np.nan
    x = g_.iloc[0]
    h, a, k_ = x["FTHG"], x["FTAG"], r_["key"]
    simple = {"H": h > a, "D": h == a, "A": a > h, "1X": h >= a, "X2": a >= h, "O15": h + a > 1.5, "O25": h + a > 2.5, "U25": h + a < 2.5, "U35": h + a < 3.5,
              "BTTS": (h > 0) and (a > 0), "BTTSN": not ((h > 0) and (a > 0)), "H05": h > 0, "A05": a > 0, "H15": h > 1, "A15": a > 1, "HH": h - a >= 2, "AH": a - h >= 2}
    if k_ in simple:
        return float(simple[k_])
    if k_ in ("C45", "C45U", "CH", "CA") and pd.notna(x.get("HY")):
        return float({"C45": x["HY"] + x["AY"] > 4.5, "C45U": x["HY"] + x["AY"] < 4.5, "CH": x["HY"] >= 2, "CA": x["AY"] >= 2}[k_])
    if k_ in ("K95", "K95U") and pd.notna(x.get("HC")):
        return float((x["HC"] + x["AC"] > 9.5) if k_ == "K95" else (x["HC"] + x["AC"] < 9.5))
    if k_.startswith("MK:"):
        c_ = k_[3:].split("|")
        if c_[0] == "TOT" and pd.notna(x.get(c_[1])) and pd.notna(x.get(c_[2])):
            return float(x[c_[1]] + x[c_[2]] > float(c_[3]))
        if c_[0] in ("H", "A") and pd.notna(x.get(c_[1])):
            return float(x[c_[1]] > float(c_[2]))
        if c_[0] in ("HT_D", "HT_H", "BOTHHALVES"):
            ht_ = all_matches[(all_matches["HomeTeam"] == r_["Home"]) & (all_matches["AwayTeam"] == r_["Away"]) & ((all_matches["Date"] - pd.Timestamp(r_["Date"])).abs() <= pd.Timedelta(days=1))]
            if ht_.empty or pd.isna(ht_["HTHG"].iloc[0]):
                return np.nan
            hg, ag = ht_["HTHG"].iloc[0], ht_["HTAG"].iloc[0]
            return float({"HT_D": hg == ag, "HT_H": hg > ag, "BOTHHALVES": (hg + ag > 0) and (h + a - hg - ag > 0)}[c_[0]])
        if c_[0] == "CNT" and "COUNT_LONG" in globals() and len(COUNT_LONG):        # v30: offsides and tackles
            t_ = COUNT_LONG[(COUNT_LONG["stat"] == c_[1]) & (COUNT_LONG["Team"] == r_["Home"]) & (COUNT_LONG["is_home"] == 1)
                            & ((COUNT_LONG["Date"] - pd.Timestamp(r_["Date"])).abs() <= pd.Timedelta(days=1))]
            if not len(t_):
                return np.nan
            val_ = {"tot": t_["own"].iloc[0] + t_["against"].iloc[0], "home": t_["own"].iloc[0], "away": t_["against"].iloc[0]}[c_[2]]
            return float(val_ > float(c_[3]))
        if c_[0] == "THROW" and "THROW_LONG" in globals() and len(THROW_LONG):
            t_ = THROW_LONG[(THROW_LONG["Team"] == r_["Home"]) & (THROW_LONG["is_home"] == 1) & ((THROW_LONG["Date"] - pd.Timestamp(r_["Date"])).abs() <= pd.Timedelta(days=1))]
            return float(t_["own"].iloc[0] + t_["against"].iloc[0] > float(c_[1])) if len(t_) else np.nan
        if c_[0] == "PL" and "L" in globals():
            rows_ = L[(L["player"] == c_[3]) & ((L["date"] - pd.Timestamp(r_["Date"])).abs() <= pd.Timedelta(days=1))]
            return float(pd.to_numeric(rows_[c_[1]], errors="coerce").sum() >= int(c_[2])) if len(rows_) else np.nan
        return np.nan
    if (k_.startswith("SC:") or k_.startswith("AS:")) and "L" in globals():
        nm_ = k_[3:]
        rows_ = L[(L["player"] == nm_) & ((L["date"] - pd.Timestamp(r_["Date"])).abs() <= pd.Timedelta(days=1))]
        if len(rows_):
            return float((rows_["goals"] if k_.startswith("SC:") else rows_["assists"]).sum() > 0)
        return np.nan
    return np.nan
if len(vlog):
    open_ = vlog["won"].isna() if "won" in vlog else pd.Series(True, index=vlog.index)
    vlog.loc[open_ & (pd.to_datetime(vlog["Date"]) < TODAY), "won"] = [settle(r_) for _, r_ in vlog[open_ & (pd.to_datetime(vlog["Date"]) < TODAY)].iterrows()]
    vlog.to_csv(VERDICT_LOG, index=False)
    st_ = vlog.dropna(subset=["won"]) if "won" in vlog else vlog.iloc[:0]
    for kind_ in ["best", "safer"]:
        s_ = st_[st_["kind"] == kind_]
        if len(s_):
            pr_ = s_.dropna(subset=["price"])
            verdict_summary[kind_] = {"settled": int(len(s_)), "hit": float(100 * s_["won"].mean()), "expected": float(100 * s_["p"].mean()),
                                      "priced": int(len(pr_)), "roi": float(100 * (np.where(pr_["won"] > 0, pr_["price"] - 1, -1)).mean()) if len(pr_) else None}
    for kind_, v_ in verdict_summary.items():
        print(f"Verdict track record ({kind_} picks): {v_['settled']} settled, won {v_['hit']:.0f}% vs {v_['expected']:.0f}% expected"
              + (f"; ROI at the best price {v_['roi']:+.1f}% on {v_['priced']} priced picks" if v_["roi"] is not None else ""))

# add each verdict to its match report
if "match_reports" in globals() and match_reports:
    for m_ in match_reports:
        v_ = VERDICTS.get((m_["Competition"], m_["Date"], m_["Home"], m_["Away"]))
        if not v_:
            continue
        lines_ = ["MATCH VERDICT (the model's view, not a guaranteed winner; no edge confirmed yet)"]
        for i_, b_ in enumerate(v_["best"], 1):
            lines_.append(f"{i_}. {b_['Bet']}: {100 * b_['p']:.0f}%, fair odds {b_['fair']:.2f}"
                          + (f", best price {b_['price']:.2f} (value {100 * b_['value']:+.0f}%)" if b_["price"] else "") + f" [{b_['evidence']}]")
            for rs_ in b_["reasons"]:
                lines_.append(f"     - {rs_}")
        if v_["safer"]:
            lines_.append(f"Safer angle: {v_['safer']['Bet']} ({100 * v_['safer']['p']:.0f}%): only worth it at {1.05 * v_['safer']['fair']:.2f} or better")
        for a_ in v_["avoid"]:
            lines_.append(f"Avoid: {a_}")
        m_["text"] = m_["text"].replace("\nREASONING", "\n" + "\n".join(lines_) + "\n\nREASONING", 1)


# ---------- v25: your own odds for niche markets, logged and scored ----------
ODDS_LOG = f"{SAVE_DIR}/my_odds_ledger.csv"
olog = checked_read(ODDS_LOG, text=("Date", "Home", "Away", "Bet", "Matched", "key"), num=("odds", "p", "fair", "won"), name="my_odds_ledger")
new_o, not_found = [], []
for d_, h_, a_, bet_, odds_ in (MY_ODDS if "MY_ODDS" in globals() else []):
    k_ = next((k for k in list(MARKETS) + list(VERDICTS) if k[1] == d_ and tsim(k[2], h_) >= 0.8 and tsim(k[3], a_) >= 0.8), None)
    cands_ = []
    if k_:
        cands_ += [(m_["Bet"], m_["p"], f"MK:{m_['code']}") for m_ in MARKETS.get(k_, []) if m_.get("code")]
        cands_ += [(b_["Bet"], b_["p"], b_["key"]) for b_ in (VERDICTS.get(k_, {}).get("best") or [])]
    hit_ = [c_ for c_ in cands_ if str(bet_).lower() in c_[0].lower()]
    if not hit_:
        not_found.append(f"{h_} v {a_} ({d_}): '{bet_}'")
        continue
    lab_, p_, key_ = hit_[0]
    new_o.append({"Logged": TODAY.strftime("%Y-%m-%d"), "Competition": k_[0], "Date": d_, "Home": k_[2], "Away": k_[3], "Bet": bet_, "Matched": lab_,
                  "key": key_, "odds": float(odds_), "p": float(p_), "fair": 1 / float(p_)})
if new_o:
    olog = pd.concat([olog, pd.DataFrame(new_o)], ignore_index=True).drop_duplicates(["Date", "Home", "Away", "Matched"], keep="first")
if not_found:
    print("MY_ODDS entries not matched (check the date, team names and wording against the card):", "; ".join(not_found))
my_odds_summary = {}
if len(olog):
    open_o = olog["won"].isna() if "won" in olog else pd.Series(True, index=olog.index)
    due_ = open_o & (pd.to_datetime(olog["Date"]) < TODAY)
    if due_.any():
        olog.loc[due_, "won"] = [settle(r_) for _, r_ in olog[due_].iterrows()]
    olog.to_csv(ODDS_LOG, index=False)
    st_o = olog.dropna(subset=["won"]) if "won" in olog else olog.iloc[:0]
    if len(st_o):
        val_ = st_o[st_o["odds"] > st_o["fair"]]
        my_odds_summary = {"logged": int(len(olog)), "settled": int(len(st_o)), "hit": float(100 * st_o["won"].mean()), "expected": float(100 * st_o["p"].mean()),
                           "roi_all": float(100 * np.where(st_o["won"] > 0, st_o["odds"] - 1, -1).mean()),
                           "value_bets": int(len(val_)), "roi_value": float(100 * np.where(val_["won"] > 0, val_["odds"] - 1, -1).mean()) if len(val_) else None}
        print(f"Your odds ledger: {my_odds_summary['settled']} settled; won {my_odds_summary['hit']:.0f}% vs {my_odds_summary['expected']:.0f}% expected; "
              f"ROI {my_odds_summary['roi_all']:+.1f}%" + (f"; on bets priced above fair odds ({my_odds_summary['value_bets']}): ROI {my_odds_summary['roi_value']:+.1f}%" if my_odds_summary["value_bets"] else ""))
    else:
        print(f"Your odds ledger: {len(olog)} logged, none settled yet.")

# ---------- v26: bet history, "last time out" for both teams ----------
# Backfilled from the backtest (replayed predictions, all made before each match): the verdict's picks rebuilt for every
# replayed match and settled with the real result. Live logged picks take precedence where they exist.
LAST_TIME, BET_HISTORY_SUMMARY = {}, {}
hist_rows = []
if RUN_BACKTEST and bt_scored is not None and len(bt_scored):
    _rf = reasons_for
    reasons_for = lambda *a, **k: []                     # no reasons in the backfill: they'd use today's trends, which the past couldn't know
    for r_ in bt_scored.dropna(subset=["ExpHome", "ExpAway", "pH"]).to_dict("records"):
        if pd.Timestamp(r_["Date"]) >= TODAY:
            continue
        v_ = verdict_for(r_)
        picks = [("best", b_) for b_ in v_["best"]] + ([("safer", v_["safer"])] if v_["safer"] else [])
        for kind_, b_ in picks:
            hist_rows.append({"Competition": r_["Competition"], "Date": str(r_["Date"])[:10], "Home": r_["Home"], "Away": r_["Away"],
                              "kind": kind_, "key": b_["key"], "Bet": b_["Bet"], "p": b_["p"], "source": "replay"})
    reasons_for = _rf
H_ = pd.DataFrame(hist_rows)
if len(H_):
    H_["won"] = [settle(r_) for _, r_ in H_.iterrows()]
if len(vlog) and "won" in vlog:
    live_ = vlog.dropna(subset=["won"])[["Competition", "Date", "Home", "Away", "kind", "key", "Bet", "p", "won"]].assign(source="live")
    if len(H_):
        H_ = H_[~H_.set_index(["Date", "Home", "Away"]).index.isin(live_.set_index(["Date", "Home", "Away"]).index)]
    H_ = pd.concat([H_, live_], ignore_index=True)
if len(H_):
    H_ = H_.dropna(subset=["won"])
    H_["Date"] = pd.to_datetime(H_["Date"])
    by_team = {}
    for t_col, o_col, venue in [("Home", "Away", "H"), ("Away", "Home", "A")]:
        for (team_, date_), g_ in H_.groupby([t_col, "Date"]):
            by_team.setdefault(team_, []).append({"date": date_, "opp": g_[o_col].iloc[0], "venue": venue, "comp": g_["Competition"].iloc[0],
                                                  "picks": [{"Bet": b_.Bet, "p": float(b_.p), "won": bool(b_.won), "kind": b_.kind} for b_ in g_.itertuples()]})
    for k_ in VERDICTS:
        d_ = pd.Timestamp(k_[1])
        out_ = {}
        for side_, team_ in [("home", k_[2]), ("away", k_[3])]:
            prev = [e_ for e_ in by_team.get(team_, []) if e_["date"] < d_]
            if prev:
                e_ = max(prev, key=lambda x: x["date"])
                out_[side_] = {**e_, "date": e_["date"].strftime("%Y-%m-%d")}
        if out_:
            LAST_TIME[k_] = out_
    hr_ = H_.groupby("kind").agg(hit=("won", "mean"), expected=("p", "mean"), n=("won", "size"))
    BET_HISTORY_SUMMARY = {k: {"hit": float(100 * r.hit), "expected": float(100 * r.expected), "n": int(r.n)} for k, r in hr_.iterrows()}
    print(f"Bet history: {len(H_)} settled picks ({(H_['source'] == 'replay').sum()} rebuilt from the replay); "
          f"'last time out' available for {len(LAST_TIME)} upcoming matches. Hit rates vs what the model expected: "
          + ", ".join(f"{k} picks {v['hit']:.0f}% vs {v['expected']:.0f}%" for k, v in BET_HISTORY_SUMMARY.items()))
