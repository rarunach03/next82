# Next82

**Live site: https://next82.vercel.app** (the old GitHub Pages address redirects there)

Next82 forecasts how many games every NBA player will play this season (2026-27), explains
what drives each number, and turns it into fantasy basketball rankings.

## What's on the site

The site answers one question, "How many games will this player play, and why?", and its menus
follow that story: the forecast (Players), using it (Fantasy) and trusting it (How it works).
Five destinations:

- **All players** (`/`): every player by expected games, with views for who's injured (injury,
  expected return, source, games still expected) and who's worth stashing (`/?view=injured`,
  `/?view=stash`), plus a team filter.
- **Player pages** (`/player/:id`): one header with status, tier and a plain sentence on injury,
  return and games expected; then the forecast (preseason vs. updated, with ranges), what drives
  it, games by season, and details (injury sources, back-to-backs, comebacks when they apply).
- **Rankings** (`/rankings`) and **My roster** (`/roster`, which also tests trades) under Fantasy.
- **How it works** (`/how-it-works`): how the forecasts are made, how accurate they are, limits.

Injured players carry one "Injured" badge everywhere (its source shows on hover or tap), jargon has
short hover explanations, and the header shows how recent the data is. Old addresses (`/injured`,
`/stash`, `/trade`, `/about`, `/accuracy`) redirect to where their content lives now.

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
  ranked once they've played 5 games. A default column shows the value each player loses to
  expected missed games.
- **My roster.** Enter up to 13 players (saved in the browser) to see games left, likely ranges,
  tiers and value, plus 5,000 simulated rest-of-season outcomes for the roster (bad, typical and
  good season), plain-English risk flags, and safer players with similar production to swap in.
  "Test a trade" compares both sides' rest-of-season value and reruns the simulation and risk
  check for the roster after the trade; the trade lives in the link (`/roster?trade=1_2-for-3`).
- **Accuracy.** The frozen preseason forecast graded every day against games played so far,
  next to two simple guesses, with an honest "too early to tell" while the gap could be luck.
- **Injury adjustments.** The NBA's official injury report is read daily. Players listed Out with a
  serious injury (ACL, Achilles, labrum, meniscus, patellar tendon tear; foot, lower-leg, fibula,
  hand or wrist fracture; ankle dislocation; back surgery) get an automatic return estimate
  from cited recovery studies. Every 3 days an automatic news search (Claude Code, restricted to web
  search and one file) looks for team-announced timelines, which override the estimate; manual
  adjustments cover the rest. Each is labeled on the site with its sources.
- **Game by game (beta).** The chance each player plays each of their team's next games, from a
  second model (`game_level.py`) trained on every player-game since 2000-01, calibrated on
  2023-24 and tested on 2024-25 and 2025-26 (log loss 0.385 vs. 0.511 and 0.745 for two simple
  play-rate guesses; calibration error 0.012). The live injury report overrides it (Out, or before
  an expected return: under 5%). Player pages show the next five games and My Roster this week's
  expected games. Shown only while `config.GAME_LEVEL_BETA` is on and every quality gate in
  `models/game_level_metrics.json` passes; if the daily step fails, the site hides it.
- **Back-to-backs.** On player pages: how many each team has left and each player's chance of
  sitting the second night.

Data from NBA.com. Unofficial, non-commercial student project, not affiliated with the NBA or its
teams. No ads or paid features.

## How accurate is it?

| Forecast | Tested on | Average miss | Best simple guess |
|---|---|---|---|
| Season model, current (LightGBM + linear blend) | 2024-25, 2025-26 | 15.4 games | 17.2 (3-season average) |
| Season model behind the frozen 2026-27 preseason forecasts (LightGBM) | 2024-25, 2025-26 | 15.6 games | 17.2 |
| Updated forecast (rest of season) | 2024-25, 2025-26 | 7.5 games | 8.0 (pace/preseason blend) |
| Updated forecast, players currently out 5+ games | 2024-25, 2025-26 | 6.5 games | 7.6 (current pace) |
| Comeback players, games if healthy | 2001-02 to 2025-26 | 15.1 games | 23.2 (3-season average) |

"Tested on" is the season being forecast (each season-model forecast uses data through the season
before). Settings and feature choices were made on separate validation seasons, so the test seasons
only measure accuracy. Half of preseason forecasts land within about 11 games (11.3 for the frozen
model, 11.5 for the blend). Comeback players are scored season by season, each season predicted by
models trained only on earlier ones.

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
python -m next82.improve ablation  # season model: ablation, candidates, tune, finalize, final (once)
python -m next82.game_level    # game-by-game beta: player-game rows, model, quality gates
python -m next82.export        # write the website's data (web/public/data/)
pytest                         # tests
cd web && npm test             # website logic tests (roster, trades, views, menus, redirects)
```

The frozen files (`data/processed/preseason_*.parquet`) can't be overwritten; delete them only
when starting a new season. The latest finished season moves forward on its own each May 1;
until the pipeline is rerun, the site says newer data is available. Set
`NEXT82_LAST_SEASON=2025` to pin a season.

## Daily updates

The refresh is split in two, because stats.nba.com doesn't answer cloud servers (tested from
GitHub's Linux, macOS and Windows runners, with browser headers, long timeouts, retries, IPv6 and
HTTP/2: `.github/workflows/cloud-probe*.yml` re-tests). Everything else runs in the cloud.

**The Mac: the NBA stats.** `scripts/refresh.sh` downloads current rosters, the draft order,
positions, the schedule and this season's game logs (`python -m next82.data --current --stats-only`,
each call retried with backoff), runs the news step when it's due (`scripts/news_timelines.sh`,
below; if it fails the stats still go out), and commits and pushes those raw files. A launchd job
(`com.next82.refresh`) runs it every hour and at login from a separate copy of the repo (macOS
doesn't let background jobs into the Desktop folder); launchd runs a missed hour on wake. It does
the work once per "NBA day", which starts at 4 am Eastern so the night's late games are final, and
shows a macOS notification if a run fails (it retries the next hour).

**GitHub Actions: everything else.** `.github/workflows/refresh.yml` reads the latest official
injury report, runs the news step if the `CLAUDE_CODE_OAUTH_TOKEN` secret is set, runs
`python -m next82.export` (updated forecasts, automatic injury adjustments, ranges, tiers, fantasy
values including rookies, back-to-backs, the stash list, the game-by-game beta and accuracy),
checks the result (`scripts/check_site_data.py` and the full pytest suite), and commits the site
data only if something changed. It runs when the Mac pushes stats, when someone pushes
`data/news_timelines.csv` or `data/overrides.csv`, at 5:20 am and 4:40 pm Eastern (so injuries stay
current while the Mac is off), and by hand from the Actions tab. If any step fails, the run fails
(GitHub emails the owner) and nothing is committed: the site keeps the last good data. Each run
re-enables the workflow, so GitHub's 60-day inactivity rule can't switch the schedule off in the
off-season.

Each push redeploys the site on Vercel (https://next82.vercel.app, built from `web/`); the old
GitHub Pages address only redirects there (`.github/workflows/deploy-pages.yml`, `pages-redirect/`).
If the stats or the site data are more than two days old, the site says so next to the "games
thru" date (`web/src/freshness.ts`).

Run either half by hand:

```bash
./scripts/refresh.sh --force           # on the Mac
gh workflow run refresh.yml            # in the cloud (add -f news=force to force the news search)
```

To move the news search to the cloud too, run `claude setup-token` and store the token with
`gh secret set CLAUDE_CODE_OAUTH_TOKEN`. The schedule is shared (`data/news_state.json`), so it
won't run twice.

## Injury adjustments

The updated forecast can't read injury news on its own, so three kinds of adjustment change it
(fantasy values and tiers use them; the preseason forecast, the accuracy grading and the model's test
metrics never do). All use the same math: games played so far plus the model's share of the team's
games from the return window onward; the earliest return sets the high end of the range and the
latest return the low end (0 more games if there's no latest return, e.g. when it could be
season-ending).

1. **Automatic, from the NBA's official injury report** (`next82.injuries`, `next82.auto_overrides`).
   Each cloud refresh reads the latest report and stores only the parsed facts (player, status,
   reason, body part, injury type, report time and link), never the PDF. The season's log keeps one
   report per day (the latest read that day); days the refresh missed are filled in from the NBA's
   archive with that day's final report (up to 30 days back). A player listed Out with a
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
   `data/news_state.json`, committed so the schedule holds wherever the search runs. Claude Code runs in a temporary folder holding only a copy of the
   news file, with `--restricted --tools WebSearch,WebFetch,Read,Edit`, Read and Edit allowed only on
   that file, and `--permission-mode dontAsk` (no shell, no other files, no git). It's told to add a
   row only when a dated source clearly states a timeline, never to guess, and that "out for the
   season" means a return after the regular season ends. Its rows are then checked in Python (right
   columns, a player it was asked about, valid dates after the injury and the source, a source URL
   that resolves); valid rows are merged, bad ones rejected, and every added, changed or rejected row
   is printed to the refresh log. Timeout 25 minutes, budget cap $10 a run. It uses `NEXT82_CLAUDE` if
   set, then the standalone install (`~/.local/bin/claude`), then `claude` on the PATH, then the copy
   bundled with the VS Code extension. A news timeline applies while the player is listed Out and
   lapses once its return window has passed.
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
  via nba_api, plus this season's games. Official injury reports only go back to 2019-20 (they feed
  the updated forecast, below), so the season model finds long absences by matching each player's
  game log against their team's schedule.
- **Season model** (`train.py`): 0.8 LightGBM + 0.2 linear regression on 12,300 past
  player-seasons (the blend misses less than either alone; this season's frozen preseason
  forecasts came from LightGBM alone). The target is the share of the schedule played, so
  shortened seasons compare fairly. 27 inputs: age, experience, minutes, games played in each of
  the last three seasons, long absences, games missed at the start or end of a season, and
  comeback inputs. SHAP values explain each forecast (exactly, for both parts of the blend).
- **Improving it** (`improve.py`): every choice on five rolling validation seasons (forecasting
  2019-20 to 2023-24), the test seasons read once at the end. Ablation: minutes and workload matter most on
  top of everything else, then absences; past games played is the strongest group on its own.
  Six new feature groups were tried and none kept (`models/improve.json`, `models/ablation.png`).
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
  models.py        baselines, ridge regression, LightGBM, the blend, quantile models
  evaluate.py      train/test split and error measures
  train.py         preseason models, evaluation, forecasts and ranges
  improve.py       season-model ablation, candidate features, tuning, one-time final test
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
  injury_features.py  does adding injury-report features help the updated forecast?
  game_level.py    game-by-game availability (beta): model, quality gates, upcoming games
  back_to_back.py  back-to-back rest rates
  explain.py       SHAP factors with readable labels
  export.py        the website's data (the only way data reaches the site)
web/               React site (Vite, TypeScript, Tailwind, Recharts); data in public/data/
  src/roster/      My roster logic: simulation, risk flags (rules in flags.ts), swaps, trades
  src/nav.ts       header menus; redirects.ts sends old addresses on; playerViews.ts the All players views
scripts/           refresh.sh (the Mac's daily stats download), news_timelines.sh (news search),
                   check_site_data.py (checks an export), cloud_probe.py (which sources the cloud reaches)
data/, models/     committed: frozen forecasts, current-season data, LightGBM models (text format)
app/               the original Streamlit app (internal)
tests/             pytest; tests needing the full downloaded data skip themselves
```

## Limitations

- The updated forecast sees injury-report status (listed Out, serious injury type, trend) but not
  recovery timelines; those enter through the adjustments above: recovery studies for serious
  injuries, team timelines from the news search for any injury, and manual adjustments. Injuries
  with none of these are left to the model. Rookies' updated forecasts use the model without these
  inputs (they made rookie forecasts worse on validation). This season's report log runs from Oct 26, 2026 (the
  Oct 30 to Nov 11 days the refresh missed were filled in from the NBA's archive).
- Injury start dates are estimated from the last game played, so a preseason injury can look older
  than it is (a still-out player past the typical recovery is treated as "back any day").
- Forecasts assume the player is in the league. Players not on a roster who haven't played get
  no updated forecast.
- The preseason edge over simple guessing is real but modest (15.6 games for this season's frozen
  forecasts, 15.4 for the current model, vs 17.2 for the best simple guess).
- Comeback forecasts can't see injury type or medical clearance.
- The news search only finds what's published and stated clearly; vague reports ("no timeline",
  "day to day") add nothing, and unless the cloud has a Claude token it runs on the Mac, so it
  pauses when the Mac is off.

## Next up

- **A data-use agreement with the NBA.** NBA.com's terms limit its statistics to news reporting or
  private, non-commercial use and require consent for a website built around a database; this
  project proceeds as a non-commercial student project with attribution.
- **NBA-specific recovery studies** where the table borrows from the NFL (fibula fractures, ankle
  dislocations, patellar tendon tears), and rows for concussions, plantar fascia and knee surgeries
  of unknown type, so more injuries get automatic estimates.
- **Moving the stats download off the Mac** if stats.nba.com ever answers cloud servers (the rest
  of the refresh already runs in GitHub Actions).
- **Grading the updated forecast** at the end of the season, alongside the preseason one.
