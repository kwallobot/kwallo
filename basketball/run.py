"""Kwallo basketball runner (v37: the NBA). Separate from the football pipeline: its own data in R2 (bb-data/), its own runs.

Modes (BB_MODE): daily  new results and box scores, this week's predictions, the website files (about 5-15 minutes)
                 full   also the weekly test: replay last season, test each adjustment, and the publishing gate (about 15-30 minutes;
                        the first one also reads last season's bookmaker lines, about 10 minutes more)
The first run of either kind does the weekly test too, if it has never been done.
"""
import os, sys, json, re, time, traceback, unicodedata
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
import storage, nba

MODE = os.environ.get("BB_MODE", "daily")
DATA = os.path.abspath(os.environ.get("BB_DATA", "./bb-data"))
PREFIX = "bb-data/"


def slug(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return None if not np.isfinite(o) else round(float(o), 4)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return o.isoformat()
    return o


def publish(files):
    """Write the website's basketball files (site/bb/...) to R2, plus a local copy."""
    n = 0
    for key, obj in files.items():
        body = json.dumps(clean(obj), ensure_ascii=False, allow_nan=False, default=str)
        local = os.path.join(DATA, key)
        os.makedirs(os.path.dirname(local), exist_ok=True)
        open(local, "w", encoding="utf-8").write(body)
        n += storage.put_public_async(key, body.encode("utf-8"))
    done, failed = storage.flush()
    print(f"Website: {len(files)} basketball files written" + (f", {done} uploaded" if done else " (local only)") + (f", {len(failed)} failed" if failed else "") + ".")


def team_info(row, side):
    return {"id": str(row[f"{side}_id"]), "abbr": row[f"{side}_abbr"], "name": row[f"{side}_name"], "short": row.get(f"{side}_short") or row[f"{side}_name"],
            "slug": slug(row[f"{side}_name"]), "color": ("#" + str(row.get(f"{side}_color"))) if isinstance(row.get(f"{side}_color"), str) else None,
            "alt": ("#" + str(row.get(f"{side}_alt"))) if isinstance(row.get(f"{side}_alt"), str) else None,
            "conf": nba.TEAMS.get(row[f"{side}_abbr"], ("", 0, 0))[0]}


def main():
    t0 = time.time()
    os.makedirs(DATA, exist_ok=True)
    print(f"Kwallo basketball, mode '{MODE}', data in {DATA}")
    seen = storage.sync_down(DATA, prefix=PREFIX)
    today = pd.Timestamp.now(tz="America/New_York").tz_localize(None).normalize()      # the NBA's calendar day
    season = nba.season_of(today)
    try:
        # ---- data
        print("History (hoopR files, downloaded once)...")
        hist_team, hist_player = nba.load_history(DATA, [season - 3, season - 2, season - 1])
        print("This season from ESPN...")
        sg = nba.update_season(DATA, today)
        st_box, sp_box = nba.update_boxes(DATA, sg, minutes=8 if MODE == "full" else 5)
        g = nba.game_table(hist_team, sg, st_box)
        print(f"  {len(g)} finished games since {g['date'].min():%b %Y} ({(g['season'] == season).sum()} this season)")
        past_ids = list(g.loc[g["season"] >= season - 1, "game_id"])
        # v37b: the whole of last season's bookmaker lines (stored once read; the first weekly test reads most of them)
        odds = nba.update_past_odds(DATA, past_ids, minutes=20 if MODE == "full" else 3, recent_ids=list(g.loc[g["season"] == season, "game_id"]))
        allbox = pd.concat([hist_player.assign(game_id=hist_player["game_id"].astype(str)), sp_box], ignore_index=True)
        pr = nba.player_ratings(allbox)
        miss = nba.missing_strength(g, pr)
        ptab, plast = nba.player_table(pr, g)                           # v37b: player ratings before every game
        lineup = nba.lineup_strength(ptab)
        pl_all = nba.player_lines(allbox)                               # v37d: every player's stat lines (stats pages, props)
        ptp, pnow, tadj = nba.prop_table(pl_all, g)
        # upcoming and today's games (the next 7 days)
        sg["day"] = [nba.us_day(t) for t in sg["tip"]]
        up = sg[(sg["day"] >= today - pd.Timedelta(days=1)) & (sg["day"] <= today + pd.Timedelta(days=7))
                & pd.to_numeric(sg["season_type"], errors="coerce").isin([2, 3, 5])].copy()
        cols = ["game_id", "date", "season", "stage", "home_id", "away_id", "home_abbr", "away_abbr", "hs", "as"]
        upx = up.rename(columns={"day": "date", "season_type": "stage"}).assign(home_id=lambda d: d["home_id"].astype(str),
                                                                                 away_id=lambda d: d["away_id"].astype(str), hs=np.nan)
        upx["as"] = np.nan
        allg = pd.concat([g[cols], upx[cols]], ignore_index=True).drop_duplicates("game_id")   # finished games keep their result
        sf = nba.schedule_features(allg)
        settled = nba.stakes(allg)
        ge = nba.enrich(g, sf, {"missing": miss, "lineup": lineup, "settled": settled})   # each game with both sides' adjustment values

        # ---- the weekly test (or the first run ever)
        cfg_p, gate_p = os.path.join(DATA, "model.json"), os.path.join(DATA, "gate.json")
        cfg = json.load(open(cfg_p)) if os.path.exists(cfg_p) else None
        gate = json.load(open(gate_p)) if os.path.exists(gate_p) else {"pass": False, "why": "not tested yet"}
        bt, cur = None, None
        if MODE == "full" or cfg is None:
            print("Weekly test: replaying last season, testing each adjustment...")
            cfg, bt = nba.choose(ge, odds, today)
            gate = nba.gate(bt, cfg, odds)
            gate["replay_pass"], gate["replay_why"] = gate["pass"], gate["why"]
            if any(f in cfg["features"] for f in ("lineup", "missing")):    # v37b: the cautious view (lineups as known before the injury report)
                last = season - 1
                sb = nba.walk(ge, cfg, pd.Timestamp(f"{last - 1}-11-01"), pd.Timestamp(f"{last}-04-20"), pred=nba.knowable(ge))
                s_ = nba.score(sb, cfg["sd_margin"], cfg["home_rate"], odds)
                gate["strict"] = {k: round(s_[k], 4) for k in ("model_ll", "model_ll_on_odds", "book_ll") if k in s_}
                print(f"  strict replay (lineups from each team's previous game): log loss {s_.get('model_ll', float('nan')):.4f}, "
                      f"on games with lines {s_.get('model_ll_on_odds', float('nan')):.4f} against the bookmakers' {s_.get('book_ll', float('nan')):.4f}")
            # this season so far too, for the record (not part of the decision)
            cur = nba.walk(ge, cfg, pd.Timestamp(f"{season - 1}-10-25"), today)
            gate["this_season"] = nba.score(cur, cfg["sd_margin"], cfg["home_rate"], odds) if len(cur) else {}
            bt.to_csv(os.path.join(DATA, "replay.csv"), index=False)  # v37b: the replay itself, for checking month by month
            json.dump(cfg, open(cfg_p, "w"), indent=1)
            json.dump(gate, open(gate_p, "w"), indent=1, default=str)
            print(f"  adjustments in use: {', '.join(cfg['features']) or 'home court only'}; margin spread {cfg['sd_margin']:.1f} points, total {cfg['sd_total']:.1f}")
            print(f"  GATE: {'PASSED' if gate['pass'] else 'not passed'} ({gate['why']}); " + ", ".join(f"{k} {v}" for k, v in gate.items() if k not in ("pass", "why", "this_season")))
        # ---- v37d: the tests for halves and quarters, player props and live chances (weekly; also the first run after they were added,
        #      using the stored replay of last season)
        #      v37h: these tests now include this season's games (so their verdicts move week by week); a model.json from before that
        #      change is re-tested on the next run of either kind
        TESTS_V = "37h"
        rp_ = os.path.join(DATA, "replay.csv")
        stale = cfg.get("tests_v") != TESTS_V
        if bt is None and stale and os.path.exists(rp_):
            bt = pd.read_csv(rp_, dtype={"game_id": str}, parse_dates=["date"])
        if bt is not None and len(bt) and (MODE == "full" or stale):
            print("Weekly test: halves and quarters, player props, live chances (last season and this season so far)...")
            last = season - 1
            if cur is None:
                cur = nba.walk(ge, cfg, pd.Timestamp(f"{season - 1}-10-25"), today)
            bt_all = pd.concat([bt, cur], ignore_index=True) if cur is not None and len(cur) else bt
            pq = nba.update_past_quarters(DATA, last, minutes=10)
            sq = sg[["game_id", "home_q", "away_q"]].copy() if "home_q" in sg else pd.DataFrame(columns=["game_id", "home_q", "away_q"])
            sq = sq[sq["home_q"].astype(str).str.contains(",", na=False)]
            pq_all = pd.concat([pq, sq], ignore_index=True).drop_duplicates("game_id", keep="last")
            cfg["quarters"] = nba.quarter_fit(bt_all, pq_all)
            cfg["live"] = nba.live_fit(bt_all, pq_all, cfg["sd_margin"])
            cfg["props"] = nba.prop_fit(ptp, pd.Timestamp(f"{last - 1}-11-01"), today, split=pd.Timestamp(f"{last}-02-01"))
            cfg["tests_v"] = TESTS_V
            json.dump(cfg, open(cfg_p, "w"), indent=1)

        # ---- v37b: the live record (real pre-game predictions against the bookmakers) also decides, every run
        lp = os.path.join(DATA, "pred_log.csv")
        log = pd.read_csv(lp, dtype={"game_id": str}) if os.path.exists(lp) else pd.DataFrame()
        gate = nba.live_check(gate, log, g, odds)
        json.dump(gate, open(gate_p, "w"), indent=1, default=str)
        lv = gate["live"]
        print(f"  live record: {lv['games']} real predictions with bookmaker lines" + (f", log loss {lv['model_ll']} against the bookmakers' {lv['book_ll']}" if lv["games"] else ""))

        # ---- this week's predictions
        model = nba.fit(ge, today + pd.Timedelta(days=1), cfg)
        form = nba.player_form(pr, g)
        inj = nba.injuries()
        recent = form[form["last_date"] >= today - pd.Timedelta(days=30)]
        out_by_team = {}
        for aid, (status, w, name) in inj.items():
            if aid in recent.index:
                r = recent.loc[aid]
                out_by_team.setdefault(str(r["team_id"]), []).append({"name": r["name"] or name, "status": status, "weight": w, "value": float(r["value"]),
                                                                       "minutes": float(r["minutes"])})
        miss_now = {}
        for x in up.itertuples():
            for tid in (x.home_id, x.away_id):
                miss_now[(x.game_id, str(tid))] = sum(p["weight"] * p["value"] for p in out_by_team.get(str(tid), []))
        pending = up[~up["completed"].astype(str).str.lower().eq("true") & up["state"].isin(["pre"])]
        pend_ = pending.rename(columns={"day": "date"}).assign(home_id=lambda d: d["home_id"].astype(str), away_id=lambda d: d["away_id"].astype(str),
                                                                neutral=lambda d: d["neutral"].astype(str).str.lower().eq("true"))   # (read back from a file as text)
        # v37b: each team's expected lineup: today's roster, every player's minutes cut by his chance of missing (the injury report)
        teams_up = sorted(set(pend_["home_id"]) | set(pend_["away_id"]))
        props_on = any((v or {}).get("pass") for v in (cfg.get("props") or {}).values())
        roster = nba.rosters(teams_up) if ("lineup" in cfg["features"] or props_on) and teams_up else {}
        lu_now = nba.lineup_upcoming(plast, roster, {a: w for a, (s_, w, n_) in inj.items()}, teams_up, today)
        line_now = {(x.game_id, t): lu_now[t] for x in pend_.itertuples() for t in (x.home_id, x.away_id) if t in lu_now}
        if roster:
            print(f"  rosters: {len(roster)} players in {len(set(roster.values()))} teams; expected lineups for {len(lu_now)} teams")
        preds = nba.predict(model, nba.enrich(pend_, sf, {"missing": miss_now, "lineup": line_now, "settled": settled}), cfg) if len(pending) else pd.DataFrame()
        pred_by_gid = {pending.loc[i, "game_id"]: preds.loc[i] for i in preds.index} if len(preds) else {}
        rt = nba.ratings_table(model)
        print(f"Predictions: {len(preds)} games in the next week; published: {'yes' if gate['pass'] else 'no (' + gate['why'] + ')'}")
        # v37d: player props for each side's likely players (15+ expected minutes, not ruled out), statistics that passed their test only
        inj_w = {a: w for a, (s_, w, n_) in inj.items()}
        inj_st = {a: s_ for a, (s_, w, n_) in inj.items()}
        team_of = plast[plast["last_date"] >= today - pd.Timedelta(days=200)]["team_id"].to_dict()
        team_of.update({a: t for a, t in roster.items() if a in plast.index})
        def props_for(tid, opp):
            if not props_on:
                return []
            out_ = []
            for a in [a for a, t in team_of.items() if t == str(tid) and a in pnow]:
                w_ = inj_w.get(a, 0.0)
                em_ = (pnow[a]["em"] or 0) * (1 - w_)
                if em_ < 15 or w_ >= 0.5:
                    continue
                lad = nba.prop_ladders(pnow[a], tadj, cfg.get("props"), str(opp), str(tid), em_)
                if lad:
                    out_.append({"id": a, "name": plast.loc[a, "name"], "min": round(em_, 1), "status": inj_st.get(a), "stats": lad})
            return sorted(out_, key=lambda z: -z["min"])[:8]

        # ---- the prediction log (the last prediction before tip-off is kept), for past days and later the track record
        if len(preds):
            new = pending[["game_id", "tip", "home_name", "away_name"]].join(preds[["p_home", "margin", "total", "pts_home", "pts_away"]])
            new["published"], new["predicted_on"] = bool(gate["pass"]), today.strftime("%Y-%m-%d")
            log = pd.concat([log, new], ignore_index=True).drop_duplicates("game_id", keep="last")
            log.to_csv(lp, index=False)

        # ---- the website's files
        files, games_out = {}, []
        names = {}
        for x in sg.itertuples():
            names[str(x.home_id)] = (x.home_name, x.home_abbr); names[str(x.away_id)] = (x.away_name, x.away_abbr)
        rt["name"], rt["abbr"] = rt["team_id"].map(lambda t: names.get(t, ("", ""))[0]), rt["team_id"].map(lambda t: names.get(t, ("", ""))[1])
        rt["rank"] = rt["net"].rank(ascending=False, method="min").astype(int)
        rmap = rt.set_index("team_id").to_dict("index")
        cur = g[g["season"] == season]
        def last10(tid):
            rows = cur[(cur["home_id"] == tid) | (cur["away_id"] == tid)].tail(10)
            return [{"date": r.date.strftime("%Y-%m-%d"), "opp": r.away_name if r.home_id == tid else r.home_name, "venue": "H" if r.home_id == tid else "A",
                     "score": f"{int(r.hs)}-{int(r.as_)}" if r.home_id == tid else f"{int(r.as_)}-{int(r.hs)}",
                     "result": "W" if (r.hs > r.as_) == (r.home_id == tid) else "L", "game_id": r.game_id} for r in rows.rename(columns={"as": "as_"}).itertuples()][::-1]
        def record(tid):
            hw = ((cur["home_id"] == tid) & (cur["hs"] > cur["as"])).sum() + ((cur["away_id"] == tid) & (cur["as"] > cur["hs"])).sum()
            n = ((cur["home_id"] == tid) | (cur["away_id"] == tid)).sum()
            return int(hw), int(n - hw)
        for i, x in enumerate(up.itertuples()):
            row = up.loc[x.Index].to_dict()
            H, A = team_info(row, "home"), team_info(row, "away")
            gslug = f"nba-{x.day:%Y-%m-%d}-{A['slug']}-at-{H['slug']}"
            e = {"slug": gslug, "tip": x.tip, "date": x.day.strftime("%Y-%m-%d"), "home": H, "away": A, "espn": {"code": "nba", "id": str(x.game_id), "sport": "basketball"},
                 "state": x.state, "score": [x.home_score, x.away_score] if x.state != "pre" else None, "published": bool(gate["pass"])}
            for s, t in (("home", H), ("away", A)):
                t["record"] = record(t["id"]); r_ = rmap.get(t["id"], {})
                t["rating"] = {"off": r_.get("off"), "def": r_.get("def"), "net": r_.get("net"), "rank": r_.get("rank")}
            notes = []
            f_ = sf.loc[x.game_id] if x.game_id in sf.index else None
            for s, t in (("home", H), ("away", A)):
                if f_ is not None and f_.get(f"{s}_b2b") == 1:
                    notes.append(f"{t['short']} played yesterday (second night of a back-to-back)")
                if f_ is not None and (f_.get(f"{s}_travel") or 0) >= 2.5:
                    notes.append(f"{t['short']} travelled about {int(round(f_.get(f'{s}_travel') * 1000, -2)):,} km since their last game")
            if x.game_id in pred_by_gid:
                p = pred_by_gid[x.game_id]
                if gate["pass"]:
                    spreads, totals = nba.fair_lines(p["margin"], p["total"], cfg["sd_margin"], cfg["sd_total"])
                    e.update({"pH": float(p["p_home"]), "pA": float(1 - p["p_home"]), "pts": [float(p["pts_home"]), float(p["pts_away"])],
                              "margin": float(p["margin"]), "total": float(p["total"]), "fair_spread": round(-p["margin"] * 2) / 2, "fair_total": round(p["total"] * 2) / 2,
                              "fair": {"home": 1 / max(p["p_home"], 1e-6), "away": 1 / max(1 - p["p_home"], 1e-6)}, "spreads": spreads, "totals": totals,
                              # v37d: halves and quarters, player props and the live chances (each only where its test passed)
                              "quarters": nba.quarter_markets(cfg.get("quarters"), float(p["margin"]), float(p["total"])),
                              "props": {"home": props_for(H["id"], A["id"]), "away": props_for(A["id"], H["id"])},
                              "live": {"c": cfg["live"]["c"], "a": cfg["live"].get("a", 0.5), "sd": cfg["sd_margin"]} if (cfg.get("live") or {}).get("pass") else None})
            e["notes"] = notes
            e["injuries"] = {s: [{"name": p["name"], "status": p["status"]} for p in sorted(out_by_team.get(t["id"], []), key=lambda z: -z["minutes"]) if p["minutes"] >= 10][:8]
                             for s, t in (("home", H), ("away", A))}
            games_out.append(e)
        games_out.sort(key=lambda e: (e["tip"] or "", e["home"]["name"]))
        meta = {"updated": pd.Timestamp.now("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"), "season": season, "gate": {k: v for k, v in gate.items() if k != "this_season"},
                "this_season": gate.get("this_season"), "adjustments": cfg["features"]}
        files["site/bb/index.json"] = {"meta": meta, "games": [{k: v for k, v in e.items() if k not in ("spreads", "totals", "injuries", "quarters", "props")} for e in games_out]}
        for e in games_out:
            h2h = cur[((cur["home_id"] == e["home"]["id"]) & (cur["away_id"] == e["away"]["id"])) | ((cur["home_id"] == e["away"]["id"]) & (cur["away_id"] == e["home"]["id"]))]
            files[f"site/bb/game/{e['slug']}.json"] = {**e, "form": {"home": last10(e["home"]["id"]), "away": last10(e["away"]["id"])},
                                                       "h2h": [{"date": r.date.strftime("%Y-%m-%d"), "home": r.home_name, "away": r.away_name, "score": f"{int(r.hs)}-{int(r.as_)}"}
                                                               for r in h2h.rename(columns={"as": "as_"}).itertuples()][::-1],
                                                       "sd": {"margin": cfg["sd_margin"], "total": cfg["sd_total"]}}
        files["site/bb/schedule.json"] = [{"slug": e["slug"], "kickoff": e["tip"], "date": e["date"], "competition": "NBA", "espn": e["espn"],
                                           "home": e["home"]["name"], "away": e["away"]["name"]} for e in games_out]
        # standings and team pages
        stand = {"East": [], "West": []}
        for tid, (nm, ab) in names.items():
            if ab not in nba.TEAMS:
                continue
            w, l = record(tid); r_ = rmap.get(tid, {})
            l10 = last10(tid)
            stand[nba.TEAMS[ab][0]].append({"team": nm, "abbr": ab, "slug": slug(nm), "W": w, "L": l, "pct": w / (w + l) if w + l else None,
                                            "l10": "".join(x["result"] for x in l10[::-1]), "net": r_.get("net"), "off": r_.get("off"), "def": r_.get("def"), "rank": r_.get("rank")})
        for conf in stand:
            stand[conf].sort(key=lambda r: (-(r["pct"] if r["pct"] is not None else 0.5), -r["W"], r["team"]))   # no games yet: between 1-0 and 0-1
            lead = stand[conf][0] if stand[conf] else None
            for i, r in enumerate(stand[conf]):
                r["pos"] = i + 1
                r["gb"] = ((lead["W"] - r["W"]) + (r["L"] - lead["L"])) / 2 if lead else 0
        files["site/bb/standings.json"] = {"season": season, "updated": meta["updated"], "conferences": stand}
        for tid, (nm, ab) in names.items():
            if ab not in nba.TEAMS:
                continue
            w, l = record(tid); r_ = rmap.get(tid, {})
            files[f"site/bb/team/{slug(nm)}.json"] = {"name": nm, "abbr": ab, "slug": slug(nm), "conf": nba.TEAMS[ab][0], "W": w, "L": l,
                                                      "rating": {"off": r_.get("off"), "def": r_.get("def"), "net": r_.get("net"), "rank": r_.get("rank"), "pace": r_.get("pace")},
                                                      "last10": last10(tid), "upcoming": [e["slug"] for e in games_out if tid in (e["home"]["id"], e["away"]["id"]) and e["state"] == "pre"],
                                                      "injuries": [{"name": p["name"], "status": p["status"]} for p in out_by_team.get(tid, []) if p["minutes"] >= 10]}
        # ---- v37d: player pages (this season's averages, last season's for comparison, the last 10 games), team rosters, leaders
        gi = g.set_index("game_id")
        reg = g[pd.to_numeric(g["stage"], errors="coerce") == 2]
        def season_avgs(rows):
            n_ = len(rows)
            if not n_:
                return None
            s_ = rows[nba.LINE_COLS].sum()
            pct = lambda m_, a_: round(100 * s_[m_] / s_[a_], 1) if s_[a_] > 0 else None
            return {"gp": n_, **{c: round(float(s_[c] / n_), 1) for c in ("min", "pts", "reb", "ast", "stl", "blk", "to", "fg3")},
                    "fg_pct": pct("fgm", "fga"), "fg3_pct": pct("fg3", "fg3a"), "ft_pct": pct("ftm", "fta"), "starts": int(rows["starter"].sum())}
        plc = pl_all[pl_all["game_id"].isin(set(reg.loc[reg["season"] == season, "game_id"]))]
        pll = pl_all[pl_all["game_id"].isin(set(reg.loc[reg["season"] == season - 1, "game_id"]))]
        pslug = lambda name, aid: f"{slug(name)}-{aid}"
        roster_of, leaders_rows = {}, []
        for aid, rows in plc.groupby("athlete_id"):
            rows = rows.assign(date=rows["game_id"].map(gi["date"])).sort_values("date")
            tid = str(roster.get(aid) or rows["team_id"].iloc[-1])
            nm = rows["name"].iloc[-1]; ps = pslug(nm, aid)
            av, prev_ = season_avgs(rows), season_avgs(pll[pll["athlete_id"] == aid])
            log10 = []
            for x in rows.tail(10).iloc[::-1].itertuples():
                gr = gi.loc[x.game_id]
                home_ = gr["home_id"] == x.team_id
                ts_, os_ = (gr["hs"], gr["as"]) if home_ else (gr["as"], gr["hs"])
                log10.append({"date": gr["date"].strftime("%Y-%m-%d"), "opp": gr["away_name"] if home_ else gr["home_name"], "venue": "H" if home_ else "A",
                              "result": f"{'W' if ts_ > os_ else 'L'} {int(ts_)}-{int(os_)}", "espn": f"nba:{x.game_id}",
                              **{c: (None if pd.isna(getattr(x, c)) else int(getattr(x, c))) for c in ("min", "pts", "reb", "ast", "stl", "blk", "to", "fgm", "fga", "fg3", "fg3a", "ftm", "fta")}})
            tn, ta = names.get(tid, ("", ""))
            files[f"site/bb/player/{ps}.json"] = {"slug": ps, "id": aid, "name": nm, "pos": rows["pos"].dropna().iloc[-1] if rows["pos"].notna().any() else None,
                                                  "team": tn, "team_abbr": ta, "team_slug": slug(tn) if tn else None, "season": season, "avg": av,
                                                  "last_season": prev_, "log": log10, "injury": inj_st.get(aid)}
            roster_of.setdefault(tid, []).append({"slug": ps, "name": nm, "pos": files[f"site/bb/player/{ps}.json"]["pos"], "injury": inj_st.get(aid), **av})
            leaders_rows.append({"slug": ps, "name": nm, "team": ta, "team_slug": slug(tn) if tn else None, **av})
        team_gp = max([r_["W"] + r_["L"] for c_ in stand.values() for r_ in c_] or [1])
        min_gp = max(1, int(round(0.4 * team_gp)))
        cats = [("pts", "Points"), ("reb", "Rebounds"), ("ast", "Assists"), ("stl", "Steals"), ("blk", "Blocks"), ("fg3", "3-pointers made")]
        files["site/bb/leaders.json"] = {"season": season, "updated": meta["updated"], "min_games": min_gp,
                                         "categories": [{"key": k, "label": lab, "players": sorted([r_ for r_ in leaders_rows if r_["gp"] >= min_gp], key=lambda r_: -(r_[k] or 0))[:15]}
                                                        for k, lab in cats]}
        for key_, t_ in list(files.items()):
            if key_.startswith("site/bb/team/"):
                t_["roster"] = sorted(roster_of.get(next((i for i, (n_, a_) in names.items() if slug(n_) == t_["slug"]), ""), []), key=lambda r_: -(r_["min"] or 0))
        # past days: every result this season, with the pre-game chances where Kwallo logged them
        logm = log.set_index("game_id").to_dict("index") if len(log) else {}
        sgf = sg[sg["completed"].astype(str).str.lower().eq("true") & pd.to_numeric(sg["season_type"], errors="coerce").isin([2, 3, 5])]
        for d, dd in sgf.groupby(sgf["day"].dt.strftime("%Y-%m-%d")):
            rows = []
            for x in dd.itertuples():
                lg_ = logm.get(str(x.game_id))
                pH = lg_["p_home"] if lg_ and lg_.get("published") in (True, "True", "true") else None
                rows.append({"home": x.home_name, "away": x.away_name, "home_abbr": x.home_abbr, "away_abbr": x.away_abbr, "home_slug": slug(x.home_name), "away_slug": slug(x.away_name),
                             "hs": x.home_score, "as": x.away_score, "espn": f"nba:{x.game_id}", "id": str(x.game_id), "pH": pH,
                             "margin": (lg_.get("margin") if pH is not None else None),
                             "hit": (None if pH is None else bool((pH >= 0.5) == (x.home_score > x.away_score)))})
            files[f"site/bb/days/{d}.json"] = {"date": d, "games": rows}
        publish(files)
    except Exception:
        traceback.print_exc()
        print("Basketball run FAILED; the website keeps its previous basketball files.")
        storage.sync_up(DATA, seen, prefix=PREFIX)
        sys.exit(1)
    storage.sync_up(DATA, seen, prefix=PREFIX)
    print(f"Finished in {(time.time() - t0) / 60:.1f} minutes.")


if __name__ == "__main__":
    main()
