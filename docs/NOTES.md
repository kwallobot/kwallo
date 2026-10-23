# Kwallo: roadmap and decisions

*Last updated: 23 October 2026 (v37d built: NBA box scores, quarters, plays, player pages, leaders; halves and quarters, rebound and assist props, live chances. v37c built: the league gate over three seasons, held leagues shown without chances, Matches / Games; v37b: NBA player ratings and the live record; v37: the NBA. v36 before it: the 22 leagues, the league gate, PlayerElo, the installable app and the live view).*

### v37d, as built (23 October 2026): NBA stats pages, halves and quarters, player props, live chances
- **Worker** `/api/bbgame?id=`: ESPN's game page, trimmed, with:
  - the status, the score by quarter, team statistics and every player's box-score line
  - the scoring plays

  It's cached for 30 seconds in play, 5 minutes before tip-off, and a day after the final.
- **Game page tabs:**
  - **Overview:** the quarters with 1st- and 2nd-half totals, Kwallo's pick ✓/✗, game leaders, scoring runs of 8+ points, the lead chart, Kwallo's live chance through the game, and the live chances card in play.
  - **Markets:** winner, spread and total; halves and quarters; player props.
  - **Box score** (sortable), **Team stats**, and **Plays** (scoring plays, filterable by quarter).
  - **Past games** open as `#/bb/result/{id}/{date}` from past days, team form and player logs.
- **Player pages** (`#/bb/player/{name}-{id}`): this season's and last season's averages, plus the last 10 games. Teams get a sortable roster. **Leaders** (`#/bb/leaders`): points, rebounds, assists, steals, blocks and threes per game, for players with 40% of their team's games.
- **Data:** 3-pointers are added to the box scores (the history files are downloaded again once, and this season's box scores are re-read once). The score by quarter comes from the scoreboards; last season's is read once (`past_quarters.csv`).
- **The tests**, weekly, each published only if it passes. First results (2025/26):
  - **Halves and quarters:** fitted before 1 February, judged after. 1st half winner 0.748 against 0.818 for the simple guess. 1st quarter winner, 1st half points and 1st quarter points also pass. The highest-scoring quarter fails (no better than the simple guess).
  - **Live chances:** tested at the end of Q1, at half-time and at the end of Q3 of every game (3,672 moments). Log loss 0.457 against 0.580 for the pre-game chances alone, and 0.016 out on calibration: passed. The spread is 13 × 1.35 × (share of the game left)^0.45.
  - **Player props:** tuned before 1 February, judged after, on 8,674 rotation-player games. The model must beat the player's own over-rate at his 20-game average, and be no more than 0.02 out on calibration.

    | Prop | Result |
    |---|---|
    | Rebounds | passed (0.675 vs 0.695, 0.013 out) |
    | Assists | passed (0.671 vs 0.696, 0.010 out) |
    | Points | not passed: better than the guess, but 0.039 out on calibration |
    | 3-pointers | not passed: worse than the guess |

    Shown as ladders (4+, 6+, 8+ …) for each likely player: 15+ expected minutes and not ruled out by the injury report.
- **First run after upload:** if `model.json` has no test results yet, the daily run does these tests too, using the stored replay.

### v37c, as built (23 October 2026): a fairer league gate, held leagues shown, Matches / Games
- **Why:** the first v36 gate (this season only, 50–200 matches) held back 13 of the 22 new leagues. Some failed only the naive test, while being close to the bookmakers or even ahead of them: 2. Bundesliga (0.018 behind), Serie B (0.003 behind) and League Two (0.004 ahead). In very even leagues a small sample can make the naive guess look good by luck.
- **Past seasons** (section 8): each new league's two previous seasons are replayed week by week, the same way as this season. Each league-season is replayed once and kept (`backtest_past_v36leagues.csv`). This runs in the full run only, within 40 minutes, and continues next week if it runs out of time. It uses no player adjustment, because these leagues' lineup data starts this season, so it's slightly strict. The gate now judges about 1,000 matches per league.
- **The rule:** a league with bookmaker odds (40+ replayed matches with them) passes by coming within 0.03 of the bookmakers. The five leagues without odds pass by beating their usual home / draw / away split by 0.01, judged per season on the earlier seasons. Every league needs 60+ matches.
- **Held leagues are shown without chances:** their matches, kick-off times, live scores, lineups, statistics, form, head-to-head, tables and leaders, with a note that the chances are still being tested. They have no chances, verdict, markets, Goals tab or Follow button. They stay out of the channel, the bot's alerts and previews, the angles and the track record. The Worker skips `held` matches for alerts and lineup runs. Section 4 hands their fixtures to the exporter as `HELD_FIXTURES`.
- **Rename:** the first tab is "Matches" on football and "Games" on basketball. That tab and Leagues reopen the sport viewed last. The app shortcut is "Matches". The offline cache version is `kwallo-v37c-1`.

### v37b, as built (23 October 2026): a better NBA model
Tested on the 2025/26 season (1,228 games, three seasons of history), each change kept only if the replay improved:
- **Fairer test:** last season's bookmaker lines are now read from the whole season in a shuffled order. Earlier, only the newest games were read, so the test covered the season's end alone. 1,009 games now have lines. The first weekly test reads them (about 10 minutes); later runs reuse the stored file. The end of a season had flattered the bookmakers: there the gap was 0.015–0.021 a month, against about 0.004–0.013 in mid-season.
- **Player ratings (kept, the biggest gain):** every player is rated from all his earlier games, for any team and season (game score per 36 minutes, older games fading, pulled towards a bench player's level until he has played a few hundred minutes). A lineup's strength is the minutes-weighted rating of the 9 players expected to play most. For upcoming games, that's ESPN's current roster minus the injury report, so trades and new signings count straight away (the season-start fix). Log loss went from 0.5950 to 0.5829, and to 0.5800 with missing regulars on top.
- **Not kept** (no improvement on top of the player ratings): back-to-backs, days of rest, travel, late-season teams with nothing to play for, and each team's own home advantage. They're re-tested every week.
- **Re-tuned:** old games halve every 60 days, with a pull towards average of 0.2; pace fades over 90 days.
- **Result:** Kwallo 0.5883 against the bookmakers' 0.5757 on 1,009 games, a gap of 0.013, so **the gate passes**. Margin error was 11.3 points against their 11.1. The strict replay (lineups from each team's previous game, i.e. before the injury report) has a gap of 0.028. Real use sits between the two.
- **The live record (new):** each run scores Kwallo's real pre-game predictions this season against the bookmakers' lines on the same games. Once 150 exist, chances stay published only while the live record is within 0.02. `WAIT_FOR_LIVE` in `nba.py` holds publishing until that record exists.

### v37, as built (23 October 2026): the NBA
- **Its own pipeline** in `basketball/` (`nba.py` holds the data and the model; `run.py` runs it), separate from football. Two workflows: **Basketball daily** (06:00 UTC = 07:00 Lagos, every day except Tuesday) and **Basketball weekly test** (Tuesdays at the same time; also startable by hand). They share the R2 bucket under `bb-data/` and publish the website's files under `site/bb/`. Runs take a few minutes; the first one downloads the history and takes longer.
- **Data:** three past seasons of team and player box scores from hoopR (sportsdataverse, downloaded once). From ESPN: this season's results and box scores, the bookmakers' lines (spread, total and moneylines), and the injury report.
- **Model:** each team's offence and defence in points per 100 possessions, plus pace, fitted with time decay (ridge regression), plus home court. The weekly test tunes how fast old games fade and how hard ratings are pulled to average (best so far: halve every 60 days, pull 0.6). It turns margins into win chances with the spread width that scores best (12.5 points).
- **Adjustments, each tested on last season before use:** back-to-backs and travel didn't help (not used). Missing players (regulars who sat out, weighted by their game score; the injury report for upcoming games) did help, so it's kept.
- **The gate:** chances are published only when the replay of last season beats a naive guess by 0.02 and comes within 0.02 of the bookmakers' log loss on games with lines. First test (2 history seasons): Kwallo 0.584 against the naive guess's 0.687, so it clearly beats it. On the 273 games with lines it scored 0.514 against the bookmakers' 0.487, and the average margin error was 11.6 points against their 10.9. **Not passed yet**, so the site shows NBA games, live scores, results, standings and team pages, with a "still being tested" note in place of the chances. The weekly test lets them out automatically once the model gets close. Ideas to close the gap: starters and minutes from the injury report, player-based ratings, and late-season rest.
- **Website:** a Football / Basketball switch on Today and Leagues; `#/bb` (game nights by US date, the last 7 days, a date picker from October 2026, swipes), `#/bb/game/…` (chances, winner, spread and total cells for the accumulator when published; ratings, injury report, last 10, this season's meetings), `#/bb/team/…`, `#/bb/standings` (with the playoff and play-in cut lines).
- **Worker:** live scores now include the NBA (read from `site/bb/schedule.json`, ESPN's basketball scoreboard, followed for 200 minutes after tip-off, "Final" and "Half"). The bot and the channel stay football-only until v39.

### v36 round 3, as built (23 October 2026): the live view
- **In-play chances** (`web/app.js`, worked out in the browser): the pre-match expected goals for the time still to play (the goal rate rises by about a third from 0' to 90'). A red card cuts that side's goals by 28% and raises the other's by 25%. Each side's xG so far is compared with what was expected (damped, capped at x0.6 to x1.6). The result is added to the current score. Shown as "Kwallo's live chances" at the top of a live match's Overview, updated every minute. The header bar is now labelled as the pre-match chances.
- **Win-probability graph**: the three chances at every minute (home on top, draw in the middle, away below), with goals and red cards marked. On live matches it runs up to now; on finished ones (match pages and past days) it runs to the result. Past days need the pre-match expected goals, which the day files now carry (`eh`, `ea`; from the next pipeline run).
- **Real xG from ESPN** (Worker): in the 15 competitions where ESPN's play-by-play gives every shot an xG (the big five, the three European cups, the Championship, MLS, Liga MX, Brazil, Argentina, the Libertadores and the Sudamericana), it replaces Kwallo's estimate whenever 80% or more of the match's shots so far have one. This was checked on finished matches, where it matched PitchAPI within a few hundredths. Whether ESPN fills it in during play is checked automatically, match by match; otherwise the estimate stays ("est."). The Worker also sends each side's xG minute by minute (`xg.cum`) for the graph.

### v36 round 2, as built (23 October 2026): the installable app
- `web/manifest.webmanifest`: the name, Kwallo's colours (the splash screen on Android), the icons and three shortcuts (Today, Angles, Record). The icons are `icon-192.png`, `icon-512.png`, `icon-maskable-512.png` (full-bleed, for Android's shapes) and `apple-touch-icon.png` (iPhone), drawn from `logo.svg`.
- `web/sw.js`, the service worker. Pages, files and the Worker's data are fetched fresh when online (network first), and the saved copies are the fallback, so the app opens offline with the last loaded matches and a yellow "You're offline" note. A new version of `sw.js` (change `VERSION`) takes over the next time the app is opened and clears the old saved files. Up to 200 data files are kept.
- The More page offers "Install the Kwallo app": a one-tap install on Android and Chrome; on an iPhone, the steps (Safari's Share button, then "Add to Home Screen"). It says so when you're already in the app.
- iPhone note: iOS shows its own blank launch screen. Android builds the splash screen from the manifest.

### v36 round 1, as built (23 October 2026)
- **22 new leagues**, each predicted on its own. Second tiers come from football-data.co.uk's main files, with odds, corners and cards; a club just relegated into a second tier is rated from its results in the division above. Austria, Switzerland, Denmark, Norway, Sweden, Romania, Poland, J1 and the Chinese Super League come from football-data's "new" files. Czechia, Croatia, Serbia, Israel and Slovakia come from PitchAPI.
- **Data sources for the new leagues:**
  - **ESPN** (Championship, League One and Two, Segunda, 2. Bundesliga, Serie B, Ligue 2, Scottish Championship, Austria, Denmark, Norway, Sweden, J1, China): lineups (from this season), live scores and match statistics.
  - **PitchAPI:** fixtures and kick-off times for the eight ESPN doesn't cover.
  - **PitchAPI xG:** shown on team stats; it feeds the ratings once the xG experiment can test these leagues.
- **The league gate** (`league_gate.json`, section 8): every run, a new league's replay of this season is checked. It must have 60 or more matches, beat a naive guess by 0.01, and come within 0.03 of the bookmakers (the five leagues without odds take the naive test only). A league that fails is kept off the site, the channel and the track record. Decisions apply from the next run.
- **Chances only:** the five leagues without odds show result chances, with no angles, markets or scorers.
- **Site groups:** "Europe: second tiers and smaller leagues" and "Asia".
- **Schedules:** the daily run starts at 05:00 Lagos time. The full run's limit is 350 minutes, under GitHub's 360. The Sunday parallel-backtest run wasn't needed: backtests were already incremental (cached by week), and each new league now replays its season once, on first sight.
- **PlayerElo** (section 10b): a weekly snapshot of club Elo and the league-strength table in the full run. European ties are logged with both clubs' Elo and compared with our model once 150 have been played. Player Elo for lineup strength waits until the club-level test is in, because the free plan's 500 requests a month can't cover squads too.

## Roadmap

| Version | Contents |
|---|---|
| **v32** | The Kwallo website on Cloudflare Pages, private dashboard, kick-off alerts, full player statistics, per-group calibration, UI fixes |
| **v33** | Live filter and live scores, collapsible competition cards, collapsible Leagues, match header and tabs, every market, "Follow this match" |
| **v34** | Lineups on a pitch, xG for the European cups and 19 more competitions (smaller European leagues, second divisions, League One and Two), position fixes, the expected-lineup bug fix |
| **v35** (current) | **Faster bot alerts** (live alerts sent within the minute, lineup alerts the moment they're announced, no lost or repeated goal alerts); **team news** (injuries and press-conference news read by Claude, feeding the expected lineups); **pitch positions fixed** (away side mirrored, usual and announced positions, a playable shape); **European cups**: league-phase table, corners, cards, tackles, offsides and throw-ins; **website**: back button and swipes, Markets as advised bets against team averages with likeliest scorers and assisters, Players / Team stats / H2H tabs, past matches open with full statistics, every player tappable, transfer history; **match stats card** in play (ESPN, every minute) and at full-time (PitchAPI: xG, big chances, ratings, 1st / 2nd half), scoreboard with white scores; **match overview** (momentum chart and timeline); Kwallo's colours on every card; **tabs switch in place** (no reload or history entry, the chosen tab in view); **lineups**: squads and coach before the team sheet, then the official XI, bench, substitutions and ratings; **Markets** = advised bets, players to watch, score grid, 15-minute goal timing; new **Goals & more** tab; **Players** tab with goals, assists, xG, xA, shots (sortable); leaders and player stats **per competition, this season**; cup matchdays and knockout round names; Egypt "Time TBC" and full-time results from PitchAPI; stars either side of each fixture |
| **v36** | The **full live view** (in-play chances, momentum, win-probability graphs), the **installable app** (PWA); **more predicted leagues**: Championship, LaLiga Hypermotion (Segunda División), Ligue 2, Austria, Switzerland, Denmark, Norway and Sweden, the **J1 League** (now an August–June season: 2026/27 runs to June 2027; ESPN code jpn.1) and the **Chinese Super League** (calendar year, March–November; mainly for 2027; ESPN chn.1), plus a check of whether PitchAPI covers the **J2 League** (ESPN doesn't) to rate J1's promoted sides; added 22 October 2026 (data already downloaded): **Romania, Poland, 2. Bundesliga, Serie B, League One, League Two** (results, odds and xG), the **Scottish Championship** (results and odds, no xG; Scottish League One and Two left out), and **Czechia, Croatia, Serbia, Israel and Slovakia** (PitchAPI results and xG, no bookmaker odds, so their backtest is against a naive guess only): each league's backtest (vs a naive guess and the bookmakers) runs in the weekly run, and only leagues that pass are published (result chances first; corners and cards only where the statistics exist). (Checked 22 October 2026: PitchAPI has no J2 either, so J1's promoted sides use the typical-promoted-side rating.) **PlayerElo experiment**: a weekly snapshot of club, league and player Elo (free key, 500 requests a month; secret `PLAYERELO_KEY`) tested inside the model only, the way ClubElo was: as a second opinion on European ties, for clubs from leagues no source covers (Hungary, Cyprus, Ukraine, Azerbaijan…), and as lineup strength; adopted only if the backtest improves. Their numbers are never shown on the site (commercial display needs their paid licence) |
| **v37** (built) | **NBA**: its own pipeline and workflows, model with a publishing gate, website pages, live scores |
| **v38** | **EuroLeague**, player props and in-play basketball chances; work on closing the NBA's gap to the bookmakers |
| **v39** | Basketball on the Telegram bot and channel |
| **Then** | **Free profiles and sign-in**: Telegram and Google sign-in (the site stays fully usable without one), then **email sign-in** (needs a domain); the **premium tier** |

## Decisions already made

- **Free tier:** fixtures, results, tables, team pages, basic home/draw/away chances with fair odds, expected and confirmed lineups, stats and trends, the Telegram channel, personal alerts and live alerts (with basic chances only).
- **Premium tier:** detailed probabilities (BTTS, over/under, scorelines, corners, cards), player props, match verdicts, today's best angles, more markets, the accumulator calculator, the live view, in-play chances and top angles in alerts.
- **Channel digest under premium:** basic chances plus one free pick per match, never that match's top angle (its second-best angle, else its safer angle).
- **Owner:** permanent premium for the admin Telegram account and kwallo.hq@gmail.com; a complimentary-premium list for testers and partners.
- **Public rules:** fair odds only, no bookmaker names or prices, 18+.
- **Language:** English only at launch (Nigerian Pidgin possibly later).
- **GitHub project stays private** (the model is the main asset).
- **Profiles are optional:** the website works fully without signing in (after basketball; moved out of v36 on 22 October 2026).
- **Not doing:** goal-kick markets (no source records goal kicks).
- **ClubElo switched off** (its service is usually down; it only fed one experiment, never adopted).
- **NPFL 2026/27:** Inter Lagos FC and Ranchers Bees confirmed as promoted (they start with promoted-side ratings).
- **Data sources by statistic (v35):** corners, cards, fouls, tackles and offsides for every competition come from ESPN's match statistics (football-data.co.uk first where it has them); throw-ins only from PitchAPI (now including the European cups); transfer history from ESPN; team news from ESPN's match news, read by Claude Haiku (optional `ANTHROPIC_API_KEY`).

## Open items

- **Domain:** kwallo.com and kwallo.app are taken. Candidates: **kwallo.ng** (about $48/year) plus **kwallo.com.ng** (about $5/year), or **getkwallo.com**. Email sign-in needs a domain.
- **Before a wide public launch:** Nigerian legal review (predictions site, NDPA data protection, profiles, later paid subscriptions); trademark checks and registering Kwallo with the logo; data-source terms for public display (ESPN, BSD, football-data.co.uk, Understat, FPL; PitchAPI already confirmed). ESPN now also supplies team news text (read, not republished), past-match pages and transfer history.
- **Scaling:** Cloudflare Workers Paid (about $5/month) once live alerts reach hundreds of followers per match. The Worker logs show when the free plan's per-minute request allowance is the limit.
- **GitHub minutes:** watch usage; lower `LINEUP_DAILY_MAX` (Worker variable) if it gets tight. Lineup alerts no longer depend on these runs (v35).

## Basketball data sources (evaluated October 2026; rechecked 20 October 2026)

| Source | What it offers | Verdict |
|---|---|---|
| **nba_api** (github.com/swar/nba_api) | Python client for NBA.com stats and live data (box scores, play-by-play, game logs, live scoreboard). MIT-licensed, widely used (3.8k stars), Python 3.10+; NBA.com's terms apply; endpoints change without notice; reportedly slow or blocked from cloud servers (to test from GitHub) | **Main NBA source** |
| **hoopR** (sportsdataverse) | R package over ESPN, NBA Stats, KenPom (subscription) and more; NBA play-by-play 2002–2026, men's college 2006–2026, as release files in the hoopR-nba-data / hoopR-mbb-data repositories. MIT | **Use its data files from Python** (or sportsdataverse-py) for the history backfill |
| **ESPN** (as used for football) | NBA fixtures, scores, injuries, some odds | **Backup and cross-check** |
| **Playbook API** (playbook-api.com) | Rechecked: the site and docs now only clearly show **injury reports** (NBA/NFL examples); no prices or terms published (earlier notes said odds, props, free 500 requests/month, app use allowed) | **Trial for NBA injuries only**; confirm what's included and the terms with support@playbook-api.com first |
| **ParlayAPI** (parlay-api.com) | Odds from 30+ bookmakers, props, line movement, history from 2005, 90+ sports (incl. some football: EPL, Serie A props). Free 1,000 credits/month, no card. Public display or commercial use needs a separate agreement, even on paid plans | **Private comparison only** (fits the no-bookmaker-prices rule); mainly for NBA props |
| **PropLine** | Props-focused odds API; free 500 requests/day; grades props against box scores | Alternative for props lines |
| **SportyApi** (sportyapi.com) | Scores and schedules only (NFL, NBA, NHL, MLB, college football and basketball, one soccer feed); no odds, stats or lineups; no free plan (14-day trial with card, then $9/month); sources not named | **Not needed** (ESPN gives the same free) |
| **Postgame-Stats-Api** (github.com/csyork19) | Small self-hosted Flask hobby project (13 stars): NBA, WNBA, G League, some NFL; source not named. MIT | **Not needed** (use nba_api directly) |
| **SportyBet "API"** (unofficial, on a scraping marketplace) | Scraped SportyBet odds | **Avoid** (terms risk); private use only if ever |
| **EuroLeague** | Official data feed | **To check** in the probe |

**Plan:** start basketball with a probe from GitHub's servers (nba_api, the sportsdataverse files, ESPN NBA, the EuroLeague feed, and a free Playbook API key), then choose sources based on what actually works.
