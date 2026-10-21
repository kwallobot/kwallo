# ===================== 2g. TACTICS AND MANAGERS: rolling style profiles, manager changes, tests =====================
# Style per team from its previous 6 matches (nothing from the match being predicted): possession, directness (accurate long
# balls per pass), set-piece share of xG, touches in the opposition box, pressing (tackles + interceptions per opponent pass),
# back-three formations (PitchAPI), and pressing intensity PPDA / deep completions (Understat, big five). Manager changes from
# BSD's coach records. Tested on goals first; all of it also feeds the machine-learning layer (section 9c).
import joblib, re
TAC_LONG = pd.DataFrame(columns=["Team", "Date"])
inv_pa = {f"{c}:{n}": our for our, (c, n) in {**PA_XG_LEAGUES, **PA_TACTIC_LEAGUES}.items()} if "PA_XG_LEAGUES" in globals() else {}
inv_pa.update({k_: v_[0] for k_, v_ in (PA_CUP_TACTICS.items() if "PA_CUP_TACTICS" in globals() else [])})     # v35: the European cups (throw-ins)
parts_t, THROW_ROWS, COUNT_ROWS = [], [], []
TEAM_FORM_PA = {}                                          # v35: our team name -> (date, formation) from PitchAPI
if len(PA_TACTICS):
    for key_, g_ in PA_TACTICS.groupby("league"):
        our = inv_pa.get(key_)
        if not our:
            continue
        f_ = euro[euro["Competition"] == our] if our in EURO_CODES.values() and len(euro) else league_frame(our)
        if f_ is None or not len(f_):
            continue                                              # v29: this league's results didn't load this run
        mp_ = map_by_fixtures(g_.rename(columns={"date": "Date", "home": "H", "away": "A"})[["Date", "H", "A"]],
                              f_[["Date", "HomeTeam", "AwayTeam"]].rename(columns={"HomeTeam": "H", "AwayTeam": "A"}))
        for r_ in g_.itertuples():
            st_ = json.loads(r_.stats) if isinstance(r_.stats, str) else {}
            gv = lambda k, i: (st_.get(k) or [np.nan, np.nan])[i]
            for i_, team_, opp_i, form_ in [(0, r_.home, 1, r_.f_home), (1, r_.away, 0, r_.f_away)]:
                if team_ not in mp_:
                    continue
                if isinstance(form_, str) and re.match(r"^\d(-\d)+$", form_.strip()):    # v35: each team's latest formation, for the pitch
                    d_f = pd.Timestamp(r_.date)
                    if mp_[team_] not in TEAM_FORM_PA or d_f > TEAM_FORM_PA[mp_[team_]][0]:
                        TEAM_FORM_PA[mp_[team_]] = (d_f, form_.strip())
                opp_name = r_.away if i_ == 0 else r_.home
                for stat_, key_ in [("offsides", "Offsides"), ("tackles", "matchstats.headers.tackles")]:          # v30
                    if pd.notna(gv(key_, i_)) and opp_name in mp_:
                        COUNT_ROWS.append({"League": our, "Team": mp_[team_], "Opp": mp_[opp_name], "Date": pd.Timestamp(r_.date).normalize(),
                                           "is_home": int(i_ == 0), "stat": stat_, "own": gv(key_, i_), "against": gv(key_, opp_i), "src": "pitchapi"})
                if pd.notna(gv("player_throws", i_)) and opp_name in mp_:
                    THROW_ROWS.append({"League": our, "Team": mp_[team_], "Opp": mp_[opp_name], "Date": pd.Timestamp(r_.date).normalize(), "is_home": int(i_ == 0),
                                       "own": gv("player_throws", i_), "against": gv("player_throws", opp_i)})
                passes, opp_passes = gv("passes", i_), gv("passes", opp_i)
                xg_ = gv("expected_goals", i_)
                parts_t.append({"Team": mp_[team_], "Date": pd.Timestamp(r_.date).normalize(), "poss": gv("BallPossesion", i_),
                                "direct": gv("long_balls_accurate", i_) / passes if passes else np.nan,
                                "setp": gv("expected_goals_set_play", i_) / xg_ if xg_ else np.nan, "box": gv("touches_opp_box", i_),
                                "press": (np.nan_to_num(gv("interceptions", i_)) + np.nan_to_num(gv("matchstats.headers.tackles", i_))) / opp_passes if opp_passes else np.nan,
                                "back3": float(str(form_ or "").startswith("3")) if form_ else np.nan,
                                "xg_per_shot": xg_ / gv("total_shots", i_) if gv("total_shots", i_) else np.nan,                    # v24: shot quality
                                "box_share": gv("shots_inside_box", i_) / gv("total_shots", i_) if gv("total_shots", i_) else np.nan,
                                "finishing": gv("expected_goals_on_target", i_) - xg_ if pd.notna(gv("expected_goals_on_target", i_)) and xg_ else np.nan})
if len(understat_teams) and "us_map" in globals():
    ut_ = understat_teams.copy()
    ut_["Team"] = [us_map.get((l_, t_), t_) for l_, t_ in zip(ut_["League"], ut_["team"])]
    parts_t.append(ut_.assign(Date=pd.to_datetime(ut_["date"]).dt.normalize())[["Team", "Date", "ppda", "ppda_allowed", "deep", "deep_allowed"]])
if parts_t:
    TAC_LONG = pd.concat([pd.DataFrame(p_) if isinstance(p_, list) else p_ for p_ in [pd.DataFrame([x for x in parts_t if isinstance(x, dict)])] + [x for x in parts_t if not isinstance(x, dict)]], ignore_index=True)
    TAC_LONG = TAC_LONG.groupby(["Team", "Date"], as_index=False).mean(numeric_only=True).sort_values("Date")
# v35: cards in ESPN's team statistics (saved from v35 on): fill in the European cups' earlier matches, newest first, time-limited
TS_BACKFILL_MINUTES = 8
TS_COLS_SAVED = ["totalTackles", "effectiveTackles", "offsides", "interceptions", "possessionPct", "totalShots", "shotsOnTarget", "wonCorners",
                 "foulsCommitted", "totalPasses", "yellowCards", "redCards"]
def _ts_missing(code_, have_, t0_, minutes_):
    """v35: team statistics for cup matches downloaded before v30 (when they weren't saved yet), newest first."""
    comp_ = EURO_CODES.get(code_)
    if not comp_ or not len(euro) or "event_id" not in euro:
        return []
    e_ = euro[(euro["Competition"] == comp_) & ~euro["event_id"].astype(str).isin(have_)].sort_values("Date", ascending=False)
    rows_ = []
    for r_ in e_.itertuples():
        if time.time() - t0_ > minutes_ * 60:
            break
        s_ = espn_get(f"{ESPN_BASE}/{code_}/summary?event={r_.event_id}", pause=0.3) or {}
        for tm_ in (s_.get("boxscore") or {}).get("teams") or []:
            st_ = {x_.get("name"): x_.get("displayValue") for x_ in tm_.get("statistics") or []}
            if st_:
                rows_.append({"event_id": str(r_.event_id), "date": str(pd.Timestamp(r_.Date))[:10], "comp": code_, "team_id": str((tm_.get("team") or {}).get("id")),
                              "team": (tm_.get("team") or {}).get("displayName"), "side": tm_.get("homeAway"),
                              **{k_: st_.get(k_, "na" if k_ in ("yellowCards", "redCards") else None) for k_ in TS_COLS_SAVED}})
    return rows_
def _ts_backfill(codes_, minutes_):
    t0_, n_ = time.time(), 0
    for code_ in codes_:
        tp_ = f"{SAVE_DIR}/lineups/{code_}_teamstats.csv"
        if time.time() - t0_ > minutes_ * 60:
            continue
        have_ = set(pd.read_csv(tp_, dtype=str)["event_id"]) if os.path.exists(tp_) else set()
        add_ = _ts_missing(code_, have_, t0_, minutes_)
        if add_:
            old_ = pd.read_csv(tp_, dtype=str) if os.path.exists(tp_) else pd.DataFrame()
            pd.concat([old_, pd.DataFrame(add_)], ignore_index=True).to_csv(tp_, index=False)
            n_ += len({r_["event_id"] for r_ in add_})
        if not os.path.exists(tp_):
            continue
        ts_ = pd.read_csv(tp_, dtype=str)
        for c_ in ("yellowCards", "redCards"):
            ts_[c_] = (ts_[c_] if c_ in ts_ else pd.Series(np.nan, index=ts_.index)).astype(object)    # text column (holds "na" markers)
        todo_ = ts_[ts_["yellowCards"].isna()].sort_values("date", ascending=False)["event_id"].drop_duplicates().tolist()
        got_ = {}
        for eid_ in todo_:
            if time.time() - t0_ > minutes_ * 60:
                break
            s_ = espn_get(f"{ESPN_BASE}/{code_}/summary?event={eid_}", pause=0.3) or {}
            for tm_ in (s_.get("boxscore") or {}).get("teams") or []:
                st_ = {x_.get("name"): x_.get("displayValue") for x_ in tm_.get("statistics") or []}
                got_[(str(eid_), str((tm_.get("team") or {}).get("id")))] = (st_.get("yellowCards", "na"), st_.get("redCards", "na"))
            if s_ and not got_.get((str(eid_), str(ts_.loc[ts_["event_id"] == str(eid_), "team_id"].iloc[0]))):
                got_[(str(eid_), "*")] = ("na", "na")           # no statistics for this match: don't ask again
            n_ += 1
        if got_:
            for i_, r_ in ts_.iterrows():
                v_ = got_.get((str(r_["event_id"]), str(r_["team_id"]))) or got_.get((str(r_["event_id"]), "*"))
                if v_ and pd.isna(r_["yellowCards"]):
                    ts_.at[i_, "yellowCards"], ts_.at[i_, "redCards"] = v_
            ts_.to_csv(tp_, index=False)
    return n_
if TS_BACKFILL_MINUTES > 0:
    try:
        n_bf_ = _ts_backfill(list(EURO_CODES), TS_BACKFILL_MINUTES)
        if n_bf_:
            print(f"ESPN team statistics: {n_bf_} earlier European cup matches filled in (statistics and cards; continues next run if any are left).")
    except Exception as e_:
        print("ESPN cards backfill skipped:", str(e_)[:80])

# v30: ESPN's team statistics (kept by the lineup download) for every ESPN league, in our team names
# v35: linked to our results by ESPN's match id (domestic links and the European cups), so every competition counts;
#      corners, cards, shots and fouls are kept too (TS_EXTRA), for the cups and leagues football-data.co.uk doesn't cover
_ev_names = {}
if "links" in globals() and len(links):
    for r_ in links.itertuples():
        _ev_names[str(r_.event_id)] = (r_.League, pd.Timestamp(r_.Date).normalize(), r_.HomeTeam, r_.AwayTeam)
for fr_ in (euro, euro_up if "euro_up" in globals() else pd.DataFrame()):
    if len(fr_) and "event_id" in fr_:
        for r_ in fr_.itertuples():
            _ev_names.setdefault(str(r_.event_id), (r_.Competition, pd.Timestamp(r_.Date).normalize(), r_.HomeTeam, r_.AwayTeam))
TS_COLS = {"wonCorners": ("HC", "AC"), "yellowCards": ("HY", "AY"), "redCards": ("HR", "AR"), "totalShots": ("HS", "AS"), "shotsOnTarget": ("HST", "AST"),
           "foulsCommitted": ("HF", "AF"), "totalTackles": ("HTK", "ATK"), "offsides": ("HO", "AO")}
ts_rows_ = []
for code_ in list(ESPN_LEAGUES) + list(ESPN_EXTRA_LEAGUES) + list(EURO_CODES):
    tp_ = f"{SAVE_DIR}/lineups/{code_}_teamstats.csv"
    if not os.path.exists(tp_):
        continue
    ts_ = checked_read(tp_, text=("event_id", "team_id", "team", "side", "comp"), num=("totalTackles", "offsides"), name=f"{code_}_teamstats")
    ts_ = ts_.drop_duplicates(["event_id", "team_id"])
    for c_ in TS_COLS:
        ts_[c_] = pd.to_numeric(ts_.get(c_), errors="coerce")
    for ev_id, gg in ts_.groupby("event_id"):
        if len(gg) != 2:
            continue
        h_, a_ = (gg[gg["side"] == "home"], gg[gg["side"] == "away"]) if set(gg["side"]) == {"home", "away"} else (gg.iloc[[0]], gg.iloc[[1]])
        if h_.empty or a_.empty:
            continue
        h_, a_ = h_.iloc[0], a_.iloc[0]
        d_ = pd.Timestamp(h_["date"]).tz_localize(None).normalize() if pd.Timestamp(h_["date"]).tzinfo is None else pd.Timestamp(h_["date"]).tz_convert(None).normalize()
        if str(ev_id) in _ev_names:
            league_, d_, hn, an = _ev_names[str(ev_id)]
        elif code_ in ESPN_LEAGUES:
            league_ = ESPN_LEAGUES[code_]
            hn, an = team_map.get((league_, h_["team"]), h_["team"]), team_map.get((league_, a_["team"]), a_["team"])
        else:
            continue                                              # not linked to one of our results
        for stat_, col_ in [("offsides", "offsides"), ("tackles", "totalTackles")]:
            if pd.notna(h_.get(col_)) and pd.notna(a_.get(col_)):
                COUNT_ROWS.append({"League": league_, "Team": hn, "Opp": an, "Date": d_, "is_home": 1, "stat": stat_, "own": float(h_[col_]), "against": float(a_[col_]), "src": "espn"})
                COUNT_ROWS.append({"League": league_, "Team": an, "Opp": hn, "Date": d_, "is_home": 0, "stat": stat_, "own": float(a_[col_]), "against": float(h_[col_]), "src": "espn"})
        row_ = {"Comp": league_, "Date": d_, "HomeTeam": hn, "AwayTeam": an, "espn": f"{code_}:{ev_id}"}
        for c_, (hc_, ac_) in TS_COLS.items():
            row_[hc_], row_[ac_] = h_.get(c_), a_.get(c_)
        ts_rows_.append(row_)
TS_EXTRA = pd.DataFrame(ts_rows_).drop_duplicates(["Date", "HomeTeam", "AwayTeam"]) if ts_rows_ else pd.DataFrame(columns=["Comp", "Date", "HomeTeam", "AwayTeam", "espn"])
print(f"ESPN team statistics linked to our results: {len(TS_EXTRA)} matches"
      + (f" ({int(TS_EXTRA['Comp'].isin(list(EURO_CODES.values())).sum())} in the European cups)" if len(TS_EXTRA) else "") + ".")
COUNT_LONG = (pd.DataFrame(COUNT_ROWS).sort_values(["src"], ascending=False).drop_duplicates(["League", "Team", "Date", "stat"]).sort_values("Date")
              if COUNT_ROWS else pd.DataFrame(columns=["League", "Team", "Opp", "Date", "is_home", "stat", "own", "against", "src"]))
print(f"Team counts for new markets: " + ", ".join(f"{s_} {int((COUNT_LONG['stat'] == s_).sum())} team-matches" for s_ in ["offsides", "tackles"]))
THROW_LONG = pd.DataFrame(THROW_ROWS).drop_duplicates(["Team", "Date"]).sort_values("Date") if THROW_ROWS else pd.DataFrame()
TAC_COLS = [c_ for c_ in ["poss", "direct", "setp", "box", "press", "back3", "ppda", "deep", "xg_per_shot", "box_share", "finishing"] if c_ in TAC_LONG]
if len(TAC_LONG):
    roll_ = TAC_LONG.groupby("Team")[TAC_COLS].transform(lambda s_: s_.rolling(6, min_periods=3).mean())
    TAC_ROLL = pd.concat([TAC_LONG[["Team", "Date"]], roll_], axis=1).sort_values("Date")
else:
    TAC_ROLL = pd.DataFrame(columns=["Team", "Date"] + TAC_COLS)

# manager timelines from BSD coach ids
MGR = pd.DataFrame(columns=["Team", "Date", "coach"])
if len(CTX_MATCH) and "home_coach" in CTX_MATCH:
    MGR = pd.concat([CTX_MATCH[["HomeTeam", "Date", "home_coach"]].set_axis(["Team", "Date", "coach"], axis=1),
                     CTX_MATCH[["AwayTeam", "Date", "away_coach"]].set_axis(["Team", "Date", "coach"], axis=1)]).dropna().sort_values("Date")
def new_manager(team_col, dates):
    """1 if the team's coach for this match took over within its last 6 matches (and someone else was in charge before)."""
    out_ = np.zeros(len(dates))
    by_t = {t_: g_ for t_, g_ in MGR.groupby("Team")}
    for i_, (t_, d_) in enumerate(zip(team_col, pd.to_datetime(dates))):
        g_ = by_t.get(t_)
        if g_ is None:
            continue
        upto = g_[g_["Date"] <= d_]
        if len(upto) < 2:
            continue
        now = upto["coach"].iloc[-1]
        prev = upto[upto["coach"] != now]
        if prev.empty:
            continue
        since = upto[upto["Date"] > prev["Date"].iloc[-1]]
        out_[i_] = float(len(since) <= 6)
    return out_

def _tac_lookup(teams, dates):
    q_ = pd.DataFrame({"_i": np.arange(len(teams)), "Team": list(teams), "Date": pd.to_datetime(dates).astype("datetime64[ns]")}).sort_values("Date")
    if TAC_ROLL.empty:
        return pd.DataFrame(index=np.arange(len(teams)), columns=TAC_COLS, dtype=float)
    r_ = TAC_ROLL.assign(Date=TAC_ROLL["Date"].astype("datetime64[ns]"), Team=TAC_ROLL["Team"].astype(str))
    q_["Team"] = q_["Team"].astype(str)
    m_ = pd.merge_asof(q_, r_, on="Date", by="Team", direction="backward", allow_exact_matches=False)
    return m_.set_index("_i").sort_index()[TAC_COLS]

def ml_features(df):
    """Every signal for the machine-learning layer, for any table of matches with model probabilities."""
    d_ = df.copy()
    for src_, dst_ in [("Competition", "League"), ("Home", "HomeTeam"), ("Away", "AwayTeam")]:
        if src_ in d_:
            d_ = d_.drop(columns=[src_]) if dst_ in d_ else d_.rename(columns={src_: dst_})
    d_ = d_.reset_index(drop=True)
    d_["Date"] = pd.to_datetime(d_["Date"]).dt.normalize()
    X = pd.DataFrame({"lp_h": np.log(d_["pH"] / d_["pD"]), "lp_a": np.log(d_["pA"] / d_["pD"]), "exp_h": d_["ExpHome"], "exp_a": d_["ExpAway"]})
    rf_ = rest_flags(d_)
    for k_, v_ in rf_.items():
        X[k_] = v_
    cx_ = ctx_lookup(d_) if "ctx_lookup" in globals() else pd.DataFrame({"derby": [False] * len(d_)}, index=d_.index)   # v31: context section not run
    X["derby"] = cx_["derby"].fillna(False).astype(float).values
    for k_, v_ in (weather_x(cx_).items() if "weather_x" in globals() else []):
        X[k_] = v_
    X["h_new_mgr"], X["a_new_mgr"] = new_manager(d_["HomeTeam"], d_["Date"]), new_manager(d_["AwayTeam"], d_["Date"])
    th_, ta_ = _tac_lookup(d_["HomeTeam"], d_["Date"]), _tac_lookup(d_["AwayTeam"], d_["Date"])
    for c_ in TAC_COLS:
        X[f"h_{c_}"], X[f"a_{c_}"] = th_[c_].values, ta_[c_].values
    if "poss" in TAC_COLS:
        X["poss_diff"] = X["h_poss"] - X["a_poss"]
    if "press" in TAC_COLS and "poss" in TAC_COLS:
        X["press_vs_poss"] = X["h_press"] * X["a_poss"] - X["a_press"] * X["h_poss"]
    return X.astype(float)

# ---- tests on goals: the new-manager bounce, and style matchups ----
tac_report = []
if "base" in globals() and len(base) and TEST_GOAL_LEVEL_AND_REST:
    bb_ = base.dropna(subset=["ExpHome", "ExpAway"]).reset_index(drop=True)
    season_start = all_matches.loc[all_matches["Season"] == SEASONS[-1], "Date"].min()
    nh_, na_ = new_manager(bb_["HomeTeam"], bb_["Date"]), new_manager(bb_["AwayTeam"], bb_["Date"])
    th_, ta_ = _tac_lookup(bb_["HomeTeam"], bb_["Date"]), _tac_lookup(bb_["AwayTeam"], bb_["Date"])
    from scipy.stats import poisson as _po2
    rng_t = np.random.default_rng(8)
    def goal_test(name, cols_h, cols_a):
        Lg = pd.concat([pd.DataFrame({"g": bb_["FTHG"], "off": np.log(bb_["ExpHome"]), **cols_h, "D": bb_["Date"]}),
                        pd.DataFrame({"g": bb_["FTAG"], "off": np.log(bb_["ExpAway"]), **cols_a, "D": bb_["Date"]})], ignore_index=True).dropna()
        cs = list(cols_h.keys())
        tr_, ts_ = Lg[Lg["D"] < season_start], Lg[Lg["D"] >= season_start]
        if len(tr_) < 500 or len(ts_) < 200 or tr_[cs].abs().sum().min() < 10:
            tac_report.append({"Test": name, "Result": f"not enough data yet ({len(tr_)} earlier, {len(ts_)} later rows)"}); return
        mu_ = tr_[cs].mean(); sd_ = tr_[cs].std().replace(0, 1)
        z = lambda d: (d[cs] - mu_) / sd_
        prm = sm.GLM(tr_["g"], z(tr_), family=sm.families.Poisson(), offset=tr_["off"]).fit().params
        l0 = -_po2.logpmf(ts_["g"], np.exp(ts_["off"])); l1 = -_po2.logpmf(ts_["g"], np.exp(ts_["off"] + z(ts_).values @ prm.values))
        d_ = np.asarray(l1 - l0)
        pct = 100 * (np.array([rng_t.choice(d_, len(d_)).mean() for _ in range(2000)]) < 0).mean()
        tac_report.append({"Test": name, "Change in log loss": float(d_.mean()), "Better in % of reshuffles": float(pct),
                           "Result": "passes (used via the machine-learning layer)" if (pct >= 95 and d_.mean() < 0) else "no clear effect",
                           "Effects (per 1 SD)": ", ".join(f"{c} {100 * (np.exp(v) - 1):+.1f}%" for c, v in prm.items())})
    goal_test("New-manager bounce", {"own_new": nh_, "opp_new": na_}, {"own_new": na_, "opp_new": nh_})
    if "poss" in TAC_COLS:
        goal_test("Style: possession and pressing matchup", {"own_poss": th_["poss"].values, "opp_press": ta_["press"].values if "press" in TAC_COLS else np.zeros(len(bb_))},
                  {"own_poss": ta_["poss"].values, "opp_press": th_["press"].values if "press" in TAC_COLS else np.zeros(len(bb_))})
        goal_test("Style: directness and set pieces", {"own_direct": th_["direct"].values, "own_setp": th_["setp"].values},
                  {"own_direct": ta_["direct"].values, "own_setp": ta_["setp"].values})
    if "xg_per_shot" in TAC_COLS:
        goal_test("Shot quality and finishing", {"own_xgps": th_["xg_per_shot"].values, "own_fin": th_["finishing"].values, "opp_xgps": ta_["xg_per_shot"].values},
                  {"own_xgps": ta_["xg_per_shot"].values, "own_fin": ta_["finishing"].values, "opp_xgps": th_["xg_per_shot"].values})
    if "ppda" in TAC_COLS:
        goal_test("Pressing intensity (PPDA, big five)", {"own_ppda": th_["ppda"].values, "opp_ppda": ta_["ppda"].values},
                  {"own_ppda": ta_["ppda"].values, "opp_ppda": th_["ppda"].values})
    print(f"Tactics data: {TAC_LONG['Team'].nunique() if len(TAC_LONG) else 0} teams with style profiles; manager records for {MGR['Team'].nunique() if len(MGR) else 0} teams.")
    display(pd.DataFrame(tac_report).round(4))
    EXTRA_TABLES_EARLY = list(globals().get("EXTRA_TABLES_EARLY", [])) + [{"title": "Tactics and managers", "hint": "Learned before this season, tested on this season's matches.", "rows": json.loads(pd.DataFrame(tac_report).to_json(orient="records"))}]

# ---- the machine-learning layer, if it passed its test on an earlier run ----
ML_PATH = f"{SAVE_DIR}/ml_layer.json"
ML = json.load(open(ML_PATH)) if os.path.exists(ML_PATH) else None
def ml_apply(t_):
    """v23: the model's own log-odds plus the learned corrections."""
    X_ = ml_features(t_)
    for c_ in ML["features"]:
        if c_ not in X_:
            X_[c_] = np.nan
    Z_ = ((X_[ML["features"]] - np.array(ML["mu"])) / np.array(ML["sd"])).fillna(0).values
    W_ = np.array(ML["W"])
    lh, la = X_["lp_h"].values + Z_ @ W_[0], X_["lp_a"].values + Z_ @ W_[1]
    z = np.stack([lh, np.zeros_like(lh), la], axis=1); z = z - z.max(axis=1, keepdims=True); e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)
health("Tactics and managers", True, f"{TAC_LONG['Team'].nunique() if len(TAC_LONG) else 0} style profiles; machine-learning layer {'ON' if ML else 'off'}")
