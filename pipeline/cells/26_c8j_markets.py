# ===================== 8c. MORE MARKETS: shots, fouls, half-time, player props, first goalscorer, penalties, throw-ins =====================
# Each market gets an honest calibration test on past matches (predictions made with earlier data only). Only markets whose
# corrected probabilities are within 3 points in every well-filled band are "trusted" and can appear in the Match verdict.
# All show fair odds (1 / probability); we have no bookmaker prices for these markets.
from scipy.stats import poisson as _pp
MARKETS, MARKET_TRUST, market_tables = {}, {}, []
def nb_over(mu, k, line):
    return over_prob(mu, k, line) if np.isfinite(k) and k > 0 else 1 - _pp.cdf(np.floor(line), mu)
def est_k(y, mu):
    """Spread as a variance-to-mean ratio (what over_prob expects): 1 = Poisson, above 1 = more spread out."""
    y, mu = np.asarray(y, float), np.asarray(mu, float)
    return float(np.clip(np.mean((y - mu) ** 2) / max(np.mean(mu), 1e-9), 1.0, 10.0))
def band_check(name, p, y, dates, groups=None):
    """Isotonic correction learned on the earlier half, checked on the later half (same rule as the player probabilities)."""
    p, y, dates = np.asarray(p, float), np.asarray(y, float), np.asarray(dates)
    ok_ = np.isfinite(p) & np.isfinite(y); p, y, dates = p[ok_], y[ok_], dates[ok_]      # v31: skip incomplete matches
    r_ = calibrate_player(name, p, y, dates, min_cases=500) if len(p) >= 500 else _small_check(name, p, y)
    MARKET_TRUST[name] = r_
    if r_.get("table"):
        market_tables.append({"title": f"{name}: calibration", "hint": f"{'Trusted' if r_['trusted'] else 'Experimental'}; worst band gap {r_.get('worst_gap', 0):.1f} points.", "rows": r_["table"]})
    return r_

_band_check_overall = band_check
def band_check(name, p, y, dates, groups=None):
    r_ = _band_check_overall(name, p, y, dates)
    if groups is not None and len(groups) == len(p):
        grp_ = np.array([cal_group(c_) for c_ in groups])
        p_a, y_a, d_a = np.asarray(p, float), np.asarray(y, float), np.asarray(dates)
        for gg_ in sorted(set(grp_)):
            sel_ = grp_ == gg_
            if sel_.sum() >= 300:
                n_tab = len(market_tables)
                _band_check_overall(f"{name}|{gg_}", p_a[sel_], y_a[sel_], d_a[sel_])
                del market_tables[n_tab:]                          # per-group tables stay out of the scorecard (labels are listed instead)
    return r_
def _small_check(name, p, y):
    """For markets with fewer than 2,000 cases: plain calibration bands, no correction."""
    p, y = np.asarray(p, float), np.asarray(y, float)
    if len(p) < 300:
        return {"trusted": False, "n": len(p)}
    tab, worst = [], 0.0
    for lo, hi in zip([0, 0.3, 0.45, 0.55, 0.7], [0.3, 0.45, 0.55, 0.7, 1.01]):
        sel = (p >= lo) & (p < hi)
        if sel.sum() >= 30:
            gap = 100 * (p[sel].mean() - y[sel].mean())
            tol = band_tolerance(y[sel].mean(), sel.sum())
            tab.append({"Predicted chance": f"{int(100 * lo)}-{min(100, int(100 * hi))}%", "Cases": int(sel.sum()), "Predicted %": float(100 * p[sel].mean()),
                        "Actually happened %": float(100 * y[sel].mean()), "Gap (points)": float(gap), "Allowed (points)": float(tol)})
            if sel.sum() >= 100:
                worst = max(worst, abs(gap) - tol + 3.0)
    brier, naive = np.mean((p - y) ** 2), np.mean((y.mean() - y) ** 2)
    passed = bool(worst <= 3.0 and brier < naive)
    r_ = {"passed": passed, "trusted": stable_trust(name, passed), "worst_gap": float(max(worst, 0)), "skill": float(1 - brier / naive), "n": int(len(p)), "table": tab}
    print(f"{name}: {'passed' if passed else 'failed'} this run (worst band {max(worst, 0):.1f} vs allowance 3.0{'' if passed or brier < naive else ' - no skill'}), "
          f"skill {100 * r_['skill']:+.1f}% -> {'TRUSTED' if r_['trusted'] else 'experimental'}.")
    return r_
HIDE_MARKETS = {"Goalkeeper 3+ saves"}                       # v27: no skill yet, so not shown
def add_market(key_, label, p, family, trust_name, code=None, corrected=False):
    if trust_name in HIDE_MARKETS:
        return
    comp_ = key_[0] if isinstance(key_, tuple) else None
    if not corrected:
        p = apply_player_cal(trust_name, p, comp_)          # v32: the match's league group correction if it has one
    tn_ = group_key(trust_name, comp_, MARKET_TRUST)
    tr_ = MARKET_TRUST.get(tn_, {}).get("trusted") or (tn_ == "Goalscorers" and scorer_calibration.get("trusted"))
    if trust_name in ("Goalscorers", "Assisters") and f"{trust_name}|{cal_group(comp_)}" in GROUP_TRUST:
        tr_ = GROUP_TRUST[f"{trust_name}|{cal_group(comp_)}"]
    MARKETS.setdefault(key_, []).append({"Bet": label, "p": float(p), "fair": float(1 / max(p, 1e-6)), "family": family,
                                          "trusted": bool(tr_), "test": trust_name, "code": code})

MT_PATH = f"{SAVE_DIR}/market_tests.json"
if not RUN_REPLAYS and os.path.exists(MT_PATH):            # v27: quick runs reuse the weekly run's tests and corrections
    saved_m = json.load(open(MT_PATH))
    MARKET_TRUST.update(saved_m.get("trust", {})); PLAYER_CAL.update(saved_m.get("cal", {}))
upc_m = pd.concat([x for x in [pred_dom, pred_eu] if len(x)], ignore_index=True) if (len(pred_dom) or len(pred_eu)) else pd.DataFrame()
season_start_m = all_matches.loc[all_matches["Season"] == SEASONS[-1], "Date"].min()
keyof = lambda r_: (r_["Competition"], str(r_["Date"])[:10], r_["Home"], r_["Away"])

# ---------- 1. team shots, shots on target and fouls (main leagues) ----------
STATS = {"shots": ("HS", "AS", "shots"), "sot": ("HST", "AST", "shots on target"), "fouls": ("HF", "AF", "fouls")}
for st_key, (ch, ca, word) in STATS.items():
    rows_p, rows_y, rows_d, rows_l = {"tot": [], "h": [], "a": []}, {"tot": [], "h": [], "a": []}, [], []
    live_parts = []
    for lg_ in LEAGUES.values():
        lg = all_matches[all_matches["League"] == lg_].dropna(subset=[ch, ca])
        if len(lg) < 400:
            continue
        lines_ = {"tot": np.floor((lg[ch] + lg[ca]).median()) + 0.5, "h": np.floor(lg[ch].median()) + 0.5, "a": np.floor(lg[ca].median()) + 0.5}
        test_ = lg[lg["Date"] >= season_start_m]
        wk_ = (test_["Date"] - pd.to_timedelta(test_["Date"].dt.weekday, unit="D")).dt.normalize()
        for w_ in (sorted(wk_.unique()) if RUN_REPLAYS else []):
            w_ = pd.Timestamp(w_)
            tr_ = lg[lg["Date"] < w_]
            games = test_[(test_["Date"] >= w_) & (test_["Date"] < w_ + pd.Timedelta(days=7))]
            known = set(pd.concat([tr_["HomeTeam"], tr_["AwayTeam"]]).value_counts().loc[lambda s: s >= 5].index)
            games = games[games["HomeTeam"].isin(known) & games["AwayTeam"].isin(known)]
            if games.empty or len(tr_) < 300:
                continue
            m_ = fit_weighted(tr_, ch, ca, 0.05, 365)
            mh_, ma_ = shrunk_means(m_, games)
            fh_, fa_ = shrunk_means(m_, tr_.tail(600))
            k_ = est_k(np.r_[tr_.tail(600)[ch], tr_.tail(600)[ca]], np.r_[fh_, fa_])
            for part, mu_, y_ in [("tot", mh_ + ma_, games[ch] + games[ca]), ("h", mh_, games[ch]), ("a", ma_, games[ca])]:
                rows_p[part] += list(nb_over(mu_, k_, lines_[part]))
                rows_y[part] += list((y_.values > lines_[part]).astype(float))
            rows_d += [np.datetime64(d_) for d_ in games["Date"]]; rows_l += [lg_] * len(games)
        # live
        fx_ = upc_m[upc_m["Competition"] == lg_]
        if len(fx_):
            m_ = fit_weighted(lg, ch, ca, 0.05, 365)
            g_ = fx_.rename(columns={"Home": "HomeTeam", "Away": "AwayTeam"})
            known = set(pd.concat([lg["HomeTeam"], lg["AwayTeam"]]))
            g_ = g_[g_["HomeTeam"].isin(known) & g_["AwayTeam"].isin(known)]
            if len(g_):
                mh_, ma_ = shrunk_means(m_, g_)
                fh_, fa_ = shrunk_means(m_, lg.tail(600))
                k_ = est_k(np.r_[lg.tail(600)[ch], lg.tail(600)[ca]], np.r_[fh_, fa_])
                live_parts.append((g_, mh_, ma_, k_, lines_))
    for part, lab in [("tot", f"Total {word}"), ("h", f"Home {word}"), ("a", f"Away {word}")]:
        if len(rows_p[part]) >= 300:
            band_check(f"{lab} over the league line", rows_p[part], rows_y[part], np.array(rows_d), rows_l)
    for g_, mh_, ma_, k_, lines_ in live_parts:
        for i_, r_ in enumerate(g_.to_dict("records")):
            k0 = (r_["Competition"], str(r_["Date"])[:10], r_["HomeTeam"], r_["AwayTeam"])
            add_market(k0, f"Over {lines_['tot']} total {word} (expected {mh_[i_] + ma_[i_]:.1f})", nb_over(mh_[i_] + ma_[i_], k_, lines_["tot"]), st_key, f"Total {word} over the league line", code=f"TOT|{ch}|{ca}|{lines_['tot']}")
            add_market(k0, f"{r_['HomeTeam']} over {lines_['h']} {word} (expected {mh_[i_]:.1f})", nb_over(mh_[i_], k_, lines_["h"]), st_key, f"Home {word} over the league line", code=f"H|{ch}|{lines_['h']}")
            add_market(k0, f"{r_['AwayTeam']} over {lines_['a']} {word} (expected {ma_[i_]:.1f})", nb_over(ma_[i_], k_, lines_["a"]), st_key, f"Away {word} over the league line", code=f"A|{ca}|{lines_['a']}")

# ---------- 1b. v37f: halves (shots, shots on target, fouls, corners, passes) and full-match passes, from PitchAPI ----------
# The same method as above, on PitchAPI's figures for every league it covers: each team's figure for and against (weighted towards
# recent matches), the league's usual line, replayed week by week this season with earlier data only; trusted only if calibrated.
# Halves come from PitchAPI's own 1st / 2nd-half statistics only (exact). v37i: the earlier fallback that counted shots from the
# shot-by-shot data is gone: it overcounted (off-target shots carry an xG-on-target value too, and the shot file can hold a match
# twice), so a match without PitchAPI's half figures yet simply has none until the re-read reaches it.
HALF_KEYS = {"shots": ("total_shots", "TotalShots"), "sot": ("shots_on_target", "ShotsOnTarget"), "fouls": ("fouls", "Fouls"),
             "corners": ("corners", "Corners", "corner_kicks"), "passes": ("passes", "Passes")}
HALF_WORD = {"shots": "shots", "sot": "shots on target", "fouls": "fouls", "corners": "corners", "passes": "passes"}
def _nid(x):
    try:
        return str(int(float(x)))
    except Exception:
        return ""
def half_frames():
    """Per league (our names): one row per match with each statistic's 1st- and 2nd-half figures (home and away), and full-match passes."""
    if "PA_TACTICS" not in globals() or not len(PA_TACTICS):
        return {}
    inv_ = {f"{c}:{n}": our for our, (c, n) in {**PA_XG_LEAGUES, **PA_TACTIC_LEAGUES}.items()}
    out = {}
    for key_, g_ in PA_TACTICS.groupby("league"):
        our = inv_.get(key_)
        if not our:
            continue
        f_ = league_frame(our)
        if f_ is None or not len(f_):
            continue
        mp_ = map_by_fixtures(g_.rename(columns={"date": "Date", "home": "H", "away": "A"})[["Date", "H", "A"]],
                              f_[["Date", "HomeTeam", "AwayTeam"]].rename(columns={"HomeTeam": "H", "AwayTeam": "A"}))
        rows_ = []
        for r_ in g_.itertuples():
            if r_.home not in mp_ or r_.away not in mp_:
                continue
            st_ = json.loads(r_.stats) if isinstance(r_.stats, str) else {}
            sh_ = json.loads(r_.stats_h) if isinstance(getattr(r_, "stats_h", None), str) and r_.stats_h.startswith("{") else {}
            pick = lambda d_, ks_: next((d_[k] for k in ks_ if k in d_), None)
            row = {"League": our, "Date": pd.Timestamp(r_.date).normalize(), "HomeTeam": mp_[r_.home], "AwayTeam": mp_[r_.away]}
            full_p = pick(st_, HALF_KEYS["passes"])
            if full_p:
                row["passes_h"], row["passes_a"] = full_p
            for sk_, ks_ in HALF_KEYS.items():
                for h_ in ("1", "2"):
                    v_ = pick(sh_.get(h_, {}), ks_)
                    if v_ is not None:
                        row[f"{sk_}{h_}_h"], row[f"{sk_}{h_}_a"] = v_
            rows_.append(row)
        if rows_:
            out[our] = pd.DataFrame(rows_).sort_values("Date").drop_duplicates(["Date", "HomeTeam", "AwayTeam"]).reset_index(drop=True)
    return out

def team_stat_markets(frames, ch, ca, word, st_key, parts=("tot", "h", "a"), min_n=300):
    """Over / under the league's usual line for a team statistic (columns ch, ca) in each league frame: the weekly replay with
    its calibration test, then this week's fixtures. The same method as section 1."""
    rows_p, rows_y, rows_d, rows_l = {p_: [] for p_ in parts}, {p_: [] for p_ in parts}, [], []
    live_parts = []
    for lg_, lg in frames.items():
        if ch not in lg or ca not in lg:
            continue
        lg = lg.dropna(subset=[ch, ca])
        if len(lg) < min_n:
            continue
        lines_ = {"tot": np.floor((lg[ch] + lg[ca]).median()) + 0.5, "h": np.floor(lg[ch].median()) + 0.5, "a": np.floor(lg[ca].median()) + 0.5}
        test_ = lg[lg["Date"] >= season_start_m]
        wk_ = (test_["Date"] - pd.to_timedelta(test_["Date"].dt.weekday, unit="D")).dt.normalize()
        for w_ in (sorted(wk_.unique()) if RUN_REPLAYS else []):
            w_ = pd.Timestamp(w_)
            tr_ = lg[lg["Date"] < w_]
            games = test_[(test_["Date"] >= w_) & (test_["Date"] < w_ + pd.Timedelta(days=7))]
            known = set(pd.concat([tr_["HomeTeam"], tr_["AwayTeam"]]).value_counts().loc[lambda s: s >= 5].index)
            games = games[games["HomeTeam"].isin(known) & games["AwayTeam"].isin(known)]
            if games.empty or len(tr_) < 200:
                continue
            m_ = fit_weighted(tr_, ch, ca, 0.05, 365)
            mh_, ma_ = shrunk_means(m_, games)
            fh_, fa_ = shrunk_means(m_, tr_.tail(600))
            k_ = est_k(np.r_[tr_.tail(600)[ch], tr_.tail(600)[ca]], np.r_[fh_, fa_])
            for part, mu_, y_ in [("tot", mh_ + ma_, games[ch] + games[ca]), ("h", mh_, games[ch]), ("a", ma_, games[ca])]:
                if part in parts:
                    rows_p[part] += list(nb_over(mu_, k_, lines_[part]))
                    rows_y[part] += list((y_.values > lines_[part]).astype(float))
            rows_d += [np.datetime64(d_) for d_ in games["Date"]]; rows_l += [lg_] * len(games)
        fx_ = upc_m[upc_m["Competition"] == lg_] if len(upc_m) else pd.DataFrame()
        if len(fx_):
            m_ = fit_weighted(lg, ch, ca, 0.05, 365)
            g_ = fx_.rename(columns={"Home": "HomeTeam", "Away": "AwayTeam"})
            known = set(pd.concat([lg["HomeTeam"], lg["AwayTeam"]]))
            g_ = g_[g_["HomeTeam"].isin(known) & g_["AwayTeam"].isin(known)]
            if len(g_):
                mh_, ma_ = shrunk_means(m_, g_)
                fh_, fa_ = shrunk_means(m_, lg.tail(600))
                k_ = est_k(np.r_[lg.tail(600)[ch], lg.tail(600)[ca]], np.r_[fh_, fa_])
                live_parts.append((g_, mh_, ma_, k_, lines_))
    labs = {"tot": f"Total {word}", "h": f"Home {word}", "a": f"Away {word}"}
    for part in parts:
        if len(rows_p[part]) >= 300:
            band_check(f"{labs[part]} over the league line", rows_p[part], rows_y[part], np.array(rows_d), rows_l)
    n_live = 0
    for g_, mh_, ma_, k_, lines_ in live_parts:
        for i_, r_ in enumerate(g_.to_dict("records")):
            k0 = (r_["Competition"], str(r_["Date"])[:10], r_["HomeTeam"], r_["AwayTeam"])
            if "tot" in parts:
                add_market(k0, f"Over {lines_['tot']} total {word} (expected {mh_[i_] + ma_[i_]:.1f})", nb_over(mh_[i_] + ma_[i_], k_, lines_["tot"]), st_key, f"Total {word} over the league line", code=f"TOT|{ch}|{ca}|{lines_['tot']}")
            if "h" in parts:
                add_market(k0, f"{r_['HomeTeam']} over {lines_['h']} {word} (expected {mh_[i_]:.1f})", nb_over(mh_[i_], k_, lines_["h"]), st_key, f"Home {word} over the league line", code=f"H|{ch}|{lines_['h']}")
            if "a" in parts:
                add_market(k0, f"{r_['AwayTeam']} over {lines_['a']} {word} (expected {ma_[i_]:.1f})", nb_over(ma_[i_], k_, lines_["a"]), st_key, f"Away {word} over the league line", code=f"A|{ca}|{lines_['a']}")
            n_live += 1
    return n_live

# v37i: the half-shots tests and corrections saved before the fix were learned on miscounted data: ignore them until a weekly run
#       re-tests (those markets show as experimental, uncorrected, meanwhile)
HALVES_V = 2
_mt_saved = json.load(open(MT_PATH)) if os.path.exists(MT_PATH) else {}
if _mt_saved.get("halves_v") != HALVES_V:
    for d_ in (MARKET_TRUST, PLAYER_CAL):
        for k_ in [k for k in list(d_) if "-half shots" in str(k)]:
            d_.pop(k_, None)
try:
    HALF_FRAMES = half_frames()
    n_hf = {lg_: int(f_.filter(regex=r"^shots1_h$").notna().sum().sum()) for lg_, f_ in HALF_FRAMES.items()}
    print(f"Half-by-half statistics (PitchAPI): {sum(len(f_) for f_ in HALF_FRAMES.values())} matches in {len(HALF_FRAMES)} leagues; "
          f"1st-half shots known for {sum(n_hf.values())}; corners by half for "
          f"{sum(int(f_['corners1_h'].notna().sum()) if 'corners1_h' in f_ else 0 for f_ in HALF_FRAMES.values())}.")
    for h_, hw_ in (("1", "1st-half"), ("2", "2nd-half")):
        for sk_ in ("shots", "sot", "corners", "passes", "fouls"):
            team_stat_markets(HALF_FRAMES, f"{sk_}{h_}_h", f"{sk_}{h_}_a", f"{hw_} {HALF_WORD[sk_]}", f"h{h_}_{sk_}", parts=("tot",) if sk_ == "fouls" else ("tot", "h", "a"))
    team_stat_markets(HALF_FRAMES, "passes_h", "passes_a", "passes", "passes")
except Exception as ex_:
    import traceback; traceback.print_exc()
    print("Half-by-half markets: skipped this run (the other markets are unaffected).")

# ---------- 2. half-time markets ----------
HT_SHARE = {}
for lg_ in LEAGUES.values():
    d_ = all_matches[(all_matches["League"] == lg_) & (all_matches["Date"] >= TODAY - pd.Timedelta(days=730))].dropna(subset=["HTHG", "HTAG"])
    if len(d_) >= 200:
        HT_SHARE[lg_] = float((d_["HTHG"] + d_["HTAG"]).sum() / max((d_["FTHG"] + d_["FTAG"]).sum(), 1))
def ht_probs(eh, ea, f_):
    gh1 = _pp.pmf(np.arange(10), f_ * eh)[:, None] * _pp.pmf(np.arange(10), f_ * ea)[None, :]
    gh2 = _pp.pmf(np.arange(10), (1 - f_) * eh)[:, None] * _pp.pmf(np.arange(10), (1 - f_) * ea)[None, :]
    hh, aa = np.indices(gh1.shape)
    ht = {"H": gh1[hh > aa].sum(), "D": gh1[hh == aa].sum(), "A": gh1[hh < aa].sum()}
    both_halves = (1 - gh1[0, 0]) * (1 - gh2[0, 0])
    htft = {}
    for (i1, j1), p1 in np.ndenumerate(gh1):
        if p1 < 1e-7:
            continue
        for (i2, j2), p2 in np.ndenumerate(gh2):
            if p2 < 1e-7:
                continue
            fh_ = "H" if i1 + i2 > j1 + j2 else ("D" if i1 + i2 == j1 + j2 else "A")
            hr_ = "H" if i1 > j1 else ("D" if i1 == j1 else "A")
            htft[hr_ + fh_] = htft.get(hr_ + fh_, 0) + p1 * p2
    return ht, both_halves, htft
if RUN_REPLAYS and RUN_BACKTEST and bt_scored is not None and len(bt_scored) and HT_SHARE:
    bh_ = bt_scored[bt_scored["Competition"].isin(HT_SHARE)].merge(all_matches[["League", "Date", "HomeTeam", "AwayTeam", "HTHG", "HTAG"]].rename(
        columns={"League": "Competition", "HomeTeam": "Home", "AwayTeam": "Away"}), on=["Competition", "Date", "Home", "Away"]).dropna(subset=["HTHG", "HTAG", "ExpHome"])
    pd_, yd_, pb_, yb_, dd_, cc_ = [], [], [], [], [], []
    for r_ in bh_.itertuples():
        ht, bh2, _ = ht_probs(r_.ExpHome, r_.ExpAway, HT_SHARE[r_.Competition])
        pd_.append(ht["D"]); yd_.append(float(r_.HTHG == r_.HTAG))
        pb_.append(bh2); yb_.append(float((r_.HTHG + r_.HTAG > 0) and (r_.FTHG + r_.FTAG - r_.HTHG - r_.HTAG > 0)))
        dd_.append(np.datetime64(r_.Date)); cc_.append(r_.Competition)
    if len(pd_) >= 300:
        band_check("Half-time draw", pd_, yd_, np.array(dd_), cc_)
        band_check("Goal in both halves", pb_, yb_, np.array(dd_), cc_)
for r_ in upc_m.to_dict("records"):
    f_ = HT_SHARE.get(r_["Competition"])
    if f_ is None:
        continue
    ht, bh2, htft = ht_probs(r_["ExpHome"], r_["ExpAway"], f_)
    k0 = keyof(r_)
    add_market(k0, "Half-time draw", ht["D"], "halftime", "Half-time draw", code="HT_D")
    add_market(k0, f"{r_['Home']} leading at half-time", ht["H"], "halftime", "Half-time draw", code="HT_H")
    add_market(k0, "A goal in both halves", bh2, "halftime_both", "Goal in both halves", code="BOTHHALVES")
    top_ = max(htft.items(), key=lambda kv: kv[1])
    add_market(k0, f"Half-time/full-time: {dict(H=r_['Home'], D='draw', A=r_['Away'])[top_[0][0]]} / {dict(H=r_['Home'], D='draw', A=r_['Away'])[top_[0][1]]} (likeliest)",
               top_[1], "halftime", "Half-time draw")

# ---------- 3. player props, first goalscorer, time of first goal, penalties ----------
PROP_PRIOR = {"shots": {"F": 2.2, "M": 1.0, "D": 0.5, "G": 0.0}, "sot": {"F": 0.9, "M": 0.35, "D": 0.15, "G": 0.0}, "fouls": {"F": 1.0, "M": 1.2, "D": 1.1, "G": 0.1}}
def sot_faced(team, opp, before):
    """Expected shots on target a team faces: the opponent's recent shots on target and the team's recent shots on target conceded."""
    a_, b_ = TEAM_RES.get(opp), TEAM_RES.get(team)
    if a_ is None or b_ is None:
        return np.nan
    a_ = a_[a_["Date"] < before]["SOTF"].dropna().tail(10); b_ = b_[b_["Date"] < before]["SOTA"].dropna().tail(10)
    return float((a_.mean() + b_.mean()) / 2) if len(a_) >= 4 and len(b_) >= 4 else np.nan
def prop_rates(team_id, before, scale=1.0, faced=np.nan):
    """Per-player expected shots, shots on target, fouls and saves for one match (earlier data only)."""
    g = L[(L["team_id"] == str(team_id)) & (L["date"] < before) & (L["date"] >= before - pd.Timedelta(days=365))] if "L" in globals() else pd.DataFrame()
    if g.empty:
        return pd.DataFrame()
    g = g.assign(w=0.5 ** ((before - g["date"]).dt.days / 180))
    for c_ in ["shots", "sot", "fouls", "saves"]:
        g[c_] = pd.to_numeric(g.get(c_), errors="coerce").fillna(0)
    agg_ = g.assign(**{f"{c}_w": g[c] * g["w"] for c in ["shots", "sot", "fouls", "saves", "minutes"]}).groupby("player_id").agg(
        Player=("player", "last"), Pos=("pos", "last"), shots=("shots_w", "sum"), sot=("sot_w", "sum"), fouls=("fouls_w", "sum"), saves=("saves_w", "sum"), mins=("minutes_w", "sum"))
    last10 = g.drop_duplicates("event_id").sort_values("date").tail(10)["event_id"]
    rec_ = g[g["event_id"].isin(last10)]
    n10 = max(rec_["event_id"].nunique(), 1)
    agg_["p_start"] = rec_.groupby("player_id")["starter"].sum().reindex(agg_.index).fillna(0) / n10
    agg_["p_sub"] = rec_.groupby("player_id")["sub_in"].sum().reindex(agg_.index).fillna(0) / n10
    agg_["exp_min"] = agg_["p_start"] * 82 + agg_["p_sub"] * 22
    grp_ = agg_["Pos"].map(line_of) if "line_of" in globals() else agg_["Pos"].astype(str).str.upper().str[:1].where(lambda s: s.isin(list("GDMF")), "M")   # v33
    k90 = 5.0
    for c_ in ["shots", "sot", "fouls"]:
        prior_ = grp_.map(PROP_PRIOR[c_])
        agg_[f"lam_{c_}"] = (agg_[c_] + k90 * prior_) / (agg_["mins"] / 90 + k90) * agg_["exp_min"] / 90 * (scale if c_ != "fouls" else 1.0)
    g["conceded"] = pd.to_numeric(g.get("conceded"), errors="coerce").fillna(0)
    cons_ = g.assign(cw=g["conceded"] * g["w"]).groupby("player_id")["cw"].sum().reindex(agg_.index).fillna(0)
    save_rate = (agg_["saves"] + 0.70 * 10) / (agg_["saves"] + cons_ + 10)              # shrunk toward a typical 70% save rate
    has_saves = (agg_["saves"] > 0) | (cons_ > 0)                         # v26: keepers with saves actually recorded in our data
    agg_["lam_saves"] = np.where((grp_ == "G") & np.isfinite(faced) & has_saves, faced * save_rate, 0.0) * agg_["exp_min"] / 90
    return agg_[agg_["exp_min"] > 20]
pen_rate = {}
if "events_all" in globals() and len(events_all):
    ev_pen = events_all[events_all["type"].astype(str).str.startswith("Penalty - Scored")].groupby("comp")["event_id"].count()
    ev_n = events_all.groupby("comp")["event_id"].nunique()
    pen_rate = (ev_pen / ev_n).dropna().to_dict()
code_of_comp = {**{v: k for k, v in ESPN_LEAGUES.items()}, **{v: k for k, v in EURO_CODES.items()}}
GOAL_SHARE_30 = 30 / 90
if "events_all" in globals() and len(events_all):
    gm_ = pd.to_numeric(events_all.loc[events_all["type"].astype(str).str.match(r"^(Goal|Penalty - Scored|Own Goal)"), "minute"], errors="coerce").dropna()
    if len(gm_) >= 500:
        GOAL_SHARE_30 = float((gm_ <= 30).mean())           # v25: real timing (usually about 30%, not 33%)
print(f"Share of goals scored by minute 30: {100 * GOAL_SHARE_30:.1f}%")
# replay for calibration: recent replayed matches with lineups
if RUN_REPLAYS and "base" in globals() and len(base) and "mf" in globals() and len(mf) and "L" in globals():
    bt_p = base.merge(mf[["League", "Date", "HomeTeam", "AwayTeam", "event_id", "home_id", "away_id"]], on=["League", "Date", "HomeTeam", "AwayTeam"]).sort_values("Date").tail(900)
    # v28: one row per player per match (the lineup data can list a player twice in a match, which broke this replay)
    act_ = L[["event_id", "player_id"]].assign(**{c_: pd.to_numeric(L[c_], errors="coerce").fillna(0) if c_ in L else 0.0
                                                   for c_ in ["shots", "sot", "fouls", "saves"]}).groupby(["event_id", "player_id"]).max()
    first_goal = {}
    if "events_all" in globals() and len(events_all):
        gl_ = events_all[events_all["type"].astype(str).str.match(r"^(Goal|Penalty - Scored)")].dropna(subset=["minute"]).sort_values("minute")
        for eid_, g_ in gl_.groupby("event_id"):
            first_goal[str(eid_)] = (str(g_["players"].iloc[0]).split("|")[0], float(g_["minute"].iloc[0]))
    P = {k: [] for k in ["shot1", "shot2", "sot1", "foul1", "save3", "fg", "fg30", "pen"]}
    Y = {k: [] for k in P}; Dd = {k: [] for k in P}; Gl = {k: [] for k in P}
    for r_ in bt_p.itertuples():
        d_ = pd.Timestamp(r_.Date)
        lam_tot = r_.ExpHome + r_.ExpAway
        fg_ = first_goal.get(str(r_.event_id))
        all_lam = []
        for tid_, lam_t, me_, op_ in [(str(r_.home_id), r_.ExpHome, r_.HomeTeam, r_.AwayTeam), (str(r_.away_id), r_.ExpAway, r_.AwayTeam, r_.HomeTeam)]:
            pr_ = prop_rates(tid_, d_, 1.0, faced=sot_faced(me_, op_, d_))
            if pr_.empty:
                continue
            for pid_, row_ in pr_.iterrows():
                a_ = act_.loc[(str(r_.event_id), pid_)] if (str(r_.event_id), pid_) in act_.index else None
                if a_ is None:
                    continue
                for k_, p_, y_ in [("shot1", 1 - np.exp(-row_.lam_shots), a_["shots"] >= 1), ("shot2", 1 - np.exp(-row_.lam_shots) * (1 + row_.lam_shots), a_["shots"] >= 2),
                                   ("sot1", 1 - np.exp(-row_.lam_sot), a_["sot"] >= 1), ("foul1", 1 - np.exp(-row_.lam_fouls), a_["fouls"] >= 1)]:
                    P[k_].append(p_); Y[k_].append(float(y_)); Dd[k_].append(np.datetime64(d_)); Gl[k_].append(r_.League)
                if row_.lam_saves > 0:
                    P["save3"].append(1 - _pp.cdf(2, row_.lam_saves)); Y["save3"].append(float(a_["saves"] >= 3)); Dd["save3"].append(np.datetime64(d_)); Gl["save3"].append(r_.League)
        if fg_ is not None or lam_tot > 0:
            P["fg30"].append(1 - np.exp(-lam_tot * GOAL_SHARE_30)); Y["fg30"].append(float(fg_ is not None and fg_[1] <= 30)); Dd["fg30"].append(np.datetime64(d_)); Gl["fg30"].append(r_.League)
        rate_ = pen_rate.get(code_of_comp.get(r_.League, ""), np.nan)
        if np.isfinite(rate_):
            P["pen"].append(1 - np.exp(-rate_)); Y["pen"].append(float(any(str(t_).startswith("Penalty - Scored") for t_ in
                                                                     events_all.loc[events_all["event_id"].astype(str) == str(r_.event_id), "type"]))); Dd["pen"].append(np.datetime64(d_)); Gl["pen"].append(r_.League)
    names_ = {"shot1": "Player 1+ shot", "shot2": "Player 2+ shots", "sot1": "Player 1+ shot on target", "foul1": "Player 1+ foul committed",
              "save3": "Goalkeeper 3+ saves", "fg30": "First goal within 30 minutes", "pen": "A penalty scored"}
    for k_, nm_ in names_.items():
        if len(P[k_]) >= 300:
            band_check(nm_, P[k_], Y[k_], np.array(Dd[k_]), Gl[k_])
# live player props and first goalscorer
pm_ids = []
if "fixtures" in globals() and len(fixtures) and "home_id" in fixtures:
    pm_ids.append(fixtures.rename(columns={"League": "Competition", "HomeTeam": "Home", "AwayTeam": "Away"})[["Competition", "Home", "Away", "home_id", "away_id"]])
if len(euro_up) and "home_id" in euro_up:
    pm_ids.append(euro_up.rename(columns={"HomeTeam": "Home", "AwayTeam": "Away"})[["Competition", "Home", "Away", "home_id", "away_id"]])
pmx = upc_m.merge(pd.concat(pm_ids).dropna(subset=["home_id"]).drop_duplicates(["Competition", "Home", "Away"]), on=["Competition", "Home", "Away"]) if pm_ids else pd.DataFrame()
for r_ in pmx.to_dict("records"):
    k0 = keyof(r_)
    lam_tot = r_["ExpHome"] + r_["ExpAway"]
    add_market(k0, "First goal within 30 minutes", (1 - np.exp(-lam_tot * GOAL_SHARE_30)), "timing", "First goal within 30 minutes")
    rate_ = pen_rate.get(code_of_comp.get(r_["Competition"], ""), np.nan)
    if np.isfinite(rate_):
        add_market(k0, "A penalty scored in the match", (1 - np.exp(-rate_)), "penalty", "A penalty scored")
    sc_ = SCORERS.get(k0, {}) if "SCORERS" in globals() else {}
    lam_players = []
    for side_, tid_ in [("home", r_["home_id"]), ("away", r_["away_id"])]:
        me_, op_ = (r_["Home"], r_["Away"]) if side_ == "home" else (r_["Away"], r_["Home"])
        pr_ = prop_rates(str(tid_), TODAY + pd.Timedelta(days=1), 1.0, faced=sot_faced(me_, op_, TODAY + pd.Timedelta(days=1)))
        sq_ = squads.get(str(tid_)) if squads else None
        if len(pr_) and sq_:
            pr_ = pr_[pr_.index.isin(sq_)]
        if pr_.empty:
            continue
        top_s = pr_.sort_values("lam_shots", ascending=False).head(2)
        for p_ in top_s.itertuples():
            add_market(k0, f"{p_.Player} 1+ shot on target", (1 - np.exp(-p_.lam_sot)), "player_props", "Player 1+ shot on target", code=f"PL|sot|1|{p_.Player}")
            add_market(k0, f"{p_.Player} 2+ shots", (1 - np.exp(-p_.lam_shots) * (1 + p_.lam_shots)), "player_props", "Player 2+ shots", code=f"PL|shots|2|{p_.Player}")
        top_f = pr_.sort_values("lam_fouls", ascending=False).head(1)
        for p_ in top_f.itertuples():
            add_market(k0, f"{p_.Player} 1+ foul committed", (1 - np.exp(-p_.lam_fouls)), "player_props", "Player 1+ foul committed", code=f"PL|fouls|1|{p_.Player}")
        gk_ = pr_[pr_["lam_saves"] > 0].sort_values("p_start", ascending=False).head(1)
        for p_ in gk_.itertuples():
            add_market(k0, f"{p_.Player} 3+ saves", (1 - _pp.cdf(2, p_.lam_saves)), "player_props", "Goalkeeper 3+ saves", code=f"PL|saves|3|{p_.Player}")
    for side_ in ("home", "away"):
        for p_ in (sc_.get(side_) or [])[:3]:
            lam_i = -np.log(max(1 - p_["p"], 1e-6))
            lam_players.append((p_["Player"], lam_i))
    for nm_, lam_i in sorted(lam_players, key=lambda x: -x[1])[:2]:
        add_market(k0, f"{nm_} to score the first goal", (lam_i / max(lam_tot, 1e-6)) * (1 - np.exp(-lam_tot)), "first_scorer", "Goalscorers", corrected=True)

# ---------- 4. throw-ins (PitchAPI leagues): per-league lines, each side's recent throw-ins, blended toward the league average ----------
if "THROW_LONG" in globals() and len(THROW_LONG) >= 600 and "League" in THROW_LONG:
    tl_ = THROW_LONG.copy()
    tl_[["own_r", "against_r"]] = tl_.groupby("Team")[["own", "against"]].transform(lambda s_: s_.shift(1).rolling(8, min_periods=4).mean())
    hm_ = tl_[tl_["is_home"] == 1].merge(tl_[["Team", "Date", "own_r", "against_r"]].rename(columns={"Team": "Opp", "own_r": "o_own_r", "against_r": "o_against_r"}),
                                          on=["Opp", "Date"]).dropna(subset=["own_r", "against_r", "o_own_r", "o_against_r"])
    hm_["total"] = hm_["own"] + hm_["against"]
    lg_avg = hm_.groupby("League")["total"].transform(lambda s_: s_.shift(1).expanding(min_periods=20).mean())
    raw_mu = (hm_["own_r"] + hm_["o_against_r"]) / 2 + (hm_["o_own_r"] + hm_["against_r"]) / 2
    hm_["mu"] = 0.7 * raw_mu + 0.3 * lg_avg.fillna(raw_mu)                 # v26: blended toward the league's own average
    THROW_LINES = (np.floor(hm_.groupby("League")["total"].median()) + 0.5).to_dict()   # v26: each league its own line
    hm_["line"] = hm_["League"].map(THROW_LINES)
    k_thr = est_k(hm_["total"], hm_["mu"])
    if RUN_REPLAYS and len(hm_) >= 300:
        band_check("Total throw-ins over the league line", np.array([nb_over(m_, k_thr, l_) for m_, l_ in zip(hm_["mu"], hm_["line"])]),
                   (hm_["total"] > hm_["line"]).astype(float).values, hm_["Date"].values.astype("datetime64[D]"), hm_["League"].values)
    latest_ = tl_.groupby("Team")[["own", "against"]].apply(lambda d_: d_.tail(8).mean()).to_dict("index")
    team_league = tl_.groupby("Team")["League"].last().to_dict()
    lg_mean = hm_.groupby("League")["total"].mean().to_dict()
    for r_ in upc_m.to_dict("records"):
        h_, a_ = latest_.get(r_["Home"]), latest_.get(r_["Away"])
        lg_ = team_league.get(r_["Home"])
        if h_ and a_ and lg_ in THROW_LINES:
            mu_ = 0.7 * ((h_["own"] + a_["against"]) / 2 + (a_["own"] + h_["against"]) / 2) + 0.3 * lg_mean.get(lg_, 0)
            add_market(keyof(r_), f"Over {THROW_LINES[lg_]} total throw-ins (expected {mu_:.1f})", nb_over(mu_, k_thr, THROW_LINES[lg_]), "throwins",
                       "Total throw-ins over the league line", code=f"THROW|{THROW_LINES[lg_]}")
    print(f"Throw-ins: {len(THROW_LONG)} team-matches; lines by league: " + ", ".join(f"{k} {v}" for k, v in THROW_LINES.items()))
if RUN_REPLAYS:
    json.dump({"trust": {k: {kk: vv for kk, vv in v.items() if kk != "table"} for k, v in MARKET_TRUST.items()}, "cal": PLAYER_CAL, "halves_v": HALVES_V},
              open(MT_PATH, "w"), default=float)
# ---------- 5. v30: offsides and tackles (team counts from PitchAPI and ESPN): total and each team, each league's own line ----------
def count_market(stat_, label_, family_):
    if "COUNT_LONG" not in globals() or not len(COUNT_LONG):
        return
    cl_ = COUNT_LONG[COUNT_LONG["stat"] == stat_].dropna(subset=["own", "against"]).copy()     # v31: matches missing the count
    if len(cl_) < 600:
        print(f"{label_.capitalize()}: {len(cl_)} team-matches so far; the market needs about 600 to be tested.")
        return
    cl_[["own_r", "against_r"]] = cl_.groupby("Team")[["own", "against"]].transform(lambda s_: s_.shift(1).rolling(8, min_periods=4).mean())
    hm_ = cl_[cl_["is_home"] == 1].merge(cl_[["Team", "Date", "own_r", "against_r"]].rename(columns={"Team": "Opp", "own_r": "o_own_r", "against_r": "o_against_r"}),
                                          on=["Opp", "Date"]).dropna(subset=["own_r", "against_r", "o_own_r", "o_against_r"])
    if len(hm_) < 300:
        return
    hm_["total"] = hm_["own"] + hm_["against"]
    lg_avg_h = hm_.groupby("League")["own"].transform(lambda s_: s_.shift(1).expanding(min_periods=20).mean())
    lg_avg_a = hm_.groupby("League")["against"].transform(lambda s_: s_.shift(1).expanding(min_periods=20).mean())
    hm_["mu_h"] = 0.7 * (hm_["own_r"] + hm_["o_against_r"]) / 2 + 0.3 * lg_avg_h.fillna(hm_["own_r"])
    hm_["mu_a"] = 0.7 * (hm_["o_own_r"] + hm_["against_r"]) / 2 + 0.3 * lg_avg_a.fillna(hm_["o_own_r"])
    lines_t = (np.floor(hm_.groupby("League")["total"].median()) + 0.5).to_dict()
    lines_h = (np.floor(hm_.groupby("League")["own"].median()) + 0.5).to_dict()
    lines_a = (np.floor(hm_.groupby("League")["against"].median()) + 0.5).to_dict()
    k_t = est_k(hm_["total"], hm_["mu_h"] + hm_["mu_a"]); k_h = est_k(hm_["own"], hm_["mu_h"]); k_a = est_k(hm_["against"], hm_["mu_a"])
    dates_ = hm_["Date"].values.astype("datetime64[D]")
    if RUN_REPLAYS:
        band_check(f"Total {label_} over the league line", np.array([nb_over(a + b, k_t, lines_t[l]) for a, b, l in zip(hm_["mu_h"], hm_["mu_a"], hm_["League"])]),
                   (hm_["total"] > hm_["League"].map(lines_t)).astype(float).values, dates_, hm_["League"].values)
        band_check(f"Home {label_} over the league line", np.array([nb_over(a, k_h, lines_h[l]) for a, l in zip(hm_["mu_h"], hm_["League"])]),
                   (hm_["own"] > hm_["League"].map(lines_h)).astype(float).values, dates_, hm_["League"].values)
        band_check(f"Away {label_} over the league line", np.array([nb_over(a, k_a, lines_a[l]) for a, l in zip(hm_["mu_a"], hm_["League"])]),
                   (hm_["against"] > hm_["League"].map(lines_a)).astype(float).values, dates_, hm_["League"].values)
    latest_ = cl_.groupby("Team")[["own", "against"]].apply(lambda d_: d_.tail(8).mean()).to_dict("index")
    team_lg = cl_.groupby("Team")["League"].last().to_dict()
    lgm_h, lgm_a = hm_.groupby("League")["own"].mean().to_dict(), hm_.groupby("League")["against"].mean().to_dict()
    n_ = 0
    for r_ in upc_m.to_dict("records"):
        h_, a_ = latest_.get(r_["Home"]), latest_.get(r_["Away"])
        lg_ = r_["Competition"] if r_["Competition"] in lines_t else team_lg.get(r_["Home"])
        if not h_ or not a_ or lg_ not in lines_t:
            continue
        mh = 0.7 * (h_["own"] + a_["against"]) / 2 + 0.3 * lgm_h.get(lg_, h_["own"])
        ma = 0.7 * (a_["own"] + h_["against"]) / 2 + 0.3 * lgm_a.get(lg_, a_["own"])
        k0 = keyof(r_)
        add_market(k0, f"Over {lines_t[lg_]} total {label_} (expected {mh + ma:.1f})", nb_over(mh + ma, k_t, lines_t[lg_]), family_,
                   f"Total {label_} over the league line", code=f"CNT|{stat_}|tot|{lines_t[lg_]}")
        add_market(k0, f"{r_['Home']} over {lines_h[lg_]} {label_} (expected {mh:.1f})", nb_over(mh, k_h, lines_h[lg_]), family_,
                   f"Home {label_} over the league line", code=f"CNT|{stat_}|home|{lines_h[lg_]}")
        add_market(k0, f"{r_['Away']} over {lines_a[lg_]} {label_} (expected {ma:.1f})", nb_over(ma, k_a, lines_a[lg_]), family_,
                   f"Away {label_} over the league line", code=f"CNT|{stat_}|away|{lines_a[lg_]}")
        n_ += 1
    print(f"{label_.capitalize()}: {len(cl_)} team-matches; priced for {n_} upcoming matches.")
count_market("offsides", "offsides", "offsides")
count_market("tackles", "tackles", "tackles")

# ---------- 6. v30: player tackles (PitchAPI's per-player statistics): switches on once its calibration test passes ----------
PLAYER_TACKLES_PRIOR = 1.6           # tackles per 90 of a typical outfield player (shrinkage target)
PLP_ = f"{SAVE_DIR}/pitchapi_players.csv"
if os.path.exists(PLP_) and len(PA_TACTICS) if "PA_TACTICS" in globals() else False:
    pp_ = checked_read(PLP_, text=("match_id", "team_id", "player_id", "player"), num=("tackles", "minutes"), name="pitchapi_players").dropna(subset=["tackles", "minutes"])
    pp_ = pp_[pp_["minutes"] > 0]
    pcm_ = checked_read(f"{SAVE_DIR}/pitchapi_matches.csv", text=("id", "league", "home", "away", "home_id", "away_id"), name="pitchapi_matches")
    if len(pp_) >= 3000 and "home_id" in pcm_:
        pp_ = pp_.merge(pcm_[["id", "league", "date", "home", "away", "home_id", "away_id"]].rename(columns={"id": "match_id"}), on="match_id", how="inner")
        pp_["Date"] = pd.to_datetime(pp_["date"]).dt.normalize()
        pp_["team_name"] = np.where(pp_["team_id"] == pp_["home_id"], pp_["home"], np.where(pp_["team_id"] == pp_["away_id"], pp_["away"], None))
        pp_ = pp_.dropna(subset=["team_name"]).sort_values("Date").reset_index(drop=True)
        cum_t_ = pp_.groupby("player_id")["tackles"].cumsum() - pp_["tackles"]          # before this match
        cum_m_ = pp_.groupby("player_id")["minutes"].cumsum() - pp_["minutes"]
        pp_["per90_prev"] = (cum_t_ + 5 * PLAYER_TACKLES_PRIOR) / (cum_m_ / 90 + 5)        # shrunk toward a typical player
        pp_["min_prev"] = pp_.groupby("player_id")["minutes"].transform(lambda s_: s_.shift(1).rolling(6, min_periods=2).mean())
        test_ = pp_.dropna(subset=["per90_prev", "min_prev"])
        lam_ = test_["per90_prev"] * test_["min_prev"] / 90
        if RUN_REPLAYS and len(test_) >= 2000:
            band_check("Player 1+ tackle", (1 - np.exp(-lam_)).values, (test_["tackles"] >= 1).astype(float).values, test_["Date"].values.astype("datetime64[D]"), test_["league"].values)
            band_check("Player 2+ tackles", (1 - np.exp(-lam_) * (1 + lam_)).values, (test_["tackles"] >= 2).astype(float).values, test_["Date"].values.astype("datetime64[D]"), test_["league"].values)
        last_ = pp_.groupby(["team_name", "player"]).agg(per90=("per90_prev", "last"), mins=("minutes", lambda s_: s_.tail(6).mean()), n=("minutes", "size"),
                                                         last_date=("Date", "max"))
        last_ = last_[(last_["n"] >= 3) & (last_["last_date"] >= TODAY - pd.Timedelta(days=45))]
        names_pa = {}
        if "map_by_fixtures" in globals():
            for key_, g_ in pcm_.assign(Date=pd.to_datetime(pcm_["date"])).groupby("league"):
                our_ = inv_pa.get(key_) if "inv_pa" in globals() else None
                if our_:
                    names_pa.update(map_by_fixtures(g_.rename(columns={"home": "H", "away": "A"})[["Date", "H", "A"]],
                                                    league_frame(our_)[["Date", "HomeTeam", "AwayTeam"]].rename(columns={"HomeTeam": "H", "AwayTeam": "A"})))
        ours_to_pa = {v: k for k, v in names_pa.items()}
        n_pt = 0
        for r_ in upc_m.to_dict("records"):
            for team_ in (r_["Home"], r_["Away"]):
                pa_name = ours_to_pa.get(team_, team_)
                if pa_name not in last_.index.get_level_values(0):
                    continue
                cand_ = last_.loc[pa_name].assign(lam=lambda d_: d_["per90"] * d_["mins"] / 90).sort_values("lam", ascending=False).head(2)
                for pl_, row_ in cand_.iterrows():
                    add_market(keyof(r_), f"{pl_} 2+ tackles", 1 - np.exp(-row_["lam"]) * (1 + row_["lam"]), "player_props", "Player 2+ tackles",
                               code=f"PT|2|{pl_}")
                    n_pt += 1
        print(f"Player tackles: {len(pp_)} player-matches stored; priced for {n_pt} players.")
    else:
        print(f"Player tackles: {len(pp_)} player-matches so far; the model needs about 3,000 (the download continues each run).")

grp_rows_ = [{"Market": k.split("|")[0], "Group": CAL_GROUP_NAMES.get(k.split("|")[1], k.split("|")[1]), "Label": "Trusted" if v.get("trusted") else "Experimental",
              "Worst band gap": v.get("worst_gap")} for k, v in MARKET_TRUST.items() if "|" in k]
grp_rows_ += [{"Market": k.split("|")[0], "Group": CAL_GROUP_NAMES.get(k.split("|")[1], k.split("|")[1]), "Label": "Trusted" if v else "Experimental", "Worst band gap": None}
              for k, v in GROUP_TRUST.items()]
if grp_rows_:
    market_tables.append({"title": "Calibration by league group", "hint": "Each market's correction and trust label, learned separately for each group of leagues (300+ cases).",
                          "rows": sorted(grp_rows_, key=lambda r: (r["Market"], r["Group"]))})
    print(f"Calibration by league group: {sum(r['Label'] == 'Trusted' for r in grp_rows_)} of {len(grp_rows_)} market-group pairs trusted.")
print(f"More markets: priced for {len(MARKETS)} matches; trusted tests: " + ", ".join(k for k, v in MARKET_TRUST.items() if v.get("trusted")) + ".")
EXTRA_TABLES_EARLY = list(globals().get("EXTRA_TABLES_EARLY", [])) + market_tables
