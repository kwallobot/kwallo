# ===================== 2e. SECOND DIVISIONS: real ratings for promoted teams =====================
# Second-division results (football-data.co.uk) are fitted together with the top division, with a separate level for
# the second division. Teams that moved between the divisions put both on one scale, so a promoted team gets a rating
# carried over from last season. Tested on the first 60 days of each season; switched on only if it passes.
DIV2 = {"E1": ("Premier League", "Championship"), "SP2": ("La Liga", "Segunda Division"), "D2": ("Bundesliga", "2. Bundesliga"),
        "I2": ("Serie A", "Serie B"), "F2": ("Ligue 1", "Ligue 2"), "SC1": ("Scottish Premiership", "Scottish Championship")}
D2_PATH = f"{SAVE_DIR}/second_division.json"
SECOND_DIV = json.load(open(D2_PATH)) if os.path.exists(D2_PATH) else {"on": False}
frames_d2 = []
for code, (top, name) in DIV2.items():
    for season in SEASONS:
        try:
            df = pd.read_csv(f"{DATA_URL}/mmz4281/{season}/{code}.csv", encoding="latin-1", on_bad_lines="skip")
        except Exception:
            continue
        df = clean_cols(df).reindex(columns=["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"])
        df["League"], df["Season"], df["Top"] = name, season, top
        frames_d2.append(df)
div2 = pd.concat(frames_d2, ignore_index=True).dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"]) if frames_d2 else pd.DataFrame()
if len(div2):
    div2["Date"] = pd.to_datetime(div2["Date"], dayfirst=True, format="mixed")
health("Second divisions", len(div2) > 0, f"{len(div2)} matches in {div2['League'].nunique() if len(div2) else 0} leagues")

def fit_two_div(top_data, d2_data, half_life=365, alpha=0.01):
    """Team ratings on one scale across the top and second division (second division gets its own level)."""
    d = pd.concat([top_data.assign(div2=0.0), d2_data.assign(div2=1.0)], ignore_index=True)
    teams = np.r_[d["HomeTeam"].values, d["AwayTeam"].values]
    opps = np.r_[d["AwayTeam"].values, d["HomeTeam"].values]
    home = np.r_[np.ones(len(d)), np.zeros(len(d))]
    X = make_X(teams, opps, home)
    X["div2"] = np.r_[d["div2"].values, d["div2"].values] * 10
    y = np.r_[d["FTHG"].values, d["FTAG"].values].astype(float)
    days = (d["Date"].max() - d["Date"]).dt.days.values
    w = 0.5 ** (days / half_life)
    m = PoissonRegressor(alpha=alpha, max_iter=1000).fit(X, y, sample_weight=np.r_[w, w])
    m.cols = X.columns
    return m

def two_div_means(m, games, level=0.0):
    """Expected goals for `games` played in the top division (level 0) or, v36, in the second division (level 1)."""
    n = len(games)
    Xh = make_X(games["HomeTeam"].values, games["AwayTeam"].values, np.ones(n), [c for c in m.cols if c != "div2"]); Xh["div2"] = 10.0 * level
    Xa = make_X(games["AwayTeam"].values, games["HomeTeam"].values, np.zeros(n), [c for c in m.cols if c != "div2"]); Xa["div2"] = 10.0 * level
    return m.predict(Xh[m.cols]), m.predict(Xa[m.cols])

print(f"Second-division ratings for promoted teams: {'ON' if SECOND_DIV.get('on') else 'off'}.")
