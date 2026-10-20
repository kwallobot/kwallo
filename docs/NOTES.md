# Kwallo: roadmap and decisions

*Last updated: 20 October 2026 (v34).*

## Roadmap

| Version | Contents |
|---|---|
| **v32** | The Kwallo website on Cloudflare Pages, private dashboard, kick-off alerts, full player statistics, per-group calibration, UI fixes |
| **v33** | Live filter and live scores, collapsible competition cards, collapsible Leagues, match header and tabs, every market, "Follow this match" |
| **v34** (current) | Lineups on a pitch, xG for the European cups and 19 more competitions (smaller European leagues, second divisions, League One and Two), position fixes, the expected-lineup bug fix |
| **v35** | **Free profiles** (Telegram and Google sign-in), the **full live view** (in-play chances, momentum, win-probability graphs), the **installable app** (PWA) |
| **v36–v38** | **Basketball: NBA and EuroLeague** |
| **Then** | **Email sign-in** (needs a domain) and the **premium tier** |

## Decisions already made

- **Free tier:** fixtures, results, tables, team pages, basic home/draw/away chances with fair odds, expected and confirmed lineups, stats and trends, the Telegram channel, personal alerts and live alerts (with basic chances only).
- **Premium tier:** detailed probabilities (BTTS, over/under, scorelines, corners, cards), player props, match verdicts, today's best angles, more markets, the accumulator calculator, the live view, in-play chances and top angles in alerts.
- **Channel digest under premium:** basic chances plus one free pick per match, never that match's top angle (its second-best angle, else its safer angle).
- **Owner:** permanent premium for the admin Telegram account and kwallo.hq@gmail.com; a complimentary-premium list for testers and partners.
- **Public rules:** fair odds only, no bookmaker names or prices, 18+.
- **Language:** English only at launch (Nigerian Pidgin possibly later).
- **GitHub project stays private** (the model is the main asset).
- **Not doing:** goal-kick markets (no source records goal kicks).
- **ClubElo switched off** (its service is usually down; it only fed one experiment, never adopted).
- **NPFL 2026/27:** Inter Lagos FC and Ranchers Bees confirmed as promoted (they start with promoted-side ratings).

## Open items

- **Domain:** kwallo.com and kwallo.app are taken. Candidates: **kwallo.ng** (about $48/year) plus **kwallo.com.ng** (about $5/year), or **getkwallo.com**. Email sign-in (v33) needs a domain.
- **Before a wide public launch:** Nigerian legal review (predictions site, NDPA data protection, profiles, later paid subscriptions); trademark checks and registering Kwallo with the logo; data-source terms for public display (ESPN, BSD, football-data.co.uk, Understat, FPL; PitchAPI already confirmed).
- **Scaling:** Cloudflare Workers Paid (about $5/month) once live alerts reach hundreds of followers per match.
- **GitHub minutes:** watch usage; lower `LINEUP_DAILY_MAX` (Worker variable) if it gets tight.

## Basketball data sources (evaluated October 2026)

| Source | What it offers | Verdict |
|---|---|---|
| **nba_api** (github.com/swar/nba_api) | Python client for NBA.com stats and live data (box scores, play-by-play, game logs, live scoreboard). MIT-licensed; NBA.com's terms apply; endpoints change without notice; reportedly slow or blocked from cloud servers (to test from GitHub) | **Main NBA source** |
| **hoopR** (sportsdataverse) | R package wrapping NBA Stats, ESPN and more, with bulk-data loaders (NBA play-by-play 2002–2026) from the sportsdataverse data repositories | **Use its bulk files from Python** for the history backfill |
| **ESPN** (as used for football) | NBA fixtures, scores, injuries, some odds | **Backup and cross-check** |
| **Playbook API** (api.playbook-api.com) | NBA/NFL/MLB/NHL/college: odds, lines, player props, injuries, public betting splits, team stats. Terms allow use in apps, including paid ones. Free 500 requests/month; Starter $39.99/month (25,000) | **Trial in the basketball probe** for NBA injuries and props lines (private comparison only) |
| **ParlayAPI** (parlay-api.com) | Odds aggregator, a the-odds-api replacement with player props and prediction markets. Free 1,000 requests/month; paid $5–200/month | Alternative for NBA props lines; compare with Playbook |
| **PropLine** | Props-focused odds API; free 500 requests/day; grades props against box scores | Alternative for props lines |
| **SportyApi** (sportyapi.com) | Scores and schedules only (7 feeds); $9/month after a 14-day trial; appears to repackage ESPN | **Not needed** |
| **Postgame-Stats-Api** (github.com/csyork19) | Small self-hosted Flask wrapper over NBA data | **Not needed** (use nba_api directly) |
| **SportyBet "API"** (unofficial, on a scraping marketplace) | Scraped SportyBet odds | **Avoid** (terms risk); private use only if ever |
| **EuroLeague** | Official data feed | **To check** in the probe |

**Plan:** start basketball with a probe from GitHub's servers (nba_api, the sportsdataverse files, ESPN NBA, the EuroLeague feed, and a free Playbook API key), then choose sources based on what actually works.
