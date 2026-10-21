# ===================== 1e. BSD CONTEXT: domestic cups, weather, derbies, referees, travel =====================
# BSD match records carry weather, a derby flag, the referee (once appointed), coaches and sometimes travel distance.
# They're matched to our own results and fixtures; cup matches (8 cups BSD covers) fill the congestion blind spot.
# Nothing here changes predictions by itself: section 2f tests each factor first.
BSD_LEAGUES = {"Premier League": "Premier League", "La Liga": "La Liga", "Bundesliga": "Bundesliga", "Serie A": "Serie A", "Ligue 1": "Ligue 1",
               "Eredivisie": "Eredivisie", "Primeira Liga": "Liga Portugal Betclic", "Belgian Pro League": "Pro League",
               "Scottish Premiership": "Scottish Premiership", "Super Lig": "Trendyol Super Lig", "Greek Super League": "Stoiximan Super League",
               "MLS": "MLS", "Saudi Pro League": "Saudi Pro League"}
BSD_CUPS = {"FA Cup": "Premier League", "Carabao Cup": "Premier League", "Copa del Rey": "La Liga", "DFB Pokal": "Bundesliga",
            "Coppa Italia": "Serie A", "Coupe de France": "Ligue 1", "Taça de Portugal": "Primeira Liga", "Taça da Liga": "Primeira Liga"}
RIVALRIES = [("Ajax", "Feyenoord"), ("Ajax", "PSV Eindhoven"), ("Feyenoord", "PSV Eindhoven"), ("Celtic", "Rangers"), ("Benfica", "Porto"),
             ("Benfica", "Sp Lisbon"), ("Porto", "Sp Lisbon"), ("Galatasaray", "Fenerbahce"), ("Galatasaray", "Besiktas"), ("Fenerbahce", "Besiktas"),
             ("Real Madrid", "Barcelona"), ("Barcelona", "Espanol"), ("Ath Madrid", "Real Madrid"), ("Inter", "Milan"), ("Juventus", "Inter"),
             ("Roma", "Lazio"), ("Dortmund", "Schalke 04"), ("Bayern Munich", "Dortmund"), ("Liverpool", "Everton"), ("Man United", "Man City"),
             ("Arsenal", "Tottenham"), ("Liverpool", "Man United"), ("Olympiakos", "Panathinaikos"), ("Club Brugge", "Anderlecht"),
             ("Paris SG", "Marseille"), ("Al Hilal", "Al Nassr"), ("Al Ittihad", "Al Ahli")]     # editable: (team, team) in our spellings
CTX_STATUS = "not used (no BSD_KEY)"
CTX_MATCH = pd.DataFrame(columns=["League", "Date", "HomeTeam", "AwayTeam", "derby", "wind", "temp", "wcode", "referee_id", "travel_km", "home_coach", "away_coach"])
cup_results = pd.DataFrame(columns=["League", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"])
cup_fixtures = pd.DataFrame(columns=["Competition", "Date", "Home", "Away"])
REF_STATS = {}

def _bsd_key():
    try:
        from google.colab import userdata
        return userdata.get("BSD_KEY")
    except Exception:
        return os.environ.get("BSD_KEY")
_BK = _bsd_key()
def _bsd(path, **params):
    for attempt in range(3):
        try:
            r = requests.get(path if path.startswith("http") else f"https://sports.bzzoiro.com{path}",
                             headers={"Authorization": f"Token {_BK}"}, params=params, timeout=40)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (400, 401, 402, 404):
                return None
        except Exception:
            pass
        time.sleep(2 * (attempt + 1))
    return None
_ALIAS_C = {"mancity": "manchestercity", "manunited": "manchesterunited", "nottmforest": "nottinghamforest", "wolves": "wolverhampton",
            "athmadrid": "atleticomadrid", "athbilbao": "athleticbilbao", "sociedad": "realsociedad", "espanol": "espanyol",
            "mgladbach": "monchengladbach", "splisbon": "sportingcp", "sportinglisbon": "sportingcp", "parissg": "parissaintgermain", "psg": "parissaintgermain",
            "einfrankfurt": "eintrachtfrankfurt", "leverkusen": "bayerleverkusen", "spbraga": "braga", "sheffieldutd": "sheffieldunited"}
_STOP_C = {"fc", "cf", "sc", "afc", "ac", "as", "ssc", "sk", "fk", "cd", "rc", "sv", "if", "bk", "kv", "club", "de", "the", "1"}
def cname(s):
    w_ = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().replace("-", " ").replace(".", " ").replace("'", "").split()
    o_ = "".join(x for x in w_ if x not in _STOP_C) or "".join(w_)
    return _ALIAS_C.get(o_, o_)
def tsim(a, b):
    a, b = cname(a), cname(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if min(len(a), len(b)) >= 4 and (a in b or b in a):
        return 0.9
    return difflib.SequenceMatcher(None, a, b).ratio()

if _BK:
    print("BSD context: updating cups, weather, derbies and referees...")
    lgs_ = _bsd("/api/v2/leagues/", limit=300) or {}
    lg_list = lgs_.get("results", lgs_) if isinstance(lgs_, dict) else lgs_
    by_name = {}
    for l_ in lg_list or []:
        by_name.setdefault(l_.get("name"), []).append(l_)
    want = {our: by_name.get(bn, [None])[0] for our, bn in BSD_LEAGUES.items()}
    want.update({f"CUP:{c}": by_name.get(c, [None])[0] for c in BSD_CUPS})
    want = {k: v for k, v in want.items() if v}
    EVP, EVS = f"{SAVE_DIR}/bsd_events.csv", f"{SAVE_DIR}/bsd_events_state.json"
    evst = json.load(open(EVS)) if os.path.exists(EVS) else {"done": []}
    old_ev = checked_read(EVP, text=("league_key", "home_team", "away_team", "status", "wdesc"),
                          num=("id", "home_score", "away_score", "wind", "temp", "wcode", "referee_id", "travel_km", "home_coach", "away_coach"), name="bsd_events")
    since = pd.Timestamp(f"20{SEASONS[-2][:2]}-07-01")
    months = [d for d in pd.date_range(since, TODAY + pd.Timedelta(days=21), freq="MS")]
    rows = []
    t0 = time.time()
    for key_, l_ in want.items():
        for m0 in months:
            mk = f"{key_}|{m0:%Y%m}"
            if mk in evst["done"] or time.time() - t0 > 8 * 60:
                continue
            m1 = min(m0 + pd.offsets.MonthEnd(0), TODAY + pd.Timedelta(days=21))
            page = _bsd("/api/v2/events/", league_id=l_["id"], date_from=f"{m0:%Y-%m-%d}", date_to=f"{m1:%Y-%m-%d}", limit=200)
            got_ = 0
            while page:
                for e in page.get("results", []):
                    if e.get("league_id") != l_["id"]:
                        continue
                    w_ = e.get("weather") or {}
                    rows.append({"id": e.get("id"), "league_key": key_, "date": e.get("event_date"), "status": e.get("status"),
                                 "home_team": e.get("home_team"), "away_team": e.get("away_team"), "home_score": e.get("home_score"), "away_score": e.get("away_score"),
                                 "derby": bool(e.get("is_local_derby")), "wind": w_.get("wind_speed"), "temp": w_.get("temperature_c"), "wcode": w_.get("code"),
                                 "wdesc": w_.get("description"), "referee_id": e.get("referee_id"), "travel_km": e.get("travel_distance_km"),
                                 "home_coach": e.get("home_coach_id"), "away_coach": e.get("away_coach_id")})
                    got_ += 1
                nxt_ = page.get("next")
                page = _bsd(nxt_) if nxt_ else None
            if m1 < TODAY - pd.Timedelta(days=3):
                evst["done"].append(mk)
    ev = pd.concat([old_ev, pd.DataFrame(rows)], ignore_index=True) if rows else old_ev
    if len(ev):
        ev = ev.drop_duplicates("id", keep="last")
        ev.to_csv(EVP, index=False)
    json.dump(evst, open(EVS, "w"))
    if len(ev):
        ev["Date"] = pd.to_datetime(ev["date"], utc=True).dt.tz_convert(None).dt.normalize()
        # ---- league matches: pair BSD events with our results and fixtures (one-to-one per date) ----
        from scipy.optimize import linear_sum_assignment as _lsa3
        ours_ = []
        for lg_ in BSD_LEAGUES:
            fr_ = league_frame(lg_)
            if len(fr_):
                ours_.append(fr_[["League", "Date", "HomeTeam", "AwayTeam"]])
        if len(espn_fx) and {"League", "Date", "HomeTeam", "AwayTeam"}.issubset(espn_fx.columns):
            ours_.append(espn_fx[["League", "Date", "HomeTeam", "AwayTeam"]].assign(Date=lambda d: pd.to_datetime(d["Date"]).dt.normalize()))   # upcoming
        ours_ = pd.concat(ours_, ignore_index=True)
        ours_ = ours_[ours_["Date"] >= since]
        ctx_rows = []
        for lg_ in BSD_LEAGUES:
            e_ = ev[ev["league_key"] == lg_]
            o_ = ours_[ours_["League"] == lg_]
            if e_.empty or o_.empty:
                continue
            for d_, g_ in o_.groupby("Date"):
                c_ = e_[(e_["Date"] - d_).abs() <= pd.Timedelta(days=1)]
                if c_.empty:
                    continue
                S_ = np.array([[(tsim(h, bh) + tsim(a, ba)) / 2 for bh, ba in zip(c_["home_team"], c_["away_team"])] for h, a in zip(g_["HomeTeam"], g_["AwayTeam"])])
                ri, ci = _lsa3(-S_)
                for i_, j_ in zip(ri, ci):
                    if S_[i_, j_] >= 0.6:
                        b_ = c_.iloc[j_]
                        ctx_rows.append({"League": lg_, "Date": d_, "HomeTeam": g_["HomeTeam"].iloc[i_], "AwayTeam": g_["AwayTeam"].iloc[i_],
                                         "derby": bool(b_["derby"]), "wind": b_["wind"], "temp": b_["temp"], "wcode": b_["wcode"], "referee_id": b_["referee_id"],
                                         "travel_km": b_["travel_km"], "home_coach": b_["home_coach"], "away_coach": b_["away_coach"]})
        CTX_MATCH = pd.DataFrame(ctx_rows)
        # editable rivalries count as derbies too
        if len(CTX_MATCH):
            riv = {frozenset(p_) for p_ in RIVALRIES}
            CTX_MATCH["derby"] = CTX_MATCH["derby"].fillna(False).astype(bool).values | np.array([frozenset((h, a)) in riv for h, a in zip(CTX_MATCH["HomeTeam"], CTX_MATCH["AwayTeam"])])
        # ---- cups: map BSD names to ours within the same country (top division + second division) ----
        cup_ev = ev[ev["league_key"].str.startswith("CUP:")].copy()
        if len(cup_ev):
            pools = {}
            for cup_, lg_ in BSD_CUPS.items():
                pool_ = set(league_frame(lg_)["HomeTeam"])
                if "div2" in globals() and len(div2):
                    top2 = {t_: n_ for t_, n_ in DIV2.values()}
                    pool_ |= set(div2.loc[div2["League"] == top2.get(lg_, ""), "HomeTeam"])
                pools[f"CUP:{cup_}"] = sorted(pool_)
            nm_cache = {}
            def to_ours(key_, nm_):
                if (key_, nm_) in nm_cache:
                    return nm_cache[(key_, nm_)]
                sc_ = sorted(((tsim(nm_, p_), p_) for p_ in pools.get(key_, [])), reverse=True)[:2]
                res_ = sc_[0][1] if sc_ and sc_[0][0] >= 0.8 and (len(sc_) < 2 or sc_[0][0] - sc_[1][0] >= 0.05) else nm_
                nm_cache[(key_, nm_)] = res_
                return res_
            cup_ev["HomeTeam"] = [to_ours(k_, n_) for k_, n_ in zip(cup_ev["league_key"], cup_ev["home_team"])]
            cup_ev["AwayTeam"] = [to_ours(k_, n_) for k_, n_ in zip(cup_ev["league_key"], cup_ev["away_team"])]
            fin_ = cup_ev[cup_ev["status"].astype(str).str.lower().isin(["finished", "ft", "aet", "pen"]) & cup_ev["home_score"].notna()]
            cup_results = pd.DataFrame({"League": fin_["league_key"].str[4:], "Date": fin_["Date"], "HomeTeam": fin_["HomeTeam"], "AwayTeam": fin_["AwayTeam"],
                                        "FTHG": fin_["home_score"].astype(float), "FTAG": fin_["away_score"].astype(float)})
            up_c = cup_ev[(cup_ev["Date"] >= TODAY) & ~cup_ev.index.isin(fin_.index)]
            cup_fixtures = pd.DataFrame({"Competition": up_c["league_key"].str[4:], "Date": up_c["Date"], "Home": up_c["HomeTeam"], "Away": up_c["AwayTeam"]})
            if len(cup_fixtures):
                espn_schedule = pd.concat([espn_schedule, cup_fixtures], ignore_index=True)
        # ---- referee statistics for the referees we've seen (cached) ----
        RSP = f"{SAVE_DIR}/bsd_referees.json"
        REF_STATS = json.load(open(RSP)) if os.path.exists(RSP) else {}
        refs_needed = [str(int(r_)) for r_ in CTX_MATCH["referee_id"].dropna().unique()] if len(CTX_MATCH) else []
        for r_ in [x for x in refs_needed if x not in REF_STATS][:150]:
            js_ = _bsd(f"/api/v2/referees/{r_}/")
            if js_:
                REF_STATS[r_] = {"name": js_.get("name"), "matches": js_.get("matches"), "yellow": js_.get("avg_yellow_per_match")}
        json.dump(REF_STATS, open(RSP, "w"))
        n_ref_up = int(CTX_MATCH[(CTX_MATCH["Date"] >= TODAY)]["referee_id"].notna().sum()) if len(CTX_MATCH) else 0
        CTX_STATUS = (f"{len(CTX_MATCH)} league matches with context ({int(CTX_MATCH['derby'].sum()) if len(CTX_MATCH) else 0} derbies), "
                      f"{len(cup_results)} cup results, {len(cup_fixtures)} upcoming cup ties, {len(REF_STATS)} referees")
        print(f"  {CTX_STATUS}; referees already appointed for {n_ref_up} upcoming matches.")
health("BSD context (cups, weather, derbies, referees)", _BK is not None and "not used" not in CTX_STATUS, CTX_STATUS)

# ---------- v35: coaches' names (BSD gives each match's coach ids), for the website's lineups; cached, a few new ones per run ----------
COACH_NAMES, COACH_OF = {}, {}                      # coach id -> name; our team name -> current coach's name
CNP = f"{SAVE_DIR}/bsd_coaches.json"
if _BK and len(CTX_MATCH) and "home_coach" in CTX_MATCH:
    COACH_NAMES = json.load(open(CNP)) if os.path.exists(CNP) else {}
    last_ = pd.concat([CTX_MATCH[["HomeTeam", "Date", "home_coach"]].set_axis(["Team", "Date", "coach"], axis=1),
                       CTX_MATCH[["AwayTeam", "Date", "away_coach"]].set_axis(["Team", "Date", "coach"], axis=1)]).dropna().sort_values("Date").groupby("Team").tail(1)
    need_ = [str(int(c_)) for c_ in last_["coach"].unique() if str(int(c_)) not in COACH_NAMES][:60]
    for c_ in need_:
        js_ = None
        for path_ in (f"/api/v2/coaches/{c_}/", f"/api/v2/managers/{c_}/"):    # (BSD's coach endpoint; whichever answers)
            js_ = _bsd(path_)
            if js_:
                break
        COACH_NAMES[c_] = (js_ or {}).get("name") or (js_ or {}).get("full_name") or ""
    json.dump(COACH_NAMES, open(CNP, "w"))
    COACH_OF = {t_: COACH_NAMES.get(str(int(c_))) for t_, c_ in zip(last_["Team"], last_["coach"]) if COACH_NAMES.get(str(int(c_)))}
    print(f"Coaches: names for {len(COACH_OF)} teams ({sum(1 for v_ in COACH_NAMES.values() if v_)} known coaches).")

# ---------- v35: the Egyptian Premier League's kick-off times from BSD, where PitchAPI gives only the date ----------
if _BK and "EXTRA_FIXTURES" in globals() and len(EXTRA_FIXTURES) and "Kickoff" in EXTRA_FIXTURES:
    eg_mask = (EXTRA_FIXTURES["League"] == "Egyptian Premier League") & EXTRA_FIXTURES["Kickoff"].isna()
    if eg_mask.any():
        try:
            egl_ = [l_ for l_ in (lg_list or []) if "egypt" in json.dumps(l_, default=str).lower()]
            n_ko = 0
            for l_ in egl_[:2]:
                js_ = _bsd("/api/v2/events/", league_id=l_["id"], date_from=f"{TODAY:%Y-%m-%d}", date_to=f"{TODAY + pd.Timedelta(days=PREDICT_DAYS):%Y-%m-%d}", limit=200) or {}
                for e_ in js_.get("results", []) if isinstance(js_, dict) else []:
                    if not e_.get("event_date"):
                        continue
                    ko_ = pd.Timestamp(e_["event_date"]).tz_convert(None)
                    for i_ in EXTRA_FIXTURES.index[eg_mask]:
                        r_ = EXTRA_FIXTURES.loc[i_]
                        if abs((pd.Timestamp(r_["Date"]) - ko_.normalize()).days) <= 1 and (tsim(r_["HomeTeam"], e_.get("home_team")) + tsim(r_["AwayTeam"], e_.get("away_team"))) / 2 >= 0.7:
                            EXTRA_FIXTURES.at[i_, "Kickoff"] = ko_; n_ko += 1
            print(f"Egypt kick-off times from BSD: {n_ko} filled" + ("" if egl_ else " (BSD has no Egyptian league)") + ".")
        except Exception as e_:
            print("Egypt kick-off times from BSD: skipped:", str(e_)[:80])

# ---------- v31: the NPFL's current season from BSD (ESPN stopped after May 2026); history before that stays from ESPN ----------
NPFL_BSD_LEAGUE = 28
if INCLUDE_NEW_LEAGUES and _BK:
    import unicodedata as _ud2, difflib as _dl2
    try:
        season_start = pd.Timestamp(f"{TODAY.year if TODAY.month >= 7 else TODAY.year - 1}-07-01")
        rows_, url_, params_ = [], "/api/v2/events/", {"league": NPFL_BSD_LEAGUE, "date_from": f"{season_start:%Y-%m-%d}",
                                                      "date_to": f"{TODAY + pd.Timedelta(days=PREDICT_DAYS):%Y-%m-%d}", "limit": 200}
        for _ in range(10):                                    # follow the pages
            js_ = _bsd(url_, **params_) if params_ else _bsd(url_)
            if not js_:
                break
            rows_ += js_.get("results", []) if isinstance(js_, dict) else js_
            url_, params_ = (js_.get("next"), None) if isinstance(js_, dict) and js_.get("next") else (None, None)
            if not url_:
                break
        ev_ = pd.DataFrame([{"Date": pd.Timestamp(e_.get("event_date") or e_.get("date")).tz_convert(None).normalize(),
                             "Kickoff": pd.Timestamp(e_.get("event_date") or e_.get("date")).tz_convert(None), "home": e_.get("home_team"),
                             "away": e_.get("away_team"), "status": str(e_.get("status")).lower(), "hs": e_.get("home_score"), "as_": e_.get("away_score")}
                            for e_ in rows_ if (e_.get("event_date") or e_.get("date"))])
        name_ = "NPFL (Nigeria)"
        hist_ = SOLO[name_]["data"] if name_ in SOLO else pd.DataFrame(columns=["League", "Season", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"])
        hist_ = hist_[hist_["Date"] < season_start]
        # BSD's club names -> the names in ESPN's history (accent-free spelling, one-to-one, clear matches only)
        _stop2 = {"fc", "club", "football", "the", "international", "int"}
        def _cn2(x):
            w_ = _ud2.normalize("NFKD", str(x)).encode("ascii", "ignore").decode().lower().replace("-", " ").replace(".", " ").split()
            return "".join(t for t in w_ if t not in _stop2) or "".join(w_)
        known_ = sorted(set(hist_["HomeTeam"]) | set(hist_["AwayTeam"])) if len(hist_) else []
        bsd_names = sorted(set(ev_["home"].dropna()) | set(ev_["away"].dropna())) if len(ev_) else []
        npfl_map, used_ = {}, set()
        for b_ in bsd_names:
            cb = _cn2(b_)
            sc_ = sorted(((1.0 if cb == _cn2(k_) else (0.92 if min(len(cb), len(_cn2(k_))) >= 4 and (cb in _cn2(k_) or _cn2(k_) in cb)
                           else _dl2.SequenceMatcher(None, cb, _cn2(k_)).ratio()), k_) for k_ in known_ if k_ not in used_), reverse=True)
            if sc_ and sc_[0][0] >= 0.85 and (len(sc_) < 2 or sc_[0][0] - sc_[1][0] >= 0.05):
                npfl_map[b_] = sc_[0][1]; used_.add(sc_[0][1])
        if len(ev_):
            ev_["HomeTeam"] = ev_["home"].map(lambda t: npfl_map.get(t, t)); ev_["AwayTeam"] = ev_["away"].map(lambda t: npfl_map.get(t, t))
            fin_ = ev_[ev_["status"].isin(["finished", "ft", "ended"]) & ev_["hs"].notna() & ev_["as_"].notna()]
            cur_ = pd.DataFrame({"League": name_, "Season": fin_["Date"].map(season_label), "Date": fin_["Date"], "HomeTeam": fin_["HomeTeam"],
                                 "AwayTeam": fin_["AwayTeam"], "FTHG": fin_["hs"].astype(float), "FTAG": fin_["as_"].astype(float)})
            for c_ in ["B365H", "B365D", "B365A", "HC", "AC", "HY", "AY", "HS", "AS"]:
                cur_[c_] = np.nan
            allr_ = pd.concat([hist_, cur_], ignore_index=True).drop_duplicates(["Date", "HomeTeam", "AwayTeam"]).sort_values("Date").reset_index(drop=True)
            if len(allr_) >= 100:
                SOLO[name_] = {"data": allr_, "season": season_label(TODAY), "half_life": 180, "group": "Africa"}
            up_ = ev_[(ev_["status"].isin(["notstarted", "scheduled"])) & (ev_["Date"] >= TODAY) & (ev_["Date"] <= TODAY + pd.Timedelta(days=PREDICT_DAYS))]
            if "EXTRA_FIXTURES" not in globals():
                EXTRA_FIXTURES = pd.DataFrame(columns=["League", "Date", "HomeTeam", "AwayTeam"])
            EXTRA_FIXTURES = pd.concat([EXTRA_FIXTURES, pd.DataFrame({"League": name_, "Date": up_["Date"], "Kickoff": up_["Kickoff"],
                                                                      "HomeTeam": up_["HomeTeam"], "AwayTeam": up_["AwayTeam"]})],
                                       ignore_index=True)
            new_clubs = sorted((set(cur_["HomeTeam"]) | set(cur_["AwayTeam"])) - set(known_))
            print(f"NPFL from BSD: {len(cur_)} results this season, {len(up_)} upcoming fixtures; names matched: "
                  + ", ".join(f"{b} -> {k}" for b, k in npfl_map.items() if b != k)[:600]
                  + (f"; new to the data (promoted, or a name to check): {', '.join(new_clubs)}" if new_clubs else ""))
            health("NPFL (BSD, this season)", len(cur_) > 0, f"{len(cur_)} results, latest {cur_['Date'].max():%d %b}" if len(cur_) else "no results yet")
    except Exception as ex_:
        health("NPFL (BSD, this season)", False, f"failed: {str(ex_)[:60]}")
