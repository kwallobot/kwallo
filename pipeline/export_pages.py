"""v32: the data behind the website's pages (competitions, tables, matchdays, teams, players, leaders, track record, best angles).
Everything here is public: model probabilities, fair odds, results and statistics; never bookmaker names or prices."""
import os, json, re
import numpy as np, pandas as pd

GROUP_ORDER = ["europe_top", "europe_other", "europe_lower", "americas", "africa_me", "asia"]
GROUP_NAMES = {"europe_top": "Europe: big leagues and cups", "europe_other": "Europe: other leagues", "americas": "The Americas", "africa_me": "Africa and the Middle East",
               "europe_lower": "Europe: second tiers and smaller leagues", "asia": "Asia"}      # v36: the last two
CUPS = {"Champions League", "Europa League", "Conference League"}


def _results(ns):
    """Every league result we hold, with each league's current season label."""
    parts, season_of = [], {}
    am = ns.get("all_matches")
    seasons = ns.get("SEASONS") or []
    if am is not None and len(am):
        parts.append(am[["League", "Season", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]])
        for lg in am["League"].unique():
            season_of[lg] = str(seasons[-1]) if seasons else str(am.loc[am["League"] == lg, "Season"].iloc[-1])
    for lg, info in (ns.get("SOLO") or {}).items():
        d = info.get("data")
        if d is not None and len(d):
            parts.append(d[["League", "Season", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]])
            season_of[lg] = str(info.get("season"))
    # v33: European cups, league phase only (September to the end of January: the single 36-team table)
    # v35: from 1 September (it was 10 September, which dropped matchday 1 when it started earlier: wrong table and matchday numbers);
    #      the qualifying rounds end in late August
    eu = ns.get("euro")
    if eu is not None and len(eu) and {"Competition", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}.issubset(eu.columns):
        e = eu.dropna(subset=["FTHG", "FTAG"]).copy()
        e["Date"] = pd.to_datetime(e["Date"]).dt.normalize()
        y = e["Date"].dt.year - (e["Date"].dt.month < 7).astype(int)
        start, end = pd.to_datetime(y.astype(str) + "-09-01"), pd.to_datetime((y + 1).astype(str) + "-01-31")
        e = e[(e["Date"] >= start) & (e["Date"] <= end)]
        e["Season"] = y.loc[e.index].map(lambda v: f"{str(v)[2:]}{str(v + 1)[2:]}")
        parts.append(e.rename(columns={"Competition": "League"})[["League", "Season", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]])
        for lg in e["Competition"].unique() if "Competition" in e else []:
            season_of[lg] = str(seasons[-1]) if seasons else e["Season"].iloc[-1]
    if not parts:
        return pd.DataFrame(), season_of
    r = pd.concat(parts, ignore_index=True).dropna(subset=["FTHG", "FTAG"])
    r["Date"] = pd.to_datetime(r["Date"]).dt.normalize()
    r["Season"] = r["Season"].astype(str)
    return r.drop_duplicates(["League", "Date", "HomeTeam", "AwayTeam"]).sort_values("Date").reset_index(drop=True), season_of


def _table(cur):
    rows = {}
    for r in cur.itertuples():
        for t, gf, ga, home in [(r.HomeTeam, r.FTHG, r.FTAG, True), (r.AwayTeam, r.FTAG, r.FTHG, False)]:
            x = rows.setdefault(t, {"team": t, "P": 0, "W": 0, "D": 0, "L": 0, "GF": 0, "GA": 0, "form": []})
            x["P"] += 1; x["GF"] += int(gf); x["GA"] += int(ga)
            res = "W" if gf > ga else ("D" if gf == ga else "L")
            x[res] += 1; x["form"].append(res)
    out = []
    for x in rows.values():
        x["GD"] = x["GF"] - x["GA"]; x["Pts"] = 3 * x["W"] + x["D"]; x["form"] = "".join(x["form"][-5:])
        out.append(x)
    out.sort(key=lambda x: (-x["Pts"], -x["GD"], -x["GF"], x["team"]))
    for i, x in enumerate(out):
        x["pos"] = i + 1
    return out


def _rounds(cur, upcoming, slug):
    """Matchday numbers: each match's round is the later of the two teams' match counts (works for any league's calendar)."""
    rows = [{"date": str(r.Date)[:10], "home": r.HomeTeam, "away": r.AwayTeam, "score": f"{int(r.FTHG)}-{int(r.FTAG)}", "played": True} for r in cur.itertuples()]
    rows += [{"date": m["Date"][:10], "home": m["Home"], "away": m["Away"], "slug": m["slug"], "pH": m.get("pH"), "pD": m.get("pD"), "pA": m.get("pA"),
              "kickoff": m.get("kickoff"), "played": False} for m in upcoming]
    rows.sort(key=lambda x: (x["date"], x["home"]))
    n = {}
    for x in rows:
        nh, na = n.get(x["home"], 0) + 1, n.get(x["away"], 0) + 1
        n[x["home"]], n[x["away"]] = nh, na
        x["round"] = max(nh, na)
        x["home_slug"], x["away_slug"] = slug(x["home"]), slug(x["away"])
    by = {}
    for x in rows:
        by.setdefault(x["round"], []).append(x)
    rounds = [{"round": k, "matches": v} for k, v in sorted(by.items())]
    nxt = next((r["round"] for r in rounds if any(not m["played"] for m in r["matches"])), rounds[-1]["round"] if rounds else None)
    return rounds, nxt


PAST_FROM = "2025-07-01"


def _likeliest(pH, pD, pA, eh, ea, n=5):
    """v35: the model's five likeliest scorelines before kickoff, rebuilt from the logged expected goals and chances (the same score
    grid as the match page: independent Poisson goals, rescaled so home wins / draws / away wins match the logged chances)."""
    if not all(pd.notna(x) for x in (pH, pD, pA, eh, ea)) or eh <= 0 or ea <= 0:
        return None
    from scipy.stats import poisson
    g = np.outer(poisson.pmf(range(9), eh), poisson.pmf(range(9), ea))
    home, draw, away = np.tril(g, -1), np.diag(np.diag(g)), np.triu(g, 1)
    g = home / home.sum() * pH + draw / draw.sum() * pD + away / away.sum() * pA
    g = g / g.sum()
    top = np.argsort(g.ravel())[::-1][:n]
    return [[int(i // g.shape[1]), int(i % g.shape[1]), round(float(g.ravel()[i]), 4)] for i in top]


def _past_days(ns, data_dir, write, slug, clean, comp_names):
    """v35: one file per date since PAST_FROM with every result in our competitions, and what Kwallo predicted before kickoff
    (the logged chances, and the top angle with won / lost). Only files whose contents changed are uploaded."""
    RES = ns.get("RES")
    if RES is None or not len(RES):
        return 0
    r = RES[(RES["Date"] >= pd.Timestamp(PAST_FROM)) & RES["Comp"].isin(comp_names)].dropna(subset=["FTHG", "FTAG"]).copy()
    if not len(r):
        return 0
    key = lambda c, d, h, a: f"{c}|{str(d)[:10]}|{h}|{a}"
    pred, top = {}, {}
    pl_p = os.path.join(data_dir, "prediction_log.csv")
    if os.path.exists(pl_p):
        pl = pd.read_csv(pl_p, usecols=lambda c: c in ("Competition", "Date", "Home", "Away", "pH", "pD", "pA", "ExpHome", "ExpAway"))
        for c in ("ExpHome", "ExpAway"):
            if c not in pl:
                pl[c] = np.nan
        pred = {key(x.Competition, x.Date, x.Home, x.Away): (x.pH, x.pD, x.pA, x.ExpHome, x.ExpAway) for x in pl.itertuples()}
    vl_p = os.path.join(data_dir, "verdict_log.csv")
    if os.path.exists(vl_p):
        vl = pd.read_csv(vl_p, usecols=lambda c: c in ("Competition", "Date", "Home", "Away", "kind", "Bet", "p", "won"))
        vl = vl[vl["kind"] == "best"].drop_duplicates(["Competition", "Date", "Home", "Away"], keep="last")
        top = {key(x.Competition, x.Date, x.Home, x.Away): {"bet": x.Bet, "p": x.p, "won": None if pd.isna(x.won) else bool(x.won)} for x in vl.itertuples()}
    n, dates = 0, []
    for d, g in r.sort_values(["Date", "Comp"]).groupby(r["Date"].dt.strftime("%Y-%m-%d")):
        rows = []
        for x in g.itertuples():
            k = key(x.Comp, d, x.HomeTeam, x.AwayTeam)
            p = pred.get(k)
            rows.append({"competition": x.Comp, "league_slug": slug(x.Comp), "home": x.HomeTeam, "away": x.AwayTeam,
                         "home_slug": slug(x.HomeTeam), "away_slug": slug(x.AwayTeam), "hs": int(x.FTHG), "as": int(x.FTAG),
                         "espn": x.espn if isinstance(getattr(x, "espn", None), str) and ":" in x.espn else None,
                         "pred": {"pH": p[0], "pD": p[1], "pA": p[2], "scores": _likeliest(*p),
                                  "eh": p[3] if pd.notna(p[3]) else None, "ea": p[4] if pd.notna(p[4]) else None}   # v36: for the win-probability graph
                                 if p and pd.notna(p[0]) else None, "top": top.get(k)})
        n += write(f"site/days/{d}.json", clean({"date": d, "matches": rows}))
        dates.append(d)
    n += write("site/days/index.json", {"from": PAST_FROM, "dates": dates})
    print(f"Past days: {len(dates)} dates with results since {PAST_FROM} ({len(r)} matches).")
    return n


def _cup_stage(date):
    """v35: the European cups' knockout rounds by date (UEFA's usual calendar): play-offs in February, last 16 in March, and so on."""
    d = pd.Timestamp(date)
    if d.month == 2:
        return "Knockout play-offs"
    if d.month == 3:
        return "Round of 16"
    if d.month == 4 and d.day <= 20:
        return "Quarter-finals"
    if (d.month == 4 and d.day > 20) or (d.month == 5 and d.day <= 15):
        return "Semi-finals"
    return "Final"


def _cup_rounds(cur, upcoming, slug):
    """v35: European cups: league-phase matchdays numbered from the results (each club plays once per matchday), knockout ties grouped
    by round name, and upcoming ties without a number yet as "Next matches" (never "null")."""
    def in_league_phase(d):
        d = pd.Timestamp(d)
        return d.month >= 7 or d.month == 1
    up_lp = [m for m in upcoming if in_league_phase(m["Date"][:10])]
    up_ko = [m for m in upcoming if not in_league_phase(m["Date"][:10])]
    rounds, nxt = ([], None)
    if len(cur):
        rounds, nxt = _rounds(cur, up_lp, slug)
    elif up_lp:
        rounds = [{"round": "next", "name": "Next matches", "matches": [{"date": m["Date"][:10], "home": m["Home"], "away": m["Away"], "slug": m["slug"],
                   "pH": m.get("pH"), "pD": m.get("pD"), "pA": m.get("pA"), "kickoff": m.get("kickoff"), "played": False,
                   "home_slug": m["home_slug"], "away_slug": m["away_slug"]} for m in up_lp]}]
        nxt = "next"
    by_stage = {}
    for m in sorted(up_ko, key=lambda x: x["Date"]):
        by_stage.setdefault(_cup_stage(m["Date"][:10]), []).append({"date": m["Date"][:10], "home": m["Home"], "away": m["Away"], "slug": m["slug"],
            "pH": m.get("pH"), "pD": m.get("pD"), "pA": m.get("pA"), "kickoff": m.get("kickoff"), "played": False,
            "home_slug": m["home_slug"], "away_slug": m["away_slug"]})
    for name, ms in by_stage.items():
        rounds.append({"round": slug(name), "name": name, "matches": ms})
    if by_stage and (nxt is None or all(x["played"] for r in rounds if r["round"] == nxt for x in r["matches"])):
        nxt = slug(next(iter(by_stage)))
    return rounds, nxt


def _family(bet):
    b = str(bet).lower()
    for fam, words in [("Corners", ["corner"]), ("Cards", ["card"]), ("Shots", ["shot"]), ("Fouls", ["foul"]), ("Offsides", ["offside"]),
                       ("Tackles", ["tackle"]), ("Half-time", ["half-time", "half time", "both halves"]),
                       ("Goals", ["goal", "both teams", "over", "under", "score"]), ("Result", ["win", "draw", "double chance"])]:
        if any(w in b for w in words):
            return fam
    return "Other"


def _track(ns, data_dir):
    """Hit rates against what the model expected: live picks (logged before kickoff) and the replayed history, kept apart."""
    parts = []
    vl = os.path.join(data_dir, "verdict_log.csv")
    if os.path.exists(vl):
        v = pd.read_csv(vl)
        v = v[pd.to_numeric(v.get("won"), errors="coerce").notna()] if "won" in v else v.iloc[0:0]
        if len(v):
            parts.append(v.assign(source="live")[["Competition", "Date", "Home", "Away", "kind", "Bet", "p", "won", "source"]])
    H = ns.get("H_")
    if H is not None and len(H) and {"Competition", "Date", "kind", "Bet", "p", "won"}.issubset(H.columns):
        parts.append(H.assign(source="replay").reindex(columns=["Competition", "Date", "Home", "Away", "kind", "Bet", "p", "won", "source"]))
    if not parts:
        return {"note": "No settled picks yet."}
    T = pd.concat(parts, ignore_index=True)
    T["won"] = pd.to_numeric(T["won"], errors="coerce").clip(0, 1); T["p"] = pd.to_numeric(T["p"], errors="coerce")
    T = T.dropna(subset=["won", "p"])
    T["Date"] = pd.to_datetime(T["Date"], errors="coerce")
    T["family"] = T["Bet"].map(_family)
    summ = lambda d: {"n": int(len(d)), "hit": round(100 * float(d["won"].mean()), 1), "expected": round(100 * float(d["p"].mean()), 1)} if len(d) else None
    today = pd.Timestamp.now().normalize()
    out = {"overall": {}, "by_competition": [], "by_family": [], "by_period": {}, "calibration": [], "recent": []}
    for src in ["live", "replay"]:
        d = T[T["source"] == src]
        out["overall"][src] = {k: summ(d[d["kind"] == k]) for k in ["best", "safer"]}
    best = T[T["kind"] == "best"]
    for comp, d in best.groupby("Competition"):
        if len(d) >= 20:
            out["by_competition"].append({"competition": comp, **summ(d)})
    out["by_competition"].sort(key=lambda x: -x["n"])
    for fam, d in best.groupby("family"):
        if len(d) >= 20:
            out["by_family"].append({"family": fam, **summ(d)})
    out["by_family"].sort(key=lambda x: -x["n"])
    for lab, days in [("last_7_days", 7), ("last_30_days", 30), ("last_365_days", 365)]:
        out["by_period"][lab] = summ(best[best["Date"] >= today - pd.Timedelta(days=days)])
    for lo, hi in [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]:
        d = best[(best["p"] >= lo) & (best["p"] < hi)]
        if len(d) >= 30:
            out["calibration"].append({"band": f"{int(100 * lo)}-{min(100, int(100 * hi))}%", **summ(d)})
    rec = T.sort_values(["source", "Date"], ascending=[True, False]).head(60)       # live first, newest first
    out["recent"] = [{"date": str(r.Date)[:10], "competition": r.Competition, "match": f"{r.Home} v {r.Away}", "pick": r.Bet, "p": round(float(r.p), 3),
                      "won": bool(r.won), "kind": r.kind, "source": r.source} for r in rec.itertuples()]
    return out


CALENDAR_PA = {"USA", "BRA", "ARG", "BOL", "NOR", "SWE"}          # PitchAPI countries whose seasons follow the calendar year
CALENDAR_ESPN = {"usa.1", "bra.1", "bra.2", "arg.1", "bol.1", "nor.1", "swe.1"}

def _season_start(calendar):
    """v35: the start of the current season: 1 January for calendar-year leagues, otherwise 1 July."""
    now = pd.Timestamp.now()
    return pd.Timestamp(now.year, 1, 1) if calendar else pd.Timestamp(now.year if now.month >= 7 else now.year - 1, 7, 1)

STAT_KEYS = {"goals": ("goals",), "assists": ("assists", "goal_assist", "goalassist"), "xg": ("expected_goals", "expectedgoals", "xg"),
             "xa": ("expected_assists", "expectedassists", "xa"), "shots": ("total_shots", "totalshots", "shots"),
             "sot": ("shotsontarget", "shots_on_target", "sot", "ontargetscoringattempt")}

def headline(stats):
    """v35: goals, assists, xG, xA, shots and shots on target (totals) from whichever keys the source uses."""
    out = {}
    for k, cands in STAT_KEYS.items():
        v = next((stats[c] for c in cands if c in stats), None)
        if isinstance(v, dict):
            v = v.get("total")
        out[k] = v
    return out

def _players(ns, data_dir, slug):
    """Every PitchAPI statistic per player: totals, per 90 and per match, by PitchAPI's own sections; and a match log.
    v35: this season only (each competition's own start), with a per-competition breakdown, and leader tables built from each
    competition's own matches (before, a player was listed under his last match's competition with every competition's totals)."""
    pp_p, pm_p, lab_p = (os.path.join(data_dir, f) for f in ["pitchapi_players.csv", "pitchapi_matches.csv", "pitchapi_player_stat_labels.json"])
    if not (os.path.exists(pp_p) and os.path.exists(pm_p)):
        return {}, {}, {}
    pp = pd.read_csv(pp_p, dtype={"match_id": str, "team_id": str, "player_id": str})
    if "stats_json" not in pp:
        return {}, {}, {}
    pm = pd.read_csv(pm_p, dtype={"id": str, "home_id": str, "away_id": str})
    labels = json.load(open(lab_p)) if os.path.exists(lab_p) else {}
    pp = pp.merge(pm[["id", "league", "date", "home", "away", "home_id", "away_id", "score_home", "score_away"]].rename(columns={"id": "match_id"}), on="match_id", how="inner")
    pp = pp[pd.to_datetime(pp["date"]) >= pd.Timestamp.now() - pd.Timedelta(days=400)]
    if not len(pp):
        return {}, {}, labels
    home = pp["team_id"] == pp["home_id"]
    pp["team"], pp["opp"] = np.where(home, pp["home"], pp["away"]), np.where(home, pp["away"], pp["home"])
    pp["venue"] = np.where(home, "H", "A")
    # PitchAPI's club names -> ours, where the markets section linked them
    pa_to_ours = {v: k for k, v in (ns.get("ours_to_pa") or {}).items()}
    pp["team"] = pp["team"].map(lambda t: pa_to_ours.get(t, t))
    pp["stats"] = pp["stats_json"].map(lambda s: json.loads(s) if isinstance(s, str) and s.startswith("{") else {})
    kind = {k: (v.get("type") or "") for k, v in labels.items()}
    is_cum = lambda k: k.startswith("expected_") or k.startswith("xg")              # v35: xG and xA add up over matches (decimals, but not averages)
    is_avg = lambda k: not is_cum(k) and (kind.get(k) in ("double", "percent", "fraction") or any(w in k for w in ("rating", "percent", "accuracy", "pct")))
    def agg(g):
        mins = sum(float(s.get("minutes_played", 0) or 0) for s in g["stats"])
        tot, avg_w = {}, {}
        for s in g["stats"]:
            m = float(s.get("minutes_played", 0) or 0)
            for k, v in s.items():
                if is_avg(k):
                    a = avg_w.setdefault(k, [0.0, 0.0]); a[0] += v * max(m, 1); a[1] += max(m, 1)
                else:
                    tot[k] = tot.get(k, 0.0) + v
        stats = {}
        for k, v in tot.items():
            stats[k] = {"total": round(v, 2), "per90": round(90 * v / mins, 2) if mins >= 90 else None, "per_match": round(v / len(g), 2)}
        for k, (num, den) in avg_w.items():
            stats[k] = {"average": round(num / den, 2)}
        return mins, stats
    starts = {lg: _season_start(str(lg).split(":")[0] in CALENDAR_PA) for lg in pp["league"].unique()}
    pp["in_season"] = pd.to_datetime(pp["date"]) >= pp["league"].map(starts)
    pa_to_ours_lg = {f"{cc}:{name}": ours for d in [ns.get("PA_XG_LEAGUES") or {}, ns.get("PA_TACTIC_LEAGUES") or {}] for ours, (cc, name) in d.items()}
    pa_to_ours_lg.update({k: v[0] for k, v in (ns.get("PA_XG_MORE") or {}).items()})
    comp_name = lambda lg: pa_to_ours_lg.get(lg, lg)
    players, by_league = {}, {}
    for pid, g in pp.sort_values("date").groupby("player_id"):
        name, last = g["player"].iloc[-1], g.iloc[-1]
        ps = f"{slug(name)}-{str(pid)[-4:]}"
        seas = g[g["in_season"]]
        mins, stats = agg(seas if len(seas) else g)
        by_comp = []
        for lg, gl in seas.groupby("league"):
            m_l, st_l = agg(gl)
            by_comp.append({"competition": comp_name(lg), "matches": int(len(gl)), "minutes": int(m_l), **headline(st_l)})
            by_league.setdefault(lg, []).append({"slug": ps, "name": name, "team": last["team"], "team_slug": slug(last["team"]),
                                                 "matches": int(len(gl)), "minutes": int(m_l), "stats": st_l})
        log = [{"date": str(r.date)[:10], "competition": comp_name(r.league), "team": r.team, "opp": r.opp, "venue": r.venue,
                "score": f"{r.score_home}-{r.score_away}" if pd.notna(r.score_home) else None, "stats": r.stats} for r in g.tail(10).iloc[::-1].itertuples()]
        players[ps] = {"slug": ps, "name": name, "team": last["team"], "team_slug": slug(last["team"]), "league": comp_name(last["league"]),
                       "matches": int(len(seas) if len(seas) else len(g)), "minutes": int(mins), "stats": stats, "log": log,
                       "period": "this season" if len(seas) else "the last 12 months", "by_competition": sorted(by_comp, key=lambda x: -x["minutes"])}
    return players, by_league, labels


ESPN_STATS = {"goals": "Goals", "assists": "Assists", "shots": "Shots", "sot": "Shots on target", "fouls": "Fouls committed",
              "yellow": "Yellow cards", "red": "Red cards", "saves": "Saves", "conceded": "Goals conceded"}

def _espn_players(ns, slug, skip_names):
    """v32: players in leagues PitchAPI doesn't cover (NPFL, second divisions, smaller European leagues), from ESPN's lineups."""
    lu = ns.get("lu")
    if lu is None or not len(lu):
        return {}, {}
    code_to = {**(ns.get("ESPN_LEAGUES") or {}), **(ns.get("EURO_CODES") or {})}
    tm = ns.get("team_map") or {}
    d = lu.copy()
    d["league"] = d["comp"].map(code_to)
    d = d.dropna(subset=["league"])
    d["date"] = pd.to_datetime(d["date"])
    d = d[(d["date"] >= pd.Timestamp.now() - pd.Timedelta(days=330)) & (d["starter"].astype(bool) | d.get("sub_in", False).astype(bool))]
    if not len(d):
        return {}, {}
    d["team"] = [tm.get((l, t), t) for l, t in zip(d["league"], d["team"])]
    d["in_season"] = d["date"] >= d["comp"].map(lambda c: _season_start(c in CALENDAR_ESPN))      # v35: this season, per competition
    def agg(g):
        mins = float(pd.to_numeric(g["minutes"], errors="coerce").fillna(0).sum()) if "minutes" in g else 0.0
        stats = {}
        for k in ESPN_STATS:
            if k in g:
                v = float(pd.to_numeric(g[k], errors="coerce").fillna(0).sum())
                stats[k] = {"total": round(v, 2), "per90": round(90 * v / mins, 2) if mins >= 90 else None, "per_match": round(v / len(g), 2)}
        return mins, stats
    players, by_league = {}, {}
    for pid, g in d.sort_values("date").groupby("player_id"):
        name, last = str(g["player"].iloc[-1]), g.iloc[-1]
        if (str(last["team"]), name) in skip_names:                          # already has a PitchAPI page with every statistic
            continue
        ps = f"{slug(name)}-{str(pid)[-4:]}"
        seas = g[g["in_season"]]
        mins, stats = agg(seas if len(seas) else g)
        by_comp = []
        for lg, gl in seas.groupby("league"):
            m_l, st_l = agg(gl)
            by_comp.append({"competition": lg, "matches": int(len(gl)), "minutes": int(m_l), **headline(st_l)})
            by_league.setdefault(lg, []).append({"slug": ps, "name": name, "team": last["team"], "team_slug": slug(last["team"]),
                                                 "matches": int(len(gl)), "minutes": int(m_l), "stats": st_l})
        log = [{"date": str(r.date)[:10], "competition": r.league, "team": r.team, "started": bool(r.starter),
                "stats": {k: getattr(r, k) for k in ESPN_STATS if k in g and pd.notna(getattr(r, k))}} for r in g.tail(10).iloc[::-1].itertuples()]
        players[ps] = {"slug": ps, "name": name, "team": last["team"], "team_slug": slug(last["team"]), "league": last["league"], "source": "ESPN",
                       "position": last.get("pos"), "matches": int(len(seas) if len(seas) else len(g)), "minutes": int(mins), "stats": stats, "log": log,
                       "espn_id": str(pid), "period": "this season" if len(seas) else "the last 12 months",       # v35: ESPN id for the transfer history
                       "by_competition": sorted(by_comp, key=lambda x: -x["minutes"])}
    return players, by_league


def build(ns, data_dir, mode, write, slug, clean):
    if mode == "lineups":
        return                                                     # quick runs only refresh matches
    idx_p = os.path.join(data_dir, "site", "index.json")
    matches = json.load(open(idx_p))["matches"] if os.path.exists(idx_p) else []
    cal_group = ns.get("cal_group") or (lambda c: "europe_other")
    res, season_of = _results(ns)
    n_files = 0
    # ---------- competitions: tables and matchdays ----------
    hidden_ = set(ns.get("GATE_HIDDEN") or [])                    # v36: new leagues still waiting for their backtest to pass
    comps, comp_names = [], set(m["Competition"] for m in matches) | set(season_of)   # v37c: shown too, without chances ("held")
    for comp in sorted(comp_names):
        cs = slug(comp)
        cur = res[(res["League"] == comp) & (res["Season"] == season_of.get(comp, ""))] if len(res) else pd.DataFrame()
        up = [m for m in matches if m["Competition"] == comp]
        if not len(cur) and not up:
            continue
        # v35: the European cups get their league-phase table too (_results keeps only league-phase matches for them)
        table = _table(cur) if len(cur) else []
        for t in table:
            t["team_slug"] = slug(t["team"])
        if comp in CUPS:
            rounds, nxt = _cup_rounds(cur, up, slug)                     # v35: league-phase matchdays 1-8, then knockout rounds by name
        else:
            rounds, nxt = _rounds(cur, up, slug)
        n_files += write(f"site/comp/{cs}.json", clean({"name": comp, "slug": cs, "group": cal_group(comp), "season": season_of.get(comp), "table": table,
                                                        "rounds": rounds, "current_round": nxt, "upcoming": [m["slug"] for m in up], "held": comp in hidden_}))
        comps.append({"slug": cs, "name": comp, "group": cal_group(comp), "group_name": GROUP_NAMES.get(cal_group(comp)), "upcoming": len(up), "has_table": bool(table),
                      "held": comp in hidden_})
    comps.sort(key=lambda c: (GROUP_ORDER.index(c["group"]) if c["group"] in GROUP_ORDER else 9, -c["upcoming"], c["name"]))
    n_files += write("site/competitions.json", comps)
    n_files += _past_days(ns, data_dir, write, slug, clean, {c["name"] for c in comps})
    # ---------- players (every statistic) and leaders ----------
    players, by_league, labels = _players(ns, data_dir, slug)
    # v32: ESPN-only leagues too (their own leader tables), skipping anyone who already has a PitchAPI page
    pa_name_to_ours = {}
    for d in [ns.get("PA_XG_LEAGUES") or {}, ns.get("PA_TACTIC_LEAGUES") or {}]:
        for ours, (cc, name) in d.items():
            pa_name_to_ours[f"{cc}:{name}"] = ours
    pa_name_to_ours.update({k: v[0] for k, v in (ns.get("PA_XG_MORE") or {}).items()})    # v35: the European cups and the extra leagues too
    by_league = {pa_name_to_ours.get(lg, lg): rows for lg, rows in by_league.items()}   # leader tables by our competition names
    covered = {lg for lg, rows in by_league.items() if len(rows) >= 50}                 # PitchAPI already has this league's players
    e_players, e_by = _espn_players(ns, slug, {(p["team"], p["name"]) for p in players.values()})
    for ps, p in e_players.items():
        players.setdefault(ps, p)
    for lg, rows in e_by.items():
        if lg in covered:                                                # keep PitchAPI's richer tables there
            continue
        by_league.setdefault(lg, []).extend(rows)
    for k, v in ESPN_STATS.items():
        labels.setdefault(k, {"label": v, "section": "Match stats (ESPN)", "order": 10000 + list(ESPN_STATS).index(k)})
    # v35: ESPN's id for PitchAPI players too (matched by team and name in ESPN's lineups), so every player page can show transfers
    lu_ = ns.get("lu")
    if lu_ is not None and len(lu_):
        tm_ = ns.get("team_map") or {}
        code_to_ = {**(ns.get("ESPN_LEAGUES") or {}), **(ns.get("EURO_CODES") or {})}
        nk_ = lambda s: re.sub(r"[^a-z]", "", __import__("unicodedata").normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower())
        l2_ = lu_.drop_duplicates("player_id", keep="last")
        by_tn_ = {(slug(tm_.get((code_to_.get(c), t), t)), nk_(n)): str(i) for c, t, n, i in zip(l2_["comp"], l2_["team"], l2_["player"], l2_["player_id"])}
        for p in players.values():
            if not p.get("espn_id"):
                p["espn_id"] = by_tn_.get((p["team_slug"], nk_(p["name"])))
    for ps, p in players.items():
        n_files += write(f"site/player/{ps}.json", clean({**p, "labels": {k: labels.get(k) for k in p["stats"]}}))
    # v35: each competition's leaders from its own matches this season (each row is that player's figures in that competition)
    for ours, rws in by_league.items():
        rows = [{"slug": r["slug"], "name": r["name"], "team": r["team"], "team_slug": r["team_slug"], "matches": r["matches"], "minutes": r["minutes"],
                 "stats": {k: {"p90": v.get("per90"), "total": v.get("total", v.get("average"))} for k, v in r["stats"].items()},   # v33: both
                 "totals": {k: v.get("total") for k, v in r["stats"].items() if "total" in v}} for r in rws if r["slug"] in players]
        n_files += write(f"site/leaders/{slug(ours)}.json", clean({"competition": ours, "labels": labels, "players": rows}))
    # ---------- teams ----------
    team_players = {}
    for ps, p in players.items():
        if p.get("period") != "this season":
            continue                                                     # v35: this season's squad only
        st_ = p["stats"]
        team_players.setdefault(p["team_slug"], []).append({"slug": ps, "name": p["name"], "matches": p["matches"], "minutes": p["minutes"], "espn_id": p.get("espn_id"),
                                                            "position": p.get("position"),
                                                            "rating": (st_.get("rating_title") or st_.get("rating") or {}).get("average"),
                                                            **headline(st_)})        # v35: goals, assists, xG, xA, shots, shots on target
    P = ns.get("payload") or {}
    teams = {}
    if len(res):
        for comp, season in season_of.items():
            cur = res[(res["League"] == comp) & (res["Season"] == season)]
            tab = {t["team"]: t for t in _table(cur)} if len(cur) else {}
            for t in tab:
                g = cur[(cur["HomeTeam"] == t) | (cur["AwayTeam"] == t)].tail(10).iloc[::-1]
                form = []
                for r in g.itertuples():
                    gf, ga = (r.FTHG, r.FTAG) if r.HomeTeam == t else (r.FTAG, r.FTHG)
                    form.append({"date": str(r.Date)[:10], "opp": r.AwayTeam if r.HomeTeam == t else r.HomeTeam, "venue": "H" if r.HomeTeam == t else "A",
                                 "score": f"{int(r.FTHG)}-{int(r.FTAG)}", "result": "W" if gf > ga else ("D" if gf == ga else "L")})
                teams[slug(t)] = {"name": t, "slug": slug(t), "league": comp, "league_slug": slug(comp), "record": tab[t], "form": form}
    for m in matches:
        for side in ("Home", "Away"):
            ts = m[f"{side.lower()}_slug"]
            teams.setdefault(ts, {"name": m[side], "slug": ts, "league": m["Competition"], "league_slug": m["league_slug"], "record": None, "form": []})
            teams[ts].setdefault("upcoming", []).append({"slug": m["slug"], "date": m["Date"][:10], "kickoff": m.get("kickoff"), "competition": m["Competition"],
                                                         "opp": m["Away"] if side == "Home" else m["Home"], "venue": side[0], "pH": m.get("pH"), "pD": m.get("pD"), "pA": m.get("pA")})
    for ts, t in teams.items():
        t["players"] = sorted(team_players.get(ts, []), key=lambda x: -x["minutes"])
        t["trends"] = (P.get("trends") or {}).get(t["name"])
        t["style"] = (P.get("team_style") or {}).get(t["name"])
        n_files += write(f"site/team/{ts}.json", clean(t))
    # ---------- track record and best angles ----------
    n_files += write("site/track.json", clean(_track(ns, data_dir)))
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    tomorrow = (pd.Timestamp.now() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    best = [{"slug": m["slug"], "date": m["Date"][:10], "kickoff": m.get("kickoff"), "competition": m["Competition"], "home": m["Home"], "away": m["Away"],
             **(m.get("top_pick") or {})} for m in matches if m.get("top_pick")]
    days_ = sorted({b["date"] for b in best if b["date"] >= today})
    use_ = [d for d in days_ if d in (today, tomorrow)] or days_[:2]      # quiet days: the next two matchdays
    best = [b for b in best if b["date"] in use_]
    best = sorted([b for b in best if b.get("p")], key=lambda b: -b["p"])[:40]
    n_files += write("site/best.json", clean({"date": today, "days": use_, "angles": best}))
    print(f"Website pages: {len(comps)} competitions, {len(teams)} teams, {len(players)} players, {len(by_league)} leader tables; {n_files} files changed.")
