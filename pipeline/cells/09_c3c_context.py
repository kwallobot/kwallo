# ===================== 2c. GOAL LEVEL AND REST DAYS =====================
# Two candidate adjustments, each tested on honest week-by-week predictions and switched on only if it helps
# in at least 95% of reshuffles:
#  - goal level: if a league's recent matches have produced more (or fewer) goals than predicted, scale expected goals
#  - rest days: a team that played within 3 days before, or plays again within 3 days after, may be weaker
CTX_PATH = f"{SAVE_DIR}/context_adjustments.json"
CONTEXT = json.load(open(CTX_PATH)) if os.path.exists(CTX_PATH) else {"drift": False, "rest": None}

# every team's match dates: results everywhere we have them, plus scheduled fixtures
_parts = [all_matches[["Date", "HomeTeam", "AwayTeam"]], extra_matches[["Date", "HomeTeam", "AwayTeam"]]] + \
         [info["data"][["Date", "HomeTeam", "AwayTeam"]] for info in SOLO.values()]
if len(euro): _parts.append(euro[["Date", "HomeTeam", "AwayTeam"]])
if len(other_dom): _parts.append(other_dom[["Date", "HomeTeam", "AwayTeam"]])
if len(espn_schedule): _parts.append(espn_schedule.rename(columns={"Home": "HomeTeam", "Away": "AwayTeam"})[["Date", "HomeTeam", "AwayTeam"]])
if "cup_results" in globals() and len(cup_results): _parts.append(cup_results[["Date", "HomeTeam", "AwayTeam"]])      # v21: domestic cups
_td = pd.concat(_parts, ignore_index=True)
_td["Date"] = pd.to_datetime(_td["Date"]).dt.normalize()
_long = pd.concat([_td[["Date", "HomeTeam"]].rename(columns={"HomeTeam": "Team"}), _td[["Date", "AwayTeam"]].rename(columns={"AwayTeam": "Team"})])
TEAM_DATES = {t: np.unique(g["Date"].values.astype("datetime64[D]")) for t, g in _long.groupby("Team")}

def rest_flags(df):
    """1 if the team played within 3 days before / plays again within 3 days after (home and away)."""
    out = {}
    dates = pd.to_datetime(df["Date"]).values.astype("datetime64[D]")
    for side, col in [("h", "HomeTeam"), ("a", "AwayTeam")]:
        before, after = np.zeros(len(df)), np.zeros(len(df))
        for i, (t, d) in enumerate(zip(df[col].values, dates)):
            arr = TEAM_DATES.get(t)
            if arr is None:
                continue
            k = np.searchsorted(arr, d)
            if k > 0 and (d - arr[k - 1]).astype(int) <= 3:
                before[i] = 1
            k2 = np.searchsorted(arr, d, side="right")
            if k2 < len(arr) and (arr[k2] - d).astype(int) <= 3:
                after[i] = 1
        out[f"{side}_rest_before"], out[f"{side}_rest_after"] = before, after
    return out

def goal_level(league, before, base_rows):
    """How many more goals than predicted this league has produced in the 60 days before `before` (shrunk toward 1)."""
    b_ = base_rows[(base_rows["League"] == league) & (base_rows["Date"] < before) & (base_rows["Date"] >= before - pd.Timedelta(days=60))]
    if len(b_) < 30:
        return 1.0
    ratio = (b_["FTHG"] + b_["FTAG"]).sum() / (b_["ExpHome"] + b_["ExpAway"]).sum()
    w_ = len(b_) / (len(b_) + 100)
    return float(np.clip(1 + w_ * (ratio - 1), 0.85, 1.15))

def context_multipliers(games):
    """Scale factors for home and away expected goals from the adjustments that passed their tests."""
    fh, fa = np.ones(len(games)), np.ones(len(games))
    if CONTEXT.get("drift") and "base" in globals() and len(base):
        wk = pd.to_datetime(games["Date"]).min()
        wk = wk - pd.Timedelta(days=wk.weekday())
        f_ = np.array([goal_level(l_, wk, base) for l_ in games["League"]])
        fh, fa = fh * f_, fa * f_
    r_ = CONTEXT.get("rest")
    if r_:
        rf = rest_flags(games)
        fh = fh * np.exp(r_["own_before"] * rf["h_rest_before"] + r_["own_after"] * rf["h_rest_after"] + r_["opp_before"] * rf["a_rest_before"] + r_["opp_after"] * rf["a_rest_after"])
        fa = fa * np.exp(r_["own_before"] * rf["a_rest_before"] + r_["own_after"] * rf["a_rest_after"] + r_["opp_before"] * rf["h_rest_before"] + r_["opp_after"] * rf["h_rest_after"])
    return fh, fa

if TEST_GOAL_LEVEL_AND_REST and "base" in globals() and len(base):
    rng_k = np.random.default_rng(0)
    share = lambda d_: 100 * (np.array([rng_k.choice(d_, len(d_)).mean() for _ in range(2000)]) < 0).mean()
    def probs_rho(df, h, a):
        p = np.zeros((len(df), 3))
        for r_v in np.unique(df["rho"].values):
            idx = np.where(df["rho"].values == r_v)[0]
            p[idx] = outcome_probs(h[idx], a[idx], r_v)
        return p
    bb = base.dropna(subset=["ExpHome", "ExpAway", "rho"]).sort_values("Date").reset_index(drop=True)
    o_ = outcome(bb)
    goals = (bb["FTHG"] + bb["FTAG"]).values
    new_ctx = {"drift": False, "rest": None}

    # goal level: test on every week that has 60 days of earlier predictions
    wk = bb["Date"] - pd.to_timedelta(bb["Date"].dt.weekday, unit="D")
    f_ = np.array([goal_level(l_, w_, bb) for l_, w_ in zip(bb["League"], wk)])
    test = f_ != 1.0
    if test.sum() >= 200:
        h0, a0 = bb["ExpHome"].values, bb["ExpAway"].values
        ll0 = -np.log(probs_rho(bb, h0, a0)[np.arange(len(bb)), o_])
        ll1 = -np.log(probs_rho(bb, h0 * f_, a0 * f_)[np.arange(len(bb)), o_])
        ov0 = 1 - poisson.cdf(2, h0 + a0); ov1 = 1 - poisson.cdf(2, (h0 + a0) * f_)
        y_ = goals > 2.5
        oll0 = -np.log(np.where(y_, ov0, 1 - ov0)); oll1 = -np.log(np.where(y_, ov1, 1 - ov1))
        p1, p2 = share((ll1 - ll0)[test]), share((oll1 - oll0)[test])
        print(f"Goal level, tested on {test.sum()} matches: win/draw/loss log loss {np.mean((ll1 - ll0)[test]):+.4f} (better in {p1:.0f}% of reshuffles); "
              f"over 2.5 log loss {np.mean((oll1 - oll0)[test]):+.4f} (better in {p2:.0f}%).")
        new_ctx["drift"] = bool((p1 >= 95 and np.mean((oll1 - oll0)[test]) <= 0) or (p2 >= 95 and np.mean((ll1 - ll0)[test]) <= 0))

    # rest days: learn on earlier seasons, test on this one
    rf = rest_flags(bb)
    season_start = all_matches.loc[all_matches["Season"] == SEASONS[-1], "Date"].min()
    long_ = pd.concat([pd.DataFrame({"goals": bb["FTHG"], "offset": np.log(bb["ExpHome"]), "own_before": rf["h_rest_before"], "own_after": rf["h_rest_after"],
                                     "opp_before": rf["a_rest_before"], "opp_after": rf["a_rest_after"], "Date": bb["Date"]}),
                       pd.DataFrame({"goals": bb["FTAG"], "offset": np.log(bb["ExpAway"]), "own_before": rf["a_rest_before"], "own_after": rf["a_rest_after"],
                                     "opp_before": rf["h_rest_before"], "opp_after": rf["h_rest_after"], "Date": bb["Date"]})], ignore_index=True)
    feats_r = ["own_before", "own_after", "opp_before", "opp_after"]
    tr_ = long_[long_["Date"] < season_start]
    if len(tr_) > 1000 and tr_[feats_r].sum().min() > 20:
        params_r = sm.GLM(tr_["goals"], tr_[feats_r], family=sm.families.Poisson(), offset=tr_["offset"]).fit().params
        te = (bb["Date"] >= season_start).values
        if te.sum() >= 100:
            CONTEXT_try = {k: float(params_r[k]) for k in feats_r}
            fh_ = np.exp(CONTEXT_try["own_before"] * rf["h_rest_before"] + CONTEXT_try["own_after"] * rf["h_rest_after"] + CONTEXT_try["opp_before"] * rf["a_rest_before"] + CONTEXT_try["opp_after"] * rf["a_rest_after"])
            fa_ = np.exp(CONTEXT_try["own_before"] * rf["a_rest_before"] + CONTEXT_try["own_after"] * rf["a_rest_after"] + CONTEXT_try["opp_before"] * rf["h_rest_before"] + CONTEXT_try["opp_after"] * rf["h_rest_after"])
            h0, a0 = bb["ExpHome"].values, bb["ExpAway"].values
            ll0 = -np.log(probs_rho(bb, h0, a0)[np.arange(len(bb)), o_])
            ll1 = -np.log(probs_rho(bb, h0 * fh_, a0 * fa_)[np.arange(len(bb)), o_])
            d_ = (ll1 - ll0)[te]
            pct = share(d_)
            eff = {k: f"{100 * (np.exp(v) - 1):+.1f}%" for k, v in CONTEXT_try.items()}
            print(f"Rest days (learned before this season, tested on {te.sum()} matches this season): log loss {d_.mean():+.4f}, better in {pct:.0f}% of reshuffles.")
            print("  Effect on a team's expected goals:", ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in eff.items()))
            if pct >= 95 and d_.mean() < 0:
                full = sm.GLM(long_["goals"], long_[feats_r], family=sm.families.Poisson(), offset=long_["offset"]).fit().params
                new_ctx["rest"] = {k: float(full[k]) for k in feats_r}
    CONTEXT = new_ctx
    json.dump(CONTEXT, open(CTX_PATH, "w"))
    print(f"Goal-level adjustment: {'ON' if CONTEXT['drift'] else 'off'}. Rest-days adjustment: {'ON' if CONTEXT['rest'] else 'off'}.")
else:
    print(f"Goal-level adjustment: {'ON' if CONTEXT.get('drift') else 'off'}. Rest-days adjustment: {'ON' if CONTEXT.get('rest') else 'off'} (not retested this run).")
health("Goal level / rest days", True, f"goal level {'on' if CONTEXT.get('drift') else 'off'}, rest days {'on' if CONTEXT.get('rest') else 'off'}")
