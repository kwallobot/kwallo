"""Kwallo basketball (v37): the NBA.

Data: three past seasons of team and player box scores from the sportsdataverse (hoopR) files, this season from ESPN (results,
box scores, upcoming games with bookmaker lines, the injury report). Bookmaker lines are only used to test the model; they are never
published.

Model: each team's attack and defence in points per 100 possessions and its pace, fitted with recent games weighted more (a ridge
regression, so a team with few games stays near average). Adjustments, each switched on only if it improves the replayed seasons:
home court (always), the expected lineup's strength from player ratings (v37b; ratings follow players across teams and seasons, so
trades count at once), missing regulars, back-to-backs, days of rest, travel, late-season teams with nothing left to play for, and
each team's own home advantage. The final
margin and total are treated as normal spreads around the predictions (their widths learned from the replays), which gives the win
chances, a fair spread and total, and chances at nearby lines. A team never draws: overtime decides.
"""
import os, json, time, math, datetime as dt
import numpy as np, pandas as pd, requests
from scipy.stats import norm
from sklearn.linear_model import Ridge

ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
HOOPR = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# the 30 arenas (for travel) and the conferences (for standings), by ESPN's team abbreviations
TEAMS = {
    "ATL": ("East", 33.757, -84.396), "BOS": ("East", 42.366, -71.062), "BKN": ("East", 40.683, -73.975), "CHA": ("East", 35.225, -80.839),
    "CHI": ("East", 41.881, -87.674), "CLE": ("East", 41.496, -81.688), "DET": ("East", 42.341, -83.055), "IND": ("East", 39.764, -86.155),
    "MIA": ("East", 25.781, -80.188), "MIL": ("East", 43.045, -87.917), "NY": ("East", 40.751, -73.993), "ORL": ("East", 28.539, -81.384),
    "PHI": ("East", 39.901, -75.172), "TOR": ("East", 43.643, -79.379), "WSH": ("East", 38.898, -77.021),
    "DAL": ("West", 32.790, -96.810), "DEN": ("West", 39.749, -105.008), "GS": ("West", 37.768, -122.388), "HOU": ("West", 29.751, -95.362),
    "LAC": ("West", 33.945, -118.341), "LAL": ("West", 34.043, -118.267), "MEM": ("West", 35.138, -90.051), "MIN": ("West", 44.979, -93.276),
    "NO": ("West", 29.949, -90.082), "OKC": ("West", 35.463, -97.515), "PHX": ("West", 33.446, -112.071), "POR": ("West", 45.532, -122.667),
    "SAC": ("West", 38.580, -121.500), "SA": ("West", 29.427, -98.437), "UTAH": ("West", 40.768, -111.901)}

# optional adjustments, tested in this order (home court is always in): the expected lineup's strength (player ratings), regulars
# missing, back-to-backs, days of rest, travel, a late-season team with nothing left to play for, each team's own home advantage
FEATURES = ["lineup", "missing", "b2b", "rest", "travel", "settled", "team_home"]
CONFIG_DEFAULT = {"features": [], "alpha": 5.0, "half_life": 120, "sd_margin": 12.5, "sd_total": 18.5, "home_rate": 0.56}


def season_of(d):
    """The NBA season a date belongs to, named by the year it ends in (October 2026 to June 2027 = 2027)."""
    d = pd.Timestamp(d)
    return d.year + 1 if d.month >= 8 else d.year


def us_day(ts_utc):
    """The US (Eastern) calendar day of a tip-off given in UTC: evening games start after midnight UTC."""
    return (pd.Timestamp(ts_utc).tz_convert(None) - pd.Timedelta(hours=5)).normalize()


def km(a, b):
    """Great-circle distance in kilometres between two arenas (by abbreviation)."""
    if a not in TEAMS or b not in TEAMS or a == b:
        return 0.0
    (_, la1, lo1), (_, la2, lo2) = TEAMS[a], TEAMS[b]
    p1, p2, dl = math.radians(la1), math.radians(la2), math.radians(lo2 - lo1)
    return 6371 * math.acos(min(1.0, math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl)))


def get_json(url, pause=0.35, tries=3):
    for i in range(tries):
        try:
            time.sleep(pause)
            r = requests.get(url, headers=HEADERS, timeout=25)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(5 * (i + 1)); continue
            return None
        except Exception:
            time.sleep(3)
    return None


# ---------------------------------------------------------------- history (hoopR files, cached in the data folder)
TEAM_COLS = ["game_id", "season", "season_type", "game_date", "game_date_time", "team_id", "team_abbreviation", "team_display_name", "team_short_display_name",
             "team_color", "team_alternate_color", "team_home_away", "team_score", "field_goals_attempted", "free_throws_attempted",
             "offensive_rebounds", "total_turnovers", "opponent_team_id", "opponent_team_abbreviation", "opponent_team_score"]
PLAYER_COLS = ["game_id", "season", "season_type", "game_date", "athlete_id", "athlete_display_name", "team_id", "team_abbreviation", "minutes",
               "field_goals_made", "field_goals_attempted", "free_throws_made", "free_throws_attempted", "offensive_rebounds", "defensive_rebounds",
               "assists", "steals", "blocks", "turnovers", "fouls", "points", "starter", "did_not_play", "athlete_position_abbreviation",
               "three_point_field_goals_made", "three_point_field_goals_attempted"]                      # v37d: threes (player props, stats)


def load_history(data_dir, seasons):
    """Team and player box scores of past seasons, downloaded once and kept (only the columns used)."""
    os.makedirs(os.path.join(data_dir, "hist"), exist_ok=True)
    tparts, pparts = [], []
    for s in seasons:
        for kind, tag, name, cols, parts in [("team", "espn_nba_team_boxscores", f"team_box_{s}.csv", TEAM_COLS, tparts),
                                              ("player", "espn_nba_player_boxscores", f"player_box_{s}.csv", PLAYER_COLS, pparts)]:
            path = os.path.join(data_dir, "hist", name)
            if os.path.exists(path) and not set(cols) <= set(pd.read_csv(path, nrows=0).columns):
                os.remove(path)                                          # v37d: a file kept before a column was added: download it again
            if not os.path.exists(path):
                try:
                    df = pd.read_csv(f"{HOOPR}/{tag}/{name}", usecols=lambda c: c in cols, low_memory=False)
                    df.to_csv(path, index=False)
                    print(f"  history: {name} downloaded ({len(df)} rows)")
                except Exception as ex:
                    print(f"  history: {name} not available ({str(ex)[:60]})")
                    continue
            parts.append(pd.read_csv(path, low_memory=False))
    team = pd.concat(tparts, ignore_index=True) if tparts else pd.DataFrame(columns=TEAM_COLS)
    player = pd.concat(pparts, ignore_index=True) if pparts else pd.DataFrame(columns=PLAYER_COLS)
    return team, player


# ---------------------------------------------------------------- this season (ESPN), cached and updated each run
def _odds(o):
    """Spread (home line), total and both moneylines from one ESPN odds entry; decimal odds."""
    if not isinstance(o, dict):
        return {}
    def dec(x):
        try:
            v = float(str(x).replace("+", "")); return 1 + (v / 100 if v > 0 else 100 / abs(v))
        except Exception:
            return np.nan
    return {"spread": pd.to_numeric(o.get("spread"), errors="coerce"), "total": pd.to_numeric(o.get("overUnder"), errors="coerce"),
            "ml_home": dec((o.get("homeTeamOdds") or {}).get("moneyLine")), "ml_away": dec((o.get("awayTeamOdds") or {}).get("moneyLine"))}


def _quarters(competitor):
    """A team's points in each period as text, "33,29,38,25" (overtimes follow), or "" when not played yet."""
    ls = competitor.get("linescores") or []
    return ",".join(str(int(float(x.get("value", x.get("displayValue", 0)) or 0))) for x in ls) if ls else ""


def quarters_of(text):
    """'33,29,38,25' -> [33, 29, 38, 25]"""
    return [int(x) for x in str(text).split(",") if x.strip().lstrip("-").isdigit()] if isinstance(text, str) and text else []


def update_past_quarters(data_dir, season, minutes=8.0):
    """v37d: a past season's scores by quarter, from ESPN's daily scoreboards (about 270 pages, read once and kept)."""
    path, sp = os.path.join(data_dir, "past_quarters.csv"), os.path.join(data_dir, "past_quarters_state.json")
    st = json.load(open(sp)) if os.path.exists(sp) else {"days_done": []}
    old = pd.read_csv(path, dtype={"game_id": str}) if os.path.exists(path) else pd.DataFrame()
    t0, rows = time.time(), []
    for d in pd.date_range(f"{season - 1}-10-15", f"{season}-06-30"):
        key = d.strftime("%Y%m%d")
        if key in st["days_done"]:
            continue
        if time.time() - t0 > minutes * 60:
            break
        b = get_json(f"{ESPN}/scoreboard?dates={key}")
        if b is None:
            continue
        for ev in b.get("events", []):
            c = ev["competitions"][0]
            cs = {x.get("homeAway"): x for x in c.get("competitors", [])}
            if "home" in cs and "away" in cs and (ev.get("status", {}).get("type", {}) or {}).get("completed"):
                rows.append({"game_id": str(ev["id"]), "home_q": _quarters(cs["home"]), "away_q": _quarters(cs["away"])})
        st["days_done"].append(key)
    if rows:
        old = pd.concat([old, pd.DataFrame(rows)], ignore_index=True).drop_duplicates("game_id", keep="last")
        old.to_csv(path, index=False)
    json.dump(st, open(sp, "w"))
    print(f"  last season's scores by quarter: {len(old)} games stored ({len(rows)} added)")
    return old


def update_season(data_dir, today, days_ahead=7):
    """ESPN's scoreboards day by day since 1 October (finished days are cached), plus the next week. Returns every game of
    this season with its status, scores and (for upcoming games) the bookmaker lines first seen."""
    path, sp = os.path.join(data_dir, "season_games.csv"), os.path.join(data_dir, "season_state.json")
    st = json.load(open(sp)) if os.path.exists(sp) else {"days_done": []}
    old = pd.read_csv(path, dtype={"game_id": str, "home_id": str, "away_id": str}) if os.path.exists(path) else pd.DataFrame()
    if len(old) and "home_q" not in old.columns:
        st["days_done"] = []                                             # v37d: read again once, for the scores by quarter
    start = pd.Timestamp(f"{season_of(today) - 1}-10-01")
    rows = []
    for d in pd.date_range(start, today + pd.Timedelta(days=days_ahead)):
        key = d.strftime("%Y%m%d")
        if key in st["days_done"]:
            continue
        b = get_json(f"{ESPN}/scoreboard?dates={key}")
        if b is None:
            continue
        all_done = True
        for ev in b.get("events", []):
            c = ev["competitions"][0]
            cs = {x.get("homeAway"): x for x in c.get("competitors", [])}
            if "home" not in cs or "away" not in cs:
                continue
            stt = ev["status"]["type"]
            all_done &= bool(stt.get("completed"))
            o = _odds((c.get("odds") or [None])[0])
            rows.append({"game_id": str(ev["id"]), "tip": ev["date"], "season": (ev.get("season") or {}).get("year"), "season_type": (ev.get("season") or {}).get("type"),
                         "state": stt.get("state"), "completed": bool(stt.get("completed")), "neutral": bool(c.get("neutralSite")),
                         **{f"{s}_{k}": v for s in ("home", "away") for k, v in {
                             "id": str(cs[s]["team"]["id"]), "abbr": cs[s]["team"].get("abbreviation"), "name": cs[s]["team"].get("displayName"),
                             "short": cs[s]["team"].get("shortDisplayName"), "color": cs[s]["team"].get("color"), "alt": cs[s]["team"].get("alternateColor"),
                             "score": pd.to_numeric(cs[s].get("score"), errors="coerce"), "q": _quarters(cs[s])}.items()},
                         **{f"pre_{k}": v for k, v in o.items()}})
        if all_done and d < today - pd.Timedelta(days=1):
            st["days_done"].append(key)
    new = pd.DataFrame(rows)
    if len(old) and len(new):
        keep = old.set_index("game_id")[[c for c in old.columns if c.startswith("pre_")]]   # the first lines seen stay (not the ones after tip-off)
        new = new.set_index("game_id")
        for c in keep.columns:
            if c in new:
                new[c] = keep[c].reindex(new.index).fillna(new[c]) if c in keep else new[c]
        new = new.reset_index()
    g = pd.concat([old, new], ignore_index=True).drop_duplicates("game_id", keep="last") if len(new) else old
    if len(g):
        g.to_csv(path, index=False)
    json.dump(st, open(sp, "w"))
    return g


def update_boxes(data_dir, season_games, minutes=6.0):
    """Box scores (team and players) of this season's finished games, read once each from ESPN's game pages."""
    tp, pp = os.path.join(data_dir, "season_team_box.csv"), os.path.join(data_dir, "season_player_box.csv")
    if os.path.exists(pp) and "three_point_field_goals_made" not in pd.read_csv(pp, nrows=0).columns:
        for f_ in (tp, pp):                                              # v37d: kept before threes were read: read this season again
            os.remove(f_) if os.path.exists(f_) else None
    tb = pd.read_csv(tp, dtype={"game_id": str, "team_id": str}) if os.path.exists(tp) else pd.DataFrame()
    pb = pd.read_csv(pp, dtype={"game_id": str, "team_id": str, "athlete_id": str}) if os.path.exists(pp) else pd.DataFrame()
    have = set(tb["game_id"]) if len(tb) else set()
    todo = season_games[season_games["completed"].astype(str).str.lower().eq("true") & ~season_games["game_id"].isin(have)
                        & pd.to_numeric(season_games["season_type"], errors="coerce").isin([2, 3, 5])]
    t0, trows, prows = time.time(), [], []
    for g in todo.itertuples():
        if time.time() - t0 > minutes * 60:
            break
        s = get_json(f"{ESPN}/summary?event={g.game_id}")
        if not s:
            continue
        for t in (s.get("boxscore") or {}).get("teams") or []:
            v = {x.get("name"): x.get("displayValue") for x in t.get("statistics") or []}
            fg, ft = str(v.get("fieldGoalsMade-fieldGoalsAttempted", "-")).split("-"), str(v.get("freeThrowsMade-freeThrowsAttempted", "-")).split("-")
            trows.append({"game_id": g.game_id, "team_id": str((t.get("team") or {}).get("id")), "field_goals_attempted": pd.to_numeric(fg[-1], errors="coerce"),
                          "free_throws_attempted": pd.to_numeric(ft[-1], errors="coerce"), "offensive_rebounds": pd.to_numeric(v.get("offensiveRebounds"), errors="coerce"),
                          "total_turnovers": pd.to_numeric(v.get("totalTurnovers", v.get("turnovers")), errors="coerce")})
        for t in (s.get("boxscore") or {}).get("players") or []:
            tid = str((t.get("team") or {}).get("id"))
            for blk in t.get("statistics") or []:
                keys = blk.get("keys") or []
                for a in blk.get("athletes") or []:
                    vals = dict(zip(keys, a.get("stats") or []))
                    def num(k):
                        return pd.to_numeric(str(vals.get(k, "")).split("-")[0], errors="coerce")
                    def att(k):
                        return pd.to_numeric(str(vals.get(k, "-")).split("-")[-1], errors="coerce")
                    prows.append({"game_id": g.game_id, "team_id": tid, "athlete_id": str((a.get("athlete") or {}).get("id")),
                                  "athlete_display_name": (a.get("athlete") or {}).get("displayName"), "minutes": num("minutes"),
                                  "field_goals_made": num("fieldGoalsMade-fieldGoalsAttempted"), "field_goals_attempted": att("fieldGoalsMade-fieldGoalsAttempted"),
                                  "free_throws_made": num("freeThrowsMade-freeThrowsAttempted"), "free_throws_attempted": att("freeThrowsMade-freeThrowsAttempted"),
                                  "three_point_field_goals_made": num("threePointFieldGoalsMade-threePointFieldGoalsAttempted"),
                                  "three_point_field_goals_attempted": att("threePointFieldGoalsMade-threePointFieldGoalsAttempted"),
                                  "offensive_rebounds": num("offensiveRebounds"), "defensive_rebounds": num("defensiveRebounds"), "assists": num("assists"),
                                  "steals": num("steals"), "blocks": num("blocks"), "turnovers": num("turnovers"), "fouls": num("fouls"), "points": num("points"),
                                  "starter": bool(a.get("starter")), "did_not_play": bool(a.get("didNotPlay")),
                                  "athlete_position_abbreviation": (((a.get("athlete") or {}).get("position")) or {}).get("abbreviation")})
    if trows:
        tb = pd.concat([tb, pd.DataFrame(trows)], ignore_index=True); tb.to_csv(tp, index=False)
    if prows:
        pb = pd.concat([pb, pd.DataFrame(prows)], ignore_index=True); pb.to_csv(pp, index=False)
    left = max(0, len(todo) - len(set(r["game_id"] for r in trows)))
    print(f"  this season's box scores: {len(set(r['game_id'] for r in trows))} added, {left} still to read")
    return tb, pb


def update_past_odds(data_dir, game_ids, minutes=6.0, recent_ids=None):
    """Bookmaker lines of past games (for testing the model only), read once each from ESPN's game pages."""
    path = os.path.join(data_dir, "past_odds.csv")
    od = pd.read_csv(path, dtype={"game_id": str}) if os.path.exists(path) else pd.DataFrame(columns=["game_id"])
    tried = set(od["game_id"].astype(str))
    t0, rows = time.time(), []
    todo = [str(g) for g in game_ids if str(g) not in tried]
    # v37b: this season's games first (few, newest first), then last season in a shuffled order, so a run that stops early still
    # leaves a sample spread over the whole season (the end of a season alone flatters the bookmakers: they know who rests)
    rs = set(map(str, recent_ids or []))
    cur, old = [x for x in todo if x in rs], [x for x in todo if x not in rs]
    order = cur[::-1] + [old[i] for i in np.random.default_rng(7).permutation(len(old))]
    for gid in order:
        if time.time() - t0 > minutes * 60:
            break
        s = get_json(f"{ESPN}/summary?event={gid}", pause=0.25)
        if s is None:
            continue
        o = next((x for x in (s.get("pickcenter") or []) + (s.get("odds") or []) if isinstance(x, dict) and x.get("spread") is not None), None)
        rows.append({"game_id": str(gid), **_odds(o)})
    if rows:
        od = pd.concat([od, pd.DataFrame(rows)], ignore_index=True).drop_duplicates("game_id", keep="last")
        od.to_csv(path, index=False)
    print(f"  past bookmaker lines: {len(rows)} games read this run, {len(od)} stored")
    return od


# ---------------------------------------------------------------- one table of games, with possessions and the adjustment features
def game_table(hist_team, season_games, season_team):
    """One row per finished game: date, teams, scores and possessions (field-goal attempts + 0.44 x free throws - offensive rebounds
    + turnovers, averaged over the two teams)."""
    h = hist_team[hist_team["season_type"].isin([2, 3, 5])].copy()
    h["game_id"], h["team_id"] = _ids(h["game_id"]), _ids(h["team_id"])
    h["poss"] = h["field_goals_attempted"] + 0.44 * h["free_throws_attempted"] - h["offensive_rebounds"] + h["total_turnovers"]
    home, away = h[h["team_home_away"] == "home"], h[h["team_home_away"] == "away"]
    gh = home.merge(away[["game_id", "team_id", "team_abbreviation", "team_display_name", "team_score", "poss"]], on="game_id", suffixes=("", "_a"))
    hist = pd.DataFrame({"game_id": gh["game_id"], "date": pd.to_datetime(gh["game_date"]), "season": gh["season"].astype(int), "stage": gh["season_type"],
                         "home_id": gh["team_id"], "away_id": gh["team_id_a"], "home_abbr": gh["team_abbreviation"], "away_abbr": gh["team_abbreviation_a"],
                         "home_name": gh["team_display_name"], "away_name": gh["team_display_name_a"], "hs": gh["team_score"], "as": gh["team_score_a"],
                         "poss": (gh["poss"] + gh["poss_a"]) / 2, "neutral": False})
    parts = [hist]
    if len(season_games) and len(season_team):
        sg = season_games[season_games["completed"].astype(str).str.lower().eq("true")].copy()
        stb = season_team.copy()
        stb["poss"] = stb["field_goals_attempted"] + 0.44 * stb["free_throws_attempted"] - stb["offensive_rebounds"] + stb["total_turnovers"]
        pm = stb.groupby("game_id")["poss"].mean()
        sg = sg[sg["game_id"].isin(pm.index)]
        parts.append(pd.DataFrame({"game_id": sg["game_id"], "date": [us_day(t) for t in sg["tip"]], "season": sg["season"].astype(int), "stage": sg["season_type"],
                                   "home_id": sg["home_id"].astype(str), "away_id": sg["away_id"].astype(str), "home_abbr": sg["home_abbr"], "away_abbr": sg["away_abbr"],
                                   "home_name": sg["home_name"], "away_name": sg["away_name"], "hs": sg["home_score"], "as": sg["away_score"],
                                   "poss": sg["game_id"].map(pm), "neutral": sg["neutral"].astype(str).str.lower().eq("true")}))
    g = pd.concat(parts, ignore_index=True).dropna(subset=["hs", "as", "poss"]).drop_duplicates("game_id", keep="last")
    g = g[pd.to_numeric(g["stage"], errors="coerce").isin([2, 3, 5])]          # regular season, play-offs, play-in (not pre-season)
    return g.sort_values("date").reset_index(drop=True)


def schedule_features(games):
    """Each side's rest (days since its last game), back-to-back flag and travel (km from where it last played).
    `games` holds finished and upcoming games (the upcoming ones need date, home_abbr and away_abbr only)."""
    long = pd.concat([games[["game_id", "date", "home_abbr", "home_abbr"]].set_axis(["game_id", "date", "team", "venue"], axis=1).assign(side="home"),
                      games[["game_id", "date", "away_abbr", "home_abbr"]].set_axis(["game_id", "date", "team", "venue"], axis=1).assign(side="away")])
    long = long.sort_values(["team", "date"])
    long["prev_date"] = long.groupby("team")["date"].shift(1)
    long["prev_venue"] = long.groupby("team")["venue"].shift(1)
    long["rest"] = (long["date"] - long["prev_date"]).dt.days
    long["b2b"] = (long["rest"] == 1).astype(float)
    long["rest"] = long["rest"].clip(upper=4).fillna(4).astype(float)     # v37b: days of rest, 4 or more counting as 4 (also a season's first game)
    long["travel"] = [km(a, b) / 1000 if isinstance(a, str) else 0.0 for a, b in zip(long["prev_venue"], long["venue"])]
    wide = long.pivot_table(index="game_id", columns="side", values=["rest", "b2b", "travel"], aggfunc="first")
    wide.columns = [f"{s}_{v}" for v, s in wide.columns]
    return wide


def player_ratings(player_box):
    """Each player-game's game score (a one-number summary of a box-score line) and minutes."""
    p = player_box.copy()
    for c in ["minutes", "points", "field_goals_made", "field_goals_attempted", "free_throws_made", "free_throws_attempted", "offensive_rebounds",
              "defensive_rebounds", "steals", "assists", "blocks", "fouls", "turnovers"]:
        p[c] = pd.to_numeric(p[c], errors="coerce").fillna(0)
    p["gmsc"] = (p["points"] + 0.4 * p["field_goals_made"] - 0.7 * p["field_goals_attempted"] - 0.4 * (p["free_throws_attempted"] - p["free_throws_made"])
                 + 0.7 * p["offensive_rebounds"] + 0.3 * p["defensive_rebounds"] + p["steals"] + 0.7 * p["assists"] + 0.7 * p["blocks"] - 0.4 * p["fouls"] - p["turnovers"])
    p["game_id"], p["team_id"], p["athlete_id"] = _ids(p["game_id"]), _ids(p["team_id"]), _ids(p["athlete_id"])
    return p[["game_id", "team_id", "athlete_id", "athlete_display_name", "minutes", "gmsc"]]


def _ids(s):
    """Ids as plain text ("1234", never "1234.0" from a column a file stored as numbers)."""
    n = pd.to_numeric(s, errors="coerce")
    return n.astype("Int64").astype(str).where(n.notna(), s.astype(str))


# ---------------------------------------------------------------- v37b: player ratings and who is expected to play
LINEUP_N = 9                       # a lineup's strength: the 9 players expected to play most


def player_table(pr, games, decay=0.98, prior_min=250.0, bench=8.0):
    """Every player-game (with minutes) in date order, with what was known before it: the player's rating (game score per 36 minutes
    from all his earlier games, for any team and season, older games fading by 2% a game and pulled towards a bench player's 8 until
    he has played a few hundred minutes) and his expected minutes (recent games weighted most). Also each player's values after his
    latest game, for upcoming games."""
    dates = games.set_index("game_id")["date"]
    p = pr[pr["game_id"].isin(dates.index) & (pr["minutes"] > 0)].assign(date=lambda x: x["game_id"].map(dates))
    p = p.sort_values(["athlete_id", "date"]).reset_index(drop=True)
    aid, gs, mn = p["athlete_id"].values, p["gmsc"].values.astype(float), p["minutes"].values.astype(float)
    r36, em = np.empty(len(p)), np.empty(len(p))
    now = {}
    sg = sm = 0.0; e = None; prev = None
    for i in range(len(p)):
        if aid[i] != prev:
            if prev is not None:
                now[prev] = (36 * (sg + bench / 36 * prior_min) / (sm + prior_min), e)
            sg = sm = 0.0; e = None; prev = aid[i]
        r36[i] = 36 * (sg + bench / 36 * prior_min) / (sm + prior_min)
        em[i] = e if e is not None else 15.0
        sg, sm = decay * sg + gs[i], decay * sm + mn[i]
        e = mn[i] if e is None else 0.75 * e + 0.25 * mn[i]
    if prev is not None:
        now[prev] = (36 * (sg + bench / 36 * prior_min) / (sm + prior_min), e)
    p["r36"], p["em"] = r36, em
    last = p.groupby("athlete_id").agg(team_id=("team_id", "last"), name=("athlete_display_name", "last"), last_date=("date", "max"))
    last["r36"] = [now[a][0] for a in last.index]
    last["em"] = [now[a][1] for a in last.index]
    return p, last


def _strength(em, r36):
    """Minutes-weighted rating of the LINEUP_N players expected to play most."""
    o = np.argsort(-em)[:LINEUP_N]
    w = em[o]
    return float((w * r36[o]).sum() / w.sum()) if w.sum() > 0 else np.nan


def lineup_strength(ptab):
    """(game_id, team_id) -> the strength of the lineup that played (each player rated on his games before that one)."""
    out = {}
    for key, x in ptab.groupby(["game_id", "team_id"]):
        out[key] = _strength(x["em"].values, x["r36"].values)
    return out


def rosters(team_ids):
    """ESPN's current roster of each team: athlete id -> team id (an empty answer leaves the last team a player played for)."""
    out = {}
    for tid in team_ids:
        j = get_json(f"{ESPN}/teams/{tid}/roster") or {}
        ath = j.get("athletes") or []
        for a in ath:
            for x in (a.get("items") if isinstance(a, dict) and "items" in a else [a]):
                if isinstance(x, dict) and x.get("id"):
                    out[str(x["id"])] = str(tid)
    return out


def lineup_upcoming(last, roster, out_w, team_ids, today):
    """team id -> the expected lineup's strength for its next game: its roster (or, without one, players whose latest game was for
    it in the last 200 days), each player's expected minutes cut by his chance of missing the game (the injury report)."""
    res = {}
    recent = last[last["last_date"] >= today - pd.Timedelta(days=200)]
    team_of = recent["team_id"].to_dict()
    if roster:
        team_of.update({a: t for a, t in roster.items() if a in last.index})
    for tid in team_ids:
        ids = [a for a, t in team_of.items() if t == str(tid)]
        if not ids:
            continue
        x = last.loc[ids]
        em = x["em"].fillna(10.0).values * np.array([1 - out_w.get(a, 0.0) for a in ids])
        res[str(tid)] = _strength(em, x["r36"].values)
    return res


def stakes(allg):
    """(game_id, team_id) -> 1 when that team's regular season no longer matters: it can't reach the play-in (10th place) any more,
    or it can't drop out of the top 6 (approximately: wins only, no tie-breaks). Late-season teams like these rest players."""
    out = {}
    g = allg[pd.to_numeric(allg["stage"], errors="coerce") == 2].sort_values("date").rename(columns={"as": "as_"})
    for season, gs_ in g.groupby("season"):
        W, L = {}, {}
        conf = {}
        for x in gs_.itertuples():
            conf[x.home_id] = TEAMS.get(x.home_abbr, ("?",))[0]; conf[x.away_id] = TEAMS.get(x.away_abbr, ("?",))[0]
        for day, dg in gs_.groupby("date"):
            table = {}
            for t, c in conf.items():
                table.setdefault(c, []).append((W.get(t, 0), L.get(t, 0), t))
            settled = set()
            for c, rows in table.items():
                rows.sort(key=lambda r: -r[0] / max(r[0] + r[1], 1))
                if len(rows) < 11 or sum(r[0] + r[1] for r in rows) / len(rows) < 50:
                    continue
                w10 = rows[9][0]
                w7, rem7 = rows[6][0], 82 - rows[6][0] - rows[6][1]
                for i, (w, l, t) in enumerate(rows):
                    rem = 82 - w - l
                    if w + rem < w10 or (i < 6 and w > w7 + rem7):
                        settled.add(t)
            for x in dg.itertuples():
                for t in (x.home_id, x.away_id):
                    out[(x.game_id, t)] = 1.0 if t in settled else 0.0
            for x in dg.itertuples():                                    # then the day's results count
                if pd.notna(x.hs) and pd.notna(x.as_):
                    win, lose = (x.home_id, x.away_id) if x.hs > x.as_ else (x.away_id, x.home_id)
                    W[win] = W.get(win, 0) + 1; L[lose] = L.get(lose, 0) + 1
    return out


def missing_strength(games, pr):
    """For every finished game and side: the strength of the team's regular players who didn't play. A regular averaged 12+ minutes
    over the team's previous 10 games; their weight is their share of the team's minutes times how far their game score per 36
    minutes is above a bench player's (8). Also returns each player's current form, for the injury report."""
    dates = games.set_index("game_id")["date"]
    pr = pr[pr["game_id"].isin(dates.index)].assign(date=lambda x: x["game_id"].map(dates)).sort_values("date")
    out = {}
    for tid, tg in pr.groupby("team_id"):
        gids = list(dict.fromkeys(tg["game_id"]))
        mins = tg.pivot_table(index="game_id", columns="athlete_id", values="minutes", aggfunc="sum").reindex(gids).fillna(0)
        gs = tg.pivot_table(index="game_id", columns="athlete_id", values="gmsc", aggfunc="sum").reindex(gids).fillna(0)
        avg_min = mins.rolling(10, min_periods=3).mean().shift(1)
        played = (mins > 0).astype(float)
        gs36 = (gs.where(mins > 5).rolling(15, min_periods=3).sum() / mins.where(mins > 5).rolling(15, min_periods=3).sum() * 36).shift(1)
        value = (avg_min / 240) * (gs36 - 8).clip(lower=0) / 10
        miss = (value * (avg_min >= 12) * (1 - played)).sum(axis=1)
        for gid, v in miss.items():
            out[(gid, tid)] = float(v)
    return out


def player_form(pr, games, n=15):
    """Each player's recent minutes and game score per 36 (for weighing an injury report), keyed by athlete id."""
    dates = games.set_index("game_id")["date"]
    p = pr[pr["game_id"].isin(dates.index) & (pr["minutes"] > 0)].assign(date=lambda x: x["game_id"].map(dates)).sort_values("date")
    last = p.groupby("athlete_id").tail(n)
    agg = last.groupby("athlete_id").agg(team_id=("team_id", "last"), name=("athlete_display_name", "last"), minutes=("minutes", "mean"),
                                         gmsc=("gmsc", "sum"), mins_tot=("minutes", "sum"), games=("minutes", "size"), last_date=("date", "max"))
    agg["gs36"] = agg["gmsc"] / agg["mins_tot"].clip(lower=1) * 36
    agg["value"] = (agg["minutes"] / 240) * (agg["gs36"] - 8).clip(lower=0) / 10
    return agg


# ---------------------------------------------------------------- the model
def enrich(games, sf, extra):
    """Each game with both sides' adjustment values as columns (home_b2b, away_travel, home_lineup...), so fitting works on whole
    columns at once. `extra` maps each of "missing", "lineup" and "settled" to a dict (game_id, team_id) -> that side's value
    (a lineup without a value gets the average one)."""
    g = games.copy()
    for side in ("home", "away"):
        for f, dflt in (("b2b", 0.0), ("travel", 0.0), ("rest", 4.0)):
            col = f"{side}_{f}"
            g[col] = g["game_id"].map(sf[col]).fillna(dflt).astype(float) if col in sf else dflt
        for f, m in (extra or {}).items():
            g[f"{side}_{f}"] = [m.get((gid, tid), np.nan) for gid, tid in zip(g["game_id"], g[f"{side}_id"])]
    for f in (extra or {}):
        fill = 0.0 if f != "lineup" else float(np.nanmean(list((extra or {})[f].values()) or [12.0]))
        for side in ("home", "away"):
            g[f"{side}_{f}"] = g[f"{side}_{f}"].astype(float).fillna(fill)
    if "neutral" not in g:
        g["neutral"] = False
    g["neutral"] = g["neutral"].astype(str).str.lower().eq("true")
    return g


def _matrix(g, teams, feats, side):
    """Efficiency regression rows for one side attacking: [attack one-hot | defence one-hot | home | own and opponent features |
    (with "team_home") each team's own extra home advantage, pulled towards the league's by the ridge]."""
    other = "away" if side == "home" else "home"
    t_index = {t: i for i, t in enumerate(teams)}
    plain = [f for f in feats if f != "team_home"]
    k, n = len(teams), len(g)
    X = np.zeros((n, 2 * k + 1 + 2 * len(plain) + (k if "team_home" in feats else 0)))
    oi = np.array([t_index.get(t, -1) for t in g[f"{side}_id"]]); di = np.array([t_index.get(t, -1) for t in g[f"{other}_id"]])
    r = np.arange(n)
    X[r[oi >= 0], oi[oi >= 0]] = 1
    X[r[di >= 0], k + di[di >= 0]] = 1
    X[:, 2 * k] = (~g["neutral"].values).astype(float) if side == "home" else 0.0
    for j, f in enumerate(plain):
        X[:, 2 * k + 1 + 2 * j] = g[f"{side}_{f}"].values
        X[:, 2 * k + 2 + 2 * j] = g[f"{other}_{f}"].values
    if "team_home" in feats and side == "home":
        ok = (oi >= 0) & ~g["neutral"].values
        X[r[ok], 2 * k + 1 + 2 * len(plain) + oi[ok]] = 1
    return X


def _pace_matrix(g, teams):
    t_index = {t: i for i, t in enumerate(teams)}
    P = np.zeros((len(g), len(teams)))
    for col in ("home_id", "away_id"):
        idx = np.array([t_index.get(t, -1) for t in g[col]])
        ok = idx >= 0
        P[np.arange(len(g))[ok], idx[ok]] += 1
    return P


def fit(g, asof, cfg):
    """Ratings as of a date from the (enriched) games before it: efficiency with the chosen adjustments, and pace."""
    g = g[(g["date"] < asof) & (g["date"] >= asof - pd.Timedelta(days=3 * 365))]
    teams = sorted(set(g["home_id"]) | set(g["away_id"]))
    feats = cfg["features"]
    X = np.vstack([_matrix(g, teams, feats, "home"), _matrix(g, teams, feats, "away")])
    y = np.r_[100 * g["hs"].values / g["poss"].values, 100 * g["as"].values / g["poss"].values]
    days = (asof - g["date"]).dt.days.values
    wg = 0.5 ** (days / cfg["half_life"])
    m = Ridge(alpha=cfg["alpha"]).fit(X, y, sample_weight=np.r_[wg, wg])
    wp = 0.5 ** (days / cfg.get("pace_hl", cfg["half_life"]))           # v37b: pace can fade at its own speed
    pm = Ridge(alpha=cfg["alpha"]).fit(_pace_matrix(g, teams), g["poss"].values, sample_weight=wp)
    return {"teams": teams, "eff": m, "pace": pm, "feats": feats, "k": len(teams)}


def predict(model, games, cfg):
    """Expected points for each side of (enriched) `games`, the margin and total, and the home side's chance of winning."""
    feats, teams = model["feats"], model["teams"]
    eh = model["eff"].predict(_matrix(games, teams, feats, "home"))
    ea = model["eff"].predict(_matrix(games, teams, feats, "away"))
    pace = model["pace"].predict(_pace_matrix(games, teams))
    ph, pa = eh * pace / 100, ea * pace / 100
    margin, total = ph - pa, ph + pa
    p_home = norm.cdf(margin / cfg["sd_margin"])
    return pd.DataFrame({"pts_home": ph, "pts_away": pa, "margin": margin, "total": total, "p_home": p_home, "pace": pace}, index=games.index)


def ratings_table(model):
    """Each team's attacking and defensive rating (points per 100 possessions above / below average) and pace."""
    k, teams = model["k"], model["teams"]
    c = model["eff"].coef_
    pc = model["pace"].coef_
    # a game's possessions = baseline + both teams' pace terms, so a team's pace against an average side is baseline + its own term
    # (v37j: was baseline / 2, which showed about half the real figure)
    return pd.DataFrame({"team_id": teams, "off": c[:k], "def": -c[k:2 * k], "pace": pc + model["pace"].intercept_}).assign(net=lambda d: d["off"] + d["def"])


# ---------------------------------------------------------------- replays (backtest), the adjustment tests and the gate
def walk(g, cfg, start, end, pred=None):
    """Replay week by week from `start` to `end` on (enriched) games: fit on the games before each week, predict that week's games
    (from `pred` when given: the same games with other adjustment values, as in the strict replay)."""
    out = []
    pred = g if pred is None else pred
    weeks = pd.date_range(start - pd.Timedelta(days=start.weekday()), end, freq="7D")
    for w in weeks:
        wk = pred[(pred["date"] >= w) & (pred["date"] < w + pd.Timedelta(days=7))]
        if wk.empty or (g["date"] < w).sum() < 300:
            continue
        p = predict(fit(g, w, cfg), wk, cfg)
        out.append(wk[["game_id", "date", "season", "home_id", "away_id", "hs", "as"]].join(p))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def knowable(g, feats=("lineup", "missing")):
    """The same games with each side's lineup and missing values taken from that team's previous game: what was known before the
    injury report. The ordinary replay uses who actually played (known at tip-off), so this stricter one is the cautious view."""
    x = g.copy()
    feats = [f for f in feats if f"home_{f}" in x]
    if not feats:
        return x
    long = pd.concat([pd.DataFrame({"gid": x["game_id"].values, "date": x["date"].values, "team": x[f"{s}_id"].values, "side": s,
                                    **{f: x[f"{s}_{f}"].values for f in feats}}) for s in ("home", "away")]).sort_values(["team", "date"])
    for f in feats:
        long[f + "_prev"] = long.groupby("team")[f].shift(1)
    for s in ("home", "away"):
        part = long[long["side"] == s].set_index("gid")
        for f in feats:
            x[f"{s}_{f}"] = x["game_id"].map(part[f + "_prev"]).fillna(x[f"{s}_{f}"])
    return x


def score(bt, sd_margin, home_rate, odds=None):
    """Log loss of the winner chances (model, a naive 'home team wins this often' guess, and the bookmakers where their lines exist),
    and how far the predicted margin and total miss (model and bookmakers' lines)."""
    if bt.empty:
        return {}
    won = (bt["hs"] > bt["as"]).astype(int).values
    p = np.clip(norm.cdf(bt["margin"] / sd_margin), 1e-6, 1 - 1e-6)
    ll = -(won * np.log(p) + (1 - won) * np.log(1 - p))
    naive = -(won * np.log(home_rate) + (1 - won) * np.log(1 - home_rate))
    res = {"games": int(len(bt)), "model_ll": float(ll.mean()), "naive_ll": float(naive.mean()),
           "margin_mae": float(np.abs(bt["margin"] - (bt["hs"] - bt["as"])).mean()), "total_mae": float(np.abs(bt["total"] - (bt["hs"] + bt["as"])).mean())}
    if odds is not None and len(odds):
        b = bt.merge(odds, on="game_id", how="inner").dropna(subset=["ml_home", "ml_away"])
        if len(b):
            ib = (1 / b["ml_home"]) / (1 / b["ml_home"] + 1 / b["ml_away"])
            wb = (b["hs"] > b["as"]).astype(int).values
            pb = np.clip(norm.cdf(b["margin"] / sd_margin), 1e-6, 1 - 1e-6)
            res.update({"odds_games": int(len(b)), "book_ll": float((-(wb * np.log(ib) + (1 - wb) * np.log(1 - ib))).mean()),
                        "model_ll_on_odds": float((-(wb * np.log(pb) + (1 - wb) * np.log(1 - pb))).mean())})
            bs = b.dropna(subset=["spread", "total_y" if "total_y" in b else "total"])
            if len(bs):
                tot_b = bs["total_y"] if "total_y" in bs else bs["total"]
                res.update({"book_margin_mae": float(np.abs(-bs["spread"] - (bs["hs"] - bs["as"])).mean()),
                            "model_margin_mae_on_odds": float(np.abs(bs["margin"] - (bs["hs"] - bs["as"])).mean()),
                            "book_total_mae": float(np.abs(tot_b - (bs["hs"] + bs["as"])).mean())})
    return res


def fit_sd(bt):
    """The spread width that turns predicted margins into the best-scoring winner chances (by log loss, not by the margin errors)."""
    won = (bt["hs"] > bt["as"]).astype(int).values
    m = bt["margin"].values
    best = None
    for sd in np.arange(8.0, 20.01, 0.25):
        p = np.clip(norm.cdf(m / sd), 1e-6, 1 - 1e-6)
        ll = float(-(won * np.log(p) + (1 - won) * np.log(1 - p)).mean())
        if best is None or ll < best[0]:
            best = (ll, float(sd))
    return best[1]


def choose(g, odds, today, log=print):
    """The weekly test on (enriched) games: replay last season with home court only, then with each adjustment added in turn (kept if
    it lowers the log loss), then the spreads' widths and the home-win rate. Returns the configuration and the final replay."""
    last = season_of(today) - 1
    s0, s1 = pd.Timestamp(f"{last - 1}-11-01"), pd.Timestamp(f"{last}-04-20")
    cfg = dict(CONFIG_DEFAULT)
    early = g[g["date"] < s0]
    cfg["home_rate"] = float((early["hs"] > early["as"]).mean()) if len(early) >= 200 else 0.56
    # how fast old games fade (half-life in days) and how strongly ratings are pulled towards average: the pair that replays best
    best, base = None, pd.DataFrame()
    for hl in (20, 35, 60, 120):
        for al in (0.2, 0.6, 2.0, 6.0):
            trial = {**cfg, "half_life": hl, "alpha": al}
            bt = walk(g, trial, s0, s1)
            if bt.empty:
                continue
            sd = fit_sd(bt)
            ll = score(bt, sd, cfg["home_rate"])["model_ll"]
            if best is None or ll < best:
                best, base, cfg = ll, bt, {**trial, "sd_margin": sd}
    log(f"  replay of {last - 1}/{str(last)[2:]}: {len(base)} games, home court only: log loss {best:.4f} (old games halve every "
        f"{cfg['half_life']} days, pull to average {cfg['alpha']})" if best else "  no replay possible yet")
    tests = []
    for f in FEATURES:
        trial = {**cfg, "features": cfg["features"] + [f]}
        bt = walk(g, trial, s0, s1)
        sd = fit_sd(bt) if len(bt) else cfg["sd_margin"]
        ll = score(bt, sd, cfg["home_rate"]).get("model_ll")
        keep = ll is not None and best is not None and ll < best - 0.001
        tests.append({"adjustment": f, "log_loss": ll, "kept": keep})
        log(f"  + {f}: log loss {ll:.4f} -> {'kept' if keep else 'not kept'}" if ll is not None else f"  + {f}: not testable")
        if keep:
            cfg, best = {**trial, "sd_margin": sd}, ll
    # v37b: with the adjustments chosen, the fade and pull settings again (player ratings can change what works best)
    if cfg["features"] and best is not None:
        for hl in (20, 35, 60, 120, 240):
            for al in (0.2, 0.6, 2.0, 6.0):
                if (hl, al) == (cfg["half_life"], cfg["alpha"]):
                    continue
                trial = {**cfg, "half_life": hl, "alpha": al}
                bt = walk(g, trial, s0, s1)
                sd = fit_sd(bt) if len(bt) else cfg["sd_margin"]
                ll = score(bt, sd, cfg["home_rate"]).get("model_ll")
                if ll is not None and ll < best:
                    cfg, best = {**trial, "sd_margin": sd}, ll
        log(f"  re-tuned with the adjustments: log loss {best:.4f} (old games halve every {cfg['half_life']} days, pull to average {cfg['alpha']})")
    # v37b: pace (for totals) at its own fading speed, the one whose totals miss least
    best_t = None
    for ph in (20, 45, 90, 180):
        bt = walk(g, {**cfg, "pace_hl": ph}, s0, s1)
        if len(bt):
            mae = float(np.abs(bt["total"] - (bt["hs"] + bt["as"])).mean())
            if best_t is None or mae < best_t[0]:
                best_t = (mae, ph)
    if best_t:
        cfg["pace_hl"] = best_t[1]
        log(f"  pace: old games halve every {best_t[1]} days (totals miss by {best_t[0]:.2f} points on average)")
    final = walk(g, cfg, s0, s1)
    cfg["sd_total"] = float(np.std(final["total"] - (final["hs"] + final["as"]))) if len(final) else 18.5
    cfg["tests"] = tests
    cfg["checked"] = today.strftime("%Y-%m-%d")
    return cfg, final


def gate(bt, cfg, odds):
    """Published only when the replay beats the naive guess clearly and comes close to the bookmakers."""
    s = score(bt, cfg["sd_margin"], cfg["home_rate"], odds)
    ok = (s.get("games", 0) >= 400 and s["model_ll"] <= s["naive_ll"] - 0.02 and s.get("odds_games", 0) >= 200
          and s["model_ll_on_odds"] <= s["book_ll"] + 0.02)
    why = ("passed" if ok else "fewer than 400 replayed games" if s.get("games", 0) < 400 else "not clearly better than the naive guess"
           if s["model_ll"] > s["naive_ll"] - 0.02 else "waiting for 200 games with bookmaker lines" if s.get("odds_games", 0) < 200
           else "too far behind the bookmakers")
    return {"pass": bool(ok), "why": why, **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in s.items()}}


# ---------------------------------------------------------------- v37d: player stat lines and player props
PROP_STATS = {"pts": ("points", [10, 15, 20, 25, 30, 35, 40]), "reb": ("rebounds", [4, 6, 8, 10, 12, 14, 16]),
              "ast": ("assists", [2, 4, 6, 8, 10, 12]), "fg3": ("3-pointers", [1, 2, 3, 4, 5, 6])}
LINE_COLS = ["min", "pts", "reb", "oreb", "dreb", "ast", "stl", "blk", "to", "pf", "fgm", "fga", "fg3", "fg3a", "ftm", "fta"]


def player_lines(player_box):
    """Every player-game with minutes: points, rebounds, assists, steals, blocks, turnovers, fouls and shooting (made / attempted)."""
    p = player_box
    num = lambda c: pd.to_numeric(p[c], errors="coerce") if c in p else pd.Series(np.nan, index=p.index)
    out = pd.DataFrame({"game_id": _ids(p["game_id"]), "team_id": _ids(p["team_id"]), "athlete_id": _ids(p["athlete_id"]),
                        "name": p["athlete_display_name"], "pos": p["athlete_position_abbreviation"] if "athlete_position_abbreviation" in p else None,
                        "starter": p["starter"].astype(str).str.lower().eq("true") if "starter" in p else False,
                        "min": num("minutes"), "pts": num("points"), "oreb": num("offensive_rebounds"), "dreb": num("defensive_rebounds"),
                        "ast": num("assists"), "stl": num("steals"), "blk": num("blocks"), "to": num("turnovers"), "pf": num("fouls"),
                        "fgm": num("field_goals_made"), "fga": num("field_goals_attempted"), "fg3": num("three_point_field_goals_made"),
                        "fg3a": num("three_point_field_goals_attempted"), "ftm": num("free_throws_made"), "fta": num("free_throws_attempted")})
    out["reb"] = out["oreb"].fillna(0) + out["dreb"].fillna(0)
    return out[out["min"] > 0].drop_duplicates(["game_id", "athlete_id"], keep="last").reset_index(drop=True)


def _team_form(g, values, halflife=15):
    """(game_id, team_id) -> a team's decayed average of `values` (a dict (game_id, team_id) -> value) over its earlier games,
    plus each team's latest average (for upcoming games)."""
    long = pd.concat([g[["game_id", "date", "home_id"]].set_axis(["game_id", "date", "team"], axis=1),
                      g[["game_id", "date", "away_id"]].set_axis(["game_id", "date", "team"], axis=1)]).sort_values(["team", "date"])
    long["v"] = [values.get((a, b), np.nan) for a, b in zip(long["game_id"], long["team"])]
    long["prior"] = long.groupby("team")["v"].transform(lambda s: s.ewm(halflife=halflife, ignore_na=True).mean().shift(1))
    latest = long.dropna(subset=["v"]).groupby("team")["v"].apply(lambda s: s.ewm(halflife=halflife).mean().iloc[-1]).to_dict()
    return {(a, b): v for a, b, v in zip(long["game_id"], long["team"], long["prior"])}, latest


def prop_table(pl, g, decay=0.95, prior_min=150.0):
    """For every player-game, what was known before it: the player's rate per minute of each prop statistic (older games fading by 5%
    a game, pulled towards the league's rate until he has played ~150 minutes), his expected minutes, his average and over-rate in
    his last 20 games (the simple guess the model must beat), and the game's adjustments: the opponent's defence against that
    statistic and the pace. Also each player's and team's latest values, for upcoming games."""
    dates = g.set_index("game_id")["date"]
    p = pl[pl["game_id"].isin(dates.index)].assign(date=lambda x: x["game_id"].map(dates)).sort_values(["athlete_id", "date"]).reset_index(drop=True)
    stats = list(PROP_STATS)
    track = stats + ["fg3a"]                                     # v37h: 3-point attempts too (threes as attempts x shooting %)
    lg = {s: float(p[s].fillna(0).sum() / p["min"].sum()) for s in track}
    lg_pct3 = float(p["fg3"].fillna(0).sum() / max(p["fg3a"].fillna(0).sum(), 1))
    A0 = 150.0                                                   # 3-point % pulled towards the league's until ~150 attempts
    vals = {s: p[s].fillna(0).values.astype(float) for s in track}
    mins, aid = p["min"].values.astype(float), p["athlete_id"].values
    rate = {s: np.empty(len(p)) for s in track}
    pct3 = np.empty(len(p))
    avg20 = {s: np.full(len(p), np.nan) for s in stats}
    nov20 = {s: np.full(len(p), np.nan) for s in stats}         # how often he went over his own 20-game average line (shrunk to 50%)
    phi20 = {s: np.full(len(p), np.nan) for s in stats}         # v37h: his own game-to-game spread (extra variance over a Poisson count)
    last20 = {s: np.full((len(p), 20), np.nan, dtype=np.float32) for s in stats}   # v37h: his last 20 figures (his own record at any line)
    em, nprev = np.empty(len(p)), np.zeros(len(p))
    hist = {s: [] for s in stats}
    S = {s: 0.0 for s in track}; sm = 0.0; e = None; prev = None; n = 0
    now = {}
    def phi_of(h_):
        if len(h_) < 3:
            return np.nan
        m_, v_ = float(np.mean(h_)), float(np.var(h_, ddof=1))
        return max(0.0, (v_ - m_) / m_ ** 2) if m_ > 0 else np.nan
    def snap():
        return {**{s: (S[s] + lg[s] * prior_min) / (sm + prior_min) for s in track}, "em": e, "n": n,
                "pct3": (S["fg3"] + lg_pct3 * A0) / (S["fg3a"] + A0), **{f"phi_{s}": phi_of(hist[s][-20:]) for s in stats},
                "n20": min(n, 20), **{f"h20_{s}": [float(v) for v in hist[s][-20:]] for s in stats}}
    for i in range(len(p)):
        if aid[i] != prev:
            if prev is not None:
                now[prev] = snap()
            S = {s: 0.0 for s in track}; sm = 0.0; e = None; prev = aid[i]; n = 0; hist = {s: [] for s in stats}
        for s in track:
            rate[s][i] = (S[s] + lg[s] * prior_min) / (sm + prior_min)
        pct3[i] = (S["fg3"] + lg_pct3 * A0) / (S["fg3a"] + A0)
        for s in stats:
            if hist[s]:
                h20 = hist[s][-20:]
                avg20[s][i] = a_ = float(np.mean(h20))
                ln_ = math.floor(a_) + 0.5
                nov20[s][i] = (sum(v > ln_ for v in h20) + 1) / (len(h20) + 2)
                phi20[s][i] = phi_of(h20)
                last20[s][i, :len(h20)] = h20
        em[i] = e if e is not None else 15.0
        nprev[i] = n
        for s in track:
            S[s] = decay * S[s] + vals[s][i]
        for s in stats:
            hist[s].append(vals[s][i])
        sm = decay * sm + mins[i]
        e = mins[i] if e is None else 0.75 * e + 0.25 * mins[i]
        n += 1
    if prev is not None:
        now[prev] = snap()
    for s in stats:
        p[f"rate_{s}"], p[f"avg20_{s}"], p[f"nov20_{s}"], p[f"phi_{s}"] = rate[s], avg20[s], nov20[s], phi20[s]
    p["rate_fg3a"], p["pct3"] = rate["fg3a"], pct3
    p["em"], p["nprev"] = em, nprev
    p["row_i"] = np.arange(len(p))
    p.attrs["last20"] = last20                                   # (rows found by row_i; kept out of the columns)
    # the opponent's defence against each statistic, and the pace
    tot = p.groupby(["game_id", "team_id"])[stats].sum()
    opp_of = {}
    for x in g[["game_id", "home_id", "away_id"]].itertuples(index=False):
        opp_of[(x.game_id, x.home_id)] = x.away_id; opp_of[(x.game_id, x.away_id)] = x.home_id
    team_adj = {"latest": {}}
    for s in stats:
        allowed = {(gid, opp_of[(gid, tid)]): v for (gid, tid), v in tot[s].items() if (gid, tid) in opp_of}
        prior, latest = _team_form(g, allowed)
        mean_ = float(np.nanmean(list(allowed.values())))
        p[f"opp_{s}"] = [np.clip((prior.get((gid, opp_of.get((gid, tid))), np.nan) or np.nan) / mean_, 0.8, 1.2) for gid, tid in zip(p["game_id"], p["team_id"])]
        p[f"opp_{s}"] = p[f"opp_{s}"].fillna(1.0)
        team_adj["latest"][s] = {t: float(np.clip(v / mean_, 0.8, 1.2)) for t, v in latest.items()}
    poss = {(x.game_id, t): x.poss for x in g[["game_id", "home_id", "away_id", "poss"]].itertuples(index=False) for t in (x.home_id, x.away_id)}
    pprior, platest = _team_form(g, poss)
    lg_pace = float(g["poss"].mean())
    p["pace_f"] = [((pprior.get((gid, tid), lg_pace) or lg_pace) + (pprior.get((gid, opp_of.get((gid, tid))), lg_pace) or lg_pace)) / 2 / lg_pace
                   for gid, tid in zip(p["game_id"], p["team_id"])]
    p["pace_f"] = p["pace_f"].fillna(1.0)
    team_adj["pace"] = {t: float(v / lg_pace) for t, v in platest.items()}
    for s in stats:
        p[f"mu_{s}"] = p[f"rate_{s}"] * p["em"] * p[f"opp_{s}"] * p["pace_f"]
    p["mu3pct_fg3"] = p["rate_fg3a"] * p["pct3"] * p["em"] * p["opp_fg3"] * p["pace_f"]   # v37h: threes as attempts x shooting %
    return p, now, team_adj


def _nb_over(mu, r, t):
    """Chance of t or more (a count with mean mu and negative-binomial spread r)."""
    from scipy.stats import nbinom
    mu = np.maximum(np.asarray(mu, float), 1e-6)
    return 1 - nbinom.cdf(np.asarray(t) - 1, r, r / (r + mu))


def _calib(p, y, bins=10):
    """Average gap between the chances given and how often it happened (by tenths), weighted by how many fall in each."""
    p, y = np.asarray(p, float), np.asarray(y, float)
    idx = np.minimum((p * bins).astype(int), bins - 1)
    gap = 0.0
    for b in range(bins):
        m = idx == b
        if m.sum():
            gap += abs(p[m].mean() - y[m].mean()) * m.sum()
    return float(gap / max(len(p), 1))


def prop_mu(c, base_mu, alt_mu=None):
    """A prop's expected figure from the tested settings: k x mu^beta (the level and a gentle stretch, both learned), mu being
    the per-minute model, or for threes (mode "pct") attempts x shooting %."""
    mu = alt_mu if c.get("mode") == "pct" and alt_mu is not None else base_mu
    return c.get("k", 1.0) * np.maximum(np.asarray(mu, float), 0.05) ** c.get("beta", 1.0)


def own_rate(h20, t):
    """How often the player reached t in his last 20 games (rows of figures, NaN where fewer), pulled a little towards 50%."""
    h = np.atleast_2d(np.asarray(h20, float))
    t = np.asarray(t, float)
    if t.ndim == 1:
        t = t[:, None]                                           # one line per player-game
    n = np.isfinite(h).sum(axis=1)
    return (np.nansum(h >= t, axis=1) + 1) / (n + 2)


def prop_p(c, mu, r, h20, t):
    """Chance of t or more: the model's count, blended with the player's own recent record (weight w, learned on the tuning games)."""
    pm = _nb_over(mu, r, t)
    w = c.get("w", 0.0)
    return pm if not w else (1 - w) * pm + w * own_rate(h20, t)


def prop_r(c, phi, n):
    """The count's spread for each player: the league's, or (with "c") his own last-20-game spread pulled towards the league's."""
    if not c.get("c"):
        return c["r"]
    phi_g = 1.0 / c["r"]
    phi = np.where(np.isfinite(np.asarray(phi, float)), phi, phi_g)
    n = np.asarray(n, float)
    return 1.0 / np.maximum((n * phi + c["c"] * phi_g) / (n + c["c"]), 0.005)


def prop_fit(pt, start, end, split=None, log=print):
    """The weekly test for player props on rotation players (10+ earlier games, 15+ expected minutes), counting only games they
    played (as bookmakers settle props): tuned on the games from `start` to `split` (1 February of last season), judged on every
    game after it, this season's included, so the verdict moves as games come in. Tuning picks, by fit on the tuning games: the
    level and stretch of the expected figure, the spread (one for the league, or each player's own pulled towards it) and for
    threes, per-minute rate or attempts x shooting %. Judged at each player's own recent average (vs the simple guess: how often he
    went over it in his last 20 games) and on the calibration of every ladder step (10+, 15+ points...). Published when it beats the
    simple guess and its chances come true as often as they say."""
    from scipy.stats import nbinom
    x_all = pt[(pt["date"] >= start) & (pt["date"] <= end) & (pt["nprev"] >= 10) & (pt["em"] >= 15)]
    split = split or pd.Timestamp(f"{end.year}-02-01")
    tr, x = x_all[x_all["date"] < split], x_all[x_all["date"] >= split]
    out = {}
    for s, (label, ladder) in PROP_STATS.items():
        yt = tr[s].fillna(0).values.astype(int)
        best = None
        for mode in (("rate", "pct") if s == "fg3" else ("rate",)):
            base_t = tr[f"mu_{s}"].values
            alt_t = tr["mu3pct_fg3"].values if mode == "pct" else None
            for beta in (0.9, 1.0, 1.1, 1.2, 1.3, 1.45, 1.6):
                raw = prop_mu({"mode": mode, "beta": beta}, base_t, alt_t)
                k = float(yt.sum() / raw.sum()) if raw.sum() > 0 else 1.0
                mt = k * raw
                for r in (1, 2, 3, 5, 8, 12, 20, 40, 100):
                    ll = float(-nbinom.logpmf(yt, r, r / (r + mt)).mean())
                    if best is None or ll < best[0]:
                        best = (ll, {"mode": mode, "beta": beta, "k": k, "r": r})
        cfg_s = best[1]
        mt = prop_mu(cfg_s, tr[f"mu_{s}"].values, tr["mu3pct_fg3"].values if s == "fg3" else None)
        for cc in (5, 20, 60):                                       # each player's own spread, pulled towards the league's
            rt = prop_r({**cfg_s, "c": cc}, tr[f"phi_{s}"].values, np.minimum(tr["nprev"].values, 20))
            ll = float(-nbinom.logpmf(yt, rt, rt / (rt + mt)).mean())
            if ll < best[0]:
                best = (ll, {**cfg_s, "c": cc})
        cfg_s = best[1]
        # the blend with the player's own recent record, learned on the tuning games over every ladder step
        L20 = pt.attrs.get("last20", {}).get(s)
        if L20 is not None:
            ht = L20[tr["row_i"].values]
            mt = prop_mu(cfg_s, tr[f"mu_{s}"].values, tr["mu3pct_fg3"].values if s == "fg3" else None)
            rt = prop_r(cfg_s, tr[f"phi_{s}"].values, np.minimum(tr["nprev"].values, 20))
            pm_t = [(_nb_over(mt, rt, t), own_rate(ht, t), (yt >= t).astype(float)) for t in ladder]
            best_w = None
            for w in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6):
                ll = 0.0
                for pmod, pown, yy in pm_t:
                    pp = np.clip((1 - w) * pmod + w * pown, 1e-4, 1 - 1e-4)
                    ll += float(-(yy * np.log(pp) + (1 - yy) * np.log(1 - pp)).mean())
                if best_w is None or ll < best_w[0]:
                    best_w = (ll, w)
            cfg_s = {**cfg_s, "w": best_w[1]}
        y = x[s].fillna(0).values
        mu = prop_mu(cfg_s, x[f"mu_{s}"].values, x["mu3pct_fg3"].values if s == "fg3" else None)
        r = prop_r(cfg_s, x[f"phi_{s}"].values, np.minimum(x["nprev"].values, 20))
        hx = L20[x["row_i"].values] if L20 is not None else None
        line = np.floor(x[f"avg20_{s}"].values) + 0.5
        ok = np.isfinite(line)
        over = (y > line).astype(float)
        pm = np.clip(prop_p(cfg_s, mu, r, hx, np.where(ok, np.floor(line) + 1, 1)), 1e-4, 1 - 1e-4)
        # the simple guess: how often he went over that line in his last 20 games (shrunk a little towards 50%)
        pn = np.clip(x[f"nov20_{s}"].fillna(0.5).values, 1e-4, 1 - 1e-4)
        llm = float(-(over[ok] * np.log(pm[ok]) + (1 - over[ok]) * np.log(1 - pm[ok])).mean())
        lln = float(-(over[ok] * np.log(pn[ok]) + (1 - over[ok]) * np.log(1 - pn[ok])).mean())
        lp, ly = [], []
        for t in ladder:
            pr = prop_p(cfg_s, mu, r, hx, t)
            keep = (pr >= 0.05) & (pr <= 0.95)
            lp.append(pr[keep]); ly.append((y[keep] >= t).astype(float))
        cal = _calib(np.concatenate(lp), np.concatenate(ly)) if lp else 1.0
        passed = bool(llm <= lln - 0.003 and cal <= 0.02)
        n_cur = int((x["date"] >= pd.Timestamp(f"{end.year if end.month >= 8 else end.year - 1}-08-01")).sum()) if len(x) else 0
        out[s] = {"pass": passed, **{k_: (round(v_, 4) if isinstance(v_, float) else v_) for k_, v_ in cfg_s.items()},
                  "ll": round(llm, 4), "naive_ll": round(lln, 4), "calib": round(cal, 4), "n": int(ok.sum()), "n_this_season": n_cur}
        how = (f"{'attempts x shooting %, ' if cfg_s.get('mode') == 'pct' else ''}stretch {cfg_s['beta']}, "
               f"{'each player own spread' if cfg_s.get('c') else 'one league spread'}, {int(100 * cfg_s.get('w', 0))}% his own record")
        log(f"  props, {label}: {int(ok.sum())} player-games ({n_cur} this season); at each player's own average, log loss {llm:.4f} vs the "
            f"simple guess's {lln:.4f}; chances off by {cal:.3f} on average ({how}) -> {'published' if passed else 'not published'}")
    return out


def prop_ladders(now_p, team_adj, s_cfg, opp, team, em_adj):
    """Upcoming game: one player's expected statistics and ladder chances (only statistics that passed their test)."""
    res = {}
    for s, (label, ladder) in PROP_STATS.items():
        c = (s_cfg or {}).get(s) or {}
        if not c.get("pass"):
            continue
        adj = team_adj["latest"][s].get(opp, 1.0) * ((team_adj["pace"].get(team, 1.0) + team_adj["pace"].get(opp, 1.0)) / 2)
        base = now_p[s] * em_adj * adj
        alt = now_p.get("fg3a", 0) * now_p.get("pct3", 0) * em_adj * adj if s == "fg3" else None
        mu = float(prop_mu(c, base, alt))
        r = float(np.asarray(prop_r(c, now_p.get(f"phi_{s}", np.nan), now_p.get("n20", 20))).ravel()[0]) if c.get("c") else c["r"]
        h20 = [now_p.get(f"h20_{s}", []) + [np.nan] * (20 - len(now_p.get(f"h20_{s}", [])))]
        steps = [[t, float(np.asarray(prop_p(c, mu, r, h20, t)).ravel()[0])] for t in ladder]
        steps = [st for st in steps if 0.05 <= st[1] <= 0.95][:5]
        if steps:
            res[s] = {"mean": round(float(mu), 1), "ladder": steps}
    return res


# ---------------------------------------------------------------- v37d: halves and quarters
def _qarrays(bt, pq):
    x = bt.merge(pq, on="game_id", how="inner")
    H = [quarters_of(v)[:4] for v in x["home_q"]]; A = [quarters_of(v)[:4] for v in x["away_q"]]
    ok = np.array([len(h) == 4 and len(a) == 4 for h, a in zip(H, A)])
    x = x[ok].reset_index(drop=True)
    return x, np.array([h for h, k in zip(H, ok) if k], float), np.array([a for a, k in zip(A, ok) if k], float)


def _three_way(mu, sd):
    """Home win / tie / away win of a period whose margin is about normal (mean mu, spread sd), scores being whole numbers."""
    pa = norm.cdf((-0.5 - mu) / sd); ph = 1 - norm.cdf((0.5 - mu) / sd)
    return np.c_[ph, np.clip(1 - ph - pa, 1e-4, 1), pa]


def quarter_fit(bt, pq, log=print):
    """The weekly test for halves and quarters: each period's margin and points as shares of the game's predicted margin and total
    (fitted on last season's games before 1 February, judged on every game after, this season's included, so the verdicts move as
    games come in). Markets: each half's and each quarter's winner (a tie is possible) and points (the 2nd half includes overtime,
    as bookmakers settle it), and which quarter scores most. Each published when it beats the simple guess (how often each outcome
    happened in the fitting games) and its chances come true as often as they say."""
    x, H, A = _qarrays(bt, pq)
    if len(x) < 400:
        log(f"  quarters: only {len(x)} games with scores by quarter; not tested yet")
        return {"tested": False}
    m, T = x["margin"].values, x["total"].values
    mh, th = (H[:, 0] + H[:, 1]) - (A[:, 0] + A[:, 1]), H[:, 0] + H[:, 1] + A[:, 0] + A[:, 1]
    # v37h: the 2nd half, overtime included (as bookmakers settle it): the final score minus the 1st half
    m2, t2 = (x["hs"].values - x["as"].values) - mh, (x["hs"].values + x["as"].values) - th
    PERIODS = [("h1", "1st half", mh, th), ("h2", "2nd half", m2, t2)] + \
              [(f"q{k + 1}", f"{['1st', '2nd', '3rd', '4th'][k]} quarter", H[:, k] - A[:, k], H[:, k] + A[:, k]) for k in range(4)]   # v37h: all of them
    def fit_params(sel):
        out_ = {}
        for key, _, mq, tq in PERIODS:
            w = float((m[sel] @ mq[sel]) / (m[sel] @ m[sel])); sh = float((T[sel] @ tq[sel]) / (T[sel] @ T[sel]))
            out_[key] = {"w": w, "sdm": float(np.std(mq[sel] - w * m[sel])), "s": sh, "sdt": float(np.std(tq[sel] - sh * T[sel]))}
        return out_
    # v37h: two-way: the games before 1 February (last season) are judged with settings fitted on the rest, and the rest with
    #      settings fitted on them, so every game is judged once and never with settings it helped fit (about twice the games)
    fa = (x["date"] < pd.Timestamp(f"{int(x['date'].dt.year.max())}-02-01")).values
    folds = [(fa, fit_params(~fa)), (~fa, fit_params(fa))]
    P = fit_params(np.ones(len(x), bool))                                  # what's published: fitted on every game
    tests = {}
    def judge(name, label, pm, o, nv):
        pm, nv = np.clip(pm, 1e-4, 1), np.clip(nv, 1e-4, 1)
        llm = float(-np.log(pm[np.arange(len(o)), o]).mean()); lln = float(-np.log(nv[np.arange(len(o)), o]).mean())
        Y = np.zeros_like(pm); Y[np.arange(len(o)), o] = 1
        cal = _calib(pm.ravel(), Y.ravel())
        passed = bool(llm <= lln - 0.003 and cal <= 0.03)
        tests[name] = {"pass": passed, "ll": round(llm, 4), "naive_ll": round(lln, 4), "calib": round(cal, 4), "n": int(len(o))}
        log(f"  {label}: {len(o)} games; log loss {llm:.4f} vs the simple guess's {lln:.4f}; chances off by {cal:.3f} -> {'published' if passed else 'not published'}")
    for key, name, mq, _ in PERIODS:
        o = np.where(mq > 0, 0, np.where(mq == 0, 1, 2))
        pm, nv = np.zeros((len(x), 3)), np.zeros((len(x), 3))
        for sel, Pf in folds:
            pm[sel] = _three_way(Pf[key]["w"] * m[sel], Pf[key]["sdm"])
            nv[sel] = np.bincount(o[~sel], minlength=3) / (~sel).sum()
        judge(f"{key}_winner", f"{name} winner", pm, o, nv)
    for key, name, _, tq in PERIODS:
        pm, nv, o = np.zeros((len(x), 2)), np.zeros((len(x), 2)), np.zeros(len(x), int)
        for sel, Pf in folds:
            L0 = float(np.floor(np.mean(tq[~sel]))) + 0.5                   # one fixed line: the usual figure in the other games
            po = 1 - norm.cdf((L0 - Pf[key]["s"] * T[sel]) / Pf[key]["sdt"])
            pm[sel] = np.c_[po, 1 - po]
            nv[sel] = [np.mean(tq[~sel] > L0), np.mean(tq[~sel] < L0)]
            o[sel] = (tq[sel] < L0).astype(int)                             # 0 = over, 1 = under
        judge(f"{key}_total", f"{name} points", pm, o, nv)
    qt = H + A
    o = np.argmax(qt + np.random.default_rng(0).uniform(0, 0.01, qt.shape), axis=1)   # (a tie goes to either, at random)
    pm, nv = np.zeros((len(x), 4)), np.zeros((len(x), 4))
    for sel, Pf in folds:
        pm[sel] = _top_quarter(Pf, T[sel])
        nv[sel] = np.bincount(o[~sel], minlength=4) / (~sel).sum()
    judge("top_quarter", "highest-scoring quarter", pm, o, nv)
    return {"tested": True, "params": P, "tests": tests}


def _top_quarter(P, T, n=4000, seed=1):
    """Chance that each quarter scores most, from the four quarters' expected points and spreads (simulated)."""
    rng = np.random.default_rng(seed)
    T = np.atleast_1d(np.asarray(T, float))
    mus = np.stack([P[f"q{k}"]["s"] * T for k in range(1, 5)], axis=1)
    sds = np.array([P[f"q{k}"]["sdt"] for k in range(1, 5)])
    out = np.zeros((len(T), 4))
    for i0 in range(0, len(T), 200):
        mu_ = mus[i0:i0 + 200]
        d = mu_[:, None, :] + rng.normal(0, 1, (len(mu_), n, 4)) * sds
        out[i0:i0 + 200] = np.stack([(d.argmax(axis=2) == k).mean(axis=1) for k in range(4)], axis=1)
    return out


def quarter_markets(qcfg, margin, total):
    """Upcoming game: the markets that passed their test (chances for home / tie / away, and over / under at lines near Kwallo's figure)."""
    if not (qcfg or {}).get("tested"):
        return {}
    P, T, res = qcfg["params"], qcfg.get("tests", {}), {}
    for key, name in (("h1", "1st half"), ("h2", "2nd half"), ("q1", "1st quarter"), ("q2", "2nd quarter"), ("q3", "3rd quarter"), ("q4", "4th quarter")):
        if key not in P:
            continue
        if T.get(f"{key}_winner", {}).get("pass"):
            ph, pd_, pa = _three_way(np.array([P[key]["w"] * margin]), P[key]["sdm"])[0]
            res[f"{key}_winner"] = {"name": f"{name} winner", "home": float(ph), "tie": float(pd_), "away": float(pa)}
        if T.get(f"{key}_total", {}).get("pass"):
            mu = P[key]["s"] * total
            base = math.floor(mu) + 0.5
            res[f"{key}_total"] = {"name": f"{name} points", "expected": round(mu, 1),
                                   "lines": [[base + d, float(1 - norm.cdf((base + d - mu) / P[key]["sdt"]))] for d in ((-6, -3, 0, 3, 6) if key.startswith("h") else (-4, -2, 0, 2, 4))]}
    if T.get("top_quarter", {}).get("pass"):
        res["top_quarter"] = {"name": "Highest-scoring quarter", "p": [float(v) for v in _top_quarter(P, [total])[0]]}
    return res


# ---------------------------------------------------------------- v37d: live chances
def live_chance(lead, f, margin, sd, c, a=0.5):
    """Home side's chance with `lead` points and a fraction `f` of regulation still to play: the pre-game margin for the time
    left, its spread shrinking as the time left runs down (sd x c x f^a; c and a learned on last season)."""
    f = np.maximum(np.asarray(f, float), 1e-4)
    return norm.cdf((np.asarray(lead, float) + np.asarray(margin, float) * f) / (sd * f ** a * c))


def live_fit(bt, pq, sd_margin, log=print):
    """The test for live chances on last season: the score after the 1st quarter, at half-time and after the 3rd quarter of every
    game. Published when the chances come true as often as they say (and, as a check, beat the pre-game chances)."""
    x, H, A = _qarrays(bt, pq)
    if len(x) < 400:
        log("  live chances: not enough games with scores by quarter yet")
        return {"pass": False}
    won = (x["hs"] > x["as"]).astype(float).values
    lead = np.cumsum(H - A, axis=1)[:, :3]
    fs = np.array([0.75, 0.5, 0.25])
    L, F = lead.ravel(), np.tile(fs, len(x))
    M, Y = np.repeat(x["margin"].values, 3), np.repeat(won, 3)
    best = None
    for a in (0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6):
        for c in np.arange(0.6, 2.51, 0.05):
            p = np.clip(live_chance(L, F, M, sd_margin, c, a), 1e-4, 1 - 1e-4)
            ll = float(-(Y * np.log(p) + (1 - Y) * np.log(1 - p)).mean())
            if best is None or ll < best[0]:
                best = (ll, float(c), p, a)
    ll, c, p, a = best
    pre = np.clip(norm.cdf(M / sd_margin), 1e-4, 1 - 1e-4)
    ll_pre = float(-(Y * np.log(pre) + (1 - Y) * np.log(1 - pre)).mean())
    cal = _calib(p, Y)
    passed = bool(cal <= 0.03 and ll < ll_pre)
    log(f"  live chances: {len(L)} game moments; log loss {ll:.4f} (pre-game chances alone {ll_pre:.4f}); chances off by {cal:.3f} -> "
        f"{'published' if passed else 'not published'}")
    return {"pass": passed, "c": round(c, 3), "a": a, "ll": round(ll, 4), "pre_ll": round(ll_pre, 4), "calib": round(cal, 4), "n": int(len(L))}


LIVE_MIN = 150                 # v37b: real pre-game predictions needed before the live record decides
WAIT_FOR_LIVE = False          # True: nothing is published until the live record exists and passes


def live_check(gate, plog, g, odds):
    """v37b: Kwallo's real pre-game chances this season (the prediction log: made on game day with that morning's injury report)
    against the bookmakers' lines on the same finished games. Once there are LIVE_MIN of them, they decide: published only while
    the live record is within 0.02 of the bookmakers (as well as the weekly replay passing)."""
    rec = {"games": 0}
    if plog is not None and len(plog) and odds is not None and len(odds):
        x = (plog[["game_id", "p_home"]].assign(game_id=lambda d: d["game_id"].astype(str))
             .merge(g[["game_id", "hs", "as"]], on="game_id").merge(odds.dropna(subset=["ml_home", "ml_away"]), on="game_id"))
        if len(x):
            won = (x["hs"] > x["as"]).astype(int).values
            pm = np.clip(x["p_home"].astype(float).values, 1e-6, 1 - 1e-6)
            pb = ((1 / x["ml_home"]) / (1 / x["ml_home"] + 1 / x["ml_away"])).values
            rec = {"games": int(len(x)), "model_ll": round(float(-(won * np.log(pm) + (1 - won) * np.log(1 - pm)).mean()), 4),
                   "book_ll": round(float(-(won * np.log(pb) + (1 - won) * np.log(1 - pb)).mean()), 4)}
    replay_ok = bool(gate.get("replay_pass", gate.get("pass")))
    ok, why = replay_ok, gate.get("replay_why", gate.get("why"))
    if replay_ok and rec["games"] >= LIVE_MIN and rec["model_ll"] > rec["book_ll"] + 0.02:
        ok, why = False, "the live record this season is too far behind the bookmakers"
    elif replay_ok and WAIT_FOR_LIVE and rec["games"] < LIVE_MIN:
        ok, why = False, f"waiting for {LIVE_MIN} real predictions to check against the bookmakers ({rec['games']} so far)"
    return {**gate, "live": rec, "pass": ok, "why": why}


# ---------------------------------------------------------------- the injury report (for upcoming games)
def injuries():
    """ESPN's NBA injury report: athlete id -> (status, how likely he misses the game)."""
    j = get_json(f"{ESPN}/injuries") or {}
    weight = {"out": 1.0, "doubtful": 0.75, "questionable": 0.4, "day-to-day": 0.4, "probable": 0.1}
    out = {}
    for t in j.get("injuries", []):
        for i in t.get("injuries", []):
            a = i.get("athlete") or {}
            st = str(i.get("status") or (i.get("type") or {}).get("description") or "").lower()
            aid = str(a.get("id") or (str(((a.get("links") or [{}])[0]).get("href", "")).split("/id/")[-1].split("/")[0]))
            if aid:
                out[aid] = (st.title(), next((w for k, w in weight.items() if k in st), 0.4), a.get("displayName"))
    return out


def fair_lines(margin, total, sd_m, sd_t):
    """Chances at nearby spreads and totals (each half-point line, either side of Kwallo's own)."""
    base_s = round(-margin * 2) / 2
    spreads = []
    for d in (-6, -3, 0, 3, 6):
        line = base_s + d + (0.5 if (base_s + d) == int(base_s + d) else 0)
        p = float(norm.cdf((margin + line) / sd_m))                           # home covers a home line of `line` (e.g. -4.5)
        spreads.append({"line": line, "home": p, "away": 1 - p})
    tot = []
    base_t = math.floor(total) + 0.5
    for d in (-10, -5, 0, 5, 10):
        p = float(1 - norm.cdf((base_t + d - total) / sd_t))
        tot.append({"line": base_t + d, "over": p, "under": 1 - p})
    return spreads, tot
