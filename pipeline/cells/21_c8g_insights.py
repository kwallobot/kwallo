# ===================== 7a. TEAM TRENDS, PLAYER STATS, GOALSCORERS AND BOTH TEAMS TO SCORE =====================
# Trend tables: each team's last 7 competitive matches (league, cups and Europe; no friendlies), across seasons.
# Player stats from ESPN lineups (all competitions), Understat xG/xA (big five), impact ratings and availability.
# Goalscorer probabilities: team expected goals x the player's scoring rate x his expected minutes, calibration-tested.
TREND_N = 7
SCORER_MIN_PROB = 0.05
SHORT_C = {"Champions League": "UCL", "Europa League": "UEL", "Conference League": "UECL"}


RUN_REPLAYS = globals().get("RUN_REPLAYS", True)

def line_of(p_):
    """v33: ESPN's detailed position codes (CD-L, LB, DM, AM-R, LW, CF...) to a line: G, D, M or F."""
    s_ = str(p_ or "").upper().strip()
    b_ = s_.split("-")[0]
    if b_ in ("G", "GK", "GOALKEEPER"):
        return "G"
    if b_ in ("D", "DF", "DEF", "CB", "CD", "LCB", "RCB", "LB", "RB", "LWB", "RWB", "WB", "SW", "DEFENDER"):
        return "D"
    if b_ in ("M", "MF", "MID", "DM", "CDM", "CM", "LCM", "RCM", "LM", "RM", "AM", "CAM", "LAM", "RAM", "MIDFIELDER"):
        return "M"
    if b_ in ("F", "FW", "FWD", "S", "ST", "CF", "LF", "RF", "LW", "RW", "SS", "W", "FORWARD", "ATTACKER"):
        return "F"
    return s_[:1] if s_[:1] in ("G", "D", "M", "F") else "M"
GROUP_TRUST = {}                                        # v32: per league group trust labels         # v27: heavy replays (calibration, lineup model) only in full runs

# ---------- v26: trust rule = within 3 points OR two standard errors (whichever is larger), and stable across runs ----------
TRUST_PATH = f"{SAVE_DIR}/trust_state.json"
TRUST_STATE = json.load(open(TRUST_PATH)) if os.path.exists(TRUST_PATH) else {}
def band_tolerance(actual_rate, n):
    se = 100 * np.sqrt(max(actual_rate * (1 - actual_rate), 1e-6) / max(n, 1))
    return max(3.0, 2 * se)
def stable_trust(name, passed):
    """A market becomes trusted after passing on two runs in a row, and loses it after failing on two in a row."""
    if name not in TRUST_STATE:                                          # first run: the label follows this run's result
        TRUST_STATE[name] = {"trusted": bool(passed), "history": [], "last_day": None}
    st_ = TRUST_STATE[name]
    if st_.get("last_day") != TODAY.strftime("%Y-%m-%d"):              # one vote per day, so reruns don't count twice
        st_["history"] = (st_.get("history", []) + [bool(passed)])[-4:]
        st_["last_day"] = TODAY.strftime("%Y-%m-%d")
    else:
        st_["history"] = (st_.get("history", [])[:-1] + [bool(passed)])[-4:]
    h_ = st_["history"]
    if not st_.get("trusted") and len(h_) >= 2 and h_[-1] and h_[-2]:
        st_["trusted"] = True
    elif st_.get("trusted") and len(h_) >= 2 and not h_[-1] and not h_[-2]:
        st_["trusted"] = False
    TRUST_STATE[name] = st_
    json.dump(TRUST_STATE, open(TRUST_PATH, "w"))
    return bool(st_["trusted"])

# ---------- v24: calibration correction and a stricter trust rule for player probabilities ----------
from sklearn.isotonic import IsotonicRegression
PLAYER_CAL = {}
# v32: calibration by league group, so thinner data in one region can't blur another's corrections
CAL_GROUPS = {"europe_top": {"Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1", "Champions League", "Europa League", "Conference League"},
              "americas": {"MLS", "Liga MX", "Argentina Liga Profesional", "Brasileirão Série A", "Brasileirão Série B", "Bolivia División Profesional"},
              "africa_me": {"Saudi Pro League", "South African Premiership", "NPFL (Nigeria)", "Egyptian Premier League"},
              # v36: second tiers and the smaller European leagues, and Asia
              "europe_lower": {"Championship", "League One", "League Two", "Segunda Division", "2. Bundesliga", "Serie B", "Ligue 2", "Scottish Championship",
                               "Romanian Liga I", "Ekstraklasa", "Czech First League", "Croatian HNL", "Serbian SuperLiga", "Israeli Premier League", "Slovak First League"},
              "asia": {"J1 League", "Chinese Super League"}}
CAL_GROUP_NAMES = {"europe_top": "Europe's big leagues and cups", "europe_other": "other European leagues", "americas": "the Americas", "africa_me": "Africa and the Middle East",
                   "europe_lower": "Europe's second tiers and smaller leagues", "asia": "Asia"}
_PA_CC = {"ENG": "europe_top", "ESP": "europe_top", "GER": "europe_top", "ITA": "europe_top", "FRA": "europe_top",
          "USA": "americas", "MEX": "americas", "ARG": "americas", "BRA": "americas", "BOL": "americas", "KSA": "africa_me", "RSA": "africa_me", "EGY": "africa_me",
          "JPN": "asia", "CHN": "asia"}
def cal_group(comp):
    c_ = str(comp)
    if ":" in c_ and c_.split(":")[0].isupper():                  # PitchAPI's "ENG:Premier League" style
        return _PA_CC.get(c_.split(":")[0], "europe_other")
    for g_, s_ in CAL_GROUPS.items():
        if c_ in s_:
            return g_
    return "europe_other"
def group_key(name, comp, store=None):
    """The group's own correction or label if it has one, else the overall one."""
    k_ = f"{name}|{cal_group(comp)}" if comp is not None else name
    return k_ if k_ in (store if store is not None else PLAYER_CAL) else name

def calibrate_player(name, preds, acts, dates, min_cases=500):
    """v25: learn a correction on the earlier half of the replay and check it on the later half. Two kinds are tried, a
    step-shaped one (isotonic) and a smooth one (a straight line on the log-odds scale), and the one that matches the later
    half better is kept. Trusted only if every band with 100+ cases is within 3 points and it beats 'everyone average'."""
    preds, acts, dates = np.clip(np.asarray(preds, float), 1e-4, 1 - 1e-4), np.asarray(acts, float), np.asarray(dates)
    if len(preds) < min_cases:
        return {"trusted": False, "n": len(preds)}
    cut = np.sort(dates)[len(dates) // 2]
    early, late = dates < cut, dates >= cut
    if early.sum() < 100 or late.sum() < 100:
        early, late = np.arange(len(preds)) < len(preds) // 2, np.arange(len(preds)) >= len(preds) // 2
    if len(np.unique(acts[early])) < 2 or len(np.unique(acts[late])) < 2:
        print(f"{name}: not testable yet (the outcome never or always happened in part of the replay).")
        return {"trusted": False, "n": int(len(preds))}
    lg = lambda p: np.log(p / (1 - p))
    from sklearn.linear_model import LogisticRegression as _LR
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(preds[early], acts[early])
    pl_ = _LR(C=1e6).fit(lg(preds[early]).reshape(-1, 1), acts[early])
    cand = {"step": iso.predict(preds[late]), "smooth": pl_.predict_proba(lg(preds[late]).reshape(-1, 1))[:, 1]}
    kind = min(cand, key=lambda k: np.mean((cand[k] - acts[late]) ** 2))
    fixed = cand[kind]
    bins = [0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.55, 0.7, 1.01]
    tab, worst = [], 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        sel = (fixed >= lo) & (fixed < hi)
        if sel.sum() >= 30:
            gap = 100 * (fixed[sel].mean() - acts[late][sel].mean())
            tol = band_tolerance(acts[late][sel].mean(), sel.sum())
            tab.append({"Corrected chance": f"{int(100 * lo)}-{min(100, int(100 * hi))}%", "Cases": int(sel.sum()), "Predicted %": float(100 * fixed[sel].mean()),
                        "Actually happened %": float(100 * acts[late][sel].mean()), "Gap (points)": float(gap), "Allowed (points)": float(tol)})
            if sel.sum() >= 100:
                worst = max(worst, abs(gap) - tol + 3.0)          # how far beyond its allowance (3.0 = exactly at the allowance)
    brier, naive = np.mean((fixed - acts[late]) ** 2), np.mean((acts[late].mean() - acts[late]) ** 2)
    passed = bool(worst <= 3.0 and brier < naive)
    res = {"passed": passed, "trusted": stable_trust(name, passed), "worst_gap": float(max(worst, 0)), "skill": float(1 - brier / naive), "n": int(len(preds)), "table": tab, "kind": kind}
    if kind == "step":
        final = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(preds, acts)
        res["x"], res["y"] = final.X_thresholds_.tolist(), final.y_thresholds_.tolist()
    else:
        f_ = _LR(C=1e6).fit(lg(preds).reshape(-1, 1), acts)
        res["a"], res["b"] = float(f_.coef_[0][0]), float(f_.intercept_[0])
    PLAYER_CAL[name] = res
    why_ = "" if passed else (" - no skill vs 'everyone average'" if brier >= naive else "")
    print(f"{name}: after correction ({kind}), {'passed' if passed else 'failed'} this run (worst band {max(worst, 0):.1f} vs allowance 3.0{why_}), "
          f"skill {100 * res['skill']:+.1f}% -> {'TRUSTED' if res['trusted'] else 'experimental'}{'' if res['trusted'] == passed else ' (label changes after two runs in a row)'}.")
    return res
def apply_player_cal(name, p, comp=None):
    name = group_key(name, comp)
    c_ = PLAYER_CAL.get(name)
    if not c_:
        return p
    if c_.get("x"):
        return float(np.interp(p, c_["x"], c_["y"]))
    if c_.get("a") is not None:
        q = min(max(float(p), 1e-4), 1 - 1e-4)
        return float(1 / (1 + np.exp(-(c_["a"] * np.log(q / (1 - q)) + c_["b"]))))
    return p

def btts_prob(eh, ea, ph, pd_, pa):
    g = score_grid(eh, ea, ph, pd_, pa)
    g = g / g.sum()
    return float(g[1:, 1:].sum())

# ---------- v26: club colours and short names for the badges (and logo links, used only if SHOW_LOGOS) ----------
TEAM_STYLE = {}
STY_PATH = f"{SAVE_DIR}/espn_team_info.json"
sty_ = json.load(open(STY_PATH)) if os.path.exists(STY_PATH) else {}
if not sty_ or sty_.get("_fetched", "") < (TODAY - pd.Timedelta(days=7)).strftime("%Y-%m-%d"):
    fresh_ = {}
    for code_ in list(ESPN_LEAGUES.keys()) + list(EURO_CODES.keys()):
        try:
            js_ = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{code_}/teams", headers={"User-Agent": "Mozilla/5.0"}, timeout=20).json()
            for t_ in js_.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", []):
                tm_ = t_.get("team", {})
                fresh_[f"{code_}|{tm_.get('displayName')}"] = {"color": tm_.get("color"), "alt": tm_.get("alternateColor"), "abbr": tm_.get("abbreviation"),
                                                              "logo": ((tm_.get("logos") or [{}])[0]).get("href")}
        except Exception:
            pass
    if fresh_:
        sty_ = {**fresh_, "_fetched": TODAY.strftime("%Y-%m-%d")}
        json.dump(sty_, open(STY_PATH, "w"))
for k_, v_ in sty_.items():
    if k_ == "_fetched":
        continue
    code_, nm_ = k_.split("|", 1)
    lg_ = ESPN_LEAGUES.get(code_)
    ours_ = team_map.get((lg_, nm_), nm_) if lg_ else nm_
    for key_ in {ours_, nm_}:
        TEAM_STYLE.setdefault(key_, {"color": f"#{v_['color']}" if v_.get("color") else None, "alt": f"#{v_['alt']}" if v_.get("alt") else None,
                                     "abbr": v_.get("abbr") or "".join(w[0] for w in str(ours_).split()[:3]).upper(),
                                     "logo": v_.get("logo") if SHOW_LOGOS else None})
print(f"Club styles: colours and short names for {len(TEAM_STYLE)} team names.")

# ---------- every competitive result we hold, with match stats where available ----------
def _res(df, comp_col):
    cols = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"] + [c for c in ["HS", "AS", "HST", "AST", "HC", "AC", "HY", "AY", "HR", "AR", "HF", "AF"] if c in df]
    out = df[[comp_col] + cols].rename(columns={comp_col: "Comp"}).copy()
    return out
parts_ = [_res(all_matches, "League"), _res(extra_matches, "League")] + [_res(info["data"], "League") for info in SOLO.values()]
if len(euro): parts_.append(_res(euro, "Competition"))
if len(other_dom): parts_.append(_res(other_dom, "League"))
if "div2" in globals() and len(div2): parts_.append(_res(div2, "League"))
if "cup_results" in globals() and len(cup_results): parts_.append(_res(cup_results, "League"))
# v33: the last few days' final scores from ESPN (football-data.co.uk adds them a day or two later; its fuller rows win once there)
recent_rows = []
for code_, lg_ in (ESPN_LEAGUES.items() if "ESPN_LEAGUES" in globals() else []):
    for back_ in range(1, 4):
        day_ = TODAY - pd.Timedelta(days=back_)
        try:
            board_ = espn_get(f"{ESPN_BASE}/{code_}/scoreboard?dates={day_:%Y%m%d}", pause=0.3) or {}
        except Exception:
            continue
        for ev_ in board_.get("events", []):
            if not ev_.get("status", {}).get("type", {}).get("completed"):
                continue
            cs_ = {c["homeAway"]: c for c in ev_["competitions"][0]["competitors"]}
            if "home" not in cs_ or "away" not in cs_:
                continue
            nm = lambda c: team_map.get((lg_, c["team"]["displayName"]), c["team"]["displayName"]) if "team_map" in globals() else c["team"]["displayName"]
            st_ = lambda c, n: next((float(x["displayValue"]) for x in c.get("statistics", []) if x.get("name") == n), np.nan)
            recent_rows.append({"Comp": lg_, "Date": pd.Timestamp(ev_["date"]).tz_convert(None).normalize(), "HomeTeam": nm(cs_["home"]), "AwayTeam": nm(cs_["away"]),
                                "FTHG": float(cs_["home"].get("score", np.nan)), "FTAG": float(cs_["away"].get("score", np.nan)),
                                "HC": st_(cs_["home"], "wonCorners"), "AC": st_(cs_["away"], "wonCorners")})
if recent_rows:
    parts_.append(pd.DataFrame(recent_rows))
    print(f"Recent results from ESPN (last 3 days, for settling picks quickly): {len(recent_rows)} matches.")
RES = pd.concat(parts_, ignore_index=True)
RES["Date"] = pd.to_datetime(RES["Date"]).dt.normalize()
for c_ in ["FTHG", "FTAG", "HS", "AS", "HST", "AST", "HC", "AC", "HY", "AY", "HR", "AR", "HF", "AF"]:
    RES[c_] = pd.to_numeric(RES.get(c_), errors="coerce")
RES = RES[RES["Date"] < TODAY].drop_duplicates(["Date", "HomeTeam", "AwayTeam"]).sort_values("Date")
# v35: missing match statistics filled from ESPN's team statistics (European cups, leagues football-data.co.uk doesn't cover),
#      plus tackles, offsides and throw-ins, and ESPN's match id ("code:id") so the website can open each past match
RES["espn"] = np.nan
if "TS_EXTRA" in globals() and len(TS_EXTRA):
    te_ = TS_EXTRA.drop(columns=["Comp"]).assign(Date=pd.to_datetime(TS_EXTRA["Date"]).dt.normalize())
    RES = RES.merge(te_, on=["Date", "HomeTeam", "AwayTeam"], how="left", suffixes=("", "_espn"))
    RES["espn"] = RES.pop("espn_espn") if "espn_espn" in RES else RES["espn"]
    for c_ in ["HS", "AS", "HST", "AST", "HC", "AC", "HY", "AY", "HR", "AR", "HF", "AF"]:
        if c_ + "_espn" in RES:
            RES[c_] = RES[c_].fillna(pd.to_numeric(RES.pop(c_ + "_espn"), errors="coerce"))
id_parts_ = []
if "links" in globals() and len(links):
    id_parts_.append(pd.DataFrame({"Date": pd.to_datetime(links["Date"]).dt.normalize(), "HomeTeam": links["HomeTeam"], "AwayTeam": links["AwayTeam"],
                                   "espn2": links["comp"].astype(str) + ":" + links["event_id"].astype(str)}))
_inv_eu = {v_: k_ for k_, v_ in EURO_CODES.items()} if "EURO_CODES" in globals() else {}
if len(euro) and "event_id" in euro:
    e_ = euro[euro["Competition"].isin(_inv_eu)]
    id_parts_.append(pd.DataFrame({"Date": pd.to_datetime(e_["Date"]).dt.normalize(), "HomeTeam": e_["HomeTeam"], "AwayTeam": e_["AwayTeam"],
                                   "espn2": e_["Competition"].map(_inv_eu) + ":" + e_["event_id"].astype(str)}))
if id_parts_:
    RES = RES.merge(pd.concat(id_parts_, ignore_index=True).drop_duplicates(["Date", "HomeTeam", "AwayTeam"]), on=["Date", "HomeTeam", "AwayTeam"], how="left")
    RES["espn"] = RES["espn"].fillna(RES.pop("espn2"))
if "THROW_LONG" in globals() and len(THROW_LONG):
    th_ = THROW_LONG[THROW_LONG["is_home"] == 1].rename(columns={"Team": "HomeTeam", "Opp": "AwayTeam", "own": "HTI", "against": "ATI"})
    th_ = th_.assign(Date=pd.to_datetime(th_["Date"]).dt.normalize())[["Date", "HomeTeam", "AwayTeam", "HTI", "ATI"]].drop_duplicates(["Date", "HomeTeam", "AwayTeam"])
    RES = RES.merge(th_, on=["Date", "HomeTeam", "AwayTeam"], how="left")
for c_ in ["HTK", "ATK", "HO", "AO", "HTI", "ATI"]:
    RES[c_] = pd.to_numeric(RES.get(c_), errors="coerce")
# v34: xG for the European cups, smaller European leagues and second divisions (PitchAPI), linked to our results by fixtures
more_rows, more_n = [], {}
for key_, (our_, prio_) in (PA_XG_MORE.items() if "PA_XG_MORE" in globals() and "PJ_MORE" in globals() else []):
    p_ = PJ_MORE[PJ_MORE["league"] == key_]
    d_ = RES[RES["Comp"] == our_]
    if p_.empty or d_.empty:
        continue
    nm_ = map_by_fixtures(p_.rename(columns={"date": "Date", "home": "H", "away": "A"})[["Date", "H", "A"]],
                          d_[["Date", "HomeTeam", "AwayTeam"]].rename(columns={"HomeTeam": "H", "AwayTeam": "A"}))
    for r_ in p_.itertuples():
        if r_.home in nm_ and r_.away in nm_:
            more_rows.append({"League": our_, "Season": r_.label, "Date": pd.Timestamp(r_.date).normalize(), "HomeTeam": nm_[r_.home], "AwayTeam": nm_[r_.away],
                              "xGH": float(r_.xGH), "xGA": float(r_.xGA)})
            more_n[our_] = more_n.get(our_, 0) + 1
if more_n:
    print("Extra xG linked (cups, smaller leagues, second divisions): " + ", ".join(f"{k} {v}" for k, v in sorted(more_n.items(), key=lambda kv: -kv[1])))
xg_all = pd.concat([xg, pd.DataFrame(more_rows)], ignore_index=True) if (len(xg) and more_rows) else (pd.DataFrame(more_rows) if more_rows else xg)
if len(xg_all):
    xm = xg_all[["League", "HomeTeam", "AwayTeam", "Season", "xGH", "xGA"]].drop_duplicates(["League", "Season", "HomeTeam", "AwayTeam"])
    seas_ = pd.concat([all_matches[["League", "Season", "Date", "HomeTeam", "AwayTeam"]]] + [i_["data"][["League", "Season", "Date", "HomeTeam", "AwayTeam"]] for i_ in SOLO.values()])
    seas_["Date"] = pd.to_datetime(seas_["Date"]).dt.normalize()
    RES = RES.merge(seas_.rename(columns={"League": "Comp"}), on=["Comp", "Date", "HomeTeam", "AwayTeam"], how="left")
    RES = RES.merge(xm.rename(columns={"League": "Comp"}), on=["Comp", "Season", "HomeTeam", "AwayTeam"], how="left")
    if more_rows:                                                   # v34: the extra competitions match by date and teams (no season labels there)
        md_ = pd.DataFrame(more_rows)[["League", "Date", "HomeTeam", "AwayTeam", "xGH", "xGA"]].rename(columns={"League": "Comp"})
        md_ = md_.drop_duplicates(["Comp", "Date", "HomeTeam", "AwayTeam"])
        RES = RES.merge(md_, on=["Comp", "Date", "HomeTeam", "AwayTeam"], how="left", suffixes=("", "_more"))
        for c_ in ["xGH", "xGA"]:
            RES[c_] = RES[c_].fillna(RES.pop(c_ + "_more"))
else:
    RES["xGH"], RES["xGA"] = np.nan, np.nan
TEAM_RES = {}
for side, other in [("Home", "Away"), ("Away", "Home")]:
    h_ = side == "Home"
    t_ = pd.DataFrame({"Team": RES[f"{side}Team"], "Date": RES["Date"], "Comp": RES["Comp"], "Venue": "H" if h_ else "A", "Opponent": RES[f"{other}Team"],
                       "GF": RES["FTHG" if h_ else "FTAG"], "GA": RES["FTAG" if h_ else "FTHG"],
                       "xGF": RES["xGH" if h_ else "xGA"], "xGA": RES["xGA" if h_ else "xGH"],
                       "ShotsF": RES["HS" if h_ else "AS"], "ShotsA": RES["AS" if h_ else "HS"], "SOTF": RES["HST" if h_ else "AST"], "SOTA": RES["AST" if h_ else "HST"],
                       "CornersF": RES["HC" if h_ else "AC"], "CornersA": RES["AC" if h_ else "HC"],
                       "CardsF": RES["HY" if h_ else "AY"].fillna(0) + 2 * RES["HR" if h_ else "AR"].fillna(0),
                       "CardsA": RES["AY" if h_ else "HY"].fillna(0) + 2 * RES["AR" if h_ else "HR"].fillna(0),
                       # v35: more team statistics for the website's averages, and ESPN's match id
                       "FoulsF": RES["HF" if h_ else "AF"], "FoulsA": RES["AF" if h_ else "HF"], "TacklesF": RES["HTK" if h_ else "ATK"], "TacklesA": RES["ATK" if h_ else "HTK"],
                       "OffsidesF": RES["HO" if h_ else "AO"], "OffsidesA": RES["AO" if h_ else "HO"], "ThrowsF": RES["HTI" if h_ else "ATI"], "ThrowsA": RES["ATI" if h_ else "HTI"],
                       "espn": RES["espn"]})
    t_.loc[RES["HY"].isna().values, ["CardsF", "CardsA"]] = np.nan
    for tm_, g_ in t_.groupby("Team"):
        TEAM_RES.setdefault(tm_, []).append(g_)
TEAM_RES = {k: pd.concat(v).sort_values("Date") for k, v in TEAM_RES.items()}

def season_start_for(comp):
    calendar = comp in ("MLS",) or comp in ("Eliteserien", "Allsvenskan")
    return pd.Timestamp(TODAY.year, 1, 1) if calendar else pd.Timestamp(TODAY.year if TODAY.month >= 7 else TODAY.year - 1, 7, 1)

ARROW_MIN = {"GF": 0.25, "GA": 0.25, "xGF": 0.2, "xGA": 0.2, "ShotsF": 1.5, "ShotsA": 1.5, "SOTF": 0.7, "SOTA": 0.7, "CornersF": 0.8, "CornersA": 0.8, "CardsF": 0.5, "CardsA": 0.5,
             "FoulsF": 1.5, "FoulsA": 1.5, "TacklesF": 2.0, "TacklesA": 2.0, "OffsidesF": 0.6, "OffsidesA": 0.6, "ThrowsF": 2.0, "ThrowsA": 2.0}   # v35: more averages

# ---------- trend spotting (v23): outcomes that happened in at least 5 of the last 7 ----------
SPOT_MIN = 5
PATTERNS = {   # name: (test on a team's match row, market key used to show the model's probability for the coming match)
    "Won": (lambda r: r.GF > r.GA, "win"), "Unbeaten": (lambda r: r.GF >= r.GA, "unbeaten"), "Lost": (lambda r: r.GF < r.GA, "loss"),
    "Over 2.5 goals": (lambda r: r.GF + r.GA > 2.5, "over25"), "Under 2.5 goals": (lambda r: r.GF + r.GA < 2.5, "under25"),
    "Both teams scored": (lambda r: (r.GF > 0) & (r.GA > 0), "btts"), "Not both teams scored": (lambda r: (r.GF == 0) | (r.GA == 0), "btts_no"),
    "Scored 2+": (lambda r: r.GF >= 2, "team2plus"), "Failed to score": (lambda r: r.GF == 0, "team0"), "Kept a clean sheet": (lambda r: r.GA == 0, "cleansheet"),
    "Conceded": (lambda r: r.GA > 0, "conceded"),
    "Over 4.5 yellow cards in the match": (lambda r: (r.CardsF + r.CardsA) > 4.5, "cards45"), "Over 9.5 corners in the match": (lambda r: (r.CornersF + r.CornersA) > 9.5, "corners95")}
LEAGUE_RATE = {}
def league_rate(comp, name):
    """How often this pattern happens in a typical match of this competition (last two seasons), for comparison."""
    k_ = (comp, name)
    if k_ not in LEAGUE_RATE:
        global ALL_TR
        if "ALL_TR" not in globals():
            ALL_TR = pd.concat([v for v in TEAM_RES.values()])
        g_ = ALL_TR
        g_ = g_[(g_["Comp"] == comp) & (g_["Date"] >= TODAY - pd.Timedelta(days=730))]
        f_, _ = PATTERNS[name]
        ok_ = g_.dropna(subset=["CardsF", "CardsA"]) if "cards" in name else (g_.dropna(subset=["CornersF", "CornersA"]) if "corners" in name else g_)
        LEAGUE_RATE[k_] = float(f_(ok_).mean()) if len(ok_) >= 50 else None
    return LEAGUE_RATE[k_]
def spot_trends(g, comp):
    """Patterns in 5+ of the last 7 matches (all competitions), and in 5+ of the last 7 home / away matches."""
    out_ = []
    for scope, rows in [("last 7", g.tail(7)), ("last 7 home", g[g["Venue"] == "H"].tail(7)), ("last 7 away", g[g["Venue"] == "A"].tail(7))]:
        if len(rows) < 7:
            continue
        for name, (f_, mk) in PATTERNS.items():
            sub = rows.dropna(subset=["CardsF", "CardsA"]) if "cards" in name else (rows.dropna(subset=["CornersF", "CornersA"]) if "corners" in name else rows)
            if len(sub) < 7:
                continue
            n_ = int(f_(sub).sum())
            if n_ >= SPOT_MIN:
                out_.append({"pattern": name, "count": n_, "of": 7, "scope": scope, "market": mk, "league_rate": league_rate(comp, name)})
    # keep the most specific: drop "Unbeaten" if "Won" also holds, "Conceded" if it holds in 7/7 alongside BTTS, etc.
    names = {(o["pattern"], o["scope"]) for o in out_}
    out_ = [o for o in out_ if not (o["pattern"] == "Unbeaten" and ("Won", o["scope"]) in names)]
    return out_
def team_trend(team, comp):
    g = TEAM_RES.get(team)
    if g is None or g.empty:
        return None
    last = g.tail(TREND_N).copy()
    ss = season_start_for(comp)
    seas = g[g["Date"] >= ss]
    last["Result"] = np.where(last["GF"] > last["GA"], "W", np.where(last["GF"] == last["GA"], "D", "L"))
    last["LastSeason"] = last["Date"] < ss
    stats, arrows = {}, {}
    for k_, thr in ARROW_MIN.items():
        a_, b_ = last[k_].dropna(), seas[k_].dropna()
        stats[k_] = [float(a_.mean()) if len(a_) else None, float(b_.mean()) if len(b_) else None]
        if len(a_) >= 3 and len(b_) >= 5 and abs(a_.mean() - b_.mean()) >= max(thr, 0.15 * abs(b_.mean())):
            arrows[k_] = "up" if a_.mean() > b_.mean() else "down"
    pts = (last["Result"] == "W") * 3 + (last["Result"] == "D")
    perf = (last["GF"] - last["xGF"]).dropna()
    home, away = last[last["Venue"] == "H"], last[last["Venue"] == "A"]
    rec = lambda d: f"W{(d['Result'] == 'W').sum()} D{(d['Result'] == 'D').sum()} L{(d['Result'] == 'L').sum()}"
    rows = [{"Date": r.Date.strftime("%Y-%m-%d"), "Comp": SHORT_C.get(r.Comp, other_names.get(r.Comp, r.Comp) if "other_names" in globals() else r.Comp),
             "Venue": r.Venue, "Opponent": r.Opponent, "Score": f"{int(r.GF)}-{int(r.GA)}", "Result": r.Result,
             "xG": None if pd.isna(r.xGF) else f"{r.xGF:.1f}-{r.xGA:.1f}", "Shots": None if pd.isna(r.ShotsF) else f"{int(r.ShotsF)}-{int(r.ShotsA)}",
             "Corners": None if pd.isna(r.CornersF) else f"{int(r.CornersF)}-{int(r.CornersA)}", "LastSeason": bool(r.LastSeason),
             "Cards": None if pd.isna(r.CardsF) else f"{int(r.CardsF)}-{int(r.CardsA)}",          # v35: cards, and ESPN's match id for the website
             "espn": r.espn if isinstance(r.espn, str) and ":" in r.espn else None} for r in last.itertuples()]
    return {"team": team, "rows": rows, "form": "".join(last["Result"].tolist()[::-1]), "ppg": float(pts.mean()), "spotted": spot_trends(g, comp),
            "stats": stats, "arrows": arrows, "perf": float(perf.mean()) if len(perf) else None, "perf_n": int(len(perf)),
            "home": rec(home), "away": rec(away), "season_matches": int(len(seas))}

# ---------- trends for every team with an upcoming fixture, and the Teams table ----------
upc_all = pd.concat([x for x in [pred_dom, pred_eu] if len(x)], ignore_index=True) if (len(pred_dom) or len(pred_eu)) else pd.DataFrame()
TRENDS = {}
for r_ in upc_all.itertuples():
    for t_ in (r_.Home, r_.Away):
        if t_ not in TRENDS:
            tr_ = team_trend(t_, r_.Competition)
            if tr_:
                TRENDS[t_] = tr_
TEAMS_TABLE = []
for comp_ in list(LEAGUES.values()) + list(SOLO):
    teams_ = sorted(set(league_frame(comp_).loc[lambda d: d["Season"] == league_season(comp_), "HomeTeam"]))
    for t_ in teams_:
        tr_ = TRENDS.get(t_) or team_trend(t_, comp_)
        if not tr_:
            continue
        st_ = tr_["stats"]
        TEAMS_TABLE.append({"League": comp_, "Team": t_, "Form": tr_["form"], "PPG (last 7)": tr_["ppg"],
                            "Goals for": st_["GF"][0], "Goals against": st_["GA"][0], "xG for": st_["xGF"][0], "xG against": st_["xGA"][0],
                            "Goals minus xG": tr_["perf"], "xG for vs season": (st_["xGF"][0] - st_["xGF"][1]) if st_["xGF"][0] is not None and st_["xGF"][1] is not None else None,
                            "Shots for": st_["ShotsF"][0], "Corners for": st_["CornersF"][0]})
print(f"Trend tables: {len(TRENDS)} teams with upcoming fixtures; Teams table: {len(TEAMS_TABLE)} teams.")

# ---------- player minutes from lineups and events ----------
PLAYERS_TABLE, KEY_PLAYERS, SCORERS, LEADERBOARDS, scorer_calibration, assist_calibration = [], {}, {}, {}, {}, {}
EXPECTED_XI, xi_acc = {}, {}
if PLAYER_MODEL and len(lu):
    L = lu.assign(player_id=lu["player_id"].astype(str), team_id=lu["team_id"].astype(str), event_id=lu["event_id"].astype(str)).copy()
    for c_ in ["goals", "assists", "shots", "sot", "yellow", "red"]:
        L[c_] = pd.to_numeric(L.get(c_), errors="coerce").fillna(0)
    L["appeared"] = L["starter"] | L["sub_in"]
    ev_ = events_all.copy() if "events_all" in globals() and len(events_all) else pd.DataFrame(columns=["event_id", "type", "minute", "players"])
    ev_["event_id"] = ev_["event_id"].astype(str)
    ex_ = ev_.assign(pl=ev_["players"].astype(str).str.split("|")).explode("pl")
    subs_ = ex_[ex_["type"].astype(str).str.startswith("Substitution")][["event_id", "pl", "minute"]]
    reds_ = ex_[ex_["type"].astype(str).str.startswith("Red Card")][["event_id", "pl", "minute"]]
    L = L.merge(subs_.groupby(["event_id", "pl"])["minute"].min().rename("sub_min"), left_on=["event_id", "player_id"], right_index=True, how="left")
    L = L.merge(reds_.groupby(["event_id", "pl"])["minute"].min().rename("red_min"), left_on=["event_id", "player_id"], right_index=True, how="left")
    has_ev = L["event_id"].isin(set(ev_["event_id"]))
    on_ = np.where(L["starter"], 0, np.where(L["sub_in"], L["sub_min"].fillna(70), np.nan))
    off_ = np.where(L["sub_out"] & ~L["sub_in"], L["sub_min"].fillna(70), 90)
    off_ = np.where(L["red_min"].notna(), np.minimum(off_, L["red_min"]), off_)
    L["minutes"] = np.where(L["appeared"], np.clip(np.where(has_ev, off_ - np.nan_to_num(on_), np.where(L["starter"], np.where(L["sub_out"], 70, 90), 20)), 1, 120), 0)

    # ---------- player table (this season, all competitions) ----------
    lu_season = L[L["date"] >= pd.Timestamp(TODAY.year if TODAY.month >= 7 else TODAY.year - 1, 7, 1)]
    agg = lu_season.groupby(["team_id", "player_id"]).agg(Player=("player", "last"), Team=("team", "last"), Pos=("pos", "last"), Apps=("appeared", "sum"),
                                                         Starts=("starter", "sum"), Minutes=("minutes", "sum"), Goals=("goals", "sum"), Assists=("assists", "sum"),
                                                         Shots=("shots", "sum"), SOT=("sot", "sum"), Yellow=("yellow", "sum"), Red=("red", "sum")).reset_index()
    agg = agg[agg["Apps"] > 0]
    agg["G+A per 90"] = np.where(agg["Minutes"] >= 270, 90 * (agg["Goals"] + agg["Assists"]) / agg["Minutes"].clip(lower=1), np.nan)
    agg["Impact"] = agg["player_id"].map(RATINGS) if "RATINGS" in globals() and RATINGS else np.nan
    # Understat xG / xA (big five), matched by name within the team
    agg["xG per 90"], agg["xA per 90"] = np.nan, np.nan
    if len(understat_players) and "us_map" in globals():
        inv_team = {}
        for (lg_, esp_), fd_ in team_map.items():
            inv_team.setdefault(fd_, esp_)
        upl = understat_players.copy()
        upl["fd_team"] = [us_map.get((lg_, tt_.split(",")[-1]), tt_.split(",")[-1]) for lg_, tt_ in zip(upl["League"], upl["team_title"].astype(str))]
        upl["esp_team"] = upl["fd_team"].map(inv_team)
        clean_n = lambda s_: unicodedata.normalize("NFKD", str(s_)).encode("ascii", "ignore").decode().lower()
        for tname, g_ in agg.groupby("Team"):
            u_ = upl[upl["esp_team"] == tname]
            if u_.empty:
                continue
            for i_, r_ in g_.iterrows():
                cand = [(difflib.SequenceMatcher(None, clean_n(r_["Player"]), clean_n(n_)).ratio(), j_) for j_, n_ in zip(u_.index, u_["player_name"])]
                sc_, j_ = max(cand)
                if sc_ >= 0.8 and u_.loc[j_, "time"] >= 270:
                    agg.loc[i_, "xG per 90"] = 90 * u_.loc[j_, "xG"] / u_.loc[j_, "time"]
                    agg.loc[i_, "xA per 90"] = 90 * u_.loc[j_, "xA"] / u_.loc[j_, "time"]
    # availability
    status = {}
    for r_ in upc_all.itertuples():
        for side_, team_ in [("h", r_.Home), ("a", r_.Away)]:
            a_ = str(getattr(r_, "Absent", "") or "")
            for part in a_.replace("Likely missing, ", "").split("; "):
                if part.startswith(("home: ", "away: ")) and ((part.startswith("home: ") and side_ == "h") or (part.startswith("away: ") and side_ == "a")):
                    for nm_ in part.split(": ", 1)[1].split(", "):
                        status[(team_, nm_.strip())] = "likely missing"
    if "fpl_out" in globals() and len(fpl_out):
        pn_ = L.drop_duplicates("player_id").set_index("player_id")["player"].to_dict()
        for r_ in fpl_out.itertuples():
            status[("pid", str(r_.player_id))] = f"FPL: {r_.news or 'flagged'}"
    def status_of(team_esp, pid, name):
        return status.get(("pid", pid)) or next((v for (t_, n_), v in status.items() if t_ != "pid" and n_ == name), "")
    agg["Status"] = [status_of(t_, p_, n_) for t_, p_, n_ in zip(agg["Team"], agg["player_id"], agg["Player"])]
    if squads:
        agg["Status"] = np.where([str(t_) in squads and p_ not in squads[str(t_)] for t_, p_ in zip(agg["team_id"], agg["player_id"])], "left the club", agg["Status"])
    # teams of interest: those playing in the next PREDICT_DAYS
    esp_names_up = set()
    for r_ in upc_all.itertuples():
        for t_ in (r_.Home, r_.Away):
            esp_names_up.add(t_)
    inv_all = {}
    for (lg_, esp_), fd_ in team_map.items():
        inv_all.setdefault(fd_, esp_)
    want = {inv_all.get(t_, t_) for t_ in esp_names_up}
    sub_ = agg[agg["Team"].isin(want)].copy()
    sub_["FdTeam"] = sub_["Team"].map({v: k for k, v in inv_all.items()}).fillna(sub_["Team"])
    PLAYERS_TABLE = json.loads(sub_.drop(columns=["player_id", "team_id"]).round(3).to_json(orient="records"))
    # key players per team
    for t_, g_ in sub_[sub_["Status"] != "left the club"].groupby("FdTeam"):
        top_s = g_.sort_values(["Goals", "Shots"], ascending=False).head(1)
        top_c = g_.sort_values(["Assists", "Shots"], ascending=False).head(1)
        KEY_PLAYERS[t_] = [{"role": "top scorer", "Player": r.Player, "Goals": int(r.Goals), "Apps": int(r.Apps), "Status": r.Status} for r in top_s.itertuples()] + \
                          [{"role": "main creator", "Player": r.Player, "Assists": int(r.Assists), "Apps": int(r.Apps), "Status": r.Status} for r in top_c.itertuples()]
    # leaderboards
    LEADERBOARDS = {
        "Goals this season": json.loads(agg.sort_values(["Goals", "Shots"], ascending=False).head(25)[["Player", "Team", "Goals", "Assists", "Apps", "Minutes"]].to_json(orient="records")),
        "Expected goals per 90 (big five, 900+ minutes)": json.loads(agg[agg["Minutes"] >= 900].dropna(subset=["xG per 90"]).sort_values("xG per 90", ascending=False).head(25)[["Player", "Team", "xG per 90", "Goals", "Minutes"]].round(2).to_json(orient="records")),
    }
    if "RATINGS" in globals() and RATINGS:
        mins_all = L.groupby("player_id")["minutes"].sum()
        top_i = pd.Series(RATINGS).to_frame("Impact").join(mins_all.rename("Minutes (all data)")).query("`Minutes (all data)` >= 1500").sort_values("Impact", ascending=False).head(25)
        nm_ = L.drop_duplicates("player_id").set_index("player_id")[["player", "team"]]
        top_i = top_i.join(nm_).rename(columns={"player": "Player", "team": "Team"}).round(2)
        LEADERBOARDS["Impact rating (1,500+ minutes)"] = json.loads(top_i[["Player", "Team", "Impact", "Minutes (all data)"]].to_json(orient="records"))
    print(f"Player stats: {len(agg)} players this season; {len(PLAYERS_TABLE)} in teams playing soon.")

    # ---------- goalscorer probabilities ----------
    POS_PRIOR = {"F": 0.38, "FW": 0.38, "ST": 0.40, "CF": 0.40, "M": 0.12, "AM": 0.20, "W": 0.25, "D": 0.04, "G": 0.0, "GK": 0.0}
    def pos_prior(p_):
        p_ = str(p_ or "").upper()
        return POS_PRIOR.get(p_, 0.38 if p_.endswith("F") or p_ in ("LW", "RW") else (0.12 if "M" in p_ else (0.0 if p_.startswith("G") else 0.05)))
    A_PRIOR = {"F": 0.12, "FW": 0.12, "ST": 0.10, "CF": 0.10, "W": 0.18, "AM": 0.18, "M": 0.10, "D": 0.05, "G": 0.005, "GK": 0.005}
    def a_prior(p_):
        p_ = str(p_ or "").upper()
        return A_PRIOR.get(p_, 0.15 if p_ in ("LW", "RW") else (0.10 if "M" in p_ else (0.005 if p_.startswith("G") else (0.05 if p_.startswith("D") else 0.12))))
    def scorer_probs(team_id, before, lam_team, exclude=(), stat="goals"):
        """Each player's chance to score at least once: lambda_team x his scoring rate share x expected minutes (data before `before` only)."""
        g = L[(L["team_id"] == str(team_id)) & (L["date"] < before) & (L["date"] >= before - pd.Timedelta(days=365))]
        if g.empty or not np.isfinite(lam_team):
            return pd.DataFrame()
        w_ = 0.5 ** ((before - g["date"]).dt.days / 180)
        g = g.assign(w=w_)
        team_matches = g.drop_duplicates("event_id")
        tm_w = team_matches["w"].sum()
        last10 = team_matches.sort_values("date").tail(10)["event_id"]
        team_goals_per_match = (g["goals"] * g["w"]).sum() / max(tm_w, 1e-9)
        pl = g.groupby("player_id").agg(Player=("player", "last"), Pos=("pos", "last"), goals=("goals", lambda s: (s * g.loc[s.index, "w"]).sum()),
                                        assists=("assists", lambda s: (s * g.loc[s.index, "w"]).sum()),
                                        shots=("shots", lambda s: (s * g.loc[s.index, "w"]).sum()), mins=("minutes", lambda s: (s * g.loc[s.index, "w"]).sum()))
        recent = g[g["event_id"].isin(last10)]
        n10 = max(recent["event_id"].nunique(), 1)
        pl["p_start"] = recent.groupby("player_id")["starter"].sum().reindex(pl.index).fillna(0) / n10
        pl["p_sub"] = recent.groupby("player_id")["sub_in"].sum().reindex(pl.index).fillna(0) / n10
        st_min = g[g["starter"]].groupby("player_id")["minutes"].mean().reindex(pl.index).fillna(80)
        sb_min = g[g["sub_in"]].groupby("player_id")["minutes"].mean().reindex(pl.index).fillna(20)
        pl.loc[pl.index.isin(exclude), ["p_start", "p_sub"]] = 0
        pl["exp_min"] = pl["p_start"] * st_min + pl["p_sub"] * sb_min
        prior = pl["Pos"].map(pos_prior)
        k90 = 5.0                                            # shrinkage: 5 x 90 minutes of "average player for his position"
        if stat == "assists":
            pl["rate"] = (pl["assists"] + k90 * pl["Pos"].map(a_prior)) / (pl["mins"] / 90 + k90)
        else:
            rate_g = (pl["goals"] + k90 * prior) / (pl["mins"] / 90 + k90)
            rate_s = (pl["shots"] * 0.11 + k90 * prior) / (pl["mins"] / 90 + k90)
            pl["rate"] = 0.5 * rate_g + 0.5 * rate_s
        scale = lam_team / max(team_goals_per_match, 0.3)
        lam_i = pl["rate"] * pl["exp_min"] / 90 * scale
        pl["p_score"] = 1 - np.exp(-lam_i)
        return pl[pl["exp_min"] > 0].sort_values("p_score", ascending=False)

    # live: top scorers per upcoming fixture
    id_rows = []
    if "fixtures" in globals() and len(fixtures) and "home_id" in fixtures:
        id_rows.append(fixtures.rename(columns={"League": "Competition", "HomeTeam": "Home", "AwayTeam": "Away"})[["Competition", "Home", "Away", "home_id", "away_id"]])
    if len(euro_up) and "home_id" in euro_up:
        id_rows.append(euro_up.rename(columns={"HomeTeam": "Home", "AwayTeam": "Away"})[["Competition", "Home", "Away", "home_id", "away_id"]])
    idm = pd.concat(id_rows).dropna(subset=["home_id"]).drop_duplicates(["Competition", "Home", "Away"]) if id_rows else pd.DataFrame()
    pm = upc_all.merge(idm, on=["Competition", "Home", "Away"], how="inner") if len(idm) else pd.DataFrame()
    for r_ in pm.itertuples():
        out_ = {}
        for side_, tid_, lam_ in [("home", r_.home_id, r_.ExpHome), ("away", r_.away_id, r_.ExpAway)]:
            sq_ = squads.get(str(tid_)) if squads else None
            pl_ = scorer_probs(str(tid_), TODAY + pd.Timedelta(days=1), float(lam_))
            if len(pl_) and sq_:
                pl_ = pl_[pl_.index.isin(sq_)]
            missing_ = {n_ for (t_, n_), v_ in status.items() if t_ == (r_.Home if side_ == "home" else r_.Away) and v_ == "likely missing"}
            pl_ = pl_[~pl_["Player"].isin(missing_)] if len(pl_) else pl_
            out_[side_] = [{"Player": p_.Player, "p": float(p_.p_score)} for p_ in pl_.head(5).itertuples() if p_.p_score >= SCORER_MIN_PROB]
            pa_ = scorer_probs(str(tid_), TODAY + pd.Timedelta(days=1), float(lam_), stat="assists")
            if len(pa_) and sq_:
                pa_ = pa_[pa_.index.isin(sq_)]
            pa_ = pa_[~pa_["Player"].isin(missing_)].sort_values("p_score", ascending=False) if len(pa_) else pa_
            out_[side_ + "_assist"] = [{"Player": p_.Player, "p": float(p_.p_score)} for p_ in pa_.head(5).itertuples() if p_.p_score >= SCORER_MIN_PROB]
        SCORERS[(r_.Competition, str(r_.Date)[:10], r_.Home, r_.Away)] = out_

    # ---------- expected lineups: three methods tested on past matches, the best one becomes the default ----------
    # A "start share": the 11 who started most of the last 10 matches (missing the last squad halves a player's chance)
    # B "last XI": exactly the last starting eleven (what PitchAPI shows until lineups are confirmed)
    # C "last XI, adjusted" (v22): the last XI with known absences swapped for the likeliest replacement in the same position group
    grp = line_of
    def xi_methods(g_, allev, k_, extra_out=frozenset()):
        prev10 = allev.iloc[max(0, k_ - 10):k_]["event_id"]
        prev_rows = g_[g_["event_id"].isin(prev10)]
        last_ev = allev.iloc[k_ - 1]["event_id"]
        last_rows = g_[g_["event_id"] == last_ev]
        last_squad = set(last_rows["player_id"])
        share_ = prev_rows.groupby("player_id")["starter"].sum() / max(len(prev10), 1)
        a_ = share_ * np.where(share_.index.isin(last_squad), 1.0, 0.5)
        xi_a = list(a_.sort_values(ascending=False).head(11).index)
        xi_b = list(last_rows.loc[last_rows["starter"], "player_id"])
        out_ = set(last_rows.loc[(last_rows["red"] > 0) | (last_rows["sub_out"] & (last_rows["sub_min"].fillna(99) < 35) & ~last_rows["sub_in"]), "player_id"]) | set(extra_out)
        pos_ = g_.drop_duplicates("player_id", keep="last").set_index("player_id")["pos"].map(grp).to_dict()
        xi_c = [p_ for p_ in xi_b if p_ not in out_]
        pool = [p_ for p_ in share_.sort_values(ascending=False).index if p_ not in xi_c and p_ not in out_]
        for gone in [p_ for p_ in xi_b if p_ in out_]:
            same = [p_ for p_ in pool if pos_.get(p_) == pos_.get(gone)]
            pick = (same or pool or [None])[0]
            if pick:
                xi_c.append(pick); pool.remove(pick)
        return xi_a, xi_b, xi_c, share_
    acc_ = {"A": [], "B": [], "C": []}
    team_groups = {tid_: g_.sort_values("date") for tid_, g_ in L.groupby("team_id")}
    up_team_ids = {str(x) for x in pd.concat([pm["home_id"], pm["away_id"]]).dropna()} if len(pm) else set()
    for tid_, g_ in (team_groups.items() if RUN_REPLAYS else []):           # v27: replays only in the weekly full run
        allev = g_.drop_duplicates("event_id")[["event_id", "date"]].sort_values("date").reset_index(drop=True)
        for k_ in allev.index[(allev["date"] >= TODAY - pd.Timedelta(days=200)).values]:
            if k_ < 5:
                continue
            actual_ = set(g_.loc[(g_["event_id"] == allev.loc[k_, "event_id"]) & g_["starter"], "player_id"])
            if len(actual_) < 10:
                continue
            xa_, xb_, xc_, _ = xi_methods(g_, allev, k_)
            if len(xb_) < 10:
                continue
            for m_, x_ in [("A", xa_), ("B", xb_), ("C", xc_)]:
                acc_[m_].append(len(set(x_) & actual_) / len(actual_))
    # ---------- v26: rotation-aware start-probability model ("M"), learned from about a year of lineups ----------
    EURO_NAMES = set(EURO_CODES.values()) | {"Conference League"}
    from sklearn.linear_model import LogisticRegression as _LRx
    XI_FEATS = ["start_last", "share10", "share_comp", "mins7", "missed_last", "red_last", "early_last", "days_since", "days_to_next",
                "this_euro", "next_euro", "rot", "congested", "c_start_last", "c_mins7", "c_share10", "is_G", "is_D", "is_M", "is_F"]
    def team_arrays(g_):
        ev_ = g_.drop_duplicates("event_id")[["event_id", "date", "comp"]].sort_values("date").reset_index(drop=True)
        pl_ = sorted(g_["player_id"].unique()); pix = {p_: i_ for i_, p_ in enumerate(pl_)}; eix = {e_: i_ for i_, e_ in enumerate(ev_["event_id"])}
        n_, p_n = len(ev_), len(pl_)
        A = {k_: np.zeros((n_, p_n)) for k_ in ["S", "Q", "M", "R", "E"]}
        ei_ = g_["event_id"].map(eix).values; pi_ = g_["player_id"].map(pix).values
        A["S"][ei_, pi_] = g_["starter"].astype(float).values
        A["Q"][ei_, pi_] = 1.0
        A["M"][ei_, pi_] = g_["minutes"].astype(float).values
        A["R"][ei_, pi_] = (g_["red"] > 0).astype(float).values
        A["E"][ei_, pi_] = (g_["sub_out"] & ~g_["sub_in"] & (g_["sub_min"].fillna(99) < 35)).astype(float).values
        pos_ = g_.drop_duplicates("player_id", keep="last").set_index("player_id")["pos"].map(grp).reindex(pl_).fillna("M").values
        euro_ = ev_["comp"].astype(str).str.startswith("uefa").values.astype(float)
        changes = np.r_[np.nan, [11 - (A["S"][j] * A["S"][j - 1]).sum() for j in range(1, n_)]]
        return ev_, pl_, A, pos_, euro_, changes
    def xi_features(ev_, A, pos_, euro_, changes, k_, date_k, this_euro, next_date, next_euro):
        lo10 = max(0, k_ - 10)
        cand = np.where(A["Q"][lo10:k_].sum(0) > 0)[0]
        if len(cand) == 0 or k_ < 5:
            return None, None
        dts = ev_["date"].values
        same = [j for j in range(max(0, k_ - 30), k_) if euro_[j] == this_euro]
        share10 = A["S"][lo10:k_].mean(0)
        share_comp = A["S"][same].mean(0) if same else share10
        recent = (dts[:k_] >= np.datetime64(date_k - pd.Timedelta(days=7)))
        mins7 = A["M"][:k_][recent].sum(0) / 90 if recent.any() else np.zeros(A["S"].shape[1])
        ds = min((date_k - pd.Timestamp(dts[k_ - 1])).days, 14)
        dn = min((next_date - date_k).days, 14) if next_date is not None else 7
        cong = float(ds <= 3 or dn <= 3)
        rot = np.nanmean(changes[max(1, k_ - 10):k_]) / 11 if k_ > 1 else 0.3
        F = pd.DataFrame({"start_last": A["S"][k_ - 1], "share10": share10, "share_comp": share_comp, "mins7": mins7, "missed_last": 1 - A["Q"][k_ - 1],
                          "red_last": A["R"][k_ - 1], "early_last": A["E"][k_ - 1], "days_since": ds, "days_to_next": dn, "this_euro": this_euro,
                          "next_euro": next_euro, "rot": rot, "congested": cong}).iloc[cand]
        F["c_start_last"], F["c_mins7"], F["c_share10"] = F["start_last"] * cong, F["mins7"] * cong, F["share10"] * cong
        for g1 in "GDMF":
            F[f"is_{g1}"] = (pos_[cand] == g1).astype(float)
        return F, cand
    def pick_xi(probs, pos_c):
        order = np.argsort(-probs)
        gks = [i for i in order if pos_c[i] == "G"]
        xi_ = ([gks[0]] if gks else []) + [i for i in order if pos_c[i] != "G"][:11 - (1 if gks else 0)]
        return xi_
    rows_X, rows_y, meta = [], [], []
    TEAM_ARR = {}
    for tid_, g_ in team_groups.items():
        if g_["date"].max() < TODAY - pd.Timedelta(days=400) or (not RUN_REPLAYS and str(tid_) not in up_team_ids):
            continue
        ev_, pl_, A, pos_, euro_, changes = team_arrays(g_)
        TEAM_ARR[tid_] = (ev_, pl_, A, pos_, euro_, changes)
        if not RUN_REPLAYS:
            continue
        for k_ in range(5, len(ev_)):
            d_k = pd.Timestamp(ev_.loc[k_, "date"])
            if d_k < TODAY - pd.Timedelta(days=400) or A["S"][k_].sum() < 10:
                continue
            nd = pd.Timestamp(ev_.loc[k_ + 1, "date"]) if k_ + 1 < len(ev_) else None
            F, cand = xi_features(ev_, A, pos_, euro_, changes, k_, d_k, euro_[k_], nd, euro_[k_ + 1] if k_ + 1 < len(ev_) else 0.0)
            if F is None:
                continue
            rows_X.append(F[XI_FEATS].values); rows_y.append(A["S"][k_][cand]); meta.append((tid_, k_, d_k, cand, F["congested"].iloc[0]))
    XI_MODEL, xi_model_acc = None, {}
    XIM_PATH, XIA_PATH = f"{SAVE_DIR}/xi_model.joblib", f"{SAVE_DIR}/xi_accuracy.json"
    if not RUN_REPLAYS:                                   # reuse the weekly run's model and test results
        import joblib as _jl
        XI_MODEL = _jl.load(XIM_PATH) if os.path.exists(XIM_PATH) else None
        saved_acc = json.load(open(XIA_PATH)) if os.path.exists(XIA_PATH) else {}
    if RUN_REPLAYS and len(meta) >= 500:
        split_ = TODAY - pd.Timedelta(days=100)
        tr_i = [i for i, m_ in enumerate(meta) if m_[2] < split_]; te_i = [i for i, m_ in enumerate(meta) if m_[2] >= split_]
        if len(tr_i) >= 300 and len(te_i) >= 100:
            XI_MODEL = _LRx(C=1.0, max_iter=2000).fit(np.vstack([rows_X[i] for i in tr_i]), np.concatenate([rows_y[i] for i in tr_i]))
            accM, accC, accM_c, accC_c = [], [], [], []
            for i in te_i:
                tid_, k_, d_k, cand, cong = meta[i]
                ev_, pl_, A, pos_, euro_, changes = TEAM_ARR[tid_]
                actual_ = set(np.where(A["S"][k_] > 0)[0])
                pr_ = XI_MODEL.predict_proba(rows_X[i])[:, 1]
                xm_ = {cand[j] for j in pick_xi(pr_, pos_[cand])}
                g_ = team_groups[tid_]
                allev = g_.drop_duplicates("event_id")[["event_id", "date"]].sort_values("date").reset_index(drop=True)
                xc_ = set(xi_methods(g_, allev, k_)[2])
                pid_ix = {p_: j for j, p_ in enumerate(pl_)}
                xc_ix = {pid_ix[p_] for p_ in xc_ if p_ in pid_ix}
                aM, aC = len(xm_ & actual_) / len(actual_), len(xc_ix & actual_) / len(actual_)
                accM.append(aM); accC.append(aC)
                if cong:
                    accM_c.append(aM); accC_c.append(aC)
            xi_model_acc = {"matches": len(accM), "model": float(100 * np.mean(accM)), "adjusted": float(100 * np.mean(accC)),
                            "cong_matches": len(accM_c), "model_cong": float(100 * np.mean(accM_c)) if accM_c else None,
                            "adjusted_cong": float(100 * np.mean(accC_c)) if accC_c else None}
            print(f"Rotation-aware model vs 'last XI adjusted', last 100 days ({len(accM)} team-matches): {xi_model_acc['model']:.1f}% vs {xi_model_acc['adjusted']:.1f}% of starters"
                  + (f"; in congested weeks ({len(accM_c)}): {xi_model_acc['model_cong']:.1f}% vs {xi_model_acc['adjusted_cong']:.1f}%" if accM_c else ""))
            coef_ = dict(zip(XI_FEATS, XI_MODEL.coef_[0]))
            print("  Strongest influences on starting: " + ", ".join(f"{k} {v:+.2f}" for k, v in sorted(coef_.items(), key=lambda kv: -abs(kv[1]))[:6]))
            if xi_model_acc["model"] > xi_model_acc["adjusted"]:
                XI_MODEL = _LRx(C=1.0, max_iter=2000).fit(np.vstack(rows_X), np.concatenate(rows_y))   # refit on everything for live use
            else:
                XI_MODEL = None

    names_m = {"A": "start share", "B": "last starting XI", "C": "last XI, adjusted for known absences", "M": "rotation-aware start chances"}
    xi_acc = {}
    if not RUN_REPLAYS:
        xi_acc = saved_acc
        best_m = "M" if XI_MODEL is not None else {v: k for k, v in names_m.items()}.get(xi_acc.get("best"), "C")
    elif acc_["A"]:
        xi_acc = {"matches": len(acc_["A"]), "ours": float(100 * np.mean(acc_["A"])), "last_xi": float(100 * np.mean(acc_["B"])),
                  "adjusted": float(100 * np.mean(acc_["C"]))}
        best_m = max(["A", "B", "C"], key=lambda m_: np.mean(acc_[m_]))
        if XI_MODEL is not None:
            best_m = "M"
            xi_acc.update({"model": xi_model_acc["model"], "model_vs": xi_model_acc["adjusted"], "model_cong": xi_model_acc.get("model_cong"),
                           "adjusted_cong": xi_model_acc.get("adjusted_cong")})
        names_m["M"] = "rotation-aware start chances"
        xi_acc["best"] = names_m[best_m]
        print(f"Expected-lineup accuracy on {len(acc_['A'])} recent team-matches (share of actual starters predicted): "
              f"start share {xi_acc['ours']:.1f}%, last starting XI {xi_acc['last_xi']:.1f}%, last XI adjusted {xi_acc['adjusted']:.1f}% -> using '{xi_acc['best']}'.")
        import joblib as _jl
        if XI_MODEL is not None:
            _jl.dump(XI_MODEL, XIM_PATH)
        elif os.path.exists(XIM_PATH):
            os.remove(XIM_PATH)
        json.dump(xi_acc, open(XIA_PATH, "w"))
    else:
        best_m = "C"
    EXPECTED_XI = {}
    pname_ = L.drop_duplicates("player_id", keep="last").set_index("player_id")[["player", "pos"]].to_dict("index")
    _st = L[L["starter"].astype(bool) & L["pos"].notna() & ~L["pos"].astype(str).str.upper().isin(["SUB", "S", ""])].sort_values("date").groupby("player_id").tail(15)
    for pid_, p_ in _st.groupby("player_id")["pos"].agg(lambda s: s.map(line_of).mode().iloc[0] if len(s) else None).items():
        if pid_ in pname_ and p_:
            pname_[pid_]["line"] = p_
    # v35: the position drawn on the pitch is the one a player usually starts in (his last 15 starts), not his last appearance
    #      (a substitute's appearance has no position, and one game on the other flank used to move him)
    for pid_, q_ in _st.groupby("player_id")["pos"].agg(lambda s: s.astype(str).str.upper().mode().iloc[0] if len(s) else None).items():
        if pid_ in pname_ and q_:
            pname_[pid_]["pos"] = q_
    # v35: only the goalkeeper is enforced (exactly one). Earlier this also forced 3-5 defenders / 2-6 midfielders / 1-4 forwards, which
    #      pulled in unlikely players when ESPN codes a team's front players as attacking midfielders (Mount at 16% "up front" for
    #      Man United). The shape on the pitch now comes from the team's formation instead (see "formation" below).
    XI_BOUNDS = {"G": (1, 1), "D": (0, 11), "M": (0, 11), "F": (0, 11)}
    TEAM_FORM_ESPN = {}                                    # ESPN team id -> (date, formation), from the team sheets we hold
    if "formation" in L:
        fl_ = L[L["formation"].notna() & L["starter"].astype(bool)].sort_values("date").drop_duplicates("team_id", keep="last")
        TEAM_FORM_ESPN = {str(t_): (pd.Timestamp(d_), str(f_)) for t_, d_, f_ in zip(fl_["team_id"], fl_["date"], fl_["formation"])}
    def team_formation(tid_, team_):
        """The team's most recent formation: ESPN's team sheets or PitchAPI's records, whichever is newer."""
        c_ = [x_ for x_ in (TEAM_FORM_ESPN.get(str(tid_)), (globals().get("TEAM_FORM_PA") or {}).get(team_)) if x_]
        return max(c_, key=lambda x_: x_[0])[1] if c_ else None
    def balance_xi(chosen_, probs_, pool_):
        """v35: exactly one goalkeeper: swaps a second keeper for the likeliest outfield player left (or adds the likeliest keeper)."""
        ln_ = lambda p_: pname_.get(p_, {}).get("line") or line_of(pname_.get(p_, {}).get("pos"))
        chosen_ = list(chosen_)
        for _ in range(6):
            cnt_ = {k_: sum(ln_(p_) == k_ for p_ in chosen_) for k_ in "GDMF"}
            short_ = [k_ for k_, (lo_, hi_) in XI_BOUNDS.items() if cnt_[k_] < lo_]
            over_ = [k_ for k_, (lo_, hi_) in XI_BOUNDS.items() if cnt_[k_] > hi_]
            if not short_ and not over_:
                break
            if short_:
                want_, donors_ = [short_[0]], over_ or [k_ for k_, (lo_, hi_) in XI_BOUNDS.items() if cnt_[k_] > lo_ and k_ != short_[0]]
            else:
                want_, donors_ = [k_ for k_, (lo_, hi_) in XI_BOUNDS.items() if cnt_[k_] < hi_ and k_ not in over_], over_
            cands_ = sorted((p_ for p_ in pool_ if p_ not in chosen_ and ln_(p_) in want_), key=lambda p_: -probs_.get(p_, 0))
            out_ = min((p_ for p_ in chosen_ if ln_(p_) in donors_), key=lambda p_: probs_.get(p_, 0), default=None)
            if not cands_ or out_ is None:
                break
            chosen_[chosen_.index(out_)] = cands_[0]
        return chosen_
    for r_ in pm.itertuples():
        key_ = (r_.Competition, str(r_.Date)[:10], r_.Home, r_.Away)
        entry_ = {}
        for side_, tid_, team_ in [("home", str(r_.home_id), r_.Home), ("away", str(r_.away_id), r_.Away)]:
            g_ = team_groups.get(tid_)
            if g_ is None or g_.empty:
                continue
            allev = g_.drop_duplicates("event_id")[["event_id", "date"]].sort_values("date").reset_index(drop=True)
            missing_names = {n_ for (t_, n_), v_ in status.items() if t_ == team_ and v_ == "likely missing"}
            sq_ = squads.get(tid_) if squads else None
            out_ids = {p_ for p_ in g_["player_id"].unique() if pname_.get(p_, {}).get("player") in missing_names
                       or str(status.get(("pid", p_), "")).startswith("FPL") or (sq_ is not None and p_ not in sq_)}
            news_ = {p_: news_flag(team_, pname_.get(p_, {}).get("player")) for p_ in g_["player_id"].unique()} if "news_flag" in globals() else {}
            out_ids |= {p_ for p_, f_ in news_.items() if f_ and f_[0] == "out"}          # v35: ruled out in team news
            news_doubts = sorted(f"{pname_.get(p_, {}).get('player', p_)} ({f_[1]})" for p_, f_ in news_.items() if f_ and f_[0] == "doubt")
            xa_, xb_, xc_, share_ = xi_methods(g_.assign(sub_min=g_["sub_min"]), allev, len(allev), out_ids)
            probs_ = {p_: float(min(1.0, share_.get(p_, 0.0))) for p_ in set(xa_) | set(xb_) | set(xc_)}
            chosen = {"A": xa_, "B": xb_, "C": xc_}.get(best_m, xc_)
            rotation_note = None
            if best_m == "M" and tid_ in TEAM_ARR:
                ev_, pl_, A, pos_, euro_, changes = TEAM_ARR[tid_]
                d_k = pd.Timestamp(r_.Date)
                nxt = [pd.Timestamp(d) for d in TEAM_DATES.get(team_, []) if pd.Timestamp(d) > d_k] if "TEAM_DATES" in globals() else []
                nd = min(nxt) if nxt else None
                ne_ = float(nd is not None and len(euro_up) > 0 and ((euro_up["Date"] == nd) & ((euro_up["HomeTeam"] == team_) | (euro_up["AwayTeam"] == team_))).any())
                A2 = {k: np.vstack([v, np.zeros((1, v.shape[1]))]) for k, v in A.items()}
                ev2 = pd.concat([ev_, pd.DataFrame([{"event_id": "next", "date": d_k, "comp": "uefa" if r_.Competition in EURO_NAMES else "league"}])], ignore_index=True)
                F, cand = xi_features(ev2, A2, pos_, np.r_[euro_, float(r_.Competition in EURO_NAMES)], np.r_[changes, np.nan], len(ev_), d_k,
                                      float(r_.Competition in EURO_NAMES), nd, ne_)
                if F is not None:
                    pr_ = XI_MODEL.predict_proba(F[XI_FEATS].values)[:, 1]
                    out_ix = np.array([pl_[c] in out_ids for c in cand])
                    pr_ = np.where(out_ix, 0.0, pr_)
                    chosen = [pl_[cand[j]] for j in pick_xi(pr_, pos_[cand])]
                    probs_ = {pl_[c]: float(p_) for c, p_ in zip(cand, pr_)}
                    exp_changes = 11 - sum(probs_.get(p_, 0) for p_ in xb_)
                    if F["congested"].iloc[0] and exp_changes >= 3:
                        rotation_note = f"rotation likely: about {exp_changes:.0f} changes expected from the last XI (busy schedule)"
            conf_, conf_ev = None, None
            for ev_id_, xi_ in (CONFIRMED.get(str(tid_), {}) if "CONFIRMED" in globals() else {}).items():
                if len(up_events) and (up_events.loc[up_events["event_id"].astype(str) == ev_id_, "Date"].astype(str).str[:10] == str(r_.Date)[:10]).any():
                    conf_, conf_ev = xi_, ev_id_
            # v35: a confirmed lineup is drawn in today's positions (from the announced team sheet), not each player's usual one
            cpos_ = {p_: globals().get("CONFIRMED_POS", {}).get((str(conf_ev), str(p_))) for p_ in (conf_ or [])}
            pos_of = lambda p_: cpos_.get(p_) or pname_.get(p_, {}).get("pos")
            line_now = lambda p_: line_of(cpos_[p_]) if cpos_.get(p_) else (pname_.get(p_, {}).get("line") or line_of(pname_.get(p_, {}).get("pos")))
            if conf_:                                         # v27: the official lineup is out
                chosen, probs_, rotation_note = list(conf_), {p_: 1.0 for p_ in conf_}, None
            if not conf_ and len(chosen) < 11:                  # v33: always a full eleven (fill with the likeliest starters left)
                rest_ = sorted((p_ for p_ in probs_ if p_ not in chosen), key=lambda p_: -probs_.get(p_, 0))
                chosen = list(chosen) + rest_[:11 - len(chosen)]
            if not conf_:
                chosen = balance_xi(chosen, probs_, list(probs_))
            chosen = sorted(chosen, key=lambda p_: "GDMF".find(line_now(p_)))
            form_ = globals().get("CONFIRMED_POS", {}).get((str(conf_ev), "formation", str(tid_))) if conf_ else None
            entry_[side_] = {"formation": form_ or team_formation(tid_, team_),        # v35: drawn in this shape on the pitch
                             "ours": [{"Player": pname_.get(p_, {}).get("player", p_), "Pos": pos_of(p_), "Line": line_now(p_), "p": probs_.get(p_, 0.0),
                                       "id": str(p_)}                         # v35: ESPN player id (the website links to the player)
                                      for p_ in chosen], "doubts": [] if conf_ else sorted(missing_names) + news_doubts,
                             "method": "confirmed lineup" if conf_ else names_m[best_m], "rotation": rotation_note, "confirmed": bool(conf_)}
        EXPECTED_XI[key_] = entry_
    if "PA_KEY" in globals() and PA_KEY and len(EXPECTED_XI):
        from scipy.optimize import linear_sum_assignment as _lsa4
        n_pa = 0
        for d_ in sorted({k_[1] for k_ in EXPECTED_XI}):
            day_ = pa(f"/v1/date/{d_}") or {}
            ml_ = day_.get("matches", [])
            keys_ = [k_ for k_ in EXPECTED_XI if k_[1] == d_]
            if not ml_ or not keys_:
                continue
            S_ = np.array([[(tsim(k_[2], m_["home_team"]["name"]) + tsim(k_[3], m_["away_team"]["name"])) / 2 for m_ in ml_] for k_ in keys_])
            ri, ci = _lsa4(-S_)
            for i_, j_ in zip(ri, ci):
                if S_[i_, j_] < 0.6:
                    continue
                lu_pa = pa(f"/v1/matches/{ml_[j_]['id']}/lineups") or {}
                for side_ in ("home", "away"):
                    sd_ = lu_pa.get(side_) or {}
                    co_ = sd_.get("coach") or sd_.get("manager")                  # v35: the coach, for the website's lineups
                    co_ = co_.get("name") if isinstance(co_, dict) else co_
                    if co_ and side_ in EXPECTED_XI[keys_[i_]]:
                        EXPECTED_XI[keys_[i_]][side_]["coach"] = str(co_)
                    if sd_.get("starters") and side_ in EXPECTED_XI[keys_[i_]]:
                        kind_ = "confirmed" if sd_.get("confirmed") else ("last starting XI" if sd_.get("lineup_type") == "lastStarting11" else str(sd_.get("lineup_type") or "predicted"))
                        names_pa = [p_.get("name") for p_ in sd_["starters"]]
                        ours_names = [p_["Player"] for p_ in EXPECTED_XI[keys_[i_]][side_]["ours"]]
                        EXPECTED_XI[keys_[i_]][side_]["pitchapi"] = {"kind": kind_, "formation": sd_.get("formation"), "names": names_pa,
                            "only_pitchapi": [n_ for n_ in names_pa if max([tsim(n_, o_) for o_ in ours_names] or [0]) < 0.8],
                            "only_ours": [o_ for o_ in ours_names if max([tsim(o_, n_) for n_ in names_pa] or [0]) < 0.8]}
                        n_pa += 1
        print(f"Expected lineups: {len(EXPECTED_XI)} matches; PitchAPI lineups for {n_pa} team-sides.")

    # ---------- calibration test: replay last season and this season, did players score as often as predicted? ----------
    PCAL_PATH = f"{SAVE_DIR}/player_calibration.json"
    if not RUN_REPLAYS and os.path.exists(PCAL_PATH):            # reuse the weekly run's corrections and trust labels
        saved_ = json.load(open(PCAL_PATH))
        PLAYER_CAL.update(saved_.get("cal", {}))
        scorer_calibration.update(saved_.get("scorers", {})); assist_calibration.update(saved_.get("assisters", {}))
        for k_, v_ in SCORERS.items():
            for side_ in ("home", "away"):
                for p_ in v_.get(side_, []):
                    p_["p"] = apply_player_cal("Goalscorers", p_["p"], k_[0] if isinstance(k_, tuple) else None)
                for p_ in v_.get(side_ + "_assist", []):
                    p_["p"] = apply_player_cal("Assisters", p_["p"], k_[0] if isinstance(k_, tuple) else None)
    if RUN_REPLAYS and "base" in globals() and len(base) and "mf" in globals() and len(mf):
        bt_ = base.merge(mf[["League", "Date", "HomeTeam", "AwayTeam", "event_id", "home_id", "away_id"]], on=["League", "Date", "HomeTeam", "AwayTeam"], how="inner")
        bt_ = bt_.sort_values("Date").tail(1500)                  # the most recent 1,500 matches keeps this quick
        goals_by_player = L[L["goals"] > 0].groupby(["event_id", "player_id"])["goals"].sum()
        assists_by_player = L[L["assists"] > 0].groupby(["event_id", "player_id"])["assists"].sum()
        preds_, acts_, apreds_, aacts_, pdates_, adates_, pcomp_, acomp_ = [], [], [], [], [], [], [], []
        for r_ in bt_.itertuples():
            for tid_, lam_ in [(str(r_.home_id), r_.ExpHome), (str(r_.away_id), r_.ExpAway)]:
                pl_ = scorer_probs(tid_, pd.Timestamp(r_.Date), float(lam_))
                if pl_.empty:
                    continue
                preds_ += list(pl_["p_score"].values); pdates_ += [np.datetime64(pd.Timestamp(r_.Date))] * len(pl_); pcomp_ += [getattr(r_, "Competition", getattr(r_, "League", None))] * len(pl_)
                acts_ += [float(goals_by_player.get((str(r_.event_id), pid_), 0) > 0) for pid_ in pl_.index]
                pla_ = scorer_probs(tid_, pd.Timestamp(r_.Date), float(lam_), stat="assists")
                apreds_ += list(pla_["p_score"].values); adates_ += [np.datetime64(pd.Timestamp(r_.Date))] * len(pla_); acomp_ += [getattr(r_, "Competition", getattr(r_, "League", None))] * len(pla_)
                aacts_ += [float(assists_by_player.get((str(r_.event_id), pid_), 0) > 0) for pid_ in pla_.index]
        if len(preds_) >= 2000:
            pr_, ac_ = np.array(preds_), np.array(acts_)
            bins = [0, 0.05, 0.1, 0.2, 0.3, 0.4, 1.01]
            tab_ = []
            for lo, hi in zip(bins[:-1], bins[1:]):
                sel = (pr_ >= lo) & (pr_ < hi)
                if sel.sum() >= 50:
                    tab_.append({"Predicted chance": f"{int(100 * lo)}-{min(100, int(100 * hi))}%", "Player-matches": int(sel.sum()),
                                 "Predicted %": float(100 * pr_[sel].mean()), "Actually scored %": float(100 * ac_[sel].mean())})
            err = np.average([abs(t["Predicted %"] - t["Actually scored %"]) for t in tab_], weights=[t["Player-matches"] for t in tab_]) if tab_ else 99
            brier, brier_naive = np.mean((pr_ - ac_) ** 2), np.mean((ac_.mean() - ac_) ** 2)
            scorer_calibration = {"table": tab_, "error_pts": float(err), "n": int(len(pr_)), "skill": float(1 - brier / brier_naive),
                                  "trusted": bool(err <= 2.5 and len(pr_) >= 2000 and brier < brier_naive)}
            print(f"\nGoalscorer probabilities, replayed on {len(pr_)} player-matches: average calibration error {err:.1f} points; "
                  f"skill vs 'everyone has the average chance' {100 * scorer_calibration['skill']:+.1f}% -> "
                  f"{'TRUSTED' if scorer_calibration['trusted'] else 'shown as experimental'}.")
            display(pd.DataFrame(tab_).round(1))
            assist_calibration = {}
            if len(apreds_) >= 2000:
                apr_, aac_ = np.array(apreds_), np.array(aacts_)
                atab_ = []
                for lo, hi in zip(bins[:-1], bins[1:]):
                    sel = (apr_ >= lo) & (apr_ < hi)
                    if sel.sum() >= 50:
                        atab_.append({"Predicted chance": f"{int(100 * lo)}-{min(100, int(100 * hi))}%", "Player-matches": int(sel.sum()),
                                      "Predicted %": float(100 * apr_[sel].mean()), "Actually assisted %": float(100 * aac_[sel].mean())})
                aerr = np.average([abs(t["Predicted %"] - t["Actually assisted %"]) for t in atab_], weights=[t["Player-matches"] for t in atab_]) if atab_ else 99
                ab, abn = np.mean((apr_ - aac_) ** 2), np.mean((aac_.mean() - aac_) ** 2)
                assist_calibration = {"table": atab_, "error_pts": float(aerr), "n": int(len(apr_)), "skill": float(1 - ab / abn), "trusted": bool(aerr <= 2.5 and ab < abn)}
                print(f"Assister probabilities, replayed on {len(apr_)} player-matches: average calibration error {aerr:.1f} points; "
                      f"skill {100 * assist_calibration['skill']:+.1f}% -> {'TRUSTED' if assist_calibration['trusted'] else 'shown as experimental'}.")
                display(pd.DataFrame(atab_).round(1))
            sc_fix = calibrate_player("Goalscorers", preds_, acts_, pdates_)
            as_fix = calibrate_player("Assisters", apreds_, aacts_, adates_) if len(apreds_) else {"trusted": False}
            for nm_, P_, A_, D_, C_ in [("Goalscorers", preds_, acts_, pdates_, pcomp_), ("Assisters", apreds_, aacts_, adates_, acomp_)]:
                grp_ = np.array([cal_group(c_) for c_ in C_])
                for gg_ in sorted(set(grp_)):
                    sel_ = grp_ == gg_
                    if sel_.sum() >= 2000:
                        r_g = calibrate_player(f"{nm_}|{gg_}", np.array(P_)[sel_], np.array(A_)[sel_], np.array(D_)[sel_])
                        GROUP_TRUST[f"{nm_}|{gg_}"] = bool(r_g.get("trusted"))
                        print(f"  {nm_}, {CAL_GROUP_NAMES[gg_]}: {'trusted' if r_g.get('trusted') else 'experimental'} ({int(sel_.sum())} cases)")
            scorer_calibration["trusted"] = bool(sc_fix.get("trusted"))
            for nm_, fx_ in [("Goalscorers", sc_fix), ("Assisters", as_fix)]:
                if fx_.get("table"):
                    print(f"{nm_}, after correction (later half of the replay):")
                    display(pd.DataFrame(fx_["table"]).round(1))
                    EXTRA_TABLES_EARLY = list(globals().get("EXTRA_TABLES_EARLY", [])) + [{"title": f"{nm_}: after correction",
                        "hint": f"{'Trusted' if fx_.get('trusted') else 'Experimental'} ({fx_.get('kind', '')} correction); worst band gap {fx_.get('worst_gap', 0):.1f} points.", "rows": fx_["table"]}]
            assist_calibration["trusted"] = bool(as_fix.get("trusted"))
            json.dump({"cal": PLAYER_CAL, "scorers": {k: v for k, v in scorer_calibration.items() if k != "table"},
                       "assisters": {k: v for k, v in assist_calibration.items() if k != "table"}}, open(PCAL_PATH, "w"), default=float)
            # apply the corrections to this run's live probabilities
            for k_, v_ in SCORERS.items():
                for side_ in ("home", "away"):
                    for p_ in v_.get(side_, []):
                        p_["p"] = apply_player_cal("Goalscorers", p_["p"], k_[0] if isinstance(k_, tuple) else None)
                    for p_ in v_.get(side_ + "_assist", []):
                        p_["p"] = apply_player_cal("Assisters", p_["p"], k_[0] if isinstance(k_, tuple) else None)
            EXTRA_TABLES_EARLY = [{"title": "Goalscorer probabilities: calibration", "hint": f"Replayed on {len(pr_)} player-matches: when the model gave a player X% to score, how often did he? "
                                   f"Average error {err:.1f} points; {'trusted' if scorer_calibration['trusted'] else 'still experimental'}.", "rows": tab_}]

# ---------- both teams to score, for every upcoming prediction ----------
for df_ in [pred_dom, pred_eu]:
    if len(df_):
        df_["pBTTS"] = [btts_prob(r.ExpHome, r.ExpAway, r.pH, r.pD, r.pA) for r in df_.itertuples()]
print(f"Both teams to score: added to {len(pred_dom) + len(pred_eu)} predictions.")

for f_ in FILE_CHECKS:
    if f_["issues"]:
        health(f"Saved file: {f_['file']}", False, "; ".join(f_["issues"]))
health("Saved-file checks", all(not f_["issues"] for f_ in FILE_CHECKS), f"{len(FILE_CHECKS)} files checked when read back")

# ---------- v35: goal timing in 15-minute periods, for the website's Markets tab ----------
# The chance of a goal in each period of the coming match (expected goals split by the competition's real goal-minute pattern),
# and each side's share of goals scored and conceded per period this season (ESPN's goal minutes; own goals left out of team shares).
TIMING_BANDS = ["0-15", "16-30", "31-45+", "46-60", "61-75", "76-90+"]
GOAL_TIMING = {}
def _band(mn):
    return min(5, max(0, (int(mn) - 1) // 15)) if pd.notna(mn) else None
if "events_all" in globals() and len(events_all) and "lu" in globals() and len(lu):
    ge_ = events_all[events_all["type"].astype(str).str.match(r"^(Goal|Penalty - Scored|Own Goal)")].copy()
    ge_["band"] = pd.to_numeric(ge_["minute"], errors="coerce").map(_band)
    ge_ = ge_.dropna(subset=["band"])
    ge_["own"] = ge_["type"].astype(str).str.startswith("Own Goal")
    all_share = (ge_["band"].value_counts(normalize=True).reindex(range(6), fill_value=0)).values
    comp_share = {c_: g_["band"].value_counts(normalize=True).reindex(range(6), fill_value=0).values for c_, g_ in ge_.groupby("comp") if len(g_) >= 300}
    code_of_ = {**{v_: k_ for k_, v_ in ESPN_LEAGUES.items()}, **{v_: k_ for k_, v_ in EURO_CODES.items()}}
    ev_teams = lu.drop_duplicates(["event_id", "team_id"])[["event_id", "team_id", "date"]].astype({"event_id": str, "team_id": str})
    ev_teams = ev_teams[pd.to_datetime(ev_teams["date"]) >= pd.Timestamp(TODAY.year if TODAY.month >= 7 else TODAY.year - 1, 7, 1)]
    ge_s = ge_[ge_["event_id"].astype(str).isin(set(ev_teams["event_id"]))].assign(event_id=lambda d: d["event_id"].astype(str), team_id=lambda d: d["team_id"].astype(str))
    def team_bands(tid):
        evs_ = set(ev_teams.loc[ev_teams["team_id"] == str(tid), "event_id"])
        g_ = ge_s[ge_s["event_id"].isin(evs_) & ~ge_s["own"]]
        f_, a_ = g_[g_["team_id"] == str(tid)], g_[g_["team_id"] != str(tid)]
        share = lambda d: [round(float(x), 3) for x in d["band"].value_counts(normalize=True).reindex(range(6), fill_value=0).values] if len(d) else None
        return {"for": share(f_), "against": share(a_), "n_for": int(len(f_)), "n_against": int(len(a_)), "matches": len(evs_)}
    ids_ = {}
    for fr_, cc_ in ((espn_fx, "League"), (euro_up, "Competition")):
        if len(fr_) and {"home_id", "away_id"}.issubset(fr_.columns):
            for r_ in fr_.itertuples():
                ids_[(getattr(r_, cc_), str(r_.Date)[:10], r_.HomeTeam, r_.AwayTeam)] = (str(r_.home_id), str(r_.away_id))
    for df_ in [pred_dom, pred_eu]:
        for r_ in (df_.itertuples() if len(df_) else []):
            k_ = (r_.Competition, str(r_.Date)[:10], r_.Home, r_.Away)
            lam_ = float(r_.ExpHome) + float(r_.ExpAway) if pd.notna(r_.ExpHome) and pd.notna(r_.ExpAway) else None
            if lam_ is None:
                continue
            sh_ = comp_share.get(code_of_.get(r_.Competition), all_share)
            ent_ = {"bands": TIMING_BANDS, "p_goal": [round(float(1 - np.exp(-lam_ * s_)), 3) for s_ in sh_]}
            if k_ in ids_:
                ent_["home"], ent_["away"] = team_bands(ids_[k_][0]), team_bands(ids_[k_][1])
            GOAL_TIMING[k_] = ent_
    print(f"Goal timing: {len(GOAL_TIMING)} matches ({len(ge_)} goals with minutes; {len(comp_share)} competitions with their own pattern).")
