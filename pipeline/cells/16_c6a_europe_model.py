# ===================== 4a. EUROPEAN MODEL COMMANDS (no need to edit) =====================
EURO_PRESETS = {"base": {"half_life": 365, "euro_weight": 1.0, "xg_weight": 0.0},
                "xg": {"half_life": 365, "euro_weight": 1.0, "xg_weight": 0.5},
                "half_life_180": {"half_life": 180, "euro_weight": 1.0, "xg_weight": 0.0},
                "europe_x3": {"half_life": 365, "euro_weight": 3.0, "xg_weight": 0.0}}
_ecfg_path = f"{SAVE_DIR}/europe_model_v2.json"
EURO_CHOSEN = json.load(open(_ecfg_path)) if os.path.exists(_ecfg_path) else {"preset": "base", "temperature": 1.0}
if EURO_MODEL != "auto":
    EURO_CHOSEN = {"preset": EURO_MODEL, "temperature": 1.0}

def calibrate(p, temperature):
    """Make probabilities more (T > 1) or less (T < 1) cautious; T = 1 changes nothing."""
    if temperature == 1.0:
        return p
    q = np.power(np.clip(p, 1e-9, 1), 1.0 / temperature)
    return q / q.sum(axis=1, keepdims=True)

def predict_europe(dom, eu, games, quiet=False, preset=None, adjust=None, temperature=None):
    """Fit the cross-league model on domestic + European matches, then predict `games` (European fixtures)."""
    cfg = EURO_PRESETS[preset or EURO_CHOSEN["preset"]]
    temperature = EURO_CHOSEN.get("temperature", 1.0) if temperature is None else temperature
    cross_ = prep_cross(with_xg(dom, cfg["xg_weight"]), eu)
    cm = fit_cross(cross_, half_life=cfg["half_life"], euro_weight=cfg["euro_weight"])
    rho_eu = estimate_rho_ha(*cross_means(cm, cross_), cross_)
    up = games.copy()
    for side in ["Home", "Away"]:
        up[f"{side}Lg"] = np.where(up[f"{side}League"] == "Other", "Other-" + up[f"{side}Country"].astype(str), up[f"{side}League"])
        up[f"{side}ID"] = up[f"{side}Lg"] + "|" + up[f"{side}Team"]
    up = up.rename(columns={"HomeTeam": "Home", "AwayTeam": "Away"}).reset_index(drop=True)
    up["Comp"] = "Europe"
    h, a = cross_means(cm, up)
    fh, fa = adjust(up) if adjust is not None else (np.ones(len(up)), np.ones(len(up)))
    h, a = h * fh, a * fa
    p = calibrate(outcome_probs(h, a, rho_eu), temperature)
    known = lambda ids: ids.map(lambda i: f"A:{i}" in cm.vocab)
    loose = up["HomeLg"].str.startswith("Other-") | up["AwayLg"].str.startswith("Other-")
    no_league = (up["HomeLg"] == "Other-oth") | (up["AwayLg"] == "Other-oth")
    note = pd.Series(np.where(~known(up["HomeID"]) | ~known(up["AwayID"]), "Team not rated yet",
                     np.where(no_league, "Other-country team (European results only)",
                     np.where(loose, "Club from a league we rate from ESPN results only (no lineups)", ""))),
                     index=up.index, dtype=object)
    # Lower-division teams: borrow the ratings of clubs just relegated from that country's top league
    for team, league in LOWER_DIVISION.items():
        mask = ((up["Home"] == team) | (up["Away"] == team)).values
        if not mask.any():
            continue
        lgd = dom[dom["League"] == league]
        seasons = sorted(lgd["Season"].unique())
        if len(seasons) < 2:
            continue
        prev, cur = lgd[lgd["Season"] == seasons[-2]], lgd[lgd["Season"] == seasons[-1]]
        proxies = sorted(set(prev["HomeTeam"]) - set(cur["HomeTeam"]))
        ps, hs, as_ = [], [], []
        for pr in proxies:
            s = up[mask].copy()
            for side in ["Home", "Away"]:
                is_t = s[side] == team
                s.loc[is_t, side] = pr
                s.loc[is_t, f"{side}ID"] = f"{league}|{pr}"
            h_, a_ = cross_means(cm, s)
            ps.append(calibrate(outcome_probs(h_, a_, rho_eu), temperature)); hs.append(h_); as_.append(a_)
        if ps:
            p[mask], h[mask], a[mask] = np.mean(ps, axis=0), np.mean(hs, axis=0), np.mean(as_, axis=0)
            note[mask] = f"{team}: rated like a relegated {league} team"
    out = pd.DataFrame({"Competition": up["Competition"], "Date": pd.to_datetime(up["Date"]).dt.strftime("%Y-%m-%d"),
                        "Home": up["Home"], "Away": up["Away"], "pH": p[:, 0], "pD": p[:, 1], "pA": p[:, 2],
                        "ExpHome": h, "ExpAway": a, "rho": rho_eu, "Note": note.values, "Group": "Europe",
                        "AdjHome": fh, "AdjAway": fa})
    if all(c in up for c in ODDS) and up[ODDS].notna().all(axis=1).any():
        bp = np.full((len(up), 3), np.nan)
        has = up[ODDS].notna().all(axis=1).values
        bp[has] = book_probs(up[has])
        out["bookH"], out["bookD"], out["bookA"] = bp[:, 0], bp[:, 1], bp[:, 2]
    return out

