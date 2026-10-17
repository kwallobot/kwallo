# ===================== 1c. CLUBELO AND UNDERSTAT (used by the Experiments section) =====================
from io import StringIO
from scipy.optimize import linear_sum_assignment

LEAGUE_COUNTRY = {"Premier League": "ENG", "La Liga": "ESP", "Bundesliga": "GER", "Serie A": "ITA", "Ligue 1": "FRA",
                  "Eredivisie": "NED", "Primeira Liga": "POR", "Belgian Pro League": "BEL", "Scottish Premiership": "SCO",
                  "Super Lig": "TUR", "Greek Super League": "GRE", "Austrian Bundesliga": "AUT", "Swiss Super League": "SUI",
                  "Danish Superliga": "DEN", "Eliteserien": "NOR", "Allsvenskan": "SWE", "Romanian Liga I": "ROM"}
UNDERSTAT_LEAGUES = {"Premier League": "EPL", "La Liga": "La_liga", "Bundesliga": "Bundesliga", "Serie A": "Serie_A", "Ligue 1": "Ligue_1"}
_norm = lambda s: unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
_squash = lambda s: "".join(ch for ch in _norm(s) if ch.isalnum())

def name_similarity(a, b):
    a, b = _squash(a), _squash(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if min(len(a), len(b)) >= 4 and (a in b or b in a):
        return 0.9
    return difflib.SequenceMatcher(None, a, b).ratio()

def best_assignment(ours, theirs):
    """Pair two lists of club names one-to-one, maximising total name similarity."""
    ours, theirs = list(ours), list(theirs)
    if not ours or not theirs:
        return {}
    S = np.array([[name_similarity(o, t) for t in theirs] for o in ours])
    r, c = linear_sum_assignment(-S)
    return {ours[i]: (theirs[j], S[i, j]) for i, j in zip(r, c)}

# ---------- ClubElo: weekly snapshots of every European club's rating (cached) ----------
elo_snap, elo_map, elo_review = pd.DataFrame(), {}, []
if USE_CLUBELO:
    EP = f"{SAVE_DIR}/clubelo_snapshots.csv"
    snap = pd.read_csv(EP, parse_dates=["Date"]) if os.path.exists(EP) else pd.DataFrame(columns=["Date", "Club", "Country", "Level", "Elo"])
    have = set(snap["Date"].dt.normalize()) if len(snap) else set()
    first = pd.Timestamp(f"20{SEASONS[0][:2]}-07-01")
    wanted = list(pd.date_range(first - pd.Timedelta(days=first.weekday()), TODAY, freq="W-MON")) + [TODAY]
    todo = [d for d in wanted if d not in have]
    elo_ok = True
    if todo:
        try:
            probe = requests.get(f"http://api.clubelo.com/{TODAY:%Y-%m-%d}", headers=HEADERS, timeout=20)
            elo_ok = probe.status_code == 200 and probe.text.startswith("Rank")
            if not elo_ok:
                print(f"ClubElo is unavailable this run (status {probe.status_code}); skipping it, and will try again next run.")
        except Exception as e:
            elo_ok = False
            print("ClubElo is unavailable this run (no response); skipping it, and will try again next run.")
    if not elo_ok:
        todo = []
    if todo:
        print(f"Downloading {len(todo)} ClubElo rating snapshots (about {len(todo)} seconds the first time)...")
    new = []
    for d in todo:
        time.sleep(1)
        try:
            r = requests.get(f"http://api.clubelo.com/{d:%Y-%m-%d}", headers=HEADERS, timeout=30)
            if r.status_code == 200 and r.text.strip():
                t = pd.read_csv(StringIO(r.text))
                new.append(t.assign(Date=d)[["Date", "Club", "Country", "Level", "Elo"]])
        except Exception as e:
            print("  ClubElo request failed:", str(e)[:60])
    if new:
        snap = pd.concat([snap[snap["Date"] != TODAY]] + new, ignore_index=True)
        snap.to_csv(EP, index=False)
    snap["Date"] = pd.to_datetime(snap["Date"]).astype("datetime64[ns]")
    snap["Elo"] = pd.to_numeric(snap["Elo"], errors="coerce")
    elo_snap = snap

    # link ClubElo names to ours, league by league (one-to-one, by name similarity within the same country)
    recent = elo_snap[elo_snap["Date"] >= TODAY - pd.Timedelta(days=800)]
    for league, cc in LEAGUE_COUNTRY.items():
        ours = sorted(set(domestic.loc[domestic["League"] == league, "HomeTeam"]))
        theirs = sorted(set(recent.loc[recent["Country"].isin([cc, "ROU" if cc == "ROM" else cc]), "Club"]))
        for team, (club, sim) in best_assignment(ours, theirs).items():
            club = ELO_NAME_FIXES.get(team, club)
            if sim >= 0.45 or team in ELO_NAME_FIXES:
                elo_map[(league, team)] = club
            if sim < 0.7 and team not in ELO_NAME_FIXES:
                elo_review.append({"League": league, "Our name": team, "ClubElo name": club, "Similarity": round(sim, 2)})
    # clubs from countries we don't model (European matches)
    if len(euro):
        foreign = sorted(set(recent.loc[~recent["Country"].isin(list(LEAGUE_COUNTRY.values()) + ["ROU"]), "Club"]))
        others = sorted(set(euro.loc[euro["HomeLeague"] == "Other", "HomeTeam"]) | set(euro.loc[euro["AwayLeague"] == "Other", "AwayTeam"])
                        | (set(euro_up.loc[euro_up["HomeLeague"] == "Other", "HomeTeam"]) | set(euro_up.loc[euro_up["AwayLeague"] == "Other", "AwayTeam"]) if len(euro_up) else set()))
        for team in others:
            if team in ELO_NAME_FIXES:
                elo_map[("Other", team)] = ELO_NAME_FIXES[team]; continue
            cand_ = sorted(((name_similarity(team, c), c) for c in foreign), reverse=True)[:1]
            if cand_ and cand_[0][0] >= 0.75:
                elo_map[("Other", team)] = cand_[0][1]
    pd.DataFrame([{"League": l, "Our name": t, "ClubElo name": c} for (l, t), c in elo_map.items()]).to_csv(f"{SAVE_DIR}/clubelo_map.csv", index=False)
    print(f"ClubElo: {elo_snap['Date'].nunique()} snapshots; {len(elo_map)} clubs linked.")
    health("ClubElo", elo_ok and len(elo_snap) > 0, f"{elo_snap['Date'].nunique()} snapshots" if elo_ok else "API unavailable this run (retried next run)")
    if elo_review:
        print("  Links to check (low name similarity). If one is wrong, add it to ELO_NAME_FIXES in Settings:")
        display(pd.DataFrame(elo_review).sort_values("Similarity"))

def elo_lookup(df, league_col_home="HomeLeague", league_col_away="AwayLeague"):
    """Each team's ClubElo rating from the latest weekly snapshot before the match date."""
    out = df.copy()
    if not len(elo_snap):
        out["EloH"], out["EloA"] = np.nan, np.nan
        return out
    snaps = elo_snap.sort_values("Date").assign(Club=lambda d: d["Club"].astype(str))
    for side, team_col, lg_col in [("H", "HomeTeam", league_col_home), ("A", "AwayTeam", league_col_away)]:
        clubs = [elo_map.get((l if l in LEAGUE_COUNTRY else "Other", t)) for l, t in zip(out[lg_col], out[team_col])]
        q = pd.DataFrame({"_i": np.arange(len(out)), "Club": clubs,
                          "Date": (pd.to_datetime(out["Date"]) - pd.Timedelta(days=1)).astype("datetime64[ns]").values}).dropna(subset=["Club"])
        q["Club"] = q["Club"].astype(str)
        m = pd.merge_asof(q.sort_values("Date"), snaps[["Date", "Club", "Elo"]], on="Date", by="Club", direction="backward")
        out[f"Elo{side}"] = pd.Series(m.set_index("_i")["Elo"]).reindex(np.arange(len(out))).values
    return out

# ---------- Understat: expected goals for the big five leagues (cached per season) ----------
xg = pd.DataFrame()
understat_players = pd.DataFrame()
understat_teams = pd.DataFrame()
if USE_UNDERSTAT:
    UP = f"{SAVE_DIR}/understat_matches.csv"
    old = pd.read_csv(UP, parse_dates=["Date"], dtype={"Season": str}) if os.path.exists(UP) else pd.DataFrame()
    if len(old):
        old = old.drop_duplicates(subset=["League", "Date", "us_home", "us_away"], keep="last")
    rows, us_players, us_teams = [], [], []
    UT_PATH = f"{SAVE_DIR}/understat_teams.csv"
    ut_old = checked_read(UT_PATH, text=("League", "Season", "team"), num=("ppda", "ppda_allowed", "deep", "deep_allowed"), name="understat_teams")
    ut_have = set(zip(ut_old["League"], ut_old["Season"])) if len(ut_old) else set()
    for league, code in UNDERSTAT_LEAGUES.items():
        for s in SEASONS:
            year = 2000 + int(s[:2])
            if len(old) and ((old["League"] == league) & (old["Season"] == s)).any() and s != SEASONS[-1] and (league, s) in ut_have:
                continue                                   # finished seasons only download once
            time.sleep(2)
            data = None
            try:
                r = requests.get(f"https://understat.com/getLeagueData/{code}/{year}", timeout=30,
                                 headers={**HEADERS, "X-Requested-With": "XMLHttpRequest", "Referer": f"https://understat.com/league/{code}/{year}"})
                if r.status_code == 200:
                    js_ = r.json()
                    data = js_.get("dates")
                    for t_ in (js_.get("teams") or {}).values():
                        for h_ in t_.get("history", []):
                            pp_, pa_ = h_.get("ppda") or {}, h_.get("ppda_allowed") or {}
                            us_teams.append({"League": league, "Season": s, "team": t_.get("title"), "date": h_.get("date"), "h_a": h_.get("h_a"),
                                             "ppda": (pp_.get("att") / pp_["def"]) if pp_.get("def") else np.nan,
                                             "ppda_allowed": (pa_.get("att") / pa_["def"]) if pa_.get("def") else np.nan,
                                             "deep": h_.get("deep"), "deep_allowed": h_.get("deep_allowed")})
                    if s == SEASONS[-1] and js_.get("players"):
                        us_players.append(pd.DataFrame(js_["players"]).assign(League=league))
            except Exception:
                data = None
            if data is None:                               # older page format: data embedded in the page
                try:
                    html_ = requests.get(f"https://understat.com/league/{code}/{year}", headers=HEADERS, timeout=30).text
                    raw = html_.split("datesData")[1].split("JSON.parse('")[1].split("')")[0]
                    data = json.loads(raw.encode("utf-8").decode("unicode_escape"))
                except Exception:
                    print(f"  Understat {league} {s}: not available this run")
                    continue
            for d_ in data:
                if not d_.get("isResult"):
                    continue
                rows.append({"League": league, "Season": s, "Date": pd.Timestamp(d_["datetime"]).normalize(),
                             "us_home": d_["h"]["title"], "us_away": d_["a"]["title"],
                             "xGH": float(d_["xG"]["h"]), "xGA": float(d_["xG"]["a"])})
    if rows:
        new = pd.DataFrame(rows)
        keep = old[~old.set_index(["League", "Season"]).index.isin(new.set_index(["League", "Season"]).index)] if len(old) else old
        old = pd.concat([keep, new], ignore_index=True)
        old.to_csv(UP, index=False)
    if len(old):
        old = old.drop_duplicates(subset=["League", "Date", "us_home", "us_away"], keep="last")
        old.to_csv(UP, index=False)
    xg = old
    if us_teams:
        nt_ = pd.DataFrame(us_teams)
        keep_t = ut_old[~ut_old.set_index(["League", "Season"]).index.isin(nt_.set_index(["League", "Season"]).index)] if len(ut_old) else ut_old
        pd.concat([keep_t, nt_], ignore_index=True).to_csv(UT_PATH, index=False)
    understat_teams = checked_read(UT_PATH, text=("League", "Season", "team"), num=("ppda", "ppda_allowed", "deep", "deep_allowed"), name="understat_teams")
    UP_PL = f"{SAVE_DIR}/understat_players.csv"
    if us_players:
        pd.concat(us_players, ignore_index=True).to_csv(UP_PL, index=False)
    understat_players = checked_read(UP_PL, text=("player_name", "team_title", "League"), num=("time", "goals", "xG", "assists", "xA", "shots", "key_passes"), name="understat_players")
    if len(xg):
        # link Understat names to ours by matching fixtures on the same dates (as with ESPN)
        us_map, parts = {}, []
        for league in UNDERSTAT_LEAGUES:
            u = xg[xg["League"] == league]
            f_ = all_matches[all_matches["League"] == league]
            pairs = []
            for shift in (-1, 0, 1):
                m = u.assign(d=u["Date"] + pd.Timedelta(days=shift)).merge(f_, left_on="d", right_on="Date")
                pairs += list(zip(m["us_home"], m["HomeTeam"])) + list(zip(m["us_away"], m["AwayTeam"]))
            counts = pd.Series(pairs).value_counts()
            for t in pd.concat([u["us_home"], u["us_away"]]).unique():
                c = counts[[k for k in counts.index if k[0] == t]]
                if len(c):
                    us_map[(league, t)] = c.idxmax()[1]
            u = u.assign(HomeTeam=[us_map.get((league, t)) for t in u["us_home"]], AwayTeam=[us_map.get((league, t)) for t in u["us_away"]])
            parts.append(u)
        xg = pd.concat(parts, ignore_index=True)
        print(f"Understat: {len(xg)} matches with expected goals, {sum(1 for _ in us_map)} team names linked.")
        health("Understat (expected goals)", True, f"{len(xg)} matches, latest {xg['Date'].max():%d %b}")
    else:
        health("Understat (expected goals)", False, "not available this run")
