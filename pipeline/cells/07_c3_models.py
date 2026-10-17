# ===================== 2. MODEL COMMANDS (no need to edit) =====================
def outcome(df):
    return np.select([df["FTHG"] > df["FTAG"], df["FTHG"] == df["FTAG"]], [0, 1], 2)

def make_X(teams, opps, home, cols=None):
    X = pd.get_dummies(pd.DataFrame({"team": teams, "opponent": opps}), dtype=float)
    X["home"] = home * 10
    return X if cols is None else X.reindex(columns=cols, fill_value=0.0)

def fit_weighted(df, home_col, away_col, alpha, half_life=None):
    teams = np.r_[df["HomeTeam"].values, df["AwayTeam"].values]
    opps = np.r_[df["AwayTeam"].values, df["HomeTeam"].values]
    home = np.r_[np.ones(len(df)), np.zeros(len(df))]
    y = np.r_[df[home_col].values, df[away_col].values].astype(float)
    days = (df["Date"].max() - df["Date"]).dt.days.values
    w = 0.5 ** (days / half_life) if half_life else np.ones(len(df))
    X = make_X(teams, opps, home)
    m = PoissonRegressor(alpha=alpha, max_iter=1000).fit(X, y, sample_weight=np.r_[w, w])
    m.cols = X.columns
    return m

def shrunk_means(m, df):
    n = len(df)
    h = m.predict(make_X(df["HomeTeam"].values, df["AwayTeam"].values, np.ones(n), m.cols))
    a = m.predict(make_X(df["AwayTeam"].values, df["HomeTeam"].values, np.zeros(n), m.cols))
    return h, a

def estimate_rho_ha(h, a, df):
    x, y = df["FTHG"].values, df["FTAG"].values
    m00, m01, m10, m11 = (x == 0) & (y == 0), (x == 0) & (y == 1), (x == 1) & (y == 0), (x == 1) & (y == 1)
    best_rho, best_score = 0, -np.inf
    for rho in np.linspace(-0.25, 0.25, 501):
        t = np.concatenate([1 - h[m00] * a[m00] * rho, 1 + h[m01] * rho, 1 + a[m10] * rho, np.full(m11.sum(), 1 - rho)])
        if (t > 0).all() and np.log(t).sum() > best_score:
            best_rho, best_score = rho, np.log(t).sum()
    return best_rho

def outcome_probs(h, a, rho):
    probs = []
    for hi, ai in zip(h, a):
        g = np.outer(poisson.pmf(range(11), hi), poisson.pmf(range(11), ai))
        g[0, 0] *= 1 - hi * ai * rho; g[0, 1] *= 1 + hi * rho; g[1, 0] *= 1 + ai * rho; g[1, 1] *= 1 - rho
        probs.append([np.tril(g, -1).sum(), np.trace(g), np.triu(g, 1).sum()])
    p = np.array(probs).reshape(-1, 3)
    return p / p.sum(axis=1, keepdims=True)

def over_prob(mu, k, line):
    if k > 1:
        return 1 - nbinom.cdf(int(line), mu / (k - 1), 1 / k)
    return 1 - poisson.cdf(int(line), mu)

def fit_total(lg, hc, ac, alpha):
    d = lg.dropna(subset=[hc, ac])
    m = fit_weighted(d, hc, ac, alpha)
    h, a = shrunk_means(m, d)
    k = np.mean(((d[hc] + d[ac]).values - (h + a)) ** 2) / np.mean(h + a)
    return m, k

def book_probs(df):
    o = df[ODDS].astype(float).values
    p = 1 / o
    return p / p.sum(axis=1, keepdims=True)

# ---------- cross-league model for European matches ----------
def prep_cross(dom, eu):
    d = pd.DataFrame({"Date": dom["Date"].values, "Home": dom["HomeTeam"].values, "Away": dom["AwayTeam"].values,
                      "HomeLg": dom["League"].values, "AwayLg": dom["League"].values, "Comp": dom["League"].values,
                      "FTHG": dom["FTHG"].values, "FTAG": dom["FTAG"].values,
                      "YH": (dom["YH"] if "YH" in dom else dom["FTHG"]).values, "YA": (dom["YA"] if "YA" in dom else dom["FTAG"]).values})
    e = pd.DataFrame({"Date": eu["Date"].values, "Home": eu["HomeTeam"].values, "Away": eu["AwayTeam"].values,
                      "HomeLg": np.where(eu["HomeLeague"] == "Other", "Other-" + eu["HomeCountry"].astype(str), eu["HomeLeague"]),
                      "AwayLg": np.where(eu["AwayLeague"] == "Other", "Other-" + eu["AwayCountry"].astype(str), eu["AwayLeague"]),
                      "Comp": "Europe", "FTHG": eu["FTHG"].values, "FTAG": eu["FTAG"].values,
                      "YH": eu["FTHG"].values, "YA": eu["FTAG"].values})
    x = pd.concat([d, e], ignore_index=True)
    x["HomeID"] = x["HomeLg"] + "|" + x["Home"]
    x["AwayID"] = x["AwayLg"] + "|" + x["Away"]
    return x.sort_values("Date").reset_index(drop=True)

def cross_features(x):
    n = len(x)
    r = np.arange(2 * n)
    att_lg = pd.Series(np.r_[x["HomeLg"].values, x["AwayLg"].values]).astype(str)
    def_lg = pd.Series(np.r_[x["AwayLg"].values, x["HomeLg"].values]).astype(str)
    oa, od = att_lg.str.startswith("Other-").values, def_lg.str.startswith("Other-").values
    parts = [
        (r, "A:" + pd.Series(np.r_[x["HomeID"].values, x["AwayID"].values]).astype(str), np.ones(2 * n)),
        (r, "D:" + pd.Series(np.r_[x["AwayID"].values, x["HomeID"].values]).astype(str), np.ones(2 * n)),
        (r, "LA:" + att_lg, np.where(oa, 1.0, 10.0)),
        (r, "LD:" + def_lg, np.where(od, 1.0, 10.0)),
        (np.arange(n), "H:" + pd.Series(x["Comp"].values).astype(str), np.full(n, 10.0)),
        (r[oa], pd.Series(["LA:Other"] * int(oa.sum()), dtype=object), np.full(int(oa.sum()), 10.0)),
        (r[od], pd.Series(["LD:Other"] * int(od.sum()), dtype=object), np.full(int(od.sum()), 10.0)),
    ]
    rows = np.concatenate([p[0] for p in parts])
    keys = np.concatenate([np.asarray(p[1].values, dtype=object) for p in parts])
    vals = np.concatenate([p[2] for p in parts])
    return rows, keys, vals

def fit_cross(x, alpha=0.01, half_life=365, euro_weight=1.0):
    rows, keys, vals = cross_features(x)
    vocab = {k: i for i, k in enumerate(pd.unique(keys))}
    cols = np.array([vocab[k] for k in keys])
    X = sparse.csr_matrix((vals, (rows, cols)), shape=(2 * len(x), len(vocab)))
    y = np.r_[x["YH"].values, x["YA"].values].astype(float)
    days = (x["Date"].max() - x["Date"]).dt.days.values
    w = 0.5 ** (days / half_life) if half_life else np.ones(len(x))
    w = w * np.where(x["Comp"].values == "Europe", euro_weight, 1.0)
    m = PoissonRegressor(alpha=alpha, max_iter=1000).fit(X, y, sample_weight=np.r_[w, w])
    m.vocab = vocab
    return m

def cross_means(m, x):
    rows, keys, vals = cross_features(x)
    keep = np.array([k in m.vocab for k in keys])
    cols = np.array([m.vocab[k] for k in keys[keep]], dtype=int)
    X = sparse.csr_matrix((vals[keep], (rows[keep], cols)), shape=(2 * len(x), len(m.vocab)))
    mu = m.predict(X)
    return mu[:len(x)], mu[len(x):]

print("Model commands ready.")

def with_xg(dom, weight):
    """Domestic matches with YH/YA = mix of goals and Understat expected goals (big five leagues only)."""
    d = dom.copy()
    d["YH"], d["YA"] = d["FTHG"].astype(float), d["FTAG"].astype(float)
    if weight <= 0 or "xg" not in globals() or not len(xg):
        return d
    m = d.merge(xg[["League", "Season", "HomeTeam", "AwayTeam", "xGH", "xGA"]].drop_duplicates(["League", "Season", "HomeTeam", "AwayTeam"]),
                on=["League", "Season", "HomeTeam", "AwayTeam"], how="left")
    d["YH"] = ((1 - weight) * m["FTHG"] + weight * m["xGH"].fillna(m["FTHG"])).values
    d["YA"] = ((1 - weight) * m["FTAG"] + weight * m["xGA"].fillna(m["FTAG"])).values
    return d

def calibrate_full(p, temperature=1.0, draw=1.0):
    """Temperature (T > 1 = more cautious, T < 1 = bolder), then scale the draw chance; rows sum to 1."""
    q = np.power(np.clip(np.asarray(p, dtype=float), 1e-9, 1), 1.0 / temperature)
    q = q / q.sum(axis=1, keepdims=True)
    q[:, 1] *= draw
    return q / q.sum(axis=1, keepdims=True)

BLEND_PATH = f"{SAVE_DIR}/blend.json"
BLEND = json.load(open(BLEND_PATH)) if os.path.exists(BLEND_PATH) else {}

def add_blend(t, group):
    """Model + market blend as a separate track (pBH/pBD/pBA), using the weight learned for this group."""
    w = BLEND.get(group, {}).get("w")
    if w is None or "bookH" not in t:
        return t
    P, B = t[["pH", "pD", "pA"]].values, t[["bookH", "bookD", "bookA"]].values
    mix = w * P + (1 - w) * B
    has = np.isfinite(B).all(axis=1)
    t["pBH"], t["pBD"], t["pBA"] = np.where(has, mix[:, 0], np.nan), np.where(has, mix[:, 1], np.nan), np.where(has, mix[:, 2], np.nan)
    t["BlendW"] = w
    return t

OUTSIDER_PATH = f"{SAVE_DIR}/outsider_adjustment.json"
OUTSIDER = json.load(open(OUTSIDER_PATH)) if os.path.exists(OUTSIDER_PATH) else {"s": 1.0}
def outsider_adjust(p, s_=None):
    """Scale down chances under 35% by s (s = 1 changes nothing), then renormalise. Used only if it passed its test."""
    s_ = OUTSIDER.get("s", 1.0) if s_ is None else s_
    if s_ == 1.0:
        return p
    q = np.asarray(p, dtype=float).copy()
    q = np.where(q < 0.35, q * s_, q)
    return q / q.sum(axis=1, keepdims=True)

XGL_PATH = f"{SAVE_DIR}/xg_leagues.json"
XG_EXTRA_LEAGUES = json.load(open(XGL_PATH)).get("leagues", []) if os.path.exists(XGL_PATH) else []
