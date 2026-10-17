# ===================== 1d. PITCHAPI: other countries' leagues, and expected goals beyond the big five =====================
import re
# Free, very new source (unnamed upstream; terms requested). Used as an extra source with fallbacks: if it fails or
# disappears, everything else keeps working. Needs your key in Colab Secrets as PITCHAPI_KEY.
PA_OTHER_LEAGUES = {"CZE": "1. Liga", "CRO": "HNL", "SRB": "Super Liga", "ISR": "Ligat ha'Al", "SVK": "1. liga"}
PA_XG_LEAGUES = {"Eredivisie": ("NED", "Eredivisie"), "Primeira Liga": ("POR", "Liga Portugal"), "Belgian Pro League": ("BEL", "First Division A"),
                 "Scottish Premiership": ("SCO", "Premiership"), "Super Lig": ("TUR", "Super Lig"), "Greek Super League": ("GRE", "Super League 1"),
                 "MLS": ("USA", "MLS"), "Saudi Pro League": ("KSA", "Saudi Pro League")}
PITCHAPI_RUN_MINUTES = 10      # time limit per run for the expected-goals download (newest matches first; resumes next run)
PA_TACTIC_LEAGUES = {"Premier League": ("ENG", "Premier League"), "La Liga": ("ESP", "LaLiga"), "Bundesliga": ("GER", "Bundesliga"),
                     "Serie A": ("ITA", "Serie A"), "Ligue 1": ("FRA", "Ligue 1")}
PITCHAPI_TACTICS_MINUTES = 10  # time limit per run for formations and match statistics (set 0 to skip)
PITCHAPI_SHOTS_MINUTES = 5     # time limit per run for shot-by-shot data (set 0 to skip)

def _secret(name):
    try:
        from google.colab import userdata
        return userdata.get(name)
    except Exception:
        return os.environ.get(name)

PA_KEY = _secret("PITCHAPI_KEY")
def pa(path, **params):
    for attempt in range(3):
        try:
            r = requests.get(f"https://api.pitchapi.dev{path}", headers={"X-API-KEY": PA_KEY}, params=params, timeout=30)
            if r.status_code == 200:
                return r.json().get("data")
            if r.status_code in (401, 404):
                return None
        except Exception:
            pass
        time.sleep(2 * (attempt + 1))
    return None

_PA_STOP = {"fc", "fk", "sk", "ac", "nk", "hnk", "afc", "sc", "cf", "club", "sv", "bk", "if", "ks", "mfk", "ofk", "fsv", "the"}
_PA_ALIAS = {"prague": "praha", "belgrade": "beograd", "redstar": "crvenazvezda"}
def _cl(s):
    w_ = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().replace("-", " ").replace("'", "").replace(".", " ").split()
    w_ = [x for x in w_ if x not in _PA_STOP] or w_
    out_ = "".join(w_)
    for k_, v_ in _PA_ALIAS.items():
        out_ = out_.replace(k_, v_)
    return out_
def _season_str(label):                      # "2526" -> ["2025/2026", "2025"]
    y = 2000 + int(label[:2])
    return [f"{y}/{y + 1}", str(y)]

def map_by_fixtures(src, dst):
    """Link team names between two sources of the same league (v20). Seeds: near-identical names. Then propagate through
    fixtures: if a source home team is known and the matching date has that team at home in the other source, its
    opponent must be the away team there. Works even when every club plays on the same days (MLS)."""
    src, dst = src.copy(), dst.copy()
    src["d"], dst["d"] = pd.to_datetime(src["Date"]).dt.normalize(), pd.to_datetime(dst["Date"]).dt.normalize()
    st_, dt_ = sorted(set(src["H"]) | set(src["A"])), sorted(set(dst["H"]) | set(dst["A"]))
    sim_ = {(x, y): difflib.SequenceMatcher(None, _cl(x), _cl(y)).ratio() for x in st_ for y in dt_}
    mp, used = {}, set()
    for x in st_:
        ranked = sorted(dt_, key=lambda y: -sim_[(x, y)])
        best = ranked[0]
        gap_ = sim_[(x, ranked[0])] - (sim_[(x, ranked[1])] if len(ranked) > 1 else 0)
        if sim_[(x, best)] >= 0.85 and gap_ >= 0.05 and best not in used:
            mp[x] = best; used.add(best)
    by_day = {d_: g_ for d_, g_ in dst.groupby("d")}
    for _ in range(6):
        votes = {}
        for r_ in src.itertuples():
            for shift in (0, -1, 1):
                g_ = by_day.get(r_.d + pd.Timedelta(days=shift))
                if g_ is None:
                    continue
                if r_.H in mp and r_.A not in mp:
                    hit = g_[g_["H"] == mp[r_.H]]
                    if len(hit) == 1:
                        votes.setdefault(r_.A, []).append(hit["A"].iloc[0])
                if r_.A in mp and r_.H not in mp:
                    hit = g_[g_["A"] == mp[r_.A]]
                    if len(hit) == 1:
                        votes.setdefault(r_.H, []).append(hit["H"].iloc[0])
        added = 0
        for x, vs in votes.items():
            top = pd.Series(vs).value_counts()
            if top.iloc[0] >= 2 and top.iloc[0] / top.sum() >= 0.7 and top.index[0] not in used:
                mp[x] = top.index[0]; used.add(top.index[0]); added += 1
        if not added:
            break
    return mp

pa_status = "not used (no PITCHAPI_KEY in Colab Secrets)"
PA_TACTICS = pd.DataFrame()
if PA_KEY:
    lgs = pa("/v1/leagues") or {}
    lg_df = pd.DataFrame(lgs.get("leagues", []))
    if lg_df.empty:
        pa_status = "unavailable this run"
    else:
        PA_CACHE = f"{SAVE_DIR}/pitchapi_matches.csv"
        pcache = checked_read(PA_CACHE, text=("id", "season", "label", "league"), num=("score_home", "score_away"), name="pitchapi_matches")
        if len(pcache):
            usa_ = pcache["league"].astype(str).str.startswith("USA:")
            pcache.loc[usa_, "label"] = pcache.loc[usa_, "season"]          # v21: MLS labels are its calendar-year seasons
        done_seasons = set(zip(pcache["league"], pcache["season"])) if len(pcache) else set()
        def league_matches(country, name):
            row = lg_df[(lg_df["country_code"] == country) & (lg_df["name"] == name)]
            if row.empty:
                return []
            lid, seasons = row["id"].iloc[0], row["seasons"].iloc[0]
            out = []
            calendar_year = country in ("USA",)            # MLS seasons are calendar years ("2026"), labelled like our MLS data
            for lab in (MLS_SEASONS[-3:] if calendar_year else SEASONS[-3:]):
                s_ = (lab if lab in seasons else None) if calendar_year else next((x for x in _season_str(lab) if x in seasons), None)
                if s_ is None:
                    continue
                key_ = (f"{country}:{name}", s_)
                if key_ in done_seasons and lab != (MLS_SEASONS[-1] if calendar_year else SEASONS[-1]):
                    continue                                  # finished seasons are fetched once
                d_ = pa(f"/v1/leagues/{lid}/matches", season=s_, status="all") or {}
                for m_ in d_.get("matches", []):
                    out.append({"league": key_[0], "season": s_, "label": lab, "id": m_["id"], "date": m_["date"], "status": m_.get("status"),
                                "home": m_["home_team"]["name"], "away": m_["away_team"]["name"],
                                "score_home": m_.get("score_home"), "score_away": m_.get("score_away")})
            return out
        new_rows = []
        for cc, nm in PA_OTHER_LEAGUES.items():
            new_rows += league_matches(cc, nm)
        for our, (cc, nm) in {**PA_XG_LEAGUES, **PA_TACTIC_LEAGUES}.items():
            new_rows += league_matches(cc, nm)
        if new_rows:
            nr = pd.DataFrame(new_rows)
            keep_ = pcache[~pcache.set_index(["league", "season"]).index.isin(nr.set_index(["league", "season"]).index)] if len(pcache) else pcache
            pcache = pd.concat([keep_, nr], ignore_index=True).drop_duplicates("id", keep="last")
            pcache.to_csv(PA_CACHE, index=False)
        pcache["date"] = pd.to_datetime(pcache["date"])

        # ---- (a) domestic leagues for European clubs from countries we didn't cover ----
        other_names_ = sorted(set(euro.loc[euro["HomeLeague"] == "Other", "HomeTeam"]) | set(euro.loc[euro["AwayLeague"] == "Other", "AwayTeam"])
                              | (set(euro_up.loc[euro_up["HomeLeague"] == "Other", "HomeTeam"]) | set(euro_up.loc[euro_up["AwayLeague"] == "Other", "AwayTeam"]) if len(euro_up) else set()))
        pa_dom = pcache[pcache["league"].isin([f"{c}:{n}" for c, n in PA_OTHER_LEAGUES.items()])]
        cand_teams = pa_dom.groupby("league").apply(lambda g: sorted(set(g["home"]) | set(g["away"]))).to_dict() if len(pa_dom) else {}
        club_map, club_league = {}, {}
        for nm_ in other_names_:
            best_, best_s, second_s = None, 0.0, 0.0
            for lg_, teams_ in cand_teams.items():
                for t_ in teams_:
                    a_, b_ = _cl(nm_), _cl(t_)
                    s_ = 1.0 if a_ == b_ else (0.9 if min(len(a_), len(b_)) >= 5 and (a_ in b_ or b_ in a_) and min(len(a_), len(b_)) / max(len(a_), len(b_)) >= 0.5
                                               else difflib.SequenceMatcher(None, a_, b_).ratio())
                    if s_ > best_s:
                        best_, best_s, second_s = (lg_, t_), s_, best_s
                    elif s_ > second_s:
                        second_s = s_
            if best_ and best_s >= 0.75 and best_s - second_s >= 0.05:
                club_map[best_[1]] = nm_                      # PitchAPI name -> our (ESPN) name
                club_league[nm_] = "pa-" + best_[0].split(":")[0]
        if club_league:
            for df_ in [euro, euro_up]:
                if len(df_):
                    for S_ in ["Home", "Away"]:
                        hit = df_[f"{S_}League"].eq("Other") & df_[f"{S_}Team"].isin(club_league)
                        df_.loc[hit, f"{S_}Country"] = df_.loc[hit, f"{S_}Team"].map(club_league)
            played = pa_dom[pa_dom["status"] == "finished"].dropna(subset=["score_home", "score_away"])
            pa_res = pd.DataFrame({"League": "Other-pa-" + played["league"].str.split(":").str[0], "Season": played["label"], "Date": played["date"].dt.normalize(),
                                   "HomeTeam": played["home"].map(lambda t: club_map.get(t, t)), "AwayTeam": played["away"].map(lambda t: club_map.get(t, t)),
                                   "FTHG": played["score_home"].astype(float), "FTAG": played["score_away"].astype(float)})
            other_dom = pd.concat([other_dom, pa_res], ignore_index=True) if len(other_dom) else pa_res
            domestic_x = pd.concat([domestic, other_dom], ignore_index=True)
            upc = pa_dom[(pa_dom["status"] != "finished") & (pa_dom["date"] >= TODAY)]
            if len(upc):
                espn_schedule = pd.concat([espn_schedule, pd.DataFrame({"Competition": "Other-pa-" + upc["league"].str.split(":").str[0], "Date": upc["date"].dt.normalize(),
                                                                        "Home": upc["home"].map(lambda t: club_map.get(t, t)), "Away": upc["away"].map(lambda t: club_map.get(t, t))})],
                                          ignore_index=True)
            other_names.update({f"Other-pa-{c}": n for c, n in PA_OTHER_LEAGUES.items()})
        print(f"PitchAPI: domestic leagues found for {len(club_league)} of {len(other_names_)} clubs from other countries: "
              + ", ".join(sorted(club_league)) if club_league else "PitchAPI: no other-country clubs matched.")

        # ---- (b) expected goals for leagues Understat doesn't cover (time-limited, newest first, cached) ----
        XGP = f"{SAVE_DIR}/pitchapi_xg.csv"
        pxg = checked_read(XGP, text=("id",), num=("xGH", "xGA"), name="pitchapi_xg")
        if pxg.empty:
            pxg = pd.DataFrame(columns=["id", "xGH", "xGA"])
        have_ = set(pxg["id"].astype(str))
        todo = pcache[pcache["league"].isin([f"{c}:{n}" for c, n in PA_XG_LEAGUES.values()]) & (pcache["status"] == "finished") & ~pcache["id"].astype(str).isin(have_)]
        todo = todo.sort_values("date", ascending=False)
        t0, got = time.time(), []
        for r_ in todo.itertuples():
            if time.time() - t0 > PITCHAPI_RUN_MINUTES * 60:
                break
            st_ = pa(f"/v1/matches/{r_.id}/stats") or {}
            xh = xa = np.nan
            extra_ = {}
            for per in st_.get("periods", []):
                if per.get("period") != "All":
                    continue
                for grp in per.get("groups", []):
                    for it in grp.get("items", []):
                        k_ = str(it.get("key", ""))
                        if k_ == "expected_goals":
                            xh, xa = pd.to_numeric(it.get("home"), errors="coerce"), pd.to_numeric(it.get("away"), errors="coerce")
                        elif any(w_ in k_.lower() for w_ in ("possession", "big_chance", "shots_on_target", "on_target")):
                            extra_[k_] = [pd.to_numeric(str(it.get("home")).rstrip("%"), errors="coerce"), pd.to_numeric(str(it.get("away")).rstrip("%"), errors="coerce")]
            got.append({"id": str(r_.id), "xGH": xh, "xGA": xa, "extra": json.dumps({k_: [None if pd.isna(v_) else float(v_) for v_ in vv] for k_, vv in extra_.items()})})
            time.sleep(0.1)
        if got:
            pxg = pd.concat([pxg, pd.DataFrame(got)], ignore_index=True).drop_duplicates("id", keep="last")
            pxg.to_csv(XGP, index=False)
        left_ = max(0, len(todo) - len(got))
        # link PitchAPI names to ours per league, one-to-one, by fixtures on the same dates plus name similarity
        from scipy.optimize import linear_sum_assignment as _lsa2
        xg_rows = []
        pj = pcache.merge(pxg, on="id", how="inner").dropna(subset=["xGH", "xGA"])
        for our, (cc, nm) in PA_XG_LEAGUES.items():
            p_ = pj[pj["league"] == f"{cc}:{nm}"]
            f_ = league_frame(our) if (our in SOLO or our in set(all_matches["League"])) else pd.DataFrame()
            if p_.empty or f_.empty:
                continue
            nm_map = map_by_fixtures(p_.rename(columns={"date": "Date", "home": "H", "away": "A"})[["Date", "H", "A"]],
                                     f_[["Date", "HomeTeam", "AwayTeam"]].rename(columns={"HomeTeam": "H", "AwayTeam": "A"}))
            for r_ in p_.itertuples():
                if r_.home in nm_map and r_.away in nm_map:
                    xg_rows.append({"League": our, "Season": r_.label, "Date": r_.date.normalize(), "HomeTeam": nm_map[r_.home], "AwayTeam": nm_map[r_.away],
                                    "xGH": float(r_.xGH), "xGA": float(r_.xGA), "us_home": r_.home, "us_away": r_.away})
        if xg_rows:
            xg = pd.concat([xg, pd.DataFrame(xg_rows)], ignore_index=True) if len(xg) else pd.DataFrame(xg_rows)
        n_by = pd.Series([r_["League"] for r_ in xg_rows]).value_counts().to_dict() if xg_rows else {}
        print(f"PitchAPI expected goals: {len(pxg)} matches stored ({len(got)} added this run, {left_} still to download); linked: {n_by}")
        pa_status = f"{len(club_league)} other-country clubs placed; xG for {len(pxg)} matches ({left_} to go)"

        # ---- (c) tactics: formations and every match statistic, for our leagues (v22) ----
        TAP = f"{SAVE_DIR}/pitchapi_tactics.csv"
        ptac = checked_read(TAP, text=("id", "f_home", "f_away", "stats", "pv"), name="pitchapi_tactics")
        have_t = set(ptac.loc[ptac.get("pv", pd.Series(dtype=str)).astype(str) == "2", "id"].astype(str)) if len(ptac) and "pv" in ptac else set()   # v23: re-fetch older rows
        tac_leagues = [f"{c}:{n}" for c, n in list(PA_XG_LEAGUES.values()) + list(PA_TACTIC_LEAGUES.values())]
        todo_t = pcache[pcache["league"].isin(tac_leagues) & (pcache["status"] == "finished") & ~pcache["id"].astype(str).isin(have_t)].sort_values("date", ascending=False)
        t1, got_t = time.time(), []
        for r_ in todo_t.itertuples():
            if time.time() - t1 > PITCHAPI_TACTICS_MINUTES * 60:
                break
            st_ = pa(f"/v1/matches/{r_.id}/stats") or {}
            lu_t = pa(f"/v1/matches/{r_.id}/lineups") or {}
            vals = {}
            for per in st_.get("periods", []):
                if per.get("period") != "All":
                    continue
                for grp_ in per.get("groups", []):
                    for it in grp_.get("items", []):
                        lead_ = lambda v_: pd.to_numeric((re.match(r"\s*(-?[0-9.]+)", str(v_)) or [None, None])[1], errors="coerce")   # "312 (85%)" -> 312
                        h_, a_ = lead_(it.get("home")), lead_(it.get("away"))
                        if pd.notna(h_) and pd.notna(a_):
                            vals[str(it.get("key"))] = [float(h_), float(a_)]
            got_t.append({"id": str(r_.id), "f_home": (lu_t.get("home") or {}).get("formation"), "f_away": (lu_t.get("away") or {}).get("formation"), "stats": json.dumps(vals), "pv": "2"})
            time.sleep(0.1)
        if got_t:
            ptac = pd.concat([ptac, pd.DataFrame(got_t)], ignore_index=True).drop_duplicates("id", keep="last")
            ptac.to_csv(TAP, index=False)
        print(f"PitchAPI tactics: {len(ptac)} matches with formations and statistics ({len(got_t)} added this run, {max(0, len(todo_t) - len(got_t))} to go).")
        PA_TACTICS = ptac.merge(pcache[["id", "league", "label", "date", "home", "away"]], on="id", how="inner") if len(ptac) else pd.DataFrame()
        # ---- (d) shot-by-shot data (v24): every shot with its minute, xG, xG on target, situation, body part and location ----
        SHP = f"{SAVE_DIR}/pitchapi_shots.csv"
        shot_done = set(checked_read(SHP, text=("match_id",), name="pitchapi_shots")["match_id"].astype(str)) if os.path.exists(SHP) else set()
        todo_s = pcache[pcache["league"].isin(tac_leagues) & (pcache["status"] == "finished") & ~pcache["id"].astype(str).isin(shot_done)].sort_values("date", ascending=False)
        t2, shots_rows, n_sm = time.time(), [], 0
        for r_ in todo_s.itertuples():
            if time.time() - t2 > PITCHAPI_SHOTS_MINUTES * 60:
                break
            sh_ = pa(f"/v1/matches/{r_.id}/shots") or {}
            for per in sh_.get("periods", []):
                for x_ in per.get("shots", []):
                    shots_rows.append({"match_id": str(r_.id), "team_id": x_.get("team_id"), "minute": x_.get("minute"), "xg": x_.get("expected_goals"),
                                       "xgot": x_.get("expected_goals_on_target"), "situation": x_.get("situation"), "body": x_.get("shot_type") or x_.get("body_part"),
                                       "outcome": x_.get("event_type") or x_.get("outcome"), "x": x_.get("x"), "y": x_.get("y"), "player": (x_.get("player") or {}).get("name")})
            if not sh_.get("periods"):
                shots_rows.append({"match_id": str(r_.id)})                   # remember matches without shot data
            n_sm += 1
            time.sleep(0.1)
        if shots_rows:
            pd.DataFrame(shots_rows).to_csv(SHP, mode="a", header=not os.path.exists(SHP), index=False)
        print(f"PitchAPI shot-by-shot: {len(shot_done) + n_sm} matches stored ({n_sm} added this run, {max(0, len(todo_s) - n_sm)} to go).")
health("PitchAPI", PA_KEY is not None and "unavailable" not in pa_status, pa_status)
