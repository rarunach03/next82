import { useEffect } from 'react'
import { Link, useLocation } from 'react-router'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import CalibrationChart from '../components/CalibrationChart'
import { baselineText, shortDate, useAccuracy, useGames } from '../data'
import type { Ablation, AccuracyMethod, GameBetaModel, Meta, SeasonAccuracy } from '../types'

// Categorical slots 1-3 of the project's validated dark palette (colorblind-safe on
// the dark surface, all pairs); the forecast takes the orange to match the site accent.
const COLORS: Record<AccuracyMethod, string> = {
  last_season: '#3987e5',
  model: '#d95926',
  three_year: '#199e70',
}
const ORDER: AccuracyMethod[] = ['model', 'three_year', 'last_season']

const PARTS = [
  { id: 'method', title: 'How the forecasts are made' },
  { id: 'accuracy', title: 'How accurate they are' },
  { id: 'limits', title: 'Limits' },
] as const

/** How the forecasts are made, how accurate they are (on past seasons and graded daily this season), and their limits. */
export default function HowItWorks({ meta }: { meta: Meta }) {
  const a = meta.accuracy
  const season = useAccuracy()
  const games = useGames(meta.gameBeta === true)
  const { hash } = useLocation()
  // Linked to a part (/how-it-works#accuracy): scroll there, again once this season's grading has loaded.
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView()
  }, [hash, season, games])

  return (
    <article className="pt-10 pb-16">
      <p className="text-sm font-semibold tracking-widest text-accent uppercase">How it works</p>
      <h1 className="mt-2 font-display text-5xl leading-none font-extrabold tracking-tight uppercase">How Next82 works</h1>
      <div className="max-w-2xl">
      <p className="mt-4 text-lg text-muted">
        Next82 forecasts how many games every NBA player will play in {meta.forecastSeason}, shows what's driving each
        number, and turns it into fantasy rankings. Availability shapes team decisions, fantasy leagues and what fans
        can expect, but most tools only report injuries after they happen.
      </p>
      </div>
      <nav aria-label="On this page" className="mt-6 flex flex-wrap gap-2">
        {PARTS.map((p) => (
          <a
            key={p.id}
            href={`#${p.id}`}
            className="rounded-lg border border-line px-3 py-1.5 text-sm text-muted transition hover:border-accent hover:text-ink"
          >
            {p.title}
          </a>
        ))}
      </nav>

      <Part id="method" title="How the forecasts are made">
      <Section title="Two forecasts">
        <p>
          <strong className="text-ink">The preseason forecast</strong> was made before opening night and is frozen: it
          never changes, so it can be graded honestly. Each one comes with the factors behind it, in games.
        </p>
        <p>
          <strong className="text-ink">The updated forecast</strong> is refreshed every day: games played so far plus a
          fresh prediction for the games left. If a player gets hurt in November, the updated forecast drops; the
          preseason one doesn't. It's the number player pages lead with ("Expected to play about X games"), with the
          preseason forecast and what drives it right below.
        </p>
        <p>
          Players coming back from a lost season get two preseason numbers instead of one. Comebacks tend to go one of
          two ways, so a single number would land in between and rarely be right: there's a forecast if they stay
          healthy, and the chance of a setback (fewer than {meta.setbackGames} games), plus the most similar past
          comebacks.
        </p>
      </Section>

      <Section title="Likely ranges and availability tiers">
        <p>
          Every forecast comes with a likely range: on past seasons, 8 in 10 real outcomes landed inside it. Ranges are
          wide early in the season, when anything can happen, and narrow as the games pile up. The preseason ranges were
          added on October 26, 2026, a week into the season, using preseason data only.
        </p>
        <p>
          The availability tier comes from the low end of the updated forecast's range: <em>Safe</em> if even a bad
          outcome is {meta.tierSafeLow}+ games, <em>Risky</em> if it's under {meta.setbackGames}, <em>Moderate</em> in
          between. On past seasons, Safe players fell short of {meta.tierSafeLow} games about 3% of the time. Tiers are
          only for players in a rotation role, since a bench player's games depend more on the coach than on health.
        </p>
      </Section>

      <Section title="Injury news">
        <p>
          The updated forecast's model sees who's listed on the NBA's official injury report (and how that changed over
          the past week), but not how long an injury takes to heal. So recovery timelines come in three ways, each
          labeled on the player's page with its sources. The injury report is read every day; a player listed Out with a
          serious injury (a torn ACL, an Achilles or patellar tendon rupture, a labrum or meniscus tear, a broken foot,
          leg, hand or wrist, a dislocated ankle, back surgery) gets an automatic return estimate based on how fast pro
          athletes (NBA players, where studied) have come back from that injury in published studies. A timeline the
          team announces replaces that estimate and is shown as a team timeline: every three days an AI assistant
          searches the news for announced timelines (only ones a dated source states clearly), and each is checked
          before it's used. A few cases are adjusted by hand when the news says more than the report; a newer team
          timeline replaces those too.
        </p>
        <p>
          These adjustments change the updated forecast, fantasy values and tiers. They never change the preseason
          forecast or the accuracy numbers, which stay model-only. Short-term things like illness, rest or a sprained
          ankle are left to the model.
        </p>
      </Section>

      <Section title="Fantasy rankings">
        <p>
          A player's fantasy value is their per-game production times the games they're forecast to play. Per-game
          production blends this season with the last three, so a hot start over a handful of games doesn't take over.
          Value is measured above replacement level, the 156th-best player per game (roughly the best free agent in a
          12-team league), so missing games always costs a player worth rostering.
        </p>
        <p>
          <Link to="/rankings" className="text-accent">
            Rankings
          </Link>{' '}
          show rest-of-season value by default, with full-season value as a second view, for ESPN points, Yahoo points
          and 9-category leagues. Rookies are ranked once they've played 5 games: their stats are blended with past
          rookies from the same draft range.
        </p>
      </Section>

      <Section title="Fantasy tools">
        <p>
          <Link to="/roster" className="text-accent">
            My roster
          </Link>{' '}
          takes your fantasy team and simulates the rest of the season 5,000 times to show a bad, typical and good
          outcome, flags risks in plain English, suggests safer players with similar production, and tests trades: each
          side's rest-of-season value with likely ranges, and how your roster's outlook changes. Trades get a link you can
          share. The{' '}
          <Link to="/?view=stash" className="text-accent">
            Worth stashing
          </Link>{' '}
          view of All players lists players who are out now but worth holding, by their value after they return, and the
          rankings show how much value each player loses to expected missed games. Player pages also show how many
          back-to-backs each team has left and how often a player sits the second night (from the player's last three
          seasons, pulled toward the league average because the samples are small).
        </p>
      </Section>

      {games && <GameBetaSection model={games.model} />}

      <Section title="The data">
        <p className="text-ink">
          Data from NBA.com. Unofficial, non-commercial student project, not affiliated with the NBA or its teams. There
          are no ads or paid features.
        </p>
        <p>
          Thirty regular seasons of NBA stats, from 1996-97 through {meta.dataThrough}, plus this season's games, from
          stats.nba.com via the open-source nba_api library. Injury statuses come from the NBA's official injury report;
          absences without a listing are worked out by matching each player's games against their team's schedule.
        </p>
        <p>
          The site lives at{' '}
          <a href="https://next82.vercel.app" className="text-accent">
            next82.vercel.app
          </a>{' '}
          (the old GitHub Pages address redirects there). The code and data are on{' '}
          <a href="https://github.com/rarunach03/next82" className="text-accent">
            GitHub
          </a>
          .
        </p>
      </Section>
        {a.ablation && <WhatMatters ablation={a.ablation} />}
      </Part>

      <Part id="accuracy" title="How accurate they are">
      <Section title="On past seasons">
        <p>
          The season model was trained on seasons up to 2022-23 and tested on {a.testSeasons.join(' and ')}, which it
          never saw. Every choice (inputs, settings) was made on earlier validation seasons, so the test seasons only
          measure accuracy.
          {a.modelChanged && a.frozenModelMae !== undefined && (
            <>
              {' '}
              The current model blends a LightGBM model (80%) with linear regression (20%): the two make different
              mistakes, so together they miss less ({a.modelMae} games, against {a.frozenModelMae} for LightGBM alone and{' '}
              {a.linearMae} for linear regression alone). It makes the updated forecast and future preseason forecasts;
              this season's preseason forecasts stay as frozen, made by LightGBM alone.
            </>
          )}
        </p>
        <dl className="grid gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-2">
          <div className="bg-surface px-4 py-4">
            <dd className="font-display text-3xl font-bold text-accent">{a.modelMae} games</dd>
            <dt className="mt-1 text-sm">our average miss, full season</dt>
            <dd className="mt-1 text-xs text-faint">
              Half within {Math.round(a.modelMedianError)} games · {Math.round(a.shareWithin16 * 100)}% within 16
            </dd>
          </div>
          <div className="bg-surface px-4 py-4">
            <dd className="font-display text-3xl font-bold text-ink">{a.bestBaselineMae} games</dd>
            <dt className="mt-1 text-sm">average miss {baselineText(a.bestBaseline)}</dt>
            <dd className="mt-1 text-xs text-faint">The best simple guess</dd>
          </div>
        </dl>
        {a.updatedMae !== undefined && (
          <p>
            The updated forecast misses the rest of a season by {a.updatedMae} games on average, against{' '}
            {a.updatedBestBaselineMae} for the best simple method, and does best for players who are currently out. For
            comeback players who stayed healthy, the if-healthy forecast missed by {a.comebackHealthyMae} games.
          </p>
        )}
        <p>
          Below, this season's preseason forecasts are graded every day against games played so far, next to two simple
          guesses, and it says plainly when it's too early to tell.
        </p>
      </Section>

        <ThisSeason meta={meta} a={season} />
      </Part>

      <Part id="limits" title="Limits">
      <Section title="What the forecasts can't do">
        <ul className="list-disc space-y-2 pl-5">
          <li>
            The preseason forecast can't see injury news, and the updated forecast only knows recovery times for a few
            serious injuries; for players not on the injury report, it can't tell an injury from rest, a benching or a
            suspension.
          </li>
          <li>
            Forecasts assume the player is in the league; players not on a roster who haven't played get no updated
            forecast.
          </li>
          <li>
            The edge over simple guessing is real but modest. Much of availability is unpredictable without injury data.
          </li>
        </ul>
      </Section>
      </Part>

      <p className="mt-12">
        <Link to="/" className="font-medium text-accent">
          ← See the forecasts
        </Link>
      </p>
    </article>
  )
}


/** A titled block inside one of the page's parts. */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8 max-w-2xl">
      <h3 className="font-display text-2xl font-bold uppercase">{title}</h3>
      <div className="mt-3 space-y-4 text-muted [&_dt]:text-ink [&_li]:text-muted">{children}</div>
    </section>
  )
}

/** One of the page's three parts, linkable by its id. */
function Part({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="mt-14 scroll-mt-20 border-t border-line pt-8">
      <h2 className="font-display text-4xl leading-none font-extrabold tracking-tight uppercase">{title}</h2>
      {children}
    </section>
  )
}

/** This season, graded every day: the preseason forecast against two simple guesses. */
function ThisSeason({ meta, a }: { meta: Meta; a: SeasonAccuracy | null | undefined }) {
  if (a === undefined) return <p className="mt-6 text-muted">Loading…</p>
  if (a === null)
    return (
      <p className="mt-6 text-muted">
        The {meta.forecastSeason} season hasn't started yet. Grading begins after opening night.
      </p>
    )

  const all = a.groups.all
  const best = a.bestBaseline
  const [low, high] = a.gapRange
  const tooEarly = low <= 0 && high >= 0
  const fmt = (v: number) => v.toFixed(2)

  return (
    <section className="mt-10">
      <h3 className="font-display text-2xl font-bold uppercase">This season, graded daily</h3>
      <p className="mt-3 max-w-2xl text-muted">
        The preseason forecasts were frozen before opening night. Each day, every player on a roster is graded on games
        played so far against what their forecast implied for that many team games: a 60-game forecast expects 60 of
        every 82. Two simple guesses are graded the same way.
      </p>

      <div className="mt-6 max-w-2xl rounded-xl border border-accent/40 bg-accent/10 px-4 py-3 text-sm">
        {tooEarly ? (
          <>
            <strong>Too early to tell.</strong> Teams have played about {a.avgTeamGames} games each. The forecast's lead
            over the {a.methods[best].toLowerCase()} could be anywhere from {fmt(low)} to {fmt(high)} games per player
            (95% range), so it could just as easily be luck. The real test is the full season: on{' '}
            {a.testSeasons.seasons.join(' and ')}, the forecast missed by {a.testSeasons.model} games on average vs.{' '}
            {a.testSeasons.bestBaseline} for the best simple guess.
          </>
        ) : (
          <>
            After about {a.avgTeamGames} games per team, the forecast's lead over the {a.methods[best].toLowerCase()} is{' '}
            {fmt(low)} to {fmt(high)} games per player (95% range): {low > 0 ? 'ahead beyond luck' : 'behind beyond luck'}.
            Final grading comes at the end of the season.
          </>
        )}
      </div>

      <dl className="mt-8 grid gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-3">
        {ORDER.map((m) => (
          <div key={m} className="bg-surface px-5 py-5">
            <dt className="flex items-center gap-2 text-sm text-muted">
              <span className="size-2.5 rounded-sm" style={{ background: COLORS[m] }} />
              {a.methods[m]}
            </dt>
            <dd className="mt-1 flex items-baseline gap-1.5">
              <span className={`tabular font-display text-4xl font-bold ${m === 'model' ? 'text-accent' : ''}`}>{fmt(all[m])}</span>
              <span className="text-sm text-muted">games</span>
            </dd>
            <dd className="text-xs text-faint">average miss so far</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-xs text-faint">
        {all.n} players graded through {shortDate(a.asOf)}. Lower is better. Misses grow as the season goes on, because
        there are more games to miss.
      </p>

      <section className="mt-12">
        <h4 className="font-display text-xl font-bold uppercase">Average miss so far, by date</h4>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
          {ORDER.map((m) => (
            <span key={m} className="flex items-center gap-1.5">
              <span className="h-0.5 w-4 rounded" style={{ background: COLORS[m] }} />
              {a.methods[m]} <span className="tabular text-ink">{fmt(all[m])}</span>
            </span>
          ))}
        </div>
        <div className="mt-2 h-72 w-full">
          <ResponsiveContainer>
            <LineChart data={a.trend} margin={{ top: 12, right: 16, left: -16, bottom: 0 }}>
              <CartesianGrid stroke="var(--color-line)" vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={(d: string) => shortDate(d)}
                tick={{ fill: 'var(--color-faint)', fontSize: 11 }}
                axisLine={{ stroke: 'var(--color-line)' }}
                tickLine={false}
                minTickGap={24}
              />
              <YAxis tick={{ fill: 'var(--color-faint)', fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip
                cursor={{ stroke: 'var(--color-faint)', strokeDasharray: '3 3' }}
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null
                  const point = payload[0].payload
                  return (
                    <div className="rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm shadow-xl">
                      <div className="font-semibold">{shortDate(String(label))}</div>
                      <div className="mb-1 text-xs text-faint">about {point.avgTeamGames} games per team</div>
                      {ORDER.map((m) => (
                        <div key={m} className="flex items-center justify-between gap-4">
                          <span className="flex items-center gap-1.5 text-muted">
                            <span className="size-2 rounded-sm" style={{ background: COLORS[m] }} />
                            {a.methods[m]}
                          </span>
                          <span className="tabular">{fmt(point[m])}</span>
                        </div>
                      ))}
                    </div>
                  )
                }}
              />
              {ORDER.map((m) => (
                <Line
                  key={m}
                  type="monotone"
                  dataKey={m}
                  stroke={COLORS[m]}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4, stroke: 'var(--color-surface)', strokeWidth: 2 }}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="mt-12">
        <h4 className="font-display text-xl font-bold uppercase">By group</h4>
        <div className="mt-3 overflow-x-auto rounded-2xl border border-line bg-surface">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs tracking-wide text-faint uppercase">
                <th className="py-3 pr-3 pl-4 font-medium">Group</th>
                <th className="py-3 pr-3 font-medium">Players</th>
                {ORDER.map((m) => (
                  <th key={m} className="py-3 pr-4 font-medium">
                    {a.methods[m]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(a.groups).map(([group, row]) => {
                const bestHere = Math.min(...ORDER.map((m) => row[m]))
                return (
                  <tr key={group} className="border-b border-line/60 last:border-0">
                    <td className="py-3 pr-3 pl-4">{group[0].toUpperCase() + group.slice(1)}</td>
                    <td className="tabular py-3 pr-3 text-muted">{row.n}</td>
                    {ORDER.map((m) => (
                      <td key={m} className={`tabular py-3 pr-4 ${row[m] === bestHere ? 'font-semibold text-ink' : 'text-muted'}`}>
                        {fmt(row[m])}
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-faint">
          Average miss in games so far; the best in each row is bold. Small groups (like comeback players) swing a lot
          from game to game.
        </p>
      </section>

      <section className="mt-12 max-w-2xl space-y-2 text-sm text-muted">
        <h4 className="font-display text-xl font-bold text-ink uppercase">How this is graded</h4>
        <p>
          Comeback players are graded on their expected games, setback risk included, not the if-healthy number. Players
          not on a current roster ({a.excludedNotOnRoster} of them) aren't graded, since every forecast assumes the player
          is in the league.
        </p>
        <p>
          "Same as last season" expects the share of games each player played last season; "3-season average" expects
          their average over the last three. Both use only information from before the season, like the forecast.
        </p>
      </section>
    </section>
  )
}

/** The game-by-game beta: what it predicts, how it's checked, and the injury-status override. */
function GameBetaSection({ model: m }: { model: GameBetaModel }) {
  return (
    <div id="game-beta" className="scroll-mt-20">
      <Section title="Game by game (beta)">
        <p>
          A second model predicts, for each upcoming game, the chance a player plays in it. It looks at rest and
          back-to-backs, games played and missed lately (and the current run of missed games), minutes recently and last
          season, games played last season, age, and how far into the season it is. Rows come from every team game while a
          player was on the team: game logs only list games played, so missed games come from the team's schedule. It's a
          LightGBM model trained on {m.trainSeasons[0]} to {m.trainSeasons[1]}, calibrated on {m.calibrationSeason} and
          tested on {m.testSeasons.join(' and ')} ({m.testRows.toLocaleString('en-US')} player-games), the same seasons the
          season forecasts are tested on.
        </p>
        <p>
          On the test seasons its log loss (lower is better) was <strong className="text-ink">{m.logLoss}</strong>, against{' '}
          {m.logLossRateSoFar} for guessing each player's play rate so far this season and {m.logLossLastSeason} for their
          rate last season. It's well calibrated: when it says 70%, players played about 70% of the time (average gap{' '}
          {(m.ece * 100).toFixed(1)} points). Adding up each game's chance over a season, made the day before each game,
          lands within {m.seasonTotalMae} games of the real total on average.
        </p>
        <CalibrationChart bins={m.calibration} />
        <p>
          The official injury report isn't a model input (there's no history of it to learn from). Instead, the live
          status goes on top: a player listed Out on the latest report gets under 5% for the next game, and a known return
          date puts every game before it under 5%; after that, the model takes over. The next game uses everything known
          today; later games assume today's status carries on, so they're rougher. It tends to slightly underrate a quick
          return after a regular misses a single game.
        </p>
      </Section>
    </div>
  )
}

/** The ablation: each feature group's validation miss on its own, and the extra miss without it. */
function WhatMatters({ ablation: ab }: { ablation: Ablation }) {
  const worst = Math.max(...ab.groups.map((g) => g.alone))
  const best = Math.min(ab.allFeatures, ...ab.groups.map((g) => g.alone))
  const most = Math.max(...ab.groups.map((g) => g.without), 0.01)
  const span = (v: number) => `${Math.max(4, ((v - best + 0.5) / (worst - best + 0.5)) * 100)}%`
  return (
    <div id="what-matters" className="scroll-mt-20">
      <Section title="What matters most">
        <p>
          To see what the season model relies on, it was retrained with only one group of inputs, and again with each
          group left out, on the {ab.validationSeasons[0]} to {ab.validationSeasons.at(-1)} seasons (each predicted from
          earlier ones). With every input it misses by {ab.allFeatures} games. Past games played tell it the most on their
          own; minutes and workload add the most on top of everything else, then absences (the injury history in the
          game logs). Groups overlap, so leaving one out can cost little when another carries the same information.
        </p>
      </Section>
      <div className="mt-4 max-w-2xl overflow-x-auto rounded-xl border border-line bg-surface">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs tracking-wide text-faint uppercase">
              <th className="py-2.5 pr-2 pl-4 font-medium">Inputs</th>
              <th className="py-2.5 pr-2 font-medium">Miss using only these</th>
              <th className="py-2.5 pr-4 text-right font-medium">Extra miss without</th>
            </tr>
          </thead>
          <tbody>
            {ab.groups.map((g) => (
              <tr key={g.name} className="border-b border-line/60 last:border-0">
                <td className="py-2 pr-2 pl-4 text-ink">{g.name}</td>
                <td className="py-2 pr-2">
                  <div className="flex items-center gap-2">
                    <span className="relative hidden h-2 w-28 rounded-full bg-surface-2 sm:block" aria-hidden>
                      <span className="absolute inset-y-0 left-0 rounded-full bg-up" style={{ width: span(g.alone) }} />
                    </span>
                    <span className="tabular text-muted">{g.alone.toFixed(1)}</span>
                  </div>
                </td>
                <td className="py-2 pr-4">
                  <div className="flex items-center justify-end gap-2">
                    <span className="relative hidden h-2 w-20 rounded-full bg-surface-2 sm:block" aria-hidden>
                      <span
                        className="absolute inset-y-0 left-0 rounded-full bg-accent"
                        style={{ width: `${(Math.max(g.without, 0) / most) * 100}%` }}
                      />
                    </span>
                    <span className="tabular w-12 text-right text-muted">
                      {g.without > 0 ? '+' : g.without < 0 ? '−' : ''}
                      {Math.abs(g.without).toFixed(2)}
                    </span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 max-w-2xl text-xs text-faint">
        Average miss in games; lower is better in the middle column, bigger means more important on the right. New inputs
        were tried too (injury detail, workload trends, usage changes, age interactions, durability streaks, production);
        none helped enough on these seasons to keep.
      </p>
    </div>
  )
}
