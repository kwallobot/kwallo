# ===================== SETTINGS: the only cell you normally edit =====================
SAVE_DIR = "/content/drive/MyDrive/football"     # your Drive folder
DATA_URL = "https://www.football-data.co.uk"

SEASONS = ["2324", "2425", "2526", "2627"]       # next summer: add "2728"
MLS_SEASONS = ["2022", "2023", "2024", "2025", "2026"]
PREDICT_DAYS = 7
INCLUDE_SAUDI = True                             # Saudi Pro League (from ESPN: results, fixtures, lineups, odds)                                 # predict fixtures in the next N days

# Where European results and fixtures come from: "espn" (automatic) or "fbref" (your exported files in Drive)
EURO_SOURCE = "espn"

# European clubs ESPN can't place in one of our leagues: {"ESPN name": ("League", "our spelling")}
EURO_TEAM_FIXES = {}

# Only used with EURO_SOURCE = "fbref": FBref spellings -> domestic spellings
NAME_FIXES = {}

# European teams from a lower division -> the top league of their country
LOWER_DIVISION = {"Torreense": "Primeira Liga"}

# Fixtures you want to add by hand: (league, "YYYY-MM-DD", home, away)
MANUAL_FIXTURES = [
    # ("MLS", "2026-10-24", "Seattle Sounders", "Portland Timbers"),
]

# Player model: adjusts predictions for likely absences (ESPN lineups; Premier League also uses Fantasy PL injury flags)
PLAYER_MODEL = True
LINEUP_RUN_MINUTES = 20          # max minutes per run spent downloading new lineups (the first full download is done)

# Team ratings in the big five leagues use this share of Understat expected goals (the rest is actual goals).
# 0.5 won clearly in testing (better than goals only in 99% of reshuffles). 0 switches it off.
XG_WEIGHT = 0.5

# European model: "auto" uses whichever tested setting won (see section 9); or force "base", "xg", "half_life_180", "europe_x3"
EURO_MODEL = "auto"
EURO_PLAYER_ADJUST = True        # player adjustment in European matches (helped in testing)
RUN_EURO_SELECTION = True        # replay European matches to pick the best setting (first run is slow; then only new weeks)

# Extra sources for the Experiments section (section 10). They don't change predictions until switched on there.
USE_CLUBELO = True
USE_UNDERSTAT = True        # also needed for XG_WEIGHT
RUN_EXPERIMENTS = True
ELO_NAME_FIXES = {}      # if a ClubElo link is wrong: {"Our name": "ClubElo name"}

# Match reports (one per upcoming fixture, in the dashboard and saved to Drive)
MATCH_REPORTS = True

# Your analyst's adjusted probabilities, if you disagree with the model after reading the news.
# They're logged and scored separately, so you can see whether the adjustments actually help.
# ("League", "YYYY-MM-DD", "Home", "Away", home %, draw %, away %)
ANALYST_PICKS = [
    # ("Premier League", "2026-10-17", "Newcastle", "Aston Villa", 40, 27, 33),
]

# Odds you see at your bookmaker for niche markets (throw-ins, player shots on target, 2+ shots, penalties, half-time draw...).
# Copy the bet's wording from the card's "More markets" or "Match verdict" (a recognisable part is enough).
# They're logged before kickoff and scored afterwards, to test whether betting above the model's fair odds actually pays.
# ("YYYY-MM-DD", "Home team", "Away team", "bet wording", decimal odds)
MY_ODDS = [
    # ("2026-10-24", "Arsenal", "Chelsea", "total throw-ins", 1.95),
]

# Club crests are trademarks and copyrighted artwork: keep this False for any public site (club-colour badges are shown instead).
SHOW_LOGOS = False

# Heavy replays (calibration tests, the lineup model's training): True in the weekly full run, False in quick runs
RUN_REPLAYS = True

# Use official lineups once they're announced (checked for fixtures starting within this many hours)
CONFIRMED_LINEUPS = True
CONFIRMED_WINDOW_HOURS = 3

# Replay this season to score the model straight away (cached in Drive; first run takes a few minutes)
RUN_BACKTEST = True

# Impact-rating data: how far back to collect lineups, substitution and goal minutes (for player ratings later).
# The first runs backfill history in chunks of LINEUP_RUN_MINUTES; raise it (e.g. 60) for a few runs to finish sooner.
LINEUP_HISTORY_FROM = "2023-07-01"
TEST_GOAL_LEVEL_AND_REST = True   # test goal-level drift and rest days; each is switched on only if it passes

# Dashboard: show it at the bottom of the notebook, and/or download it to your computer each run
SHOW_DASHBOARD = True
DOWNLOAD_DASHBOARD = False
