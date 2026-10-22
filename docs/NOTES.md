# Kwallo: roadmap and decisions

*Last updated: 23 October 2026 (v36 built: round 1, the 22 leagues, the league gate and PlayerElo; round 2, the installable app; round 3, the live view).*

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
| **v37–v39** | **Basketball: NBA and EuroLeague** (moved ahead of profiles, 22 October 2026). Its own workflows and schedule, separate from football's (so football runs never wait for it or get longer); the daily basketball run after US games finish, about 07:00–08:00 Lagos |
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
