# ===================== 2b. PLAYER MODEL: missing strength and its learned effect =====================
import statsmodels.api as sm
PLAYER_HALF_LIFE, WINDOW = 60, 365
P_FEATURES = ["own_attack_missing", "own_regulars_missing", "opp_defence_missing", "opp_regulars_missing"]

def team_features(g, force_out=frozenset(), squad_now=None, apps=None, confirmed=None):
    """Missing strength for every match of one team, using only earlier matches.
    Rows with player_id '__upcoming__' are future fixtures (no lineup yet).
    Players who have left the club are dropped (not counted as missing): either they have since appeared for
    another club (known at the time, so this also works for past matches), or, for upcoming fixtures, they are
    no longer in ESPN's current squad list (squad_now)."""
    g = g.sort_values("date")
    mt = g.drop_duplicates("event_id")[["event_id", "date", "comp"]].reset_index(drop=True)
    real = g[g["player_id"] != "__upcoming__"]
    players = real["player_id"].unique()
    mi, pi = pd.Index(mt["event_id"]), pd.Index(players)
    n, p = len(mt), len(players)
    S, A, C, Q, R = (np.zeros((n, p)) for _ in range(5))
    r, c = mi.get_indexer(real["event_id"]), pi.get_indexer(real["player_id"])
    S[r, c], A[r, c], C[r, c], Q[r, c] = real["starter"].values, (real["minutes"] > 0).values, real["contrib"].values, 1.0
    R[r, c] = (real["red"].values > 0)
    pos = real.groupby("player_id")["pos"].agg(lambda s: s.dropna().iloc[-1] if s.notna().any() else "")
    is_def = pos.reindex(players).isin(["G", "D"]).values.astype(float)
    names = real.drop_duplicates("player_id").set_index("player_id")["player"].reindex(players).values
    days = mt["date"].values.astype("datetime64[D]").astype(float)
    dd = days[:, None] - days[None, :]
    W = np.where((dd > 0) & (dd <= WINDOW), 0.5 ** (dd / PLAYER_HALF_LIFE), 0.0)
    upcoming = mt["event_id"].isin(g.loc[g["player_id"] == "__upcoming__", "event_id"]).values
    W[:, upcoming] = 0.0                       # a fixture not yet played is not an earlier match (v17 fix)
    with np.errstate(invalid="ignore", divide="ignore"):
        rate = np.nan_to_num((W @ S) / W.sum(axis=1)[:, None])
        att = W @ C
        att_share = np.nan_to_num(att / att.sum(axis=1, keepdims=True))
    # departures: appeared for another club after his last game for this one, or missing from the current squad list
    D = np.zeros((n, p))
    tid_ = g["team_id"].iloc[0]
    mdays = mt["date"].values.astype("datetime64[D]")
    if apps is not None:
        for j, pid in enumerate(players):
            a_ = apps.get(pid)
            if a_ is None:
                continue
            own = np.sort(a_[0][a_[1] == tid_]); other = np.sort(a_[0][a_[1] != tid_])
            if len(other) == 0 or len(own) == 0:
                continue
            last_own = own[np.clip(np.searchsorted(own, mdays) - 1, 0, None)]
            has_own = np.searchsorted(own, mdays) > 0
            nxt_other = other[np.clip(np.searchsorted(other, last_own, side="right"), 0, len(other) - 1)]
            D[:, j] = (has_own & (nxt_other > last_own) & (nxt_other < mdays)).astype(float)
    if squad_now is not None and upcoming.any():
        gone = ~np.isin(players, list(squad_now))
        D[np.ix_(upcoming, gone)] = 1.0
    keep = 1 - D
    imp_before = att_share + rate                                   # importance before removing departures (for the report)
    rate = rate * keep
    with np.errstate(invalid="ignore", divide="ignore"):
        att_k = att * keep
        att_share = np.nan_to_num(att_k / att_k.sum(axis=1, keepdims=True))
    played_idx = np.where(~upcoming)[0]
    prevA1, prevA2, prevQ1 = np.ones((n, p)), np.ones((n, p)), np.ones((n, p))
    suspended = np.zeros((n, p))
    comps = mt["comp"].values
    for k in range(n):
        before = played_idx[played_idx < k]                 # earlier PLAYED matches only (v17 fix)
        if len(before) >= 1:
            prevA1[k], prevQ1[k] = A[before[-1]], Q[before[-1]]
        if len(before) >= 2:
            prevA2[k] = A[before[-2]]
        same = before[comps[before] == comps[k]]
        if len(same):
            suspended[k] = R[same[-1]]
    out_now = ((((prevQ1 == 0) | ((prevA1 == 0) & (prevA2 == 0))) & (rate >= 0.5)) | (suspended > 0)).astype(float) * keep
    if force_out and upcoming.any():
        forced = np.isin(players, list(force_out))
        out_now[np.ix_(upcoming, forced)] = 1.0                       # injury flags (Fantasy PL)
        out_now *= keep
    if confirmed:                                                      # v27: official lineups are out for these fixtures
        for k in np.where(upcoming)[0]:
            xi_ = confirmed.get(str(mt.loc[k, "event_id"]))
            if xi_ and len(xi_) >= 11:
                out_now[k] = ((rate[k] >= 0.5) & ~np.isin(players, list(xi_))).astype(float) * keep[k]   # a regular who isn't starting
    with np.errstate(invalid="ignore", divide="ignore"):
        f = pd.DataFrame({"event_id": mt["event_id"], "prior_matches": (W > 0).sum(1),
                          "att": (att_share * out_now).sum(1),
                          "def": (rate * is_def * out_now).sum(1) / (rate * is_def).sum(1),
                          "reg": (rate * out_now).sum(1) / rate.sum(1)}).fillna(0.0)
    # v18: what actually happened at kickoff (played matches only): share of regular strength / attacking output not starting
    nonstart = (1 - S) * keep
    with np.errstate(invalid="ignore", divide="ignore"):
        f["act_reg"] = np.where(upcoming, np.nan, np.nan_to_num((rate * nonstart).sum(1) / rate.sum(1)))
        f["act_att"] = np.where(upcoming, np.nan, (att_share * nonstart).sum(1))
    imp = att_share + rate
    f["missing_names"] = [", ".join(names[np.argsort(-imp[k] * out_now[k])][: int(min(3, (imp[k] * out_now[k] > 0.05).sum()))])
                          if upcoming[k] else "" for k in range(n)]
    f["departed_names"] = [", ".join(names[np.argsort(-imp_before[k] * D[k])][: int(min(4, (imp_before[k] * D[k] > 0.15).sum()))])
                           if upcoming[k] else "" for k in range(n)]
    return f

def pair_features(feats, df):
    """Attach home and away missing strength to matches that have event_id, home_id and away_id."""
    h = feats.add_prefix("h_").rename(columns={"h_event_id": "event_id", "h_team_id": "home_id"})
    a = feats.add_prefix("a_").rename(columns={"a_event_id": "event_id", "a_team_id": "away_id"})
    return df.merge(h, on=["event_id", "home_id"], how="left").merge(a, on=["event_id", "away_id"], how="left")

def long_form(df):
    rows = []
    for side, opp, goals, exp in [("h", "a", "FTHG", "ExpHome"), ("a", "h", "FTAG", "ExpAway")]:
        rows.append(pd.DataFrame({"goals": df[goals].values, "offset": np.log(df[exp].values),
                                  "own_attack_missing": df[f"{side}_att"].values, "own_regulars_missing": df[f"{side}_reg"].values,
                                  "opp_defence_missing": df[f"{opp}_def"].values, "opp_regulars_missing": df[f"{opp}_reg"].values}))
    return pd.concat(rows, ignore_index=True)

ADJ_CAP_PATH = f"{SAVE_DIR}/adjustment_cap.json"
ADJ_CAP = json.load(open(ADJ_CAP_PATH)).get("cap") if os.path.exists(ADJ_CAP_PATH) else None

def multipliers(df, params):
    """How much to scale home and away expected goals for the missing strength in df (1 = no change)."""
    if params is None or df is None or len(df) == 0 or "h_att" not in df:
        return np.ones(len(df)), np.ones(len(df))
    ok = ((df["h_prior_matches"] >= 5) & (df["a_prior_matches"] >= 5)).fillna(False).values
    g = lambda col: df[col].fillna(0).values
    b = params
    fh = np.exp(b["own_attack_missing"] * g("h_att") + b["own_regulars_missing"] * g("h_reg")
                + b["opp_defence_missing"] * g("a_def") + b["opp_regulars_missing"] * g("a_reg"))
    fa = np.exp(b["own_attack_missing"] * g("a_att") + b["own_regulars_missing"] * g("a_reg")
                + b["opp_defence_missing"] * g("h_def") + b["opp_regulars_missing"] * g("h_reg"))
    fh, fa = np.where(ok, fh, 1.0), np.where(ok, fa, 1.0)
    if ADJ_CAP:                                   # cap switched on by the test in section 8a
        fh, fa = np.clip(fh, 1 - ADJ_CAP, 1 + ADJ_CAP), np.clip(fa, 1 - ADJ_CAP, 1 + ADJ_CAP)
    return fh, fa

def base_walk(lg, start, half_life, end=None):
    """Honest base-model predictions, one week at a time, using only earlier results."""
    out = []
    wk = (lg["Date"] - pd.to_timedelta(lg["Date"].dt.weekday, unit="D")).dt.normalize()
    sel = (lg["Date"] >= start) & ((lg["Date"] < end) if end is not None else True)
    for w in sorted(wk[sel].unique()):
        w = pd.Timestamp(w)
        train, games = lg[lg["Date"] < w], lg[(lg["Date"] >= w) & (lg["Date"] < w + pd.Timedelta(days=7))]
        counts = pd.concat([train["HomeTeam"], train["AwayTeam"]]).value_counts()
        known = set(counts[counts >= 5].index)
        games = games[games["HomeTeam"].isin(known) & games["AwayTeam"].isin(known)]
        if games.empty:
            continue
        m = fit_weighted(train, "FTHG", "FTAG", 0.01, half_life)
        rho = estimate_rho_ha(*shrunk_means(m, train), train)
        h, a = shrunk_means(m, games)
        out.append(games[["League", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"] + ODDS].assign(ExpHome=h, ExpAway=a, rho=rho))
    return out

coefs_live, coefs_bt, mf, up_feats = None, {}, pd.DataFrame(), pd.DataFrame()
if PLAYER_MODEL and len(lu):
    print("Measuring missing strength for every team (a minute or two)...")
    dummies = []
    up_events = espn_fx.copy()
    if len(euro_up) and "event_id" in euro_up:
        code_of = {v: k for k, v in EURO_CODES.items()}
        up_events = pd.concat([up_events, euro_up.assign(code=euro_up["Competition"].map(code_of))[["code", "event_id", "Date", "home_id", "away_id"]]],
                              ignore_index=True)
    for _, fx_ in up_events.iterrows():
        for side in ["home", "away"]:
            dummies.append({"comp": fx_["code"], "event_id": fx_["event_id"], "date": fx_["Date"], "team_id": fx_[f"{side}_id"],
                            "player_id": "__upcoming__", "player": "", "pos": "", "starter": False, "sub_in": False,
                            "sub_out": False, "minutes": 0, "contrib": 0.0, "red": 0})
    allrows = pd.concat([lu, pd.DataFrame(dummies)], ignore_index=True) if dummies else lu
    forced = fpl_out.groupby("team_id")["player_id"].apply(frozenset).to_dict() if len(fpl_out) else {}
    # every player's matchday-squad appearances, by club (to spot transfers between clubs in our data)
    ap = lu.dropna(subset=["player_id", "team_id"])
    apps = {pid: (grp["date"].values.astype("datetime64[D]"), grp["team_id"].values) for pid, grp in ap.groupby("player_id")}
    # v27: confirmed lineups for fixtures starting soon (published about 75 minutes before kickoff in the Premier League)
    CONFIRMED = {}
    if CONFIRMED_LINEUPS and len(up_events):
        soon_ = up_events
        if "Kickoff" in up_events:
            ko_ = pd.to_datetime(up_events["Kickoff"])
            now_ = pd.Timestamp.now("UTC").tz_convert(None)
            no_ko_today = ko_.isna() & (pd.to_datetime(up_events["Date"]).dt.normalize() == TODAY)      # European ties: no kickoff time stored
            soon_ = up_events[((ko_ - now_ <= pd.Timedelta(hours=CONFIRMED_WINDOW_HOURS)) & (ko_ - now_ >= pd.Timedelta(minutes=-30))) | no_ko_today]
        for r_ in soon_.itertuples():
            sm_ = espn_get(f"{ESPN_BASE}/{r_.code}/summary?event={r_.event_id}")
            if not sm_ or not sm_.get("rosters"):
                continue
            try:
                rows_ = parse_lineups(sm_, r_.code, {"id": r_.event_id, "competitions": sm_.get("header", {}).get("competitions", [{}])})
            except Exception:
                continue
            for t_, grp_ in pd.DataFrame(rows_).groupby("team_id") if rows_ else []:
                st_ = set(grp_.loc[grp_["starter"].astype(bool), "player_id"].astype(str))
                if len(st_) >= 11:
                    CONFIRMED.setdefault(str(t_), {})[str(r_.event_id)] = st_
        print(f"Confirmed lineups: {sum(len(v) for v in CONFIRMED.values())} team-sides already announced.")
    feats = pd.concat([team_features(g, forced.get(tid, frozenset()), squads.get(str(tid)), apps, CONFIRMED.get(str(tid))).assign(team_id=tid)
                       for tid, g in allrows.groupby("team_id")], ignore_index=True)
    mf = pair_features(feats, links[links["League"].isin(ESPN_LEAGUES.values())])
    up_feats = pair_features(feats, up_events[["event_id", "home_id", "away_id"]]) if len(up_events) else pd.DataFrame()

    # honest base predictions for learning the effects (cached; extended each run with newly finished weeks)
    BASE_PATH = f"{SAVE_DIR}/base_walkforward.csv"
    base = pd.read_csv(BASE_PATH, parse_dates=["Date"]) if os.path.exists(BASE_PATH) else pd.DataFrame()
    this_week = TODAY - pd.Timedelta(days=TODAY.weekday())
    new_parts = []
    for league in sorted(mf["League"].unique()):
        lg = league_frame(league)
        done_to = base.loc[base["League"] == league, "Date"].max() if len(base) else pd.NaT
        start = (done_to + pd.Timedelta(days=1)) if pd.notna(done_to) else mf.loc[mf["League"] == league, "Date"].min()
        start = start - pd.Timedelta(days=start.weekday()) if pd.notna(done_to) else start
        new_parts += base_walk(lg, start, SOLO.get(league, {}).get("half_life", 365), end=this_week)
    if new_parts:
        base = pd.concat([base] + new_parts, ignore_index=True).drop_duplicates(subset=["League", "Date", "HomeTeam", "AwayTeam"], keep="last")
        base.to_csv(BASE_PATH, index=False)
    d = base.merge(mf.drop(columns=["comp"], errors="ignore"), on=["League", "Date", "HomeTeam", "AwayTeam"])
    d = d[(d["h_prior_matches"] >= 5) & (d["a_prior_matches"] >= 5)]

    def fit_effects(rows):
        if len(rows) < 300:
            return None
        L = long_form(rows)
        return sm.GLM(L["goals"], L[P_FEATURES], family=sm.families.Poisson(), offset=L["offset"]).fit().params
    coefs_live = fit_effects(d)
    season_start = all_matches.loc[all_matches["Season"] == SEASONS[-1], "Date"].min()
    coefs_bt = {"Domestic": fit_effects(d[d["Date"] < season_start])}
    for lg_name, info in SOLO.items():
        start_ = info["data"].loc[info["data"]["Season"] == info["season"], "Date"].min()
        coefs_bt[info["group"]] = fit_effects(d[d["Date"] < start_]) if pd.notna(start_) else None
    if coefs_live is not None:
        print(f"Player effects learned from {len(d)} matches (% change in expected goals if that whole share were missing):")
        display((100 * (np.exp(coefs_live) - 1)).round(1).to_frame("Effect %"))
    else:
        print("Not enough matches yet to learn player effects; predictions run without them.")
