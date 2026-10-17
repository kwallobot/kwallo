# ===================== 2d. IMPACT RATINGS: player strength that travels with the player =====================
# Each match is split into stints (same 22 players on the pitch). A player's rating is how the goal difference per 90
# minutes changes with him on the pitch, accounting for teammates and opponents, shrunk toward 0 when evidence is thin.
# Ratings are refitted every 4 weeks using only earlier matches; team strength = the ratings of its regular eleven.
from scipy.sparse.linalg import lsqr
IMP_PATH = f"{SAVE_DIR}/impact_adjustment.json"
IMPACT = json.load(open(IMP_PATH)) if os.path.exists(IMP_PATH) else {"on": False}
IMPACT_HALF_LIFE, IMPACT_DAMP = 365, 6.0

def build_stints(lu_, events_):
    """One row per stint: date, duration, home/away players on the pitch, goals for each side."""
    ev_by = {k: g.sort_values("minute") for k, g in events_.groupby("event_id")} if len(events_) else {}
    rows = []
    for eid, g in lu_.groupby("event_id"):
        sides = g.dropna(subset=["side"]).groupby("side")["team_id"].first()
        if "home" not in sides or "away" not in sides:
            continue
        tid = {"home": sides["home"], "away": sides["away"]}
        team_of = dict(zip(g["player_id"], g["team_id"]))
        on = {s: set(g.loc[(g["team_id"] == tid[s]) & g["starter"], "player_id"]) for s in ("home", "away")}
        sub_in = set(g.loc[g["sub_in"], "player_id"])
        ev = ev_by.get(eid)
        bounds, changes, goals = [0], [], []
        if ev is not None:
            for r in ev.itertuples():
                m_ = r.minute if pd.notna(r.minute) else None
                ps = [p for p in str(r.players).split("|") if p and p != "nan"]
                if m_ is None:
                    continue
                if r.type.startswith("Substitution") and len(ps) >= 2:
                    pin = [p for p in ps if p in sub_in]
                    pout = [p for p in ps if p not in sub_in]
                    if pin and pout:
                        changes.append((m_, team_of.get(pin[0]), pout[0], pin[0])); bounds.append(m_)
                elif r.type.startswith("Red Card") and ps:
                    changes.append((m_, team_of.get(ps[0]), ps[0], None)); bounds.append(m_)
                elif r.type.startswith("Own Goal") and ps:
                    goals.append((m_, "away" if team_of.get(ps[0]) == tid["home"] else "home"))
                elif r.type.startswith("Goal") or r.type.startswith("Penalty - Scored"):
                    goals.append((m_, "home" if str(r.team_id) == str(tid["home"]) else "away"))
        end = max([90] + [b for b in bounds] + [m for m, _ in goals])
        if ev is None:                                   # no minute data: one stint, goals from the players' tallies
            gh = g.loc[g["team_id"] == tid["home"], "goals"].sum(); ga = g.loc[g["team_id"] == tid["away"], "goals"].sum()
            rows.append((eid, g["date"].iloc[0], 90.0, tuple(on["home"]), tuple(on["away"]), gh, ga))
            continue
        cuts = sorted(set(bounds + [end]))
        ci = 0
        changes = sorted((c_ for c_ in changes if c_[1] is not None), key=lambda c_: c_[0])
        for a_, b_ in zip(cuts[:-1], cuts[1:]):
            while ci < len(changes) and changes[ci][0] <= a_:
                _, team_, p_out, p_in = changes[ci]
                s_ = "home" if team_ == tid["home"] else "away"
                on[s_].discard(p_out)
                if p_in:
                    on[s_].add(p_in)
                ci += 1
            gh = sum(1 for m, s_ in goals if a_ < m <= b_ and s_ == "home") + (sum(1 for m, s_ in goals if m == 0 and s_ == "home") if a_ == 0 else 0)
            ga = sum(1 for m, s_ in goals if a_ < m <= b_ and s_ == "away") + (sum(1 for m, s_ in goals if m == 0 and s_ == "away") if a_ == 0 else 0)
            if b_ > a_:
                rows.append((eid, g["date"].iloc[0], float(b_ - a_), tuple(on["home"]), tuple(on["away"]), gh, ga))
    return pd.DataFrame(rows, columns=["event_id", "date", "minutes", "home_on", "away_on", "gh", "ga"])

def fit_impact(st, asof, damp=IMPACT_DAMP):
    """Ridge plus-minus ratings from stints before `asof` (goal difference per 90 minutes)."""
    s_ = st[st["date"] < asof]
    if len(s_) < 500:
        return {}
    players = pd.unique(np.concatenate([np.concatenate(s_["home_on"].values), np.concatenate(s_["away_on"].values)]))
    idx = {p: i for i, p in enumerate(players)}
    rows, cols, vals = [], [], []
    for k, (h_, a_) in enumerate(zip(s_["home_on"].values, s_["away_on"].values)):
        for p in h_:
            rows.append(k); cols.append(idx[p]); vals.append(1.0)
        for p in a_:
            rows.append(k); cols.append(idx[p]); vals.append(-1.0)
        rows.append(k); cols.append(len(players)); vals.append(1.0)          # home advantage
    X = sparse.csr_matrix((vals, (rows, cols)), shape=(len(s_), len(players) + 1))
    y = 90 * (s_["gh"].values - s_["ga"].values) / s_["minutes"].values
    days = (asof - s_["date"]).dt.days.values
    w = (s_["minutes"].values / 90) * 0.5 ** (days / IMPACT_HALF_LIFE)
    sw = np.sqrt(w)
    b = lsqr(sparse.diags(sw) @ X, sw * y, damp=damp)[0]
    return dict(zip(players, b[:-1]))

_TEAM_LU = {}
def team_strength(lu_, ratings, team_id, asof, squad=None, window=120):
    """Sum of ratings of the team's regular eleven: recent start rates (departures removed), plus current-squad arrivals."""
    if not _TEAM_LU:
        _TEAM_LU.update({t: g_ for t, g_ in lu_.groupby("team_id")})
    g = _TEAM_LU.get(team_id, lu_.iloc[:0])
    g = g[(g["date"] < asof) & (g["date"] >= asof - pd.Timedelta(days=window))]
    if g.empty:
        return np.nan
    n_matches = g["event_id"].nunique()
    share = g.groupby("player_id")["starter"].sum() / n_matches
    if squad is not None:
        share = share[share.index.isin(squad)]
        new = [p for p in squad if p not in share.index and p in ratings]
        if new:                                           # arrivals rated at previous clubs, assumed to start half the time
            share = pd.concat([share, pd.Series(0.5, index=new)])
    if share.sum() > 0:
        share = share * min(1.0, 11 / share.sum())
    return float(sum(share[p] * ratings.get(p, 0.0) for p in share.index))

imp_status = "not run"
if PLAYER_MODEL and len(lu) and "base" in globals() and len(base):
    ev_frames = [pd.read_csv(f"{LINEUP_DIR}/{c}_events.csv", dtype={"event_id": str, "team_id": str, "players": str})
                 for c in list(ESPN_LEAGUES) + ESPN_OTHER if os.path.exists(f"{LINEUP_DIR}/{c}_events.csv")]
    events_all = pd.concat(ev_frames, ignore_index=True).drop_duplicates() if ev_frames else pd.DataFrame(columns=["event_id"])
    with_minutes = events_all["event_id"].nunique() if len(events_all) else 0
    print(f"Building stints from {lu['event_id'].nunique()} matches ({with_minutes} with goal and substitution minutes)...")
    STINTS = build_stints(lu.assign(player_id=lu["player_id"].astype(str), team_id=lu["team_id"].astype(str)), events_all)
    span_start = lu["date"].min()
    season_start = all_matches.loc[all_matches["Season"] == SEASONS[-1], "Date"].min()
    ready = span_start <= season_start - pd.Timedelta(days=540) and with_minutes >= 0.5 * lu["event_id"].nunique()
    print(f"  {len(STINTS)} stints; lineup history starts {span_start:%b %Y}.")

    # live ratings (all data) for the dashboard and live predictions
    RATINGS = fit_impact(STINTS, TODAY + pd.Timedelta(days=1))
    pname = lu.drop_duplicates("player_id").set_index("player_id")["player"].to_dict()
    if RATINGS:
        mins = pd.concat([STINTS[["home_on", "minutes"]].rename(columns={"home_on": "on"}), STINTS[["away_on", "minutes"]].rename(columns={"away_on": "on"})]).explode("on").groupby("on")["minutes"].sum()
        top = pd.Series(RATINGS).to_frame("Impact").join(mins.rename("Minutes")).query("Minutes >= 1500").sort_values("Impact", ascending=False).head(15)
        top.index = [pname.get(p, p) for p in top.index]
        print("\nHighest-rated players (1,500+ minutes in our data; goal difference per 90 they add):")
        display(top.round(2))

    if not ready:
        imp_status = "waiting for lineup history (needs about 18 months before this season, with minutes)"
        print(f"\nImpact test skipped: {imp_status}. It will run automatically once the backfill is far enough along.")
    else:
        # honest test: ratings refitted every 4 weeks from earlier matches; team strength now vs its average over the past year
        CACHE = f"{SAVE_DIR}/impact_team_strength.csv"
        cached = pd.read_csv(CACHE, parse_dates=["week"], dtype={"team_id": str}) if os.path.exists(CACHE) else pd.DataFrame(columns=["team_id", "week", "ts"])
        mf_ids = mf[["League", "Date", "HomeTeam", "AwayTeam", "home_id", "away_id"]].astype({"home_id": str, "away_id": str})
        bb = base.merge(mf_ids, on=["League", "Date", "HomeTeam", "AwayTeam"]).dropna(subset=["ExpHome", "ExpAway", "rho"]).reset_index(drop=True)
        bb["week"] = (bb["Date"] - pd.to_timedelta(bb["Date"].dt.weekday, unit="D")).dt.normalize()
        need_weeks = sorted(set(pd.date_range(bb["week"].min() - pd.Timedelta(days=364), bb["week"].max(), freq="W-MON")) - set(cached["week"]))
        lu_s = lu.assign(player_id=lu["player_id"].astype(str), team_id=lu["team_id"].astype(str))
        teams = sorted(set(bb["home_id"]) | set(bb["away_id"]))
        new_rows, rat = [], {}
        if need_weeks:
            print(f"  Computing team strength for {len(need_weeks)} weeks (once; later runs only add new weeks)...")
        for w_ in need_weeks:
            key = w_ - pd.Timedelta(days=(w_ - pd.Timestamp("2020-01-06")).days % 28)          # ratings refitted every 4 weeks
            if key not in rat:
                rat[key] = fit_impact(STINTS, key)
            if not rat[key]:
                continue
            for t_ in teams:
                new_rows.append({"team_id": t_, "week": w_, "ts": team_strength(lu_s, rat[key], t_, w_)})
        if new_rows:
            cached = pd.concat([cached, pd.DataFrame(new_rows)], ignore_index=True)
            cached.to_csv(CACHE, index=False)
        cached["ts"] = pd.to_numeric(cached["ts"], errors="coerce")
        cached["week"] = pd.to_datetime(cached["week"])
        ts = cached.dropna(subset=["ts"]).sort_values("week")
        ts["past"] = ts.groupby("team_id")["ts"].transform(lambda s_: s_.shift(1).rolling(52, min_periods=8).mean())
        look = ts.set_index(["team_id", "week"])
        def feats_for(df):
            hk, ak = list(zip(df["home_id"], df["week"])), list(zip(df["away_id"], df["week"]))
            g_ = lambda keys, col: pd.to_numeric(look[col].reindex(keys), errors="coerce").values.astype(float)
            return g_(hk, "ts") - g_(ak, "ts"), (g_(hk, "ts") - g_(hk, "past")) - (g_(ak, "ts") - g_(ak, "past"))
        lvl, chg = feats_for(bb)
        ok = np.isfinite(lvl) & np.isfinite(chg)
        bb, lvl, chg = bb[ok].reset_index(drop=True), lvl[ok], chg[ok]
        L = pd.concat([pd.DataFrame({"goals": bb["FTHG"], "offset": np.log(bb["ExpHome"]), "level": lvl, "change": chg, "Date": bb["Date"]}),
                       pd.DataFrame({"goals": bb["FTAG"], "offset": np.log(bb["ExpAway"]), "level": -lvl, "change": -chg, "Date": bb["Date"]})])
        tr_, te_ = L[L["Date"] < season_start], (bb["Date"] >= season_start).values
        if len(tr_) > 1000 and te_.sum() >= 100:
            prm = sm.GLM(tr_["goals"], tr_[["level", "change"]], family=sm.families.Poisson(), offset=tr_["offset"]).fit().params
            fh_, fa_ = np.exp(prm["level"] * lvl + prm["change"] * chg), np.exp(-prm["level"] * lvl - prm["change"] * chg)
            def probs_rho2(df, h, a):
                p = np.zeros((len(df), 3))
                for r_v in np.unique(df["rho"].values):
                    i_ = np.where(df["rho"].values == r_v)[0]
                    p[i_] = outcome_probs(h[i_], a[i_], r_v)
                return p
            o_ = outcome(bb)
            ll0 = -np.log(probs_rho2(bb, bb["ExpHome"].values, bb["ExpAway"].values)[np.arange(len(bb)), o_])
            ll1 = -np.log(probs_rho2(bb, bb["ExpHome"].values * fh_, bb["ExpAway"].values * fa_)[np.arange(len(bb)), o_])
            d_ = (ll1 - ll0)[te_]
            rng_i = np.random.default_rng(0)
            pct = 100 * (np.array([rng_i.choice(d_, len(d_)).mean() for _ in range(2000)]) < 0).mean()
            early = te_ & (bb["Date"] < season_start + pd.Timedelta(days=60)).values
            d_early = (ll1 - ll0)[early]
            print(f"\nImpact test on {te_.sum()} matches this season: log loss {d_.mean():+.4f}, better in {pct:.0f}% of reshuffles"
                  + (f"; first 60 days of the season ({early.sum()} matches): {d_early.mean():+.4f}" if early.sum() else "") + ".")
            print(f"  Learned effects: squad-quality gap {prm['level']:+.3f}, change in squad quality {prm['change']:+.3f} (per unit of goal difference per 90).")
            on_ = bool(pct >= 95 and d_.mean() < 0)
            IMPACT = {"on": on_, "level": float(prm["level"]), "change": float(prm["change"])}
            json.dump(IMPACT, open(IMP_PATH, "w"))
            imp_status = f"{'ON' if on_ else 'off'} (better in {pct:.0f}% of reshuffles)"
        else:
            imp_status = "not enough matches with team strength yet"
    print(f"Impact ratings in predictions: {imp_status}")

def impact_multipliers(games):
    """Scale expected goals by the squad-quality gap and change (only if the impact test passed)."""
    n_ = len(games)
    if not IMPACT.get("on") or "RATINGS" not in globals() or not RATINGS or "ts" not in globals():
        return np.ones(n_), np.ones(n_)
    g_ = games.copy()
    g_["Date"] = pd.to_datetime(g_["Date"])
    if "home_id" not in g_ or g_["home_id"].isna().all():
        g_ = g_.drop(columns=[c for c in ["home_id", "away_id"] if c in g_]).merge(
            mf[["League", "Date", "HomeTeam", "AwayTeam", "home_id", "away_id"]].drop_duplicates(["League", "Date", "HomeTeam", "AwayTeam"]),
            on=["League", "Date", "HomeTeam", "AwayTeam"], how="left")
    g_["home_id"], g_["away_id"] = g_["home_id"].astype(str), g_["away_id"].astype(str)
    wk = (pd.to_datetime(g_["Date"]) - pd.to_timedelta(pd.to_datetime(g_["Date"]).dt.weekday, unit="D")).dt.normalize()
    lu_s = lu.assign(player_id=lu["player_id"].astype(str), team_id=lu["team_id"].astype(str))
    past_latest = ts.groupby("team_id")["ts"].apply(lambda s_: s_.tail(52).mean()).to_dict()
    vals = {}
    for side in ["home", "away"]:
        now, past = [], []
        for t_, w_, d_ in zip(g_[f"{side}_id"], wk, pd.to_datetime(g_["Date"])):
            if d_ >= TODAY - pd.Timedelta(days=3):          # live: current ratings and current squad
                now.append(team_strength(lu_s, RATINGS, t_, TODAY + pd.Timedelta(days=1), squad=squads.get(t_)))
                past.append(past_latest.get(t_, np.nan))
            else:
                now.append(look["ts"].get((t_, w_), np.nan)); past.append(look["past"].get((t_, w_), np.nan))
        vals[side] = (np.array(now, dtype=float), np.array(past, dtype=float))
    lvl = vals["home"][0] - vals["away"][0]
    chg = (vals["home"][0] - vals["home"][1]) - (vals["away"][0] - vals["away"][1])
    lvl, chg = np.nan_to_num(lvl), np.nan_to_num(chg)
    return np.exp(IMPACT["level"] * lvl + IMPACT["change"] * chg), np.exp(-IMPACT["level"] * lvl - IMPACT["change"] * chg)
health("Impact ratings", True, imp_status)
