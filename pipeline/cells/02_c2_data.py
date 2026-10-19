# ===================== 1. LOAD DATA =====================
import os, difflib, warnings, time
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.stats import poisson, nbinom
from sklearn.linear_model import PoissonRegressor
warnings.filterwarnings("ignore")
try:
    from google.colab import drive
    drive.mount("/content/drive", timeout_ms=300000)          # v22: 5 minutes, in case Drive is slow to connect
except ImportError:
    pass
os.makedirs(SAVE_DIR, exist_ok=True)
TODAY = pd.Timestamp.today().normalize()
HEALTH = []          # one line per data source, shown at the top of the dashboard
FILE_CHECKS = []
DASH = {}            # v21: results handed to the dashboard here, so no other section can overwrite them by accident
def checked_read(path, text=(), num=(), name=None, **kw):
    """Read a saved file and check it (v20): text columns stay text (no "2526" -> 2526), number columns are numbers.
    Problems are fixed where possible and reported in the health panel instead of surfacing days later."""
    if not os.path.exists(path):
        return pd.DataFrame()
    df_ = pd.read_csv(path, dtype={c: str for c in text}, **kw)
    issues = []
    for c in text:
        if c in df_:
            df_[c] = df_[c].astype(str).str.replace(r"\.0$", "", regex=True).replace({"nan": np.nan})
    for c in num:
        if c in df_:
            before = df_[c].notna().sum()
            df_[c] = pd.to_numeric(df_[c], errors="coerce")
            bad = before - df_[c].notna().sum()
            if bad:
                issues.append(f"{bad} non-numeric values in '{c}' ignored")
    missing = [c for c in list(text) + list(num) if c not in df_]
    if missing:
        issues.append("missing columns: " + ", ".join(missing))
    FILE_CHECKS.append({"file": name or os.path.basename(path), "rows": len(df_), "issues": issues})
    return df_
def health(source, ok, detail):
    HEALTH.append({"source": source, "ok": bool(ok), "detail": str(detail)})

LEAGUES = {"E0": "Premier League", "SP1": "La Liga", "D1": "Bundesliga", "I1": "Serie A", "F1": "Ligue 1",
           "N1": "Eredivisie", "P1": "Primeira Liga", "B1": "Belgian Pro League", "SC0": "Scottish Premiership",
           "T1": "Super Lig", "G1": "Greek Super League"}
EXTRA = {"AUT": ("at", "Austrian Bundesliga"), "SWZ": ("ch", "Swiss Super League"), "DNK": ("dk", "Danish Superliga"),
         "NOR": ("no", "Eliteserien"), "SWE": ("se", "Allsvenskan"), "ROU": ("ro", "Romanian Liga I"),
         "POL": ("pl", "Ekstraklasa")}
CODE_TO_LEAGUE = {"eng": "Premier League", "es": "La Liga", "de": "Bundesliga", "it": "Serie A", "fr": "Ligue 1",
                  "nl": "Eredivisie", "pt": "Primeira Liga", "be": "Belgian Pro League", "sct": "Scottish Premiership",
                  "tr": "Super Lig", "gr": "Greek Super League"}
CODE_TO_LEAGUE.update({cc: name for cc, name in EXTRA.values()})
OU_AH_COLS = ["B365>2.5", "B365<2.5", "Max>2.5", "Max<2.5", "Avg>2.5", "Avg<2.5", "P>2.5", "P<2.5", "B365C>2.5", "B365C<2.5", "AvgC>2.5", "AvgC<2.5",
              "PC>2.5", "PC<2.5", "MaxC>2.5", "MaxC<2.5", "AHh", "B365AHH", "B365AHA", "MaxAHH", "MaxAHA", "AvgAHH", "AvgAHA", "PAHH", "PAHA",
              "AHCh", "B365CAHH", "B365CAHA", "AvgCAHH", "AvgCAHA", "PCAHH", "PCAHA", "MaxCAHH", "MaxCAHA"]
KEEP = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "HTHG", "HTAG", "HF", "AF", "HC", "AC", "HY", "AY", "HS", "AS", "HST", "AST", "HR", "AR", "B365H", "B365D", "B365A",
        "B365CH", "B365CD", "B365CA", "PSH", "PSD", "PSA", "PSCH", "PSCD", "PSCA",
        "MaxH", "MaxD", "MaxA", "AvgH", "AvgD", "AvgA", "MaxCH", "MaxCD", "MaxCA"] + OU_AH_COLS
PRICE_COLS = ["B365CH", "B365CD", "B365CA", "PSH", "PSD", "PSA", "PSCH", "PSCD", "PSCA", "MaxH", "MaxD", "MaxA", "AvgH", "AvgD", "AvgA", "MaxCH", "MaxCD", "MaxCA"]
ODDS = ["B365H", "B365D", "B365A"]

def clean_cols(df):
    df.columns = [str(c).replace("ï»¿", "").replace("\ufeff", "").replace("▲", "").replace("▼", "").strip() for c in df.columns]
    return df

def load_main():
    frames = []
    for code, name in LEAGUES.items():
        for season in SEASONS:
            try:
                df = pd.read_csv(f"{DATA_URL}/mmz4281/{season}/{code}.csv", encoding="latin-1", on_bad_lines="skip")
            except Exception as e:
                print(f"  could not load {name} {season}: {e}")
                continue
            df = clean_cols(df).reindex(columns=KEEP)
            df["League"], df["Season"] = name, season
            frames.append(df)
    d = pd.concat(frames, ignore_index=True).dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"])
    d["Date"] = pd.to_datetime(d["Date"], dayfirst=True, format="mixed")
    for c in ODDS + PRICE_COLS + OU_AH_COLS + ["HTHG", "HTAG", "HF", "AF"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d.sort_values("Date").reset_index(drop=True)

def load_new_format(code, name):
    d = clean_cols(pd.read_csv(f"{DATA_URL}/new/{code}.csv", encoding="latin-1"))
    d = d.rename(columns={"Home": "HomeTeam", "Away": "AwayTeam", "HG": "FTHG", "AG": "FTAG",
                          "AvgCH": "B365H", "AvgCD": "B365D", "AvgCA": "B365A"})
    d["Date"] = pd.to_datetime(d["Date"], dayfirst=True, format="mixed")
    d["Season"] = d["Season"].astype(str).str.replace(r"^\d\d(\d\d)/\d\d(\d\d)$", r"\1\2", regex=True)
    d["League"] = name
    d = d[["League", "Season", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"] + ODDS].copy()
    for c in ODDS:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d.dropna(subset=["FTHG", "FTAG"]).sort_values("Date").reset_index(drop=True)

def _load_new_safe(code, name):
    """v30: football-data.co.uk sometimes times out (HTTP 504); try three times, then carry on without that league."""
    for attempt in range(3):
        try:
            return load_new_format(code, name)
        except Exception as ex_:
            last_ = ex_
            time.sleep(10 * (attempt + 1))
    print(f"  could not load {name} ({str(last_)[:60]}); carrying on without it this run")
    health(f"football-data.co.uk: {name}", False, f"not loaded this run ({str(last_)[:40]})")
    return pd.DataFrame(columns=["League", "Season", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"] + ODDS)
def read_euro(fname):
    try:
        t = pd.read_csv(f"{SAVE_DIR}/{fname}", encoding="utf-8-sig")
    except UnicodeDecodeError:
        t = pd.read_csv(f"{SAVE_DIR}/{fname}", encoding="latin-1")
    return clean_cols(t)

def parse_euro(fname, played=True):
    t = read_euro(fname)
    t = t[t["Home"].notna() & (t["Date"].astype(str) != "Date")]
    t = t[t["Score"].notna()] if played else t[t["Score"].isna()]
    if played and "Notes" in t.columns:
        t = t[~t["Notes"].fillna("").astype(str).str.contains("Extra Time")]
    cols = ["Competition", "Season", "Date", "HomeTeam", "HomeCountry", "AwayTeam", "AwayCountry"]
    if t.empty:
        return pd.DataFrame(columns=cols + (["FTHG", "FTAG"] if played else []))
    home = t["Home"].astype(str).str.rsplit(" ", n=1, expand=True).reindex(columns=[0, 1])
    away = t["Away"].astype(str).str.split(" ", n=1, expand=True).reindex(columns=[0, 1])
    out = pd.DataFrame({"Competition": "Champions League" if fname.startswith("cl") else "Europa League",
                        "Season": fname[3:7], "Date": pd.to_datetime(t["Date"]).values,
                        "HomeTeam": home[0].values, "HomeCountry": home[1].values,
                        "AwayTeam": away[1].values, "AwayCountry": away[0].values})
    if played:
        g = t["Score"].astype(str).str.replace(r"\(\d+\)", "", regex=True).str.extract(r"(\d+)\s*[–-]\s*(\d+)")
        out["FTHG"], out["FTAG"] = pd.to_numeric(g[0]).values, pd.to_numeric(g[1]).values
        out = out.dropna(subset=["FTHG", "FTAG"])
    return out

print("Loading the 11 main leagues...")
all_matches = load_main()
print("Loading MLS and the 6 extra leagues...")
mls = load_new_format("USA", "MLS")
mls = mls[mls["Season"].isin(MLS_SEASONS)].reset_index(drop=True)

# Leagues predicted on their own (not from football-data's main files): their data, current season, half-life and scorecard group.
# The Saudi Pro League is added in section 1b (from ESPN).
SOLO = {"MLS": {"data": mls, "season": MLS_SEASONS[-1], "half_life": 180, "group": "MLS"}}
# v29: Latin American leagues from football-data.co.uk (results and closing odds), predicted on their own like MLS
FD_NEW_LEAGUES = {"MEX": ("Liga MX", "Americas"), "ARG": ("Argentina Liga Profesional", "Americas"), "BRA": ("Brasileirão Série A", "Americas")}
for code_, (name_, group_) in (FD_NEW_LEAGUES.items() if INCLUDE_NEW_LEAGUES else []):
    try:
        d_ = _load_new_safe(code_, name_)
        d_ = d_[d_["Date"] >= TODAY - pd.Timedelta(days=3 * 365 + 30)].reset_index(drop=True)
        if len(d_) >= 200:
            SOLO[name_] = {"data": d_, "season": str(d_["Season"].iloc[-1]), "half_life": 180, "group": group_}
            print(f"  {name_}: {len(d_)} results since {d_['Date'].min():%b %Y}")
    except Exception as ex_:
        print(f"  {name_}: not available this run ({str(ex_)[:60]})")
def league_frame(league):
    return SOLO[league]["data"] if league in SOLO else all_matches[all_matches["League"] == league]
def league_season(league):
    return SOLO[league]["season"] if league in SOLO else SEASONS[-1]
start = pd.Timestamp(f"20{SEASONS[0][:2]}-01-01")
extra_matches = pd.concat([_load_new_safe(code, name) for code, (cc, name) in EXTRA.items()], ignore_index=True)
extra_matches = extra_matches[extra_matches["Date"] >= start]
domestic = pd.concat([all_matches, extra_matches], ignore_index=True).sort_values("Date").reset_index(drop=True)
_lag = (TODAY - all_matches["Date"].max()).days
health("football-data.co.uk (11 leagues)", _lag <= 10, f"{len(all_matches)} matches, latest {all_matches['Date'].max():%d %b}")
health("football-data.co.uk (MLS and 7 extra leagues)", len(mls) and len(extra_matches),
       f"MLS latest {mls['Date'].max():%d %b}; {extra_matches['League'].nunique()} extra leagues")

euro, euro_up = pd.DataFrame(), pd.DataFrame()
name_map = {}
if EURO_SOURCE == "fbref":
    print("Loading European files from Drive...")
    euro_files = sorted(f for f in os.listdir(SAVE_DIR) if f.startswith(("cl_", "el_")) and f.endswith(".csv"))
    names_path = f"{SAVE_DIR}/team_names.csv"
    name_map = {}
    if os.path.exists(names_path):
        nt = pd.read_csv(names_path)
        name_map = {a: b for a, b in zip(nt["FBref name"], nt["Matched to"]) if pd.notna(b)}
    name_map.update(NAME_FIXES)

    def label_euro(e):
        for side in ["Home", "Away"]:
            e[f"{side}Team"] = e[f"{side}Team"].replace(name_map)
            e[f"{side}League"] = e[f"{side}Country"].map(CODE_TO_LEAGUE).fillna("Other")
        return e

    euro = label_euro(pd.concat([parse_euro(f, True) for f in euro_files], ignore_index=True)).sort_values("Date").reset_index(drop=True)
    current_files = [f for f in euro_files if f[3:7] == SEASONS[-1]]
    euro_up = label_euro(pd.concat([parse_euro(f, False) for f in current_files], ignore_index=True)) if current_files else pd.DataFrame()
    euro["Date"] = pd.to_datetime(euro["Date"])
    euro[["FTHG", "FTAG"]] = euro[["FTHG", "FTAG"]].astype(float)
    if len(euro_up):
        euro_up["Date"] = pd.to_datetime(euro_up["Date"])

    # Check for European team names that don't match a domestic team
    dom_teams = {lg: set(g["HomeTeam"]) | set(g["AwayTeam"]) for lg, g in domestic.groupby("League")}
    check = pd.concat([euro[["HomeTeam", "HomeLeague"]].set_axis(["Team", "League"], axis=1),
                       euro[["AwayTeam", "AwayLeague"]].set_axis(["Team", "League"], axis=1)] +
                      ([euro_up[["HomeTeam", "HomeLeague"]].set_axis(["Team", "League"], axis=1),
                        euro_up[["AwayTeam", "AwayLeague"]].set_axis(["Team", "League"], axis=1)] if len(euro_up) else []))
    check = check[(check["League"] != "Other") & ~check["Team"].isin(LOWER_DIVISION)].drop_duplicates()
    unmatched = check[[t not in dom_teams.get(lg, set()) for t, lg in zip(check["Team"], check["League"])]]

    print(f"\n{len(all_matches)} main-league matches (latest {all_matches['Date'].max().date()}), "
          f"{len(extra_matches)} extra-league, {len(mls)} MLS (latest {mls['Date'].max().date()}), "
          f"{len(euro)} European (latest {euro['Date'].max().date() if len(euro) else '-'})")
    if len(unmatched):
        print("\n⚠ European team names with no domestic match. Add them to NAME_FIXES (or LOWER_DIVISION) in Settings:")
        for t, lg in zip(unmatched["Team"], unmatched["League"]):
            guess = difflib.get_close_matches(t, sorted(dom_teams.get(lg, [])), n=1, cutoff=0)
            print(f"   {t!r} ({lg}) - closest domestic name: {guess[0] if guess else '-'!r}")
    else:
        print("All European team names matched.")
else:
    print(f"\n{len(all_matches)} main-league matches (latest {all_matches['Date'].max().date()}), "
          f"{len(extra_matches)} extra-league, {len(mls)} MLS (latest {mls['Date'].max().date()}). European matches load from ESPN in section 1b.")
