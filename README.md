# Next82

**Live site: https://rarunach03.github.io/next82/**

Next82 forecasts how many games every NBA player will play this season (2026-27), explains
what drives each number, and turns it into fantasy basketball rankings.

## What's on the site

Each page leads with one plain answer and keeps the details a click away. Player pages open with
"Expected to play about X games (likely A–B)" from the updated forecast and one sentence on status,
injury, return estimate and games expected; the preseason forecast, its factors and the injury
adjustment's kind and sources are under Details. Injured players carry one "Injured" badge
everywhere (its source shows on hover or tap), jargon has short hover explanations, and the menu is
Players (all players, who's injured), Fantasy (rankings, trade analyzer, who to stash) and How it
works (accuracy, about). Rankings show rank, player, status, games left and value, with the rest
behind "More columns".

- **Preseason forecast.** Games each player will play this season, made before opening night
  (Oct 20, 2026) and frozen. It never changes, so it can be graded honestly. Each forecast
  comes with the factors behind it, in games. Players coming back from a missed season get two
  numbers instead: games if healthy, and the chance of a setback (fewer than 20 games).
- **Updated forecast.** Refreshed every day during the season: games played so far plus a fresh
  prediction for the games left. If a player gets hurt in November, this number drops; the
  preseason one doesn't.
- **Likely ranges.** Both forecasts show a likely range (10th to 90th percentile). On past
  seasons, 80% of real outcomes landed inside these ranges, and ranges are wide early in the
  season and narrow as it goes on.
- **Availability tiers.** Safe, Moderate or Risky, from the low end of the updated forecast's
  range: Safe if even a bad outcome is 45+ games, Risky if it's under 20. Only for players in a
  rotation role, since a bench player's games depend more on the coach than on health.
- **Fantasy rankings.** Per-game production (this season blended with the last three, so a hot
  start doesn't take over) times forecast games, measured above replacement level (the
  156th-best player per game, roughly the best free agent). Rest-of-season value by default,
  full-season as a second view; ESPN points, Yahoo points and 9-category leagues. Rookies are
  ranked once they've played 5 games.
- **Accuracy page.** The frozen preseason forecast graded every day against games played so far,
  next to two simple guesses, with an honest "too early to tell" while the gap could be luck.
- **Injury adjustments.** The NBA's official injury report is read daily. Players listed Out with a
  serious injury (ACL, Achilles, labrum, meniscus, patellar tendon tear; foot, lower-leg, fibula,
  hand or wrist fracture; ankle dislocation; back surgery) get an automatic return estimate
  from cited recovery studies. Every 3 days an automatic news search (Claude Code, restricted to web
  search and one file) looks for team-announced timelines, which override the estimate; manual
  adjustments cover the rest. Each is labeled on the site with its sources.
- **Fantasy tools.** A trade analyzer (rest-of-season value of two sides, shareable by link), a
  "who to stash" list of injured players worth holding, and back-to-back counts with each player's
  chance of sitting the second night.

Data from NBA.com. Unofficial, non-commercial student project, not affiliated with the NBA or its
teams. No ads or paid features.

## How accurate is it?

| Forecast | Tested on | Average miss | Best simple guess |
|---|---|---|---|
| Preseason forecast (full season) | 2023-24, 2024-25 | 15.6 games | 17.2 (3-season average) |
| Updated forecast (rest of season) | 2024-25, 2025-26 | 7.6 games | 8.1 (pace/preseason blend) |
| Updated forecast, players currently out 5+ games | 2024-25, 2025-26 | 6.6 games | 7.6 (current pace) |
| Comeback players, games if healthy | 2000-01 to 2022-23 | 15.3 games | 23.4 (3-season average) |

Settings and feature choices were made on separate validation seasons, so the test seasons
only measure accuracy. Half of preseason forecasts land within 11 games.

## Setup

```bash
brew install libomp            # macOS only, required by LightGBM
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
cd web && npm install && cd ..
```

Everything the website needs is committed, so after setup this runs straight away:

```bash
cd web && npm run dev          # http://localhost:5173
```

## Rebuild everything from scratch

```bash
python -m next82.data          # download 30 seasons + current rosters, games so far, draft (~6 min)
python -m next82.features      # player-season table
python -m next82.train         # preseason models, accuracy tests, forecasts and ranges (~1 min)
python -m next82.preseason --freeze --freeze-ranges   # freeze them; once per season, before opening night
python -m next82.in_season     # updated-forecast model: snapshots, validation, test (~2 min)
python -m next82.fantasy       # fantasy prior and how much to shrink this season's stats
python -m next82.rookies       # rookie baseline by draft range, shrinkage and games method
python -m next82.back_to_back  # back-to-back rest rates and their validation
python -m next82.auto_overrides  # each player's last game before the season (for injury start dates)
python -m next82.injury_history  # past injury reports for the model (downloaded once, cached)
python -m next82.injury_features # do injury-report features improve the updated forecast?
python -m next82.export        # write the website's data (web/public/data/)
pytest                         # tests
```

The frozen files (`data/processed/preseason_*.parquet`) can't be overwritten; delete them only
when starting a new season. The latest finished season moves forward on its own each May 1;
until the pipeline is rerun, the site says newer data is available. Set
`NEXT82_LAST_SEASON=2025` to pin a season.

## Daily updates

`scripts/refresh.sh` downloads current rosters, this season's game logs, the schedule, the draft
order and the latest official injury report,
runs `python -m next82.export` (updated forecasts, automatic injury adjustments, ranges, tiers,
fantasy values including rookies, back-to-backs, the stash list and accuracy), and commits and pushes if anything changed. Each push redeploys the site
through GitHub Actions (`.github/workflows/deploy-pages.yml`). After the injury report is read, it
runs the news step (`scripts/news_timelines.sh`, below); if that fails or times out, the refresh
carries on. If `data/news_timelines.csv` or `data/overrides.csv` changed since the last refresh, it
re-exports and pushes even on a day it already ran.

The refresh runs on a home computer, not in the cloud: stats.nba.com doesn't respond to cloud
servers. On the project's Mac a launchd job runs it hourly from a separate copy of the repo (macOS
doesn't let background jobs into the Desktop folder): the full refresh happens once a day, and on
later runs that day it only re-exports and pushes if `data/news_timelines.csv` or
`data/overrides.csv` changed.
Run it by hand any time:

```bash
./scripts/refresh.sh
```

## Injury adjustments

The updated forecast can't read injury news on its own, so three kinds of adjustment change it
(fantasy values and tiers use them; the preseason forecast, the accuracy page and the model's test
metrics never do). All use the same math: games played so far plus the model's share of the team's
games from the return window onward; the earliest return sets the high end of the range and the
latest return the low end (0 more games if there's no latest return, e.g. when it could be
season-ending).

1. **Automatic, from the NBA's official injury report** (`next82.injuries`, `next82.auto_overrides`).
   The refresh reads the latest report once a day and stores only the parsed facts (player, status,
   reason, body part, injury type, report time and link), never the PDF. A player listed Out with a
   serious type in `data/recovery_table.csv` gets an estimated return: injury start + the fast end of
   real NBA recoveries for that injury, with no latest return if it can be season-ending. The injury
   start is the later of his last game and his first listing with this injury, unless he was already
   listed Out with an injury on the last regular-season day or on his team's last playoff game day;
   then it's his last game, playoffs included. Short-term
   statuses (illness, rest, soreness, sprains, strains) are left to the model. Reports only list teams
   about to play, so each player's status is his team's most recent listing; the override clears when
   that listing drops him or he plays again. Unclassified reasons and unmatched names are logged.
2. **Team timelines from news**: `data/news_timelines.csv` replaces the automatic estimate (it's no
   longer an estimate), and is shown as "Team timeline" with its source. Format, one row per player
   (if there are several, the most recently found is used):

   | column | meaning |
   |---|---|
   | `player_id` | NBA player ID (as in the site's player URLs) |
   | `earliest_return` | YYYY-MM-DD, earliest announced return (or the re-evaluation date) |
   | `latest_return` | YYYY-MM-DD, optional |
   | `note` | the announced timeline in plain words |
   | `source_url` | link to the news story |
   | `date_found` | YYYY-MM-DD the row was added |
   | `source_date` | YYYY-MM-DD the source was published |

   It applies while the player is listed Out on the report, or when it was found after the player's
   manual row was added (then it replaces the manual row, which stays as the fallback).

   **Automatic news search** (`next82.news`, `scripts/news_timelines.sh`): Claude Code in
   non-interactive mode (`claude -p`) searches for team-announced or major-outlet timelines for every
   player listed Out with an injury on the latest report, plus anyone with a manual or automatic
   override. It skips players who got a news row in the last 7 days unless their report status
   changed. It runs when 3 or more days have passed since the last run, right away when a new player
   is listed Out with a serious injury type, or with `--force`; the state lives in
   `.git/next82-news-state.json`. Claude Code runs in a temporary folder holding only a copy of the
   news file, with `--restricted --tools WebSearch,WebFetch,Read,Edit`, Read and Edit allowed only on
   that file, and `--permission-mode dontAsk` (no shell, no other files, no git). It's told to add a
   row only when a dated source clearly states a timeline, never to guess, and that "out for the
   season" means a return after the regular season ends. Its rows are then checked in Python (right
   columns, a player it was asked about, valid dates after the injury and the source, a source URL
   that resolves); valid rows are merged, bad ones rejected, and every added, changed or rejected row
   is printed to the refresh log. Timeout 25 minutes, budget cap $10 a run. It finds `claude` on the
   PATH, then the copy bundled with the VS Code extension (`NEXT82_CLAUDE` overrides).
3. **Manual**: `data/overrides.csv` wins over the automatic estimate and over news found before
   the manual row was added: `player_id, player_name, status, earliest_return,
   latest_return, estimated, note, source_url, source_url_2, date_added, review_by` (return dates and
   the second source optional; `estimated` = yes for our own estimate). Use it when the report is less
   specific than the news. The site and the refresh log flag a manual row past its review-by date.

**Recovery table** (`data/recovery_table.csv`): each serious injury type, the average return from a
cited study (NBA where one exists, otherwise other pro leagues), the fast end used as the earliest
return (average minus one standard deviation, or the lower quartile, when the study reports a spread;
otherwise 80% of the average), the latest return (average plus one standard deviation, or 1.5 times
the average without a spread; none if it can be season-ending), and whether it can be season-ending.
`body_part_contains` limits a row to body parts containing one of its `|`-separated words; the first
matching row wins. Finger, thumb and other minor versions are left to the model. Stress fractures are
classified as fractures too, so a tibia or fibula stress fracture gets the traumatic-fracture estimate.

## How it works

- **Data:** regular-season stats, bios and game logs for 1996-97 to 2025-26 from stats.nba.com
  via nba_api, plus this season's games. There's no public injury data, so long absences come
  from matching each player's game log against their team's schedule.
- **Preseason model** (`train.py`): LightGBM on 12,300 past player-seasons. The target is the
  share of the schedule played, so shortened seasons compare fairly. 27 inputs: age, experience,
  minutes, games played in each of the last three seasons, long absences, games missed at the
  start or end of a season, and comeback inputs. SHAP values explain each forecast.
- **Updated forecast** (`in_season.py`): trained on snapshots of every player every 14 days
  through 26 past seasons, each using only games before its date. Inputs add games played and
  missed so far, the current absence streak, recent games and team games left.
- **Ranges** (`intervals.py`): LightGBM quantile models, corrected on a validation season so 80%
  of outcomes land inside; the updated forecast's correction is set separately for each third of
  the season.
- **Fantasy** (`fantasy.py`, `rookies.py`): per-game stats from the last three seasons weighted
  3:2:1, blended with this season's as (season totals + 6 × prior per game) / (games + 6). The 6
  was chosen on a validation season. Rookies are blended with past rookies from their draft range
  (weight 3), and their games come from the updated-forecast model.
- **Accuracy** (`accuracy.py`): each player's games so far against what their forecast implied for
  that many team games, with a resampled 95% range for the gap to the best simple guess.
- **Injury features in the model** (`injury_history.py`, `injury_features.py`): from official injury
  reports published before each snapshot date (2019-20 on; missing before): listed Out, status level,
  serious injury type, Out a week earlier, status trend, rough days listed. Today's values come from
  this season's report log. Decided by rolling validation, each season trained only on earlier ones:
  average over 2021-22, 2022-23 and 2023-24, MAE 7.065 -> 7.047 games; for players listed Out whose
  absence streak is under 3 games (what the features are for) 7.767 -> 7.724; coverage 80% -> 79%.
  Kept. The test seasons, scored once after deciding: 7.644 -> 7.542, coverage 81% -> 80% (the
  listed-Out group was slightly worse there, 8.316 -> 8.357). The model settings are still chosen
  without these features (re-tuning with them made the ranges much wider than needed). The features
  also cut the old model's over-forecast for healthy players early in recent seasons. Rookies use the
  model without them (`models/in_season_no_injury.txt`): with them, rookie validation got worse
  (5.79 -> 6.17 games).
- **Back-to-backs** (`back_to_back.py`): a player "rested" when they missed the second night but played
  the next game; rates from the last three seasons, pulled toward the league average (9.8%) as if the
  league rate were 40 extra back-to-backs. Shown on the site; not added to the forecast, because it
  made validation slightly worse (7.122 -> 7.133 games).

## Layout

```
src/next82/
  config.py        paths, seasons, cutoffs
  data.py          nba_api downloads (history, rosters, games so far, draft)
  features.py      player-season table
  models.py        baselines, ridge regression, LightGBM, quantile models
  train.py         preseason models, evaluation, forecasts and ranges
  preseason.py     freezing and loading the preseason forecast
  in_season.py     updated (rest-of-season) forecast
  intervals.py     likely ranges, calibration, availability tiers
  fantasy.py       per-game production, scoring, value above replacement
  rookies.py       rookie baseline and rankings
  accuracy.py      grading the preseason forecast during the season
  injuries.py      the NBA's official injury report: fetch, parse, classify, match
  auto_overrides.py  automatic return estimates from the report and recovery table
  news.py          automatic news search for team timelines (Claude Code, validated)
  injury_history.py  past injury reports for model features
  back_to_back.py  back-to-back rest rates
  explain.py       SHAP factors with readable labels
  export.py        the website's data (the only way data reaches the site)
web/               React site (Vite, TypeScript, Tailwind, Recharts); data in public/data/
scripts/           refresh.sh (daily update), news_timelines.sh (news search)
data/, models/     committed: frozen forecasts, current-season data, LightGBM models (text format)
app/               the original Streamlit app (internal)
tests/             pytest; tests needing the full downloaded data skip themselves
```

## Limitations

- The model sees injury-report status (listed Out, serious injury type, trend) but not recovery
  timelines; those enter through the adjustments above, and only for injuries with a cited recovery
  study (others are logged and left to the model). This season's report log starts on Oct 26, 2026,
  so the week-earlier features fill in from Nov 3.
- Injury start dates are estimated from the last game played, so a preseason injury can look older
  than it is (a still-out player past the typical recovery is treated as "back any day").
- Forecasts assume the player is in the league. Players not on a roster who haven't played get
  no updated forecast.
- The preseason edge over simple guessing is real but modest (15.6 vs 17.2 games).
- Comeback forecasts can't see injury type or medical clearance.
- The news search only finds what's published and stated clearly; vague reports ("no timeline",
  "day to day") add nothing, and it runs on the Mac, so it pauses when the Mac is off.

## Next up

- **A data-use agreement with the NBA.** NBA.com's terms limit its statistics to news reporting or
  private, non-commercial use and require consent for a website built around a database; this
  project proceeds as a non-commercial student project with attribution.
- **NBA-specific recovery studies** where the table borrows from the NFL (fibula fractures, ankle
  dislocations, patellar tendon tears), and rows for concussions, plantar fascia and knee surgeries
  of unknown type, so more injuries get automatic estimates.
- **Checking news rows against the injury report**: a news row stays until it's replaced; it could
  also expire when the player is back in the lineup.
- **Moving the refresh off the Mac** if stats.nba.com ever answers cloud servers.
- **Grading the updated forecast** at the end of the season, alongside the preseason one.
