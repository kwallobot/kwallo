# Kwallo: roadmap and decisions

*Last updated: 20 October 2026 (v35).*

## Roadmap

| Version | Contents |
|---|---|
| **v32** | The Kwallo website on Cloudflare Pages, private dashboard, kick-off alerts, full player statistics, per-group calibration, UI fixes |
| **v33** | Live filter and live scores, collapsible competition cards, collapsible Leagues, match header and tabs, every market, "Follow this match" |
| **v34** | Lineups on a pitch, xG for the European cups and 19 more competitions (smaller European leagues, second divisions, League One and Two), position fixes, the expected-lineup bug fix |
| **v35** (current) | **Faster bot alerts** (live alerts sent within the minute, lineup alerts the moment they're announced, no lost or repeated goal alerts); **team news** (injuries and press-conference news read by Claude, feeding the expected lineups); **pitch positions fixed** (away side mirrored, usual and announced positions, a playable shape); **European cups**: league-phase table, corners, cards, tackles, offsides and throw-ins; **website**: back button and swipes, Markets as advised bets against team averages with likeliest scorers and assisters, Players / Team stats / H2H tabs, past matches open with full statistics, every player tappable, transfer history; **match stats card** in play (ESPN, every minute) and at full-time (PitchAPI: xG, big chances, ratings, 1st / 2nd half), scoreboard with white scores |
| **v36** | **Free profiles** (Telegram and Google sign-in; the site stays fully usable without one), the **full live view** (in-play chances, momentum, win-probability graphs), the **installable app** (PWA); **more predicted leagues**: Championship, LaLiga Hypermotion (Segunda División), Ligue 2, Austria, Switzerland, Denmark, Norway and Sweden: each league's backtest (vs a naive guess and the bookmakers) runs in the weekly run, and only leagues that pass are published (result chances first; corners and cards only where the statistics exist) |
| **v37–v39** | **Basketball: NBA and EuroLeague** |
| **Then** | **Email sign-in** (needs a domain) and the **premium tier** |

## Decisions already made

- **Free tier:** fixtures, results, tables, team pages, basic home/draw/away chances with fair odds, expected and confirmed lineups, stats and trends, the Telegram channel, personal alerts and live alerts (with basic chances only).
- **Premium tier:** detailed probabilities (BTTS, over/under, scorelines, corners, cards), player props, match verdicts, today's best angles, more markets, the accumulator calculator, the live view, in-play chances and top angles in alerts.
- **Channel digest under premium:** basic chances plus one free pick per match, never that match's top angle (its second-best angle, else its safer angle).
- **Owner:** permanent premium for the admin Telegram account and kwallo.hq@gmail.com; a complimentary-premium list for testers and partners.
- **Public rules:** fair odds only, no bookmaker names or prices, 18+.
- **Language:** English only at launch (Nigerian Pidgin possibly later).
- **GitHub project stays private** (the model is the main asset).
- **Profiles are optional:** the website works fully without signing in (v36).
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
