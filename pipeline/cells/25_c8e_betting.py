# ===================== 8b. BETTING: odds archive, paper-betting ledger and edge search =====================
# Nothing here places a bet. It records the bets the model WOULD make, at the best available prices, and checks them
# honestly: profit, and closing-line value against Pinnacle (the sharpest bookmaker). Real money only after a confirmed edge.
EV_MIN = 0.03                  # a "value bet" needs the model's expected value at the best price to be at least +3%
MAX_PRICE = 10.0               # ignore longer odds than this (very noisy)
# Only prices you could realistically take count as "best". Edit this list to the bookmakers you actually use.
MY_BOOKMAKERS = ["bet365", "pinnacle", "william-hill", "betfair", "betway", "betvictor", "888sport", "betfred", "betsson",
                 "betano", "boylesports", "betmgm-uk", "unibet", "ladbrokes", "coral", "paddy-power", "sky-bet", "bwin", "betuk"]
MAX_ABOVE_PINNACLE = 1.10      # a price more than 10% above Pinnacle's is treated as stale or erroneous and ignored
MAX_PLAUSIBLE_EV = 0.25        # an "edge" above +25% is an implausibly large disagreement (model error or data problem): listed, not logged
ARCH_PATH, LEDGER_PATH = f"{SAVE_DIR}/odds_archive_v2.csv", f"{SAVE_DIR}/paper_ledger.csv"
ARCH_COLS = ["Competition", "Date", "Home", "Away", "bsd_id", "snapshot", "bestH", "bestBookH", "pinH", "bestD", "bestBookD", "pinD", "bestA", "bestBookA", "pinA"]

def bsd_key():
    try:
        from google.colab import userdata
        return userdata.get("BSD_KEY")
    except Exception:
        return os.environ.get("BSD_KEY")

BSD_KEY = bsd_key()
def bsd(path, **params):
    for attempt in range(3):
        try:
            r = requests.get(f"https://sports.bzzoiro.com{path}", headers={"Authorization": f"Token {BSD_KEY}"}, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (401, 402, 404):
                return None
        except Exception:
            pass
        time.sleep(2 * (attempt + 1))
    return None

_STOPW = {"fc", "cf", "sc", "afc", "ac", "as", "ssc", "sk", "fk", "cd", "rc", "sv", "if", "bk", "kv", "club", "de", "the"}
# football-data.co.uk's abbreviations -> fuller names, so they match BSD's (and others') spellings
_ALIAS = {"mancity": "manchestercity", "manunited": "manchesterunited", "manutd": "manchesterunited", "nottmforest": "nottinghamforest",
          "sheffieldutd": "sheffieldunited", "sheffieldweds": "sheffieldwednesday", "wolves": "wolverhampton", "athmadrid": "atleticomadrid",
          "athbilbao": "athleticbilbao", "sociedad": "realsociedad", "espanol": "espanyol", "mgladbach": "monchengladbach", "spbraga": "braga",
          "splisbon": "sportinglisbon", "redstarbelgrade": "crvenazvezda", "redstar": "crvenazvezda", "psg": "parissaintgermain", "parissg": "parissaintgermain",
          "fortunadusseldorf": "dusseldorf", "kbenhavn": "copenhagen", "kobenhavn": "copenhagen", "einfrankfurt": "eintrachtfrankfurt", "leverkusen": "bayerleverkusen", "qpr": "queensparkrangers"}
def _clean(s):
    w_ = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().replace("-", " ").replace(".", " ").replace("'", "").split()
    out_ = "".join(x for x in w_ if x not in _STOPW) or "".join(w_)
    return _ALIAS.get(out_, out_)
def team_sim(x, y):
    x, y = _clean(x), _clean(y)
    if not x or not y:
        return 0.0
    if x == y:
        return 1.0
    if min(len(x), len(y)) >= 4 and (x in y or y in x):
        return 0.9
    if min(len(x), len(y)) >= 3 and (x.startswith(y) or y.startswith(x)):   # "aek" / "aekathens"
        return 0.85
    return difflib.SequenceMatcher(None, x, y).ratio()
def pair_score(h1, a1, h2, a2):
    return (team_sim(h1, h2) + team_sim(a1, a2)) / 2

ledger_summary, ledger_open, ledger_settled, edge_rows, probable_errors = {}, [], [], [], []
upcoming_preds = pd.concat([x for x in [pred_dom, pred_eu] if len(x)], ignore_index=True) if (len(pred_dom) or len(pred_eu)) else pd.DataFrame()

# ---------- 1. today's prices from BSD: best price and Pinnacle, archived ----------
prices = pd.DataFrame()
if BSD_KEY and len(upcoming_preds):
    evs, nxt = [], None
    page = bsd("/api/v2/events/", date_from=f"{TODAY:%Y-%m-%d}", date_to=f"{TODAY + pd.Timedelta(days=PREDICT_DAYS):%Y-%m-%d}", limit=200)
    while page:
        evs += page.get("results", [])
        nxt = page.get("next")
        page = None
        if nxt:
            try:
                page = requests.get(nxt, headers={"Authorization": f"Token {BSD_KEY}"}, timeout=30).json()
            except Exception:
                page = None
    bdf = pd.DataFrame([{"bsd_id": e.get("id"), "Date": pd.Timestamp(e.get("event_date")).tz_convert(None).normalize(),
                         "bh": e.get("home_team"), "ba": e.get("away_team")} for e in evs if e.get("event_date")])
    rows, unmatched = [], []
    # pair our fixtures with BSD's one-to-one on each date, so no BSD event is used twice (v18)
    from scipy.optimize import linear_sum_assignment as _lsa
    up_ = upcoming_preds.reset_index(drop=True)
    up_["_d"] = pd.to_datetime(up_["Date"]).dt.normalize()
    pairs_ = {}
    for d_, g_ in up_.groupby("_d"):
        cand = bdf[(bdf["Date"] - d_).abs() <= pd.Timedelta(days=1)] if len(bdf) else bdf
        if cand.empty:
            continue
        S_ = np.array([[pair_score(h, a, bh, ba) for bh, ba in zip(cand["bh"], cand["ba"])] for h, a in zip(g_["Home"], g_["Away"])])
        hs_ = np.array([[max(team_sim(h, bh), team_sim(a, ba)) for bh, ba in zip(cand["bh"], cand["ba"])] for h, a in zip(g_["Home"], g_["Away"])])
        ri, ci = _lsa(-S_)
        for i_, j_ in zip(ri, ci):
            if S_[i_, j_] >= 0.5 and hs_[i_, j_] >= 0.7:
                pairs_[g_.index[i_]] = int(cand["bsd_id"].iloc[j_])
    for idx_, m in up_.iterrows():
        m = m.to_dict(); m = type("M", (), m)()
        d_ = pd.Timestamp(m.Date)
        if idx_ not in pairs_:
            unmatched.append(f"{m.Home} v {m.Away} ({m.Competition})")
            continue
        bsd_id_ = pairs_[idx_]
        od = bsd("/api/odds/", event=bsd_id_, market="1x2")
        time.sleep(0.2)
        if not od:
            continue
        q = pd.DataFrame(od.get("odds", []))
        if q.empty or "outcome" not in q:
            continue
        q = q[q["market"] == "1x2"]
        rec = {"Competition": m.Competition, "Date": d_.strftime("%Y-%m-%d"), "Home": m.Home, "Away": m.Away, "bsd_id": bsd_id_,
               "snapshot": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")}
        mine = {b_.lower() for b_ in MY_BOOKMAKERS}
        for oc, col in [("HOME", "H"), ("DRAW", "D"), ("AWAY", "A")]:
            o_ = q[q["outcome"] == oc]
            if o_.empty:
                continue
            pin = o_[o_["bookmaker_code"] == "pinnacle"]
            pin_price = float(pin["decimal_odds"].iloc[0]) if len(pin) else np.nan
            rec[f"pin{col}"] = pin_price
            ok_ = o_[o_["bookmaker_code"].astype(str).str.lower().isin(mine) | o_["bookmaker"].astype(str).str.lower().isin(mine)]
            if np.isfinite(pin_price):
                ok_ = ok_[ok_["decimal_odds"] <= pin_price * MAX_ABOVE_PINNACLE]
            if ok_.empty:
                continue
            best = ok_.loc[ok_["decimal_odds"].idxmax()]
            rec[f"best{col}"], rec[f"bestBook{col}"] = float(best["decimal_odds"]), best["bookmaker"]
        rows.append(rec)
    prices = pd.DataFrame(rows)
    if len(prices):
        prices.reindex(columns=ARCH_COLS).to_csv(ARCH_PATH, mode="a", header=not os.path.exists(ARCH_PATH), index=False)   # fixed column order
    health("BSD odds", len(prices) > 0, f"prices for {len(prices)} of {len(upcoming_preds)} upcoming matches; archived")
    print(f"BSD odds: prices for {len(prices)} of {len(upcoming_preds)} upcoming matches (added to the odds archive); "
          f"best prices only from MY_BOOKMAKERS and within {int(100 * (MAX_ABOVE_PINNACLE - 1))}% of Pinnacle.")
    if unmatched:
        print(f"  Not matched on BSD ({len(unmatched)}): " + "; ".join(unmatched[:15]) + (" ..." if len(unmatched) > 15 else ""))
elif not BSD_KEY:
    health("BSD odds", False, "no BSD_KEY found in Colab Secrets")
    print("BSD odds skipped: add your key to Colab Secrets as BSD_KEY.")

# ---------- 2. paper-betting ledger: new value bets (the first price seen is kept, like a placed bet) ----------
if os.path.exists(LEDGER_PATH) and not os.path.exists(f"{SAVE_DIR}/paper_ledger_v17_started.txt"):
    os.replace(LEDGER_PATH, f"{SAVE_DIR}/paper_ledger_void_v16.csv")
    open(f"{SAVE_DIR}/paper_ledger_v17_started.txt", "w").write(TODAY.strftime("%Y-%m-%d"))
    print("Paper ledger restarted: earlier entries were distorted (double-fixture bug, outlier prices) and are kept as paper_ledger_void_v16.csv.")
elif not os.path.exists(f"{SAVE_DIR}/paper_ledger_v17_started.txt"):
    open(f"{SAVE_DIR}/paper_ledger_v17_started.txt", "w").write(TODAY.strftime("%Y-%m-%d"))
ledger = pd.read_csv(LEDGER_PATH) if os.path.exists(LEDGER_PATH) else pd.DataFrame()
probable_errors = []
if len(ledger) and len(upcoming_preds):
    live_keys = set(zip(upcoming_preds["Competition"], pd.to_datetime(upcoming_preds["Date"]).dt.strftime("%Y-%m-%d"), upcoming_preds["Home"], upcoming_preds["Away"]))
    future_ = pd.to_datetime(ledger["Date"]) >= TODAY
    gone_ = future_ & ~pd.Series([k in live_keys for k in zip(ledger["Competition"], ledger["Date"], ledger["Home"], ledger["Away"])], index=ledger.index)
    if gone_.any():
        VOID = f"{SAVE_DIR}/paper_ledger_void.csv"
        ledger[gone_].assign(VoidReason="fixture no longer in today's predictions (team or fixture data corrected)").to_csv(VOID, mode="a", header=not os.path.exists(VOID), index=False)
        print(f"Paper ledger: {int(gone_.sum())} open bets voided because their fixture was corrected (e.g. a mis-identified team); see paper_ledger_void.csv.")
        ledger = ledger[~gone_].reset_index(drop=True)
if len(prices):
    pr = prices.merge(upcoming_preds[["Competition", "Date", "Home", "Away", "pH", "pD", "pA", "Group"]].assign(Date=lambda x: pd.to_datetime(x["Date"]).dt.strftime("%Y-%m-%d")),
                      on=["Competition", "Date", "Home", "Away"])
    new_bets, probable_errors = [], []
    for r in pr.itertuples():
        best_ev, pick = -1, None
        for col, p_col in [("H", "pH"), ("D", "pD"), ("A", "pA")]:
            price = getattr(r, f"best{col}", np.nan)
            if pd.notna(price) and price <= MAX_PRICE:
                ev = getattr(r, p_col) * price - 1
                if ev > best_ev:
                    best_ev, pick = ev, col
        if pick and best_ev > MAX_PLAUSIBLE_EV:
            probable_errors.append({"Competition": r.Competition, "Date": r.Date, "Match": f"{r.Home} v {r.Away}", "Pick": {"H": "Home", "D": "Draw", "A": "Away"}[pick],
                                    "Model": float(getattr(r, {"H": "pH", "D": "pD", "A": "pA"}[pick])), "Price": float(getattr(r, f"best{pick}")), "EV": float(best_ev)})
            continue
        if pick and best_ev >= EV_MIN:
            new_bets.append({"Logged": TODAY.strftime("%Y-%m-%d"), "Competition": r.Competition, "Group": r.Group, "Date": r.Date, "Home": r.Home, "Away": r.Away,
                             "Pick": {"H": "Home", "D": "Draw", "A": "Away"}[pick], "Price": getattr(r, f"best{pick}"), "Bookmaker": getattr(r, f"bestBook{pick}"),
                             "ModelProb": getattr(r, {"H": "pH", "D": "pD", "A": "pA"}[pick]), "EV": best_ev, "PinnacleAtBet": getattr(r, f"pin{pick}"), "bsd_id": r.bsd_id})
    if new_bets:
        nb = pd.DataFrame(new_bets)
        ledger = pd.concat([ledger, nb], ignore_index=True).drop_duplicates(subset=["Competition", "Date", "Home", "Away"], keep="first")
    print(f"Paper ledger: {len(new_bets)} value bets found today (expected value {100 * EV_MIN:.0f}% to {100 * MAX_PLAUSIBLE_EV:.0f}% at the best price); "
          f"{len(ledger)} recorded in total.")
    if probable_errors:
        print(f"  {len(probable_errors)} 'edges' above +{100 * MAX_PLAUSIBLE_EV:.0f}% were NOT logged: implausibly large disagreements with the market, almost always the model "
              f"missing something (a form slump, a squad change) or occasionally a data problem. Worth a look:")
        for e_ in probable_errors[:10]:
            print(f"    {e_['Match']} ({e_['Competition']}, {e_['Date']}): {e_['Pick']} at {e_['Price']:.2f}, model {100 * e_['Model']:.0f}% -> +{100 * e_['EV']:.0f}%")

# ---------- 3. settle the ledger: results, profit, and closing-line value vs Pinnacle ----------
if len(ledger):
    res_parts = [all_matches.rename(columns={"League": "Competition"})] + [info["data"].rename(columns={"League": "Competition"}) for info in SOLO.values()]
    if len(euro):
        res_parts.append(euro)
    res_all = pd.concat([p_[["Competition", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]] for p_ in res_parts], ignore_index=True)
    res_all["Date"] = pd.to_datetime(res_all["Date"]).dt.strftime("%Y-%m-%d")
    LEDG = ledger.drop(columns=[c for c in ["FTHG", "FTAG", "Won", "Profit", "PinnacleClose", "CLV"] if c in ledger]).merge(
        res_all.rename(columns={"HomeTeam": "Home", "AwayTeam": "Away"}), on=["Competition", "Date", "Home", "Away"], how="left")
    arch = pd.read_csv(ARCH_PATH) if os.path.exists(ARCH_PATH) else pd.DataFrame()
    for c_ in ["bestH", "bestD", "bestA", "pinH", "pinD", "pinA"]:
        if c_ in arch:
            arch[c_] = pd.to_numeric(arch[c_], errors="coerce")
    closes = {}
    if len(arch):
        arch = arch.sort_values("snapshot")
        for key_, g_ in arch.groupby(["Competition", "Date", "Home", "Away"]):
            closes[key_] = g_.iloc[-1]                     # the last price we saw before kickoff
    won_v, profit_v, pclose_v, clv_v = [], [], [], []
    for r in LEDG.itertuples():
        if pd.isna(r.FTHG):
            won_v.append(np.nan); profit_v.append(np.nan)
        else:
            res_ = "Home" if r.FTHG > r.FTAG else ("Draw" if r.FTHG == r.FTAG else "Away")
            w_ = res_ == r.Pick
            won_v.append(float(w_)); profit_v.append(r.Price - 1 if w_ else -1.0)
        c_ = closes.get((r.Competition, r.Date, r.Home, r.Away)) if pd.Timestamp(r.Date) < TODAY else None   # closing price only once kicked off
        col = {"Home": "H", "Draw": "D", "Away": "A"}[r.Pick]
        if c_ is not None and pd.notna(c_.get(f"pin{col}")) and all(pd.notna(c_.get(f"pin{x}")) for x in "HDA"):
            fair = (1 / c_[f"pin{col}"]) / sum(1 / c_[f"pin{x}"] for x in "HDA")      # Pinnacle's closing chance, margin removed
            pclose_v.append(float(c_[f"pin{col}"])); clv_v.append(r.Price * fair - 1)
        else:
            pclose_v.append(np.nan); clv_v.append(np.nan)
    LEDG["Won"], LEDG["Profit"], LEDG["PinnacleClose"], LEDG["CLV"] = won_v, profit_v, pclose_v, clv_v
    ledger = LEDG
    ledger.to_csv(LEDGER_PATH, index=False)
    st = ledger.dropna(subset=["Profit"])
    ledger_summary = {"bets": int(len(ledger)), "settled": int(len(st)), "open": int(ledger["Profit"].isna().sum()),
                      "staked": float(len(st)), "profit": float(st["Profit"].sum()) if len(st) else 0.0,
                      "roi": float(100 * st["Profit"].mean()) if len(st) else None,
                      "clv": float(100 * ledger["CLV"].mean()) if ledger["CLV"].notna().any() else None,
                      "beat_close": float(100 * (ledger["CLV"].dropna() > 0).mean()) if ledger["CLV"].notna().any() else None,
                      "clv_n": int(ledger["CLV"].notna().sum())}
    ledger_open = json.loads(ledger[ledger["Profit"].isna()].sort_values("Date").head(40).to_json(orient="records"))
    ledger_settled = json.loads(ledger.dropna(subset=["Profit"]).sort_values("Date", ascending=False).head(40).to_json(orient="records"))
    print(f"Ledger so far: {ledger_summary['settled']} settled bets, profit {ledger_summary['profit']:+.2f} units"
          + (f" (ROI {ledger_summary['roi']:+.1f}%)" if ledger_summary["roi"] is not None else "")
          + (f"; average closing-line value vs Pinnacle {ledger_summary['clv']:+.1f}% on {ledger_summary['clv_n']} bets" if ledger_summary["clv"] is not None else "")
          + ". Hundreds of bets are needed before any of this means much.")

# ---------- 4. edge search on this season's replayed predictions (main leagues, football-data prices) ----------
if RUN_BACKTEST and bt_scored is not None and len(bt_scored):
    # best price before the match: best across bookmakers, else average, else Bet365.
    # closing benchmark: Pinnacle's close, else the average closing price, else Bet365's close.
    am = all_matches.copy()
    def first_of(cols3):
        out_ = pd.DataFrame(index=am.index, columns=["H", "D", "A"], dtype=float)
        used_ = pd.Series("", index=am.index)
        for name_, (h_, d_, a_) in cols3:
            if all(c in am for c in (h_, d_, a_)):
                ok_ = out_["H"].isna() & am[[h_, d_, a_]].notna().all(axis=1)
                out_.loc[ok_, ["H", "D", "A"]] = am.loc[ok_, [h_, d_, a_]].values
                used_[ok_] = name_
        return out_, used_
    bestp, best_used = first_of([("best", ("MaxH", "MaxD", "MaxA")), ("average", ("AvgH", "AvgD", "AvgA")), ("Bet365", ("B365H", "B365D", "B365A"))])
    closep, close_used = first_of([("Pinnacle", ("PSCH", "PSCD", "PSCA")), ("average closing", ("AvgCH", "AvgCD", "AvgCA")), ("Bet365 closing", ("B365CH", "B365CD", "B365CA"))])
    am[["MaxH", "MaxD", "MaxA"]] = bestp.values
    am[["PSCH", "PSCD", "PSCA"]] = closep.values
    am["_best_src"], am["_close_src"] = best_used.values, close_used.values
    pcols = ["MaxH", "MaxD", "MaxA", "PSCH", "PSCD", "PSCA"]
    if True:
        es = bt_scored[bt_scored["Group"] == "Domestic"].merge(
            am[["League", "Date", "HomeTeam", "AwayTeam", "_best_src", "_close_src"] + pcols].rename(columns={"League": "Competition", "HomeTeam": "Home", "AwayTeam": "Away"}),
            on=["Competition", "Date", "Home", "Away"], how="inner").dropna(subset=pcols).reset_index(drop=True)
        if len(es) >= 200:
            P_ = es[["pH", "pD", "pA"]].values
            best_ = es[["MaxH", "MaxD", "MaxA"]].values
            pin_ = 1 / es[["PSCH", "PSCD", "PSCA"]].values; pin_ = pin_ / pin_.sum(axis=1, keepdims=True)
            ev_ = P_ * best_ - 1
            ev_[best_ > MAX_PRICE] = -1
            k_ = ev_.argmax(axis=1); idx_ = np.arange(len(es))
            es["EV"], es["Price"] = ev_[idx_, k_], best_[idx_, k_]
            es["Prob"], es["CLV"] = P_[idx_, k_], best_[idx_, k_] * pin_[idx_, k_] - 1
            o_ = outcome(es)
            es["Profit"] = np.where(o_ == k_, es["Price"] - 1, -1.0)
            es["Side"] = np.array(["Home", "Draw", "Away"])[k_]
            bets = es[es["EV"] >= EV_MIN].copy()
            mid = es["Date"].quantile(0.5)
            def seg_row(name, sel):
                b_ = bets[sel(bets)]
                d1, d2 = b_[b_["Date"] < mid], b_[b_["Date"] >= mid]
                row_ = {"Segment": name, "Bets (earlier)": len(d1), "ROI % (earlier)": 100 * d1["Profit"].mean() if len(d1) else np.nan,
                        "CLV % (earlier)": 100 * d1["CLV"].mean() if len(d1) else np.nan,
                        "Bets (later)": len(d2), "ROI % (later)": 100 * d2["Profit"].mean() if len(d2) else np.nan,
                        "CLV % (later)": 100 * d2["CLV"].mean() if len(d2) else np.nan}
                verdict = "too few bets"
                if len(d1) >= 25 and len(d2) >= 25:
                    if d1["CLV"].mean() > 0 and d2["CLV"].mean() > 0:
                        r_ = np.random.default_rng(3)
                        pct_ = 100 * (np.array([r_.choice(d2["CLV"].values, len(d2)).mean() for _ in range(2000)]) > 0).mean()
                        verdict = "CONFIRMED" if pct_ >= 95 else "promising, not confirmed"
                    else:
                        verdict = "no edge"
                row_["Verdict"] = verdict
                return row_
            segs = [("All value bets", lambda b: b["EV"] > -9)]
            segs += [(f"League: {lg}", (lambda lg_: lambda b: b["Competition"] == lg_)(lg)) for lg in sorted(bets["Competition"].unique())]
            segs += [("Favourites (model 50%+)", lambda b: b["Prob"] >= 0.5), ("Outsiders (model under 35%)", lambda b: b["Prob"] < 0.35),
                     ("Draws", lambda b: b["Side"] == "Draw"), ("Expected value 3-6%", lambda b: b["EV"] < 0.06),
                     ("Expected value 6-10%", lambda b: (b["EV"] >= 0.06) & (b["EV"] < 0.10)), ("Expected value 10%+", lambda b: b["EV"] >= 0.10)]
            if "Note" in bets:
                segs.append(("Promoted teams involved", lambda b: b["Note"].astype(str).str.contains("New to the league")))
            edge_rows = json.loads(pd.DataFrame([seg_row(n_, f_) for n_, f_ in segs]).to_json(orient="records"))
            src_b, src_c = es["_best_src"].value_counts().to_dict(), es["_close_src"].value_counts().to_dict()
            print(f"\nEdge search on this season's replayed domestic matches ({len(es)} with prices; {len(bets)} value bets).")
            print(f"  Prices taken: {src_b}. Closing benchmark: {src_c}.")
            print("Each segment is checked on the EARLIER half of the season and confirmed on the LATER half. CLV = closing-line value vs Pinnacle.")
            display(pd.DataFrame(edge_rows).round(1))
            conf = [r_["Segment"] for r_ in edge_rows if r_["Verdict"] == "CONFIRMED"]
            print("Confirmed edges: " + (", ".join(conf) if conf else "none yet."))
        else:
            print(f"Edge search: only {len(es)} replayed matches have usable prices so far; it needs 200.")



# ---------- 5. the bet check: every outcome of every priced match, with an evidence-based verdict ----------
# GREEN only where our tests have CONFIRMED an edge for that kind of bet; YELLOW = the model sees value but it's unproven;
# WHITE = no value at the best price. Information for your own decisions, not financial advice.
BANKROLL = 100.0               # your betting bank in units (used only to size GREEN bets)
MAX_STAKE_SHARE = 0.02         # never more than 2% of the bank on one bet
confirmed_segments = {r_["Segment"] for r_ in (edge_rows or []) if r_.get("Verdict") == "CONFIRMED"}
LC_PATH = f"{SAVE_DIR}/lower_confirmed.json"
confirmed_leagues = set(json.load(open(LC_PATH))) if os.path.exists(LC_PATH) else set()
confirmed_leagues |= {s_.replace("League: ", "") for s_ in confirmed_segments if s_.startswith("League: ")}
BET_CHECK = {}
if len(prices):
    pr2 = prices.merge(upcoming_preds[["Competition", "Date", "Home", "Away", "pH", "pD", "pA"]].assign(Date=lambda x: pd.to_datetime(x["Date"]).dt.strftime("%Y-%m-%d")),
                       on=["Competition", "Date", "Home", "Away"])
    for r in pr2.itertuples():
        rows_ = []
        for col, lab, p_col in [("H", f"{r.Home} win", "pH"), ("D", "Draw", "pD"), ("A", f"{r.Away} win", "pA")]:
            price = getattr(r, f"best{col}", np.nan)
            p_ = getattr(r, p_col)
            if pd.isna(price):
                continue
            ev_ = p_ * price - 1
            if ev_ > MAX_PLAUSIBLE_EV:
                verdict, stake = "implausible", None
            elif ev_ >= EV_MIN and r.Competition in confirmed_leagues:
                kelly = ev_ / (price - 1)
                verdict, stake = "green", round(min(BANKROLL * kelly / 4, BANKROLL * MAX_STAKE_SHARE), 2)
            elif ev_ >= EV_MIN:
                verdict, stake = "yellow", None
            else:
                verdict, stake = "white", None
            rows_.append({"Bet": lab, "Model": float(p_), "Price": float(price), "Bookmaker": getattr(r, f"bestBook{col}", ""), "EV": float(ev_),
                          "Verdict": verdict, "Stake": stake})
        BET_CHECK[(r.Competition, r.Date, r.Home, r.Away)] = rows_
    n_v = pd.Series([x["Verdict"] for v in BET_CHECK.values() for x in v]).value_counts().to_dict()
    print(f"\nBet check on {len(BET_CHECK)} priced matches: {n_v.get('green', 0)} green (confirmed edge), {n_v.get('yellow', 0)} yellow (unproven), "
          f"{n_v.get('white', 0)} white (no value), {n_v.get('implausible', 0)} implausible. Confirmed segments so far: "
          + (", ".join(sorted(confirmed_leagues)) if confirmed_leagues else "none") + ".")
    # which other markets does BSD price? (for goalscorer, totals and both-teams-to-score bet checks later)
    if len(prices):
        mk_ = bsd("/api/odds/", event=int(prices["bsd_id"].iloc[0]))
        if mk_:
            BSD_MARKETS = sorted({str(o_.get("market")) for o_ in mk_.get("odds", [])})
            print("  Markets BSD prices for that match:", ", ".join(BSD_MARKETS))

# ---------- 6. over/under 2.5 and Asian handicap: tested against real prices (v24) ----------
# The over/under model had a small edge on hit rate; here it faces actual prices: value bets at the best price, closing-line value,
# earlier half vs later half, exactly like the match-result edge search. Asian handicap cover chances come from the score grid.
ou_ah_rows = []
def ah_profit(margin, line, odds):
    """Profit per unit on an Asian handicap bet for a given goal margin (backed side's goals minus opponent's) and line; quarter lines split."""
    if abs((line * 4) % 2) == 1:                     # quarter line, e.g. -0.75 = half on -0.5, half on -1
        return 0.5 * ah_profit(margin, line - 0.25, odds) + 0.5 * ah_profit(margin, line + 0.25, odds)
    r = margin + line
    return (odds - 1) if r > 0 else (0.0 if r == 0 else -1.0)
if RUN_BACKTEST and bt_scored is not None and len(bt_scored) and all(c_ in all_matches for c_ in ["Max>2.5", "AHh"]):
    oa = bt_scored[bt_scored["Group"] == "Domestic"].merge(all_matches[["League", "Date", "HomeTeam", "AwayTeam"] + OU_AH_COLS].rename(
        columns={"League": "Competition", "HomeTeam": "Home", "AwayTeam": "Away"}), on=["Competition", "Date", "Home", "Away"], how="inner").reset_index(drop=True)
    def first_avail(df, pairs):
        out_ = np.full((len(df), 2), np.nan)
        for a_, b_ in pairs:
            if a_ in df and b_ in df:
                ok_ = np.isnan(out_).any(axis=1) & df[a_].notna().values & df[b_].notna().values
                out_[ok_] = df.loc[ok_, [a_, b_]].values
        return out_
    best_ou = first_avail(oa, [("Max>2.5", "Max<2.5"), ("Avg>2.5", "Avg<2.5"), ("B365>2.5", "B365<2.5")])
    close_ou = first_avail(oa, [("PC>2.5", "PC<2.5"), ("AvgC>2.5", "AvgC<2.5"), ("B365C>2.5", "B365C<2.5")])
    mid_ = oa["Date"].quantile(0.5)
    def segment(name, df, ev, price, fair_close, won=None, profit=None):
        prof_ = np.asarray(profit, float) if profit is not None else np.where(won, price - 1, -1.0)     # exact amounts (half wins, pushes)
        bets_ = df.assign(EV=ev, Price=price, CLV=price * fair_close - 1, Profit=prof_)
        bets_ = bets_[(bets_["EV"] >= EV_MIN) & (bets_["EV"] <= MAX_PLAUSIBLE_EV)].dropna(subset=["CLV"])
        d1, d2 = bets_[bets_["Date"] < mid_], bets_[bets_["Date"] >= mid_]
        verdict = "too few bets"
        if len(d1) >= 25 and len(d2) >= 25:
            if d1["CLV"].mean() > 0 and d2["CLV"].mean() > 0:
                r_ = np.random.default_rng(6)
                pct_ = 100 * (np.array([r_.choice(d2["CLV"].values, len(d2)).mean() for _ in range(2000)]) > 0).mean()
                verdict = "CONFIRMED" if pct_ >= 95 else "promising, not confirmed"
            else:
                verdict = "no edge"
        return {"Market": name, "Bets (earlier)": len(d1), "CLV % (earlier)": 100 * d1["CLV"].mean() if len(d1) else np.nan,
                "ROI % (earlier)": 100 * d1["Profit"].mean() if len(d1) else np.nan, "Bets (later)": len(d2),
                "CLV % (later)": 100 * d2["CLV"].mean() if len(d2) else np.nan, "ROI % (later)": 100 * d2["Profit"].mean() if len(d2) else np.nan, "Verdict": verdict}
    if "pOver25" in oa and oa["pOver25"].notna().any():
        po = oa["pOver25"].values
        fair_c = 1 / close_ou; fair_c = fair_c / fair_c.sum(axis=1, keepdims=True)
        goals_ = (oa["FTHG"] + oa["FTAG"]).values
        ou_ah_rows.append(segment("Over 2.5 goals", oa, po * best_ou[:, 0] - 1, best_ou[:, 0], fair_c[:, 0], goals_ > 2.5))
        ou_ah_rows.append(segment("Under 2.5 goals", oa, (1 - po) * best_ou[:, 1] - 1, best_ou[:, 1], fair_c[:, 1], goals_ < 2.5))
    # Asian handicap: cover probabilities from each match's score grid, at the early line (AHh); CLV only when the closing line is the same
    best_ah = first_avail(oa, [("MaxAHH", "MaxAHA"), ("AvgAHH", "AvgAHA"), ("B365AHH", "B365AHA")])
    close_ah = first_avail(oa, [("PCAHH", "PCAHA"), ("AvgCAHH", "AvgCAHA"), ("B365CAHH", "B365CAHA")])
    evh, eva, fch, fca, pr_h, pr_a = [], [], [], [], [], []
    for i_, r_ in enumerate(oa.itertuples()):
        line_ = getattr(r_, "AHh", np.nan)
        if pd.isna(line_) or np.isnan(best_ah[i_]).any():
            evh.append(np.nan); eva.append(np.nan); fch.append(np.nan); fca.append(np.nan); pr_h.append(np.nan); pr_a.append(np.nan); continue
        g_ = score_grid(r_.ExpHome, r_.ExpAway, r_.pH, r_.pD, r_.pA); g_ = g_ / g_.sum()
        hh, aa = np.indices(g_.shape)
        mrg = (hh - aa).ravel(); pg = g_.ravel()
        evh.append(float(sum(p_ * ah_profit(m_, line_, best_ah[i_, 0]) for m_, p_ in zip(mrg, pg) if p_ > 1e-6)))
        eva.append(float(sum(p_ * ah_profit(-m_, -line_, best_ah[i_, 1]) for m_, p_ in zip(mrg, pg) if p_ > 1e-6)))
        same_line = pd.notna(getattr(r_, "AHCh", np.nan)) and float(r_.AHCh) == float(line_) and not np.isnan(close_ah[i_]).any()
        if same_line:
            fc_ = (1 / close_ah[i_]) / (1 / close_ah[i_]).sum()
            fch.append(fc_[0]); fca.append(fc_[1])
        else:
            fch.append(np.nan); fca.append(np.nan)
        pr_h.append(ah_profit(r_.FTHG - r_.FTAG, line_, best_ah[i_, 0])); pr_a.append(ah_profit(r_.FTAG - r_.FTHG, -line_, best_ah[i_, 1]))
    for side_, ev_, fc_, prof_, col_ in [("Asian handicap: home side", evh, fch, pr_h, 0), ("Asian handicap: away side", eva, fca, pr_a, 1)]:
        seg_ = segment(side_, oa, np.array(ev_, float), best_ah[:, col_], np.array(fc_, float), profit=np.array(prof_, float))
        ou_ah_rows.append(seg_)
    print("\nOver/under 2.5 and Asian handicap, value bets at the best price (earlier half, then confirmed on the later half; CLV vs closing prices):")
    display(pd.DataFrame(ou_ah_rows).round(2))
    EXTRA_TABLES_EARLY = list(globals().get("EXTRA_TABLES_EARLY", [])) + [{"title": "Over/under 2.5 and Asian handicap against real prices",
        "hint": "The model's value bets in these markets at the best price, with closing-line value; only CONFIRMED counts.", "rows": json.loads(pd.DataFrame(ou_ah_rows).to_json(orient="records"))}]
