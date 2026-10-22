# ===================== 10b. PLAYERELO: an outside second opinion (experiment only; never published) =====================
# v36. Weekly, in the full run: PlayerElo's club ratings and league-strength table (free plan, 500 requests a month; a snapshot uses
# one request per page of clubs, so about 20-40 a week). Each week's European ties are logged with both clubs' Elo next to our
# chances (European ties are where clubs from leagues no other source covers turn up). Once 150 have been played, a simple Elo
# model (its home edge and draw rate fitted on the earlier half) is compared with ours on the later half, alone and blended 50/50.
# Nothing changes unless the blend clearly helps (better in 95% of reshuffles); PlayerElo's numbers are never shown on the site
# (public display needs their commercial licence).
PE_DIR = f"{SAVE_DIR}/playerelo"
PE_KEY = _secret("PLAYERELO_KEY") if "_secret" in globals() else os.environ.get("PLAYERELO_KEY")
pe_status = "not used (no PLAYERELO_KEY)" if not PE_KEY else "off in quick runs"
if RUN_EXPERIMENTS and PE_KEY:
    os.makedirs(PE_DIR, exist_ok=True)
    PE_STATE_PATH = f"{PE_DIR}/state.json"
    pe_state = json.load(open(PE_STATE_PATH)) if os.path.exists(PE_STATE_PATH) else {}
    pe_used = 0

    def pe_get(path, **params):
        global pe_used
        pe_used += 1
        try:
            r = requests.get(f"https://data-api.playerelo.football{path}", headers={"Authorization": f"Bearer {PE_KEY}"}, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            print(f"  PlayerElo {path}: HTTP {r.status_code}")
        except Exception as ex_:
            print(f"  PlayerElo {path}: {str(ex_)[:60]}")
        return None

    def pe_rows(x):
        """The list of records in a response, whatever the wrapper is called (the format isn't documented in detail)."""
        if isinstance(x, list):
            return x
        if isinstance(x, dict):
            for k_ in ("data", "items", "results", "clubs", "leagues", "players"):
                if isinstance(x.get(k_), list):
                    return x[k_]
        return []

    def pe_pick(d, keys):
        for k_ in keys:
            v_ = d.get(k_) if isinstance(d, dict) else None
            if isinstance(v_, dict):
                v_ = v_.get("name") or v_.get("value")
            if v_ not in (None, ""):
                return v_
        return None

    # ---- the weekly snapshot (at most once every 6 days, so a rerun doesn't spend requests) ----
    CLUBS_PATH, LEAGUES_PATH = f"{PE_DIR}/clubs.csv", f"{PE_DIR}/leagues.csv"
    if not os.path.exists(CLUBS_PATH) or (TODAY - pd.Timestamp(pe_state.get("last", "2000-01-01"))).days >= 6:
        rows_, off_, size_ = [], 0, None
        for _ in range(40):
            page_ = pe_rows(pe_get("/v1/clubs", limit=200, offset=off_))
            if not page_:
                break
            for c_ in page_:
                rows_.append({"pe_id": pe_pick(c_, ["id", "club_id", "team_id"]), "name": pe_pick(c_, ["club_name", "name", "team_name", "club"]),
                              "elo": pd.to_numeric(pe_pick(c_, ["team_elo", "elo", "club_elo", "rating"]), errors="coerce"),
                              "league": pe_pick(c_, ["league_name", "league", "competition"]), "country": pe_pick(c_, ["country", "country_name", "nation"])})
            size_ = size_ or len(page_)
            if len(page_) < size_:
                break
            off_ += len(page_)
        lg_rows_ = [{"name": pe_pick(l_, ["league_name", "name", "competition"]), "country": pe_pick(l_, ["country", "country_name"]),
                     "strength": pd.to_numeric(pe_pick(l_, ["strength", "league_elo", "elo", "avg_elo", "average_elo", "rating"]), errors="coerce")}
                    for l_ in pe_rows(pe_get("/v1/leagues"))]
        clubs_ = pd.DataFrame(rows_).dropna(subset=["name", "elo"]) if rows_ else pd.DataFrame()
        if len(clubs_):
            clubs_.assign(date=TODAY.strftime("%Y-%m-%d")).to_csv(CLUBS_PATH, index=False)
            if lg_rows_:
                pd.DataFrame(lg_rows_).assign(date=TODAY.strftime("%Y-%m-%d")).to_csv(LEAGUES_PATH, index=False)
            pe_state["last"] = TODAY.strftime("%Y-%m-%d")
        month_ = TODAY.strftime("%Y-%m")
        pe_state.setdefault("requests", {})
        pe_state["requests"][month_] = pe_state["requests"].get(month_, 0) + pe_used
        json.dump(pe_state, open(PE_STATE_PATH, "w"))
        print(f"PlayerElo: snapshot of {len(clubs_)} clubs and {len(lg_rows_)} leagues ({pe_used} requests; {pe_state['requests'][month_]} this month of 500).")
    clubs_ = pd.read_csv(CLUBS_PATH) if os.path.exists(CLUBS_PATH) else pd.DataFrame()

    # ---- log this week's European ties with both clubs' Elo (names linked by spelling, only clear matches) ----
    LOG_PE = f"{PE_DIR}/log.csv"
    if len(clubs_) and len(pred_eu):
        def _nk(s):
            return "".join(ch for ch in unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower() if ch.isalnum())
        by_key_ = {}
        for r_ in clubs_.itertuples():
            by_key_.setdefault(_nk(r_.name), []).append(float(r_.elo))
        keys_ = list(by_key_)
        def elo_of(team):
            k_ = _nk(team)
            if k_ in by_key_ and len(by_key_[k_]) == 1:
                return by_key_[k_][0]
            near_ = difflib.get_close_matches(k_, keys_, n=2, cutoff=0.85)
            if near_ and (len(near_) == 1 or difflib.SequenceMatcher(None, k_, near_[0]).ratio() - difflib.SequenceMatcher(None, k_, near_[1]).ratio() >= 0.05) \
                    and len(by_key_[near_[0]]) == 1:
                return by_key_[near_[0]][0]
            return np.nan
        lg_ = pred_eu[["Competition", "Date", "Home", "Away", "pH", "pD", "pA", "Note"]].copy()
        lg_["EloH"], lg_["EloA"] = lg_["Home"].map(elo_of), lg_["Away"].map(elo_of)
        lg_ = lg_.dropna(subset=["EloH", "EloA"]).assign(LoggedOn=TODAY.strftime("%Y-%m-%d"))
        old_ = pd.read_csv(LOG_PE) if os.path.exists(LOG_PE) else pd.DataFrame()
        allpe_ = pd.concat([old_, lg_], ignore_index=True).drop_duplicates(["Competition", "Date", "Home", "Away"], keep="first")   # first log = before kickoff
        allpe_.to_csv(LOG_PE, index=False)
        print(f"PlayerElo: {len(lg_)} of {len(pred_eu)} upcoming European ties linked to both clubs' Elo; {len(allpe_)} logged so far.")

    # ---- the comparison, once enough logged ties have been played ----
    if os.path.exists(LOG_PE) and len(euro):
        pl_ = pd.read_csv(LOG_PE)
        pl_["Date"] = pd.to_datetime(pl_["Date"])
        res_ = euro[["Competition", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]].rename(columns={"HomeTeam": "Home", "AwayTeam": "Away"})
        res_["Date"] = pd.to_datetime(res_["Date"]).dt.normalize()
        m_ = pl_.merge(res_.dropna(subset=["FTHG", "FTAG"]), on=["Competition", "Date", "Home", "Away"], how="inner").sort_values("Date").reset_index(drop=True)
        pe_status = f"{len(pl_)} European ties logged, {len(m_)} played (comparison from 150)"
        if len(m_) >= 150:
            from sklearn.linear_model import LogisticRegression as _LRpe
            o_ = outcome(m_)
            x_ = ((m_["EloH"] - m_["EloA"]) / 400.0).values.reshape(-1, 1)
            half_ = len(m_) // 2
            lr_ = _LRpe(C=1e6, max_iter=1000).fit(x_[:half_], o_[:half_])          # home edge and draw rate, learned on the earlier half
            pe_p = np.zeros((len(m_) - half_, 3))
            pe_p[:, lr_.classes_] = lr_.predict_proba(x_[half_:])
            ours_ = m_[["pH", "pD", "pA"]].values[half_:]
            ol_ = o_[half_:]
            ll_ = lambda p: -np.log(np.clip(p[np.arange(len(ol_)), ol_], 1e-9, 1))
            l_ours, l_pe, l_mix = ll_(ours_), ll_(pe_p), ll_(0.5 * ours_ + 0.5 * pe_p)
            rng_pe = np.random.default_rng(7)
            d_ = l_mix - l_ours
            pct_ = 100 * (np.array([rng_pe.choice(d_, len(d_)).mean() for _ in range(2000)]) < 0).mean()
            helps_ = bool(pct_ >= 95 and d_.mean() < 0)
            json.dump({"tested": int(len(ol_)), "ours": float(l_ours.mean()), "playerelo": float(l_pe.mean()), "blend": float(l_mix.mean()),
                       "pct": float(pct_), "helps": helps_, "checked": TODAY.strftime("%Y-%m-%d")}, open(f"{PE_DIR}/result.json", "w"))
            print(f"PlayerElo on {len(ol_)} played European ties (later half): log loss ours {l_ours.mean():.4f}, PlayerElo {l_pe.mean():.4f}, "
                  f"50/50 blend {l_mix.mean():.4f}; the blend was better in {pct_:.0f}% of reshuffles -> {'it HELPS (candidate to adopt)' if helps_ else 'not adopted'}.")
            if "exp_summary" in globals():
                exp_summary.append({"Experiment": "PlayerElo 50/50 blend, European ties", "Change in log loss": float(d_.mean()),
                                    "Helped in % of reshuffles": float(pct_), "Matches": int(len(ol_))})
            pe_status = f"compared on {len(ol_)} ties: {'helps' if helps_ else 'not adopted'}"
health("PlayerElo (experiment)", True, pe_status)
