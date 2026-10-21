# ===================== 1b. ESPN AND FANTASY PL: lineups, upcoming fixtures, injury flags =====================
import json, time, requests, unicodedata
LINEUP_DIR = f"{SAVE_DIR}/lineups"
os.makedirs(LINEUP_DIR, exist_ok=True)
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
HEADERS = {"User-Agent": "Mozilla/5.0"}
ESPN_LEAGUES = {"eng.1": "Premier League", "esp.1": "La Liga", "ger.1": "Bundesliga", "ita.1": "Serie A",
                "fra.1": "Ligue 1", "ned.1": "Eredivisie", "por.1": "Primeira Liga", "bel.1": "Belgian Pro League",
                "sco.1": "Scottish Premiership", "tur.1": "Super Lig", "gre.1": "Greek Super League", "usa.1": "MLS"}
if INCLUDE_SAUDI:
    ESPN_LEAGUES["ksa.1"] = "Saudi Pro League"
if INCLUDE_NEW_LEAGUES:                                   # v29
    ESPN_LEAGUES.update({"mex.1": "Liga MX", "arg.1": "Argentina Liga Profesional", "bra.1": "Brasileirão Série A",
                         "bra.2": "Brasileirão Série B", "bol.1": "Bolivia División Profesional", "rsa.1": "South African Premiership",
                         "nga.1": "NPFL (Nigeria)"})
# leagues whose whole history comes from ESPN (name, calendar-year seasons?, scorecard group)
ESPN_SOLO = {"bra.2": ("Brasileirão Série B", True, "Americas"), "bol.1": ("Bolivia División Profesional", True, "Americas"),
             "rsa.1": ("South African Premiership", False, "Africa"), "nga.1": ("NPFL (Nigeria)", False, "Africa")} if INCLUDE_NEW_LEAGUES else {}
ESPN_OTHER = ["aut.1", "den.1", "nor.1", "swe.1", "uefa.champions", "uefa.europa"]   # lineups only (rotation)
ESPN_EXTRA_LEAGUES = {"aut.1": "Austrian Bundesliga", "den.1": "Danish Superliga", "nor.1": "Eliteserien", "swe.1": "Allsvenskan"}
EURO_CODES = {"uefa.champions": "Champions League", "uefa.europa": "Europa League"}
_conf_path = f"{SAVE_DIR}/espn_conference_code.json"
CONF_CODE = json.load(open(_conf_path)).get("code") if os.path.exists(_conf_path) else None
LINEUP_START = {"usa.1": "2025-02-01", "nor.1": "2025-03-01", "swe.1": "2025-03-01"}
STAT_NAMES = {"totalGoals": "goals", "goalAssists": "assists", "totalShots": "shots", "shotsOnTarget": "sot",
              "yellowCards": "yellow", "redCards": "red", "saves": "saves", "goalsConceded": "conceded", "foulsCommitted": "fouls"}

def espn_get(url, pause=0.6):
    time.sleep(pause)
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(15 * (attempt + 1)); continue
            return None
        except Exception:
            time.sleep(5)
    return None

if CONF_CODE is None:
    for cand in ["uefa.europa.conf", "uefa.conference", "uefa.europa_conf"]:
        b_ = espn_get(f"{ESPN_BASE}/{cand}/scoreboard?dates={TODAY:%Y%m}", pause=0.3) or {}
        name_ = ((b_.get("leagues") or [{}])[0].get("name") or "")
        if b_.get("events") or "conference" in name_.lower():
            CONF_CODE = cand
            json.dump({"code": cand}, open(_conf_path, "w"))
            break
if CONF_CODE:
    EURO_CODES[CONF_CODE] = "Conference League"
    ESPN_OTHER.append(CONF_CODE)

def minute_of(e):
    """Match minute of an ESPN key event ('67'' -> 67, '90'+3'' -> 93)."""
    s_ = str((e.get("clock") or {}).get("displayValue", "")).replace("'", "")
    try:
        parts = [int(x) for x in s_.split("+") if x.strip().isdigit()]
        return sum(parts) if parts else None
    except Exception:
        return None

def parse_events(summary, code, ev):
    keep_types = ("Goal", "Penalty - Scored", "Own Goal", "Substitution", "Red Card")
    rows = []
    for e in summary.get("keyEvents", []) or []:
        t_ = (e.get("type") or {}).get("text", "")
        if not any(t_.startswith(k) for k in keep_types):
            continue
        rows.append({"comp": code, "event_id": str(ev["id"]), "type": t_, "minute": minute_of(e),
                     "team_id": (e.get("team") or {}).get("id"),
                     "players": "|".join(str((p.get("athlete") or {}).get("id", "")) for p in (e.get("participants") or []))})
    return rows

def parse_lineups(summary, code, ev):
    sides = {c["team"]["id"]: c.get("homeAway") for c in ev["competitions"][0]["competitors"]}
    rows = []
    for t in summary.get("rosters", []):
        team = t.get("team", {})
        for p in t.get("roster", []):
            st = {x.get("name"): x.get("value") for x in p.get("stats", [])}
            rows.append({"comp": code, "event_id": str(ev["id"]), "date": ev["date"][:10], "team_id": team.get("id"),
                         "team": team.get("displayName"), "side": sides.get(team.get("id")),
                         "player_id": p.get("athlete", {}).get("id"), "player": p.get("athlete", {}).get("displayName"),
                         "pos": p.get("position", {}).get("abbreviation"), "starter": bool(p.get("starter")),
                         "sub_in": bool(p.get("subbedIn")), "sub_out": bool(p.get("subbedOut")),
                         "formation": t.get("formation"),                  # v35: the team's formation that day (e.g. 3-4-2-1), for the pitch
                         **{v: st.get(k) for k, v in STAT_NAMES.items()}})
    return rows

def update_lineups(minutes):
    """New matches first, then backfill history to LINEUP_HISTORY_FROM, within a time limit.
    Saves lineups and key events (goal and substitution minutes) per competition; resumable."""
    t0, total_new, total_events = time.time(), 0, 0
    this_month = TODAY.strftime("%Y%m")
    hist = pd.Timestamp(LINEUP_HISTORY_FROM)
    calendar_year = {"usa.1", "nor.1", "swe.1"}
    out_of_time = False
    for code in list(ESPN_LEAGUES) + ESPN_OTHER:
        path, epath, state_path = f"{LINEUP_DIR}/{code}.csv", f"{LINEUP_DIR}/{code}_events.csv", f"{LINEUP_DIR}/{code}_state.json"
        state = json.load(open(state_path)) if os.path.exists(state_path) else {}
        done, ev_done = set(state.get("done", [])), set(state.get("events_done", []))
        months_full = set(state.get("months_full", []))           # months with both lineups and events stored
        first = pd.Timestamp(f"{hist.year}-02-01") if code in calendar_year else hist
        months = [d.strftime("%Y%m") for d in pd.date_range(first.replace(day=1), TODAY, freq="MS")][::-1]   # newest first
        lbuf, ebuf, tbuf = [], [], []
        for m in months:
            if m in months_full:
                continue
            if time.time() - t0 > minutes * 60:
                out_of_time = True
                break
            board = espn_get(f"{ESPN_BASE}/{code}/scoreboard?dates={m}")
            if board is None:
                continue
            complete = True
            for ev in board.get("events", []):
                eid = str(ev["id"])
                if not ev["status"]["type"].get("completed") or (eid in done and eid in ev_done):
                    continue
                if time.time() - t0 > minutes * 60:
                    complete, out_of_time = False, True
                    break
                s = espn_get(f"{ESPN_BASE}/{code}/summary?event={eid}")
                if s is None:
                    complete = False
                    continue
                if eid not in done:
                    lbuf += parse_lineups(s, code, ev); done.add(eid); total_new += 1
                if eid not in ev_done:
                    ebuf += parse_events(s, code, ev); ev_done.add(eid); total_events += 1
                for tm_ in (s.get("boxscore") or {}).get("teams") or []:          # v30: team statistics (tackles, offsides...)
                    st_ = {x_.get("name"): x_.get("displayValue") for x_ in tm_.get("statistics") or []}
                    if st_:
                        tbuf.append({"event_id": eid, "date": ev.get("date"), "comp": code, "team_id": str((tm_.get("team") or {}).get("id")),
                                     "team": (tm_.get("team") or {}).get("displayName"), "side": tm_.get("homeAway"),
                                     **{k_: st_.get(k_) for k_ in ["totalTackles", "effectiveTackles", "offsides", "interceptions", "possessionPct",
                                                                   "totalShots", "shotsOnTarget", "wonCorners", "foulsCommitted", "totalPasses",
                                                                   "yellowCards", "redCards"]}})          # v35: cards too (European cups)
            if complete and m < this_month:
                months_full.add(m)
            if out_of_time:
                break
        if lbuf:
            new_l = pd.DataFrame(lbuf)
            if os.path.exists(path) and list(pd.read_csv(path, nrows=0).columns) != list(new_l.columns):
                pd.concat([pd.read_csv(path, dtype=str), new_l], ignore_index=True).to_csv(path, index=False)   # v35: a column was added (formation)
            else:
                new_l.to_csv(path, mode="a", header=not os.path.exists(path), index=False)
        if ebuf:
            pd.DataFrame(ebuf).to_csv(epath, mode="a", header=not os.path.exists(epath), index=False)
        if tbuf:
            tpath_ = f"{SAVE_DIR}/lineups/{code}_teamstats.csv"
            new_ = pd.DataFrame(tbuf)
            if os.path.exists(tpath_) and list(pd.read_csv(tpath_, nrows=0).columns) != list(new_.columns):
                pd.concat([pd.read_csv(tpath_, dtype=str), new_], ignore_index=True).to_csv(tpath_, index=False)   # v35: new columns
            else:
                new_.to_csv(tpath_, mode="a", header=not os.path.exists(tpath_), index=False)
        state.update({"done": sorted(done), "events_done": sorted(ev_done), "months_full": sorted(months_full)})
        json.dump(state, open(state_path, "w"))
        if out_of_time:
            break
    if out_of_time:
        print(f"  Lineup download stopped at its {minutes}-minute limit; it continues next run (newest matches are always done first).")
    return total_new, total_events, out_of_time

def american_to_decimal(x):
    try:
        s = str(x).strip().upper()
        v = 100.0 if s == "EVEN" else float(s.replace("+", ""))
        return 1 + (v / 100 if v > 0 else 100 / abs(v))
    except Exception:
        return np.nan

def parse_odds_obj(o):
    """Decimal home/draw/away odds from one ESPN odds entry (handles both of ESPN's formats)."""
    if not isinstance(o, dict):
        return np.nan, np.nan, np.nan
    ml = o.get("moneyline") if isinstance(o.get("moneyline"), dict) else {}
    pick = lambda k: (ml.get(k, {}).get("close") or ml.get(k, {}).get("open") or {}).get("odds")
    h = (o.get("homeTeamOdds") or {}).get("moneyLine", pick("home"))
    a = (o.get("awayTeamOdds") or {}).get("moneyLine", pick("away"))
    d = (o.get("drawOdds") or {}).get("moneyLine", pick("draw"))
    h, d, a = american_to_decimal(h), american_to_decimal(d), american_to_decimal(a)
    return (h, d, a) if np.isfinite([h, d, a]).all() else (np.nan, np.nan, np.nan)

def espn_odds(ev):
    try:
        lst = [x for x in (ev["competitions"][0].get("odds") or []) if x]
        return parse_odds_obj(lst[0]) if lst else (np.nan, np.nan, np.nan)
    except Exception:
        return np.nan, np.nan, np.nan

def summary_odds(s):
    """Odds from a match's detailed page ('pickcenter' or 'odds'); kept there after the match is played."""
    for key in ["pickcenter", "odds"]:
        for o in (s.get(key) or []):
            res_ = parse_odds_obj(o)
            if np.isfinite(res_).all():
                return res_
    return np.nan, np.nan, np.nan

def espn_upcoming(days):
    rows = []
    months = sorted({d.strftime("%Y%m") for d in pd.date_range(TODAY, TODAY + pd.Timedelta(days=days))})
    for code, league in ESPN_LEAGUES.items():
        for m in months:
            board = espn_get(f"{ESPN_BASE}/{code}/scoreboard?dates={m}", pause=0.4) or {}
            for ev in board.get("events", []):
                if ev["status"]["type"].get("completed"):
                    continue
                when = pd.Timestamp(ev["date"]).tz_convert(None).normalize()
                if not (TODAY <= when < TODAY + pd.Timedelta(days=days)):
                    continue
                cs = {c.get("homeAway"): c for c in ev["competitions"][0]["competitors"]}
                if "home" not in cs or "away" not in cs:
                    continue
                eh, ed, ea = espn_odds(ev)
                rows.append({"code": code, "League": league, "event_id": str(ev["id"]), "Date": when, "Kickoff": pd.Timestamp(ev["date"]).tz_convert(None),
                             "home_espn": cs["home"]["team"]["displayName"], "away_espn": cs["away"]["team"]["displayName"],
                             "home_id": str(cs["home"]["team"]["id"]), "away_id": str(cs["away"]["team"]["id"]),
                             "EspnH": eh, "EspnD": ed, "EspnA": ea})
    return pd.DataFrame(rows)

def season_label(d):
    y = d.year if d.month >= 7 else d.year - 1
    return f"{str(y)[2:]}{str(y + 1)[2:]}"

def espn_league_results(code, odds_since):
    """All results (and upcoming fixtures) of one ESPN league since our first season, with odds; cached in Drive."""
    path, sp = f"{SAVE_DIR}/espn_{code}_results.csv", f"{SAVE_DIR}/espn_{code}_state.json"
    st = json.load(open(sp)) if os.path.exists(sp) else {"months_done": [], "odds_tried": []}
    rows, this_month = [], TODAY.strftime("%Y%m")
    for m in [d.strftime("%Y%m") for d in pd.date_range(f"20{SEASONS[0][:2]}-07-01", TODAY + pd.Timedelta(days=PREDICT_DAYS), freq="MS")]:
        if m in st["months_done"]:
            continue
        board = espn_get(f"{ESPN_BASE}/{code}/scoreboard?dates={m}", pause=0.4)
        if board is None:
            continue
        for e_ in board.get("events", []):
            cs = {cc.get("homeAway"): cc for cc in e_["competitions"][0]["competitors"]}
            if "home" not in cs or "away" not in cs:
                continue
            h_, d_, a_ = espn_odds(e_)
            rows.append({"event_id": str(e_["id"]), "Date": pd.Timestamp(e_["date"]).tz_convert(None).normalize(),
                         "completed": bool(e_["status"]["type"].get("completed")),
                         "HomeTeam": cs["home"]["team"]["displayName"], "AwayTeam": cs["away"]["team"]["displayName"],
                         "home_id": str(cs["home"]["team"]["id"]), "away_id": str(cs["away"]["team"]["id"]),
                         "FTHG": pd.to_numeric(cs["home"].get("score"), errors="coerce"), "FTAG": pd.to_numeric(cs["away"].get("score"), errors="coerce"),
                         "B365H": h_, "B365D": d_, "B365A": a_})
        if m < this_month:
            st["months_done"].append(m)
    old = pd.read_csv(path, dtype={"event_id": str, "home_id": str, "away_id": str}, parse_dates=["Date"]) if os.path.exists(path) else pd.DataFrame()
    new = pd.DataFrame(rows)
    if len(old) and len(new):
        kept = old.set_index("event_id")[ODDS]
        new = new.set_index("event_id")
        for c_ in ODDS:
            new[c_] = new[c_].fillna(kept[c_].reindex(new.index))
        new = new.reset_index()
    df = pd.concat([old, new], ignore_index=True)
    if len(df):
        df = df.drop_duplicates(subset=["event_id"], keep="last")
        df["completed"] = df["completed"].astype(str).str.lower().eq("true")
        need = df[df["completed"] & df["B365H"].isna() & (df["Date"] >= odds_since) & ~df["event_id"].isin(set(st["odds_tried"]))]
        if len(need):
            print(f"  Fetching odds for {len(need)} finished {code} matches (once)...")
        for idx, r_ in need.iterrows():
            s_ = espn_get(f"{ESPN_BASE}/{code}/summary?event={r_['event_id']}")
            if s_ is not None:
                df.loc[idx, ODDS] = summary_odds(s_)
                st["odds_tried"].append(r_["event_id"])
        df.to_csv(path, index=False)
    json.dump(st, open(sp, "w"))
    return df

saudi = pd.DataFrame()
if INCLUDE_SAUDI:
    print("Updating the Saudi Pro League from ESPN...")
    ks = espn_league_results("ksa.1", pd.Timestamp(f"20{SEASONS[-2][:2]}-07-01"))
    if len(ks):
        done_ks = ks[ks["completed"]].dropna(subset=["FTHG", "FTAG"])
        saudi = pd.DataFrame({"League": "Saudi Pro League", "Season": done_ks["Date"].map(season_label), "Date": done_ks["Date"],
                              "HomeTeam": done_ks["HomeTeam"], "AwayTeam": done_ks["AwayTeam"], "FTHG": done_ks["FTHG"], "FTAG": done_ks["FTAG"],
                              "B365H": done_ks["B365H"], "B365D": done_ks["B365D"], "B365A": done_ks["B365A"]}).sort_values("Date").reset_index(drop=True)
        for c_ in ["HC", "AC", "HY", "AY", "HS", "AS"]:
            saudi[c_] = np.nan
        SOLO["Saudi Pro League"] = {"data": saudi, "season": season_label(TODAY), "half_life": 180, "group": "Saudi"}
        by_season = saudi.groupby("Season").agg(Matches=("FTHG", "size"), With_odds=("B365H", lambda s_: int(s_.notna().sum())))
        health("Saudi Pro League (ESPN)", len(saudi) > 0, f"{len(saudi)} results, latest {saudi['Date'].max():%d %b}")
        print("  Saudi Pro League results by season (matches, with odds):", ", ".join(f"{i}: {r_.Matches} ({r_.With_odds})" for i, r_ in by_season.iterrows()))

for code_, (name_, calendar_, group_) in ESPN_SOLO.items():
    try:
        r_ = espn_league_results(code_, pd.Timestamp(f"20{SEASONS[-2][:2]}-07-01"))
        done_ = r_[r_["completed"]].dropna(subset=["FTHG", "FTAG"]) if len(r_) else r_
        if len(done_) >= 100:
            lab_ = done_["Date"].dt.year.astype(str) if calendar_ else done_["Date"].map(season_label)
            dd_ = pd.DataFrame({"League": name_, "Season": lab_, "Date": done_["Date"], "HomeTeam": done_["HomeTeam"], "AwayTeam": done_["AwayTeam"],
                                "FTHG": done_["FTHG"], "FTAG": done_["FTAG"], "B365H": done_["B365H"], "B365D": done_["B365D"], "B365A": done_["B365A"]}
                               ).sort_values("Date").reset_index(drop=True)
            for c_ in ["HC", "AC", "HY", "AY", "HS", "AS"]:
                dd_[c_] = np.nan
            SOLO[name_] = {"data": dd_, "season": str(TODAY.year) if calendar_ else season_label(TODAY), "half_life": 180, "group": group_}
            health(f"{name_} (ESPN)", True, f"{len(dd_)} results, latest {dd_['Date'].max():%d %b}")
            print(f"  {name_}: {len(dd_)} results from ESPN since {dd_['Date'].min():%b %Y}")
        else:
            health(f"{name_} (ESPN)", False, f"only {len(done_)} results so far")
    except Exception as ex_:
        health(f"{name_} (ESPN)", False, f"failed: {str(ex_)[:60]}")

lu, links, espn_fx, fpl_out = pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
other_dom, other_sched, other_names = pd.DataFrame(columns=["League", "Season", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]), pd.DataFrame(), {}
team_map = {}
if PLAYER_MODEL or EURO_SOURCE == "espn":
    print("Updating lineups from ESPN...")
    n_new, n_ev, partial = update_lineups(LINEUP_RUN_MINUTES)
    print(f"  {n_new} matches of lineups and {n_ev} matches of key events added.")
    frames = [pd.read_csv(f"{LINEUP_DIR}/{c}.csv", dtype={"event_id": str, "team_id": str, "player_id": str})
              for c in list(ESPN_LEAGUES) + ESPN_OTHER if os.path.exists(f"{LINEUP_DIR}/{c}.csv")]
    lu = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["event_id", "team_id", "player_id"])
    lu["date"] = pd.to_datetime(lu["date"])
    health("ESPN lineups", not partial or n_new > 0,
           f"{lu['event_id'].nunique()} matches since {lu['date'].min():%b %Y}" + (" (history still downloading)" if partial else ""))
    for c in ["starter", "sub_in", "sub_out"]:
        lu[c] = lu[c].astype(str).str.lower().eq("true")
    lu["minutes"] = np.select([lu["starter"] & ~lu["sub_out"], lu["starter"] & lu["sub_out"],
                               lu["sub_in"] & ~lu["sub_out"], lu["sub_in"] & lu["sub_out"]], [90, 65, 25, 15], 0)
    for c in ["goals", "assists", "shots", "red"]:
        lu[c] = pd.to_numeric(lu[c], errors="coerce").fillna(0)
    lu["contrib"] = lu["goals"] + 0.7 * lu["assists"] + 0.1 * lu["shots"]

    # link ESPN teams to football-data names by matching fixtures on the same dates
    ev_ = lu.dropna(subset=["side"]).drop_duplicates(subset=["event_id", "side"])
    ev = ev_.pivot_table(index=["comp", "event_id", "date"], columns="side", values="team", aggfunc="first").reset_index().dropna(subset=["home", "away"])
    ev = ev.merge(ev_.pivot_table(index="event_id", columns="side", values="team_id", aggfunc="first")
                     .rename(columns={"home": "home_id", "away": "away_id"}), left_on="event_id", right_index=True)
    fd_all = pd.concat([all_matches[["League", "Date", "HomeTeam", "AwayTeam"]]] + [i_["data"][["League", "Date", "HomeTeam", "AwayTeam"]] for i_ in SOLO.values()] + [
                        extra_matches[["League", "Date", "HomeTeam", "AwayTeam"]]]
                       , ignore_index=True)          # (the Saudi league is already among the solo leagues)
    link_parts = []
    for code, league in {**ESPN_LEAGUES, **ESPN_EXTRA_LEAGUES}.items():
        e = ev[ev["comp"] == code]
        f = fd_all[fd_all["League"] == league]
        if e.empty or f.empty:
            continue
        f = f[f["Date"] >= e["date"].min() - pd.Timedelta(days=2)]
        pairs = []
        for shift in (-1, 0, 1):
            m = e.assign(d=e["date"] + pd.Timedelta(days=shift)).merge(f, left_on="d", right_on="Date")
            pairs += list(zip(m["home"], m["HomeTeam"])) + list(zip(m["away"], m["AwayTeam"]))
        counts = pd.Series(pairs).value_counts()
        # one-to-one linking: date co-occurrence (normalised per ESPN club) plus name similarity, solved as an assignment,
        # so two ESPN clubs can never be linked to the same name (v17 fix: ties used to be broken arbitrarily)
        esp_teams = list(pd.concat([e["home"], e["away"]]).unique())
        fd_teams = list(pd.concat([f["HomeTeam"], f["AwayTeam"]]).unique())
        if esp_teams and fd_teams and len(counts):
            cnt = pd.DataFrame(list(counts.index), columns=["esp", "fd"]).assign(n=counts.values)
            cnt["share"] = cnt["n"] / cnt.groupby("esp")["n"].transform("max")
            share = cnt.pivot_table(index="esp", columns="fd", values="share", fill_value=0.0).reindex(index=esp_teams, columns=fd_teams, fill_value=0.0)
            sim = np.array([[difflib.SequenceMatcher(None, unicodedata.normalize("NFKD", a).lower(), unicodedata.normalize("NFKD", b).lower()).ratio()
                             for b in fd_teams] for a in esp_teams])
            score = share.values + 0.5 * sim
            from scipy.optimize import linear_sum_assignment as _lsa
            ri, ci = _lsa(-score)
            for i_, j_ in zip(ri, ci):
                if share.values[i_, j_] >= 0.5 or sim[i_, j_] >= 0.8:      # needs real evidence, not just a leftover pairing
                    team_map[(league, esp_teams[i_])] = fd_teams[j_]
        e = e.assign(HomeTeam=[team_map.get((league, t)) for t in e["home"]], AwayTeam=[team_map.get((league, t)) for t in e["away"]])
        m = e.merge(f, on=["HomeTeam", "AwayTeam"])
        m = m[(m["Date"] - m["date"]).abs() <= pd.Timedelta(days=1)]
        link_parts.append(m.assign(League=league)[["comp", "event_id", "League", "Date", "HomeTeam", "AwayTeam", "home_id", "away_id"]])
    links = pd.concat(link_parts, ignore_index=True).drop_duplicates(subset=["event_id"])
    pd.DataFrame([{"League": l, "ESPN name": e, "Matched to": f} for (l, e), f in team_map.items()]).to_csv(f"{SAVE_DIR}/espn_team_map.csv", index=False)

    print("Fetching upcoming fixtures and odds from ESPN...")
    espn_fx = espn_upcoming(PREDICT_DAYS)
    if len(espn_fx):
        espn_fx["HomeTeam"] = [team_map.get((l, t), t) for l, t in zip(espn_fx["League"], espn_fx["home_espn"])]
        espn_fx["AwayTeam"] = [team_map.get((l, t), t) for l, t in zip(espn_fx["League"], espn_fx["away_espn"])]
        # v30: names the linker couldn't match yet (e.g. a new league whose lineups haven't downloaded), matched to the
        # league's known clubs by accent-free name: "São Paulo" -> "Sao Paulo", "Red Bull Bragantino" -> "Bragantino",
        # "Vasco da Gama" -> "Vasco". One-to-one, and only clear matches; clubs found in the second division stay "promoted".
        import unicodedata as _ud
        _stop = {"fc", "cf", "sc", "ec", "ac", "cd", "club", "de", "da", "do", "the", "rj", "sp", "mg", "rb", "red", "bull", "esporte", "clube", "futebol"}
        def _cn(x):
            w_ = _ud.normalize("NFKD", str(x)).encode("ascii", "ignore").decode().lower().replace("-", " ").replace(".", " ").split()
            return "".join(t for t in w_ if t not in _stop) or "".join(w_)
        name_fixes = {}
        for lg_ in espn_fx["League"].unique():
            known = set(league_frame(lg_)["HomeTeam"]) | set(league_frame(lg_)["AwayTeam"]) if len(league_frame(lg_)) else set()
            if not known:
                continue
            lower2 = set(div2["HomeTeam"]) if "div2" in globals() and len(div2) else set()
            unknown = sorted({t for t in pd.concat([espn_fx.loc[espn_fx["League"] == lg_, "HomeTeam"], espn_fx.loc[espn_fx["League"] == lg_, "AwayTeam"]]) if t not in known})
            used = set(espn_fx.loc[espn_fx["League"] == lg_, ["HomeTeam", "AwayTeam"]].values.ravel()) & known
            for u_ in unknown:
                cu = _cn(u_)
                scored = []
                for k_ in known - used:
                    ck = _cn(k_)
                    sc_ = 1.0 if cu == ck else (0.92 if min(len(cu), len(ck)) >= 4 and (cu in ck or ck in cu) else difflib.SequenceMatcher(None, cu, ck).ratio())
                    # v32: initials, e.g. "OH Leuven" -> "Oud-Heverlee Leuven" (same last word, initials of the rest)
                    uw_, kw_ = str(u_).replace("-", " ").split(), str(k_).replace("-", " ").split()
                    if (len(uw_) >= 2 and len(kw_) >= 2 and uw_[-1].lower() == kw_[-1].lower() and uw_[0].isupper() and len(uw_[0]) <= 4
                            and uw_[0].lower() == "".join(w[0] for w in kw_[:-1]).lower()):
                        sc_ = max(sc_, 0.95)
                    scored.append((sc_, k_))
                scored.sort(reverse=True)
                if scored and scored[0][0] >= 0.85 and (len(scored) < 2 or scored[0][0] - scored[1][0] >= 0.05) and u_ not in lower2:
                    name_fixes[(lg_, u_)] = scored[0][1]; used.add(scored[0][1])
        for (lg_, u_), k_ in (TEAM_NAME_FIXES if "TEAM_NAME_FIXES" in globals() else {}).items():   # v32: your own fixes always win
            name_fixes[(lg_, u_)] = k_
        if name_fixes:
            espn_fx["HomeTeam"] = [name_fixes.get((l, t), t) for l, t in zip(espn_fx["League"], espn_fx["HomeTeam"])]
            espn_fx["AwayTeam"] = [name_fixes.get((l, t), t) for l, t in zip(espn_fx["League"], espn_fx["AwayTeam"])]
            print("  Fixture names matched by spelling: " + ", ".join(f"{u} -> {k}" for (_, u), k in list(name_fixes.items())[:12]))


    # ---------- European competitions from ESPN ----------
    if EURO_SOURCE == "espn":
        print("Updating Champions League and Europa League results from ESPN...")
        norm2 = lambda s: unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()
        EP, ESP = f"{SAVE_DIR}/europe_espn.csv", f"{SAVE_DIR}/europe_espn_state.json"
        estate = json.load(open(ESP)) if os.path.exists(ESP) else {"months_done": []}
        erows, this_month = [], TODAY.strftime("%Y%m")
        first_year = 2000 + int(SEASONS[0][:2])
        months = [d.strftime("%Y%m") for d in pd.date_range(f"{first_year}-07-01", TODAY + pd.Timedelta(days=PREDICT_DAYS), freq="MS")]
        for code, comp in EURO_CODES.items():
            for m in months:
                key = f"{code}:{m}"
                if key in estate["months_done"]:
                    continue
                board = espn_get(f"{ESPN_BASE}/{code}/scoreboard?dates={m}", pause=0.4)
                if board is None:
                    continue
                for e_ in board.get("events", []):
                    cs = {c.get("homeAway"): c for c in e_["competitions"][0]["competitors"]}
                    if "home" not in cs or "away" not in cs:
                        continue
                    st = e_["status"]["type"]
                    eh, ed, ea = espn_odds(e_)
                    erows.append({"event_id": str(e_["id"]), "Competition": comp,
                                  "Date": pd.Timestamp(e_["date"]).tz_convert(None).normalize(),
                                  "Kickoff": pd.Timestamp(e_["date"]).tz_convert(None),          # v33: the time too
                                  "completed": bool(st.get("completed")),
                                  "extra_time": any(x in f"{st.get('name', '')} {st.get('description', '')}".upper() for x in ["AET", "PEN", "EXTRA"]),
                                  "home_espn": cs["home"]["team"]["displayName"], "away_espn": cs["away"]["team"]["displayName"],
                                  "home_id": str(cs["home"]["team"]["id"]), "away_id": str(cs["away"]["team"]["id"]),
                                  "FTHG": pd.to_numeric(cs["home"].get("score"), errors="coerce"),
                                  "FTAG": pd.to_numeric(cs["away"].get("score"), errors="coerce"),
                                  "B365H": eh, "B365D": ed, "B365A": ea})
                if m < this_month:
                    estate["months_done"].append(key)
        old_e = pd.read_csv(EP, dtype={"event_id": str, "home_id": str, "away_id": str}, parse_dates=["Date"]) if os.path.exists(EP) else pd.DataFrame()
        new_e = pd.DataFrame(erows)
        if len(old_e) and len(new_e):
            # keep odds we already fetched for matches that are listed again without them
            kept = old_e.set_index("event_id")[ODDS]
            new_e = new_e.set_index("event_id")
            for c in ODDS:
                new_e[c] = new_e[c].fillna(kept[c].reindex(new_e.index))
            new_e = new_e.reset_index()
        eall = pd.concat([old_e, new_e], ignore_index=True)
        if len(eall):
            eall = eall.drop_duplicates(subset=["event_id"], keep="last")
            eall["completed"] = eall["completed"].astype(str).str.lower().eq("true")
            eall["extra_time"] = eall["extra_time"].astype(str).str.lower().eq("true")
            # finished matches lose their odds in ESPN's fixture lists, so read them from each match's own page (once)
            tried = set(estate.get("odds_tried", []))
            since = pd.Timestamp(f"20{SEASONS[-2][:2]}-07-01")
            need = eall[eall["completed"] & eall["B365H"].isna() & (eall["Date"] >= since) & ~eall["event_id"].isin(tried)]
            if len(need):
                print(f"  Fetching odds for {len(need)} finished European matches (once; about {int(len(need) * 0.6 / 60) + 1} minutes)...")
            comp_code = {v: k for k, v in EURO_CODES.items()}
            for idx, r_ in need.iterrows():
                s_ = espn_get(f"{ESPN_BASE}/{comp_code[r_['Competition']]}/summary?event={r_['event_id']}")
                if s_ is not None:
                    eall.loc[idx, ODDS] = summary_odds(s_)
                    tried.add(r_["event_id"])
            estate["odds_tried"] = sorted(tried)
            eall.to_csv(EP, index=False)
        json.dump(estate, open(ESP, "w"))

        # ---------- domestic leagues of clubs from countries we don't model (found by ESPN team id) ----------
        OL = f"{SAVE_DIR}/espn_other_leagues.json"
        ostate = json.load(open(OL)) if os.path.exists(OL) else {"team_league": {}, "league_names": {}, "months_done": []}
        dom_codes_ = set({**ESPN_LEAGUES, **ESPN_EXTRA_LEAGUES})
        dl_ids = set(lu.loc[lu["comp"].isin(dom_codes_), "team_id"].dropna().astype(str)) if len(lu) else set()
        euro_ids = set(eall["home_id"].astype(str)) | set(eall["away_id"].astype(str))
        ostate.setdefault("not_found", {})
        recent_nf = {t_ for t_, d_ in ostate["not_found"].items() if pd.Timestamp(d_) >= TODAY - pd.Timedelta(days=7)}
        found = {t_ for t_, v_ in ostate["team_league"].items() if v_}
        unknown = sorted(euro_ids - dl_ids - found - recent_nf)
        if unknown:
            print(f"  Looking up the domestic leagues of {len(unknown)} clubs from other countries (once)...")
            try:
                refs = requests.get("https://sports.core.api.espn.com/v2/sports/soccer/leagues?limit=1000", headers=HEADERS, timeout=30).json().get("items", [])
                codes_all = [r_["$ref"].split("/leagues/")[1].split("?")[0] for r_ in refs]
            except Exception:
                codes_all = []
            cands = [c_ for c_ in codes_all if c_.endswith(".1") and c_ not in dom_codes_ and ".w." not in c_ and not c_.startswith("uefa")]
            months_ = [TODAY.strftime("%Y%m"), (TODAY - pd.DateOffset(months=1)).strftime("%Y%m"), (TODAY - pd.DateOffset(months=2)).strftime("%Y%m")]
            left = set(unknown)
            for c_ in cands:
                if not left:
                    break
                for m_ in months_[:2]:
                    b_ = espn_get(f"{ESPN_BASE}/{c_}/scoreboard?dates={m_}", pause=0.4) or {}
                    ids_ = {str(cc["team"]["id"]) for e_ in b_.get("events", []) for cc in e_["competitions"][0]["competitors"]}
                    hit = left & ids_
                    if hit:
                        for t_ in hit:
                            ostate["team_league"][t_] = c_
                        ostate["league_names"][c_] = (b_.get("leagues") or [{}])[0].get("name", c_)
                        left -= hit
                    if ids_:
                        break
            for t_ in left:
                ostate["not_found"][t_] = TODAY.strftime("%Y-%m-%d")   # not in any league ESPN covers; retried in a week
                ostate["team_league"].pop(t_, None)
            print(f"  Checked {len(cands)} ESPN leagues: found {len(unknown) - len(left)} of {len(unknown)} clubs.")
        other_codes = sorted({c_ for c_ in ostate["team_league"].values() if c_})
        OD = f"{SAVE_DIR}/espn_other_domestic.csv"
        od_old = pd.read_csv(OD, dtype={"event_id": str, "home_id": str, "away_id": str}, parse_dates=["Date"]) if os.path.exists(OD) else pd.DataFrame()
        od_rows = []
        first_month = pd.Timestamp(f"20{SEASONS[0][:2]}-07-01")
        for c_ in other_codes:
            for m_ in [d.strftime("%Y%m") for d in pd.date_range(first_month, TODAY + pd.Timedelta(days=PREDICT_DAYS + 7), freq="MS")]:
                k_ = f"{c_}:{m_}"
                if k_ in ostate["months_done"]:
                    continue
                b_ = espn_get(f"{ESPN_BASE}/{c_}/scoreboard?dates={m_}", pause=0.4)
                if b_ is None:
                    continue
                for e_ in b_.get("events", []):
                    cs = {cc.get("homeAway"): cc for cc in e_["competitions"][0]["competitors"]}
                    if "home" not in cs or "away" not in cs:
                        continue
                    od_rows.append({"code": c_, "event_id": str(e_["id"]), "Date": pd.Timestamp(e_["date"]).tz_convert(None).normalize(),
                                    "completed": bool(e_["status"]["type"].get("completed")),
                                    "HomeTeam": cs["home"]["team"]["displayName"], "AwayTeam": cs["away"]["team"]["displayName"],
                                    "home_id": str(cs["home"]["team"]["id"]), "away_id": str(cs["away"]["team"]["id"]),
                                    "FTHG": pd.to_numeric(cs["home"].get("score"), errors="coerce"),
                                    "FTAG": pd.to_numeric(cs["away"].get("score"), errors="coerce")})
                if m_ < TODAY.strftime("%Y%m"):
                    ostate["months_done"].append(k_)
        od = pd.concat([od_old, pd.DataFrame(od_rows)], ignore_index=True)
        if len(od):
            od = od.drop_duplicates(subset=["event_id"], keep="last")
            od["completed"] = od["completed"].astype(str).str.lower().eq("true")
            od.to_csv(OD, index=False)
        json.dump(ostate, open(OL, "w"))
        other_names = {f"Other-{c_}": n_ for c_, n_ in ostate["league_names"].items()}
        if len(od):
            done_od = od[od["completed"]].dropna(subset=["FTHG", "FTAG"])
            other_dom = pd.DataFrame({"League": "Other-" + done_od["code"], "Season": done_od["Date"].map(season_label), "Date": done_od["Date"],
                                      "HomeTeam": done_od["HomeTeam"], "AwayTeam": done_od["AwayTeam"],
                                      "FTHG": done_od["FTHG"], "FTAG": done_od["FTAG"]})
            up_od = od[~od["completed"] & (od["Date"] >= TODAY)]
            other_sched = pd.DataFrame({"Competition": "Other-" + up_od["code"], "Date": up_od["Date"], "Home": up_od["HomeTeam"], "Away": up_od["AwayTeam"]})
        print(f"  Domestic leagues found for {sum(1 for v in ostate['team_league'].values() if v)} clubs from other countries "
              f"({len(other_codes)} leagues, {len(other_dom)} league results).")

        # Place each club in one of our leagues: 1) your fixes, 2) the same ESPN team id in our domestic lineups,
        # 3) the lower-division list, 4) a clear name match with a club in one of our 17 leagues. Otherwise "Other".
        dom_codes = {**ESPN_LEAGUES, **ESPN_EXTRA_LEAGUES}
        dl = lu[lu["comp"].isin(dom_codes)].dropna(subset=["team_id"])
        id_league = dl.groupby("team_id")["comp"].agg(lambda s: dom_codes[s.value_counts().idxmax()]).to_dict()
        id_name = dl.drop_duplicates("team_id", keep="last").set_index("team_id")["team"].to_dict()
        STOP = {"fc", "sc", "cf", "ac", "afc", "sk", "fk", "as", "ss", "ssc", "club", "cd", "rc", "sv", "if", "bk", "kv", "krc",
                "vfl", "vfb", "tsg", "1", "de", "the"}
        clean = lambda s: " ".join(w for w in norm2(s).replace(".", " ").replace("-", " ").split() if w not in STOP)
        dom_names = domestic.drop_duplicates(["League", "HomeTeam"])[["League", "HomeTeam"]]
        dom_names = dom_names.assign(c=dom_names["HomeTeam"].map(clean))
        _placed_cache = {}
        KNOWN_BY_ID = {team_map.get((lg_, id_name.get(t_, "")), id_name.get(t_, "")) for t_, lg_ in id_league.items()}
        def place(tid, name):
            if (tid, name) in _placed_cache:
                return _placed_cache[(tid, name)]
            if name in EURO_TEAM_FIXES:
                res_ = EURO_TEAM_FIXES[name]
            elif tid in id_league:
                lg = id_league[tid]
                res_ = (lg, team_map.get((lg, id_name.get(tid, name)), team_map.get((lg, name), name)))
            elif name in LOWER_DIVISION:
                res_ = (LOWER_DIVISION[name], name)
            else:
                # v18: a club with a different ESPN id can't be one we already know by id (e.g. Inter Club d'Escaldes is not
                # Inter), so name matching only considers clubs without a known ESPN id; "contains" needs similar lengths too
                c = clean(name)
                pool = dom_names[~dom_names["HomeTeam"].isin(KNOWN_BY_ID)]
                hits = pool[pool["c"] == c]
                if len(hits) == 0 and len(c) >= 5:
                    hits = pool[(pool["c"].str.len() >= 5) & pool["c"].apply(lambda x: (x in c or c in x) and min(len(x), len(c)) / max(len(x), len(c)) >= 0.6)]
                if len(hits) == 0:
                    close = difflib.get_close_matches(c, pool["c"].tolist(), n=1, cutoff=0.88)
                    hits = pool[pool["c"].isin(close)]
                res_ = (hits["League"].iloc[0], hits["HomeTeam"].iloc[0]) if len(hits) == 1 else ("Other", name)
            _placed_cache[(tid, name)] = res_
            return res_
        def build(df):
            out = df.copy()
            for side in ["home", "away"]:
                placed = [place(t, n) for t, n in zip(out[f"{side}_id"], out[f"{side}_espn"])]
                S = side.capitalize()
                out[f"{S}League"] = [p_[0] for p_ in placed]
                out[f"{S}Team"] = [p_[1] for p_ in placed]
                out[f"{S}Country"] = [ostate["team_league"].get(str(t), "") or "oth" for t in out[f"{side}_id"]]
            out["Season"] = out["Date"].map(season_label)
            return out
        if len(eall):
            done_e = eall[eall["completed"] & ~eall["extra_time"]].dropna(subset=["FTHG", "FTAG"])
            euro = build(done_e)
            euro = euro[euro["Season"].isin(SEASONS)].sort_values("Date").reset_index(drop=True)
            up_e = eall[~eall["completed"] & (eall["Date"] >= TODAY) & (eall["Date"] < TODAY + pd.Timedelta(days=PREDICT_DAYS))]
            euro_up = build(up_e) if len(up_e) else pd.DataFrame()
            others = sorted(set(euro.loc[euro["HomeLeague"] == "Other", "HomeTeam"]) | set(euro.loc[euro["AwayLeague"] == "Other", "AwayTeam"]))
            placed_n = len(set(euro.loc[euro["HomeLeague"] != "Other", "HomeTeam"]) | set(euro.loc[euro["AwayLeague"] != "Other", "AwayTeam"]))
            health("ESPN European results", len(euro) > 0, f"{len(euro)} results ({int(euro['B365H'].notna().sum())} with odds), latest {euro['Date'].max():%d %b}; {len(euro_up)} upcoming")
            print(f"  {len(euro)} European results ({euro['B365H'].notna().sum()} with odds), {len(euro_up)} upcoming fixtures. "
                  f"{placed_n} clubs placed in our leagues, {len(others)} from other countries.")
            print("  Clubs treated as 'other countries' (if any of these plays in one of our 17 leagues, add it to EURO_TEAM_FIXES):")
            print("   ", ", ".join(others))

    # Fantasy Premier League injury flags, linked to ESPN players by name
    try:
        boot = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/", headers=HEADERS, timeout=30).json()
        norm = lambda s: unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()
        fpl = pd.DataFrame([{"fpl_team": e["team"], "name": norm(f"{e['first_name']} {e['second_name']}"), "web": norm(e["web_name"]),
                             "status": e.get("status"), "chance": e.get("chance_of_playing_next_round"), "news": e.get("news", "")}
                            for e in boot["elements"]])
        recent = lu[(lu["comp"] == "eng.1") & (lu["date"] >= TODAY - pd.Timedelta(days=150))]
        esp_players = recent.drop_duplicates("player_id").assign(n=lambda d: d["player"].map(norm))
        team_link = {}
        for ft, g in fpl.groupby("fpl_team"):
            overlap = esp_players[esp_players["n"].isin(set(g["name"]))].groupby("team_id").size()
            if len(overlap):
                team_link[ft] = overlap.idxmax()
        out = fpl[fpl["status"].isin(["i", "s", "n"]) | (fpl["chance"].notna() & (fpl["chance"] <= 25))].copy()
        ids = []
        for _, r in out.iterrows():
            cand = esp_players[esp_players["team_id"] == team_link.get(r["fpl_team"])]
            hit = cand[cand["n"] == r["name"]]
            if hit.empty:
                hit = cand[cand["n"].str.split().str[-1] == r["web"].split()[-1]] if len(r["web"]) else hit
            ids.append(hit["player_id"].iloc[0] if len(hit) == 1 else None)
        out["player_id"], out["team_id"] = ids, out["fpl_team"].map(team_link)
        fpl_out = out.dropna(subset=["player_id"])
        print(f"Fantasy PL: {len(out)} players flagged out or doubtful, {len(fpl_out)} linked to ESPN players.")
        health("Fantasy Premier League", True, f"{len(fpl_out)} of {len(out)} flagged players linked")
    except Exception as e:
        print("Fantasy PL injury flags unavailable this run:", str(e)[:80])
        health("Fantasy Premier League", False, "unavailable this run")

    health("ESPN fixtures and odds", len(espn_fx) > 0, f"{len(espn_fx)} upcoming fixtures in the next {PREDICT_DAYS} days")
    if comp_code_conf := CONF_CODE:
        health("Conference League", True, f"ESPN code {comp_code_conf}")
    else:
        health("Conference League", False, "ESPN code not found; skipped")
    print(f"{lu['event_id'].nunique()} matches of lineups; {len(links)} linked to league results; "
          f"{len(espn_fx)} upcoming ESPN fixtures in the next {PREDICT_DAYS} days.")

domestic_x = pd.concat([domestic, other_dom], ignore_index=True) if len(other_dom) else domestic   # used by the cross-league model
sched_parts = []
if len(espn_fx):
    sched_parts.append(espn_fx.rename(columns={"League": "Competition", "HomeTeam": "Home", "AwayTeam": "Away"})[["Competition", "Date", "Home", "Away"]])
if len(other_sched):
    sched_parts.append(other_sched)
if len(euro_up):
    sched_parts.append(euro_up.rename(columns={"HomeTeam": "Home", "AwayTeam": "Away"})[["Competition", "Date", "Home", "Away"]])
espn_schedule = pd.concat(sched_parts, ignore_index=True) if sched_parts else pd.DataFrame(columns=["Competition", "Date", "Home", "Away"])

# ---------- current squads (to tell departures from absences) ----------
squads = {}
if PLAYER_MODEL and len(lu):
    SQ = f"{SAVE_DIR}/espn_squads.json"
    sq_cache = json.load(open(SQ)) if os.path.exists(SQ) else {}
    team_code = {}
    for _, r_ in espn_fx.iterrows():
        team_code[str(r_["home_id"])] = r_["code"]; team_code[str(r_["away_id"])] = r_["code"]
    if len(euro_up) and "home_id" in euro_up:
        dom_comp = lu.groupby("team_id")["comp"].agg(lambda s_: s_.value_counts().idxmax()).to_dict()
        for t_ in list(euro_up["home_id"].astype(str)) + list(euro_up["away_id"].astype(str)):
            team_code.setdefault(t_, dom_comp.get(t_) or (ostate["team_league"].get(t_) if "ostate" in globals() else None) or "uefa.champions")
    recent_ids = lu[lu["date"] >= TODAY - pd.Timedelta(days=45)].groupby("team_id")["player_id"].apply(set).to_dict()
    fetched = 0
    for t_, code_ in team_code.items():
        c_ = sq_cache.get(t_)
        if c_ is None or pd.Timestamp(c_["date"]) < TODAY - pd.Timedelta(days=7):
            data_ = espn_get(f"{ESPN_BASE}/{code_}/teams/{t_}/roster", pause=0.4)
            ids_, dob_ = set(), {}
            for a_ in (data_ or {}).get("athletes", []) or []:
                for it in (a_.get("items", [a_]) if isinstance(a_, dict) else []):
                    if isinstance(it, dict) and it.get("id"):
                        ids_.add(str(it["id"]))
                        if it.get("dateOfBirth"):
                            dob_[str(it["id"])] = str(it["dateOfBirth"])[:10]
            sq_cache[t_] = {"date": TODAY.strftime("%Y-%m-%d"), "ids": sorted(ids_), "dob": dob_}
            fetched += 1
        ids_ = set(sq_cache[t_]["ids"])
        recent = recent_ids.get(t_, set())
        # only trust a squad list that contains most of the players who've actually played for the club lately
        if ids_ and (not recent or len(recent & ids_) >= 0.6 * len(recent)):
            squads[t_] = ids_
    json.dump(sq_cache, open(SQ, "w"))
    BD = f"{SAVE_DIR}/player_birthdates.json"
    births = json.load(open(BD)) if os.path.exists(BD) else {}
    for v_ in sq_cache.values():
        births.update(v_.get("dob", {}))
    json.dump(births, open(BD, "w"))
    health("ESPN squads", len(squads) >= 0.8 * max(1, len(team_code)), f"{len(squads)} of {len(team_code)} trusted; {len(births)} birthdates stored")
    print(f"Current squads: {len(squads)} of {len(team_code)} teams with upcoming fixtures ({fetched} refreshed this run).")
