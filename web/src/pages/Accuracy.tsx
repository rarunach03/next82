import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { shortDate, useAccuracy } from '../data'
import type { AccuracyMethod, Meta } from '../types'

// Categorical slots 1-3 of the project's validated dark palette (colorblind-safe on
// the dark surface, all pairs); the forecast takes the orange to match the site accent.
const COLORS: Record<AccuracyMethod, string> = {
  last_season: '#3987e5',
  model: '#d95926',
  three_year: '#199e70',
}
const ORDER: AccuracyMethod[] = ['model', 'three_year', 'last_season']

export default function Accuracy({ meta }: { meta: Meta }) {
  const a = useAccuracy()
  if (a === undefined) return <p className="py-16 text-muted">Loading…</p>
  if (a === null)
    return (
      <p className="py-16 text-muted">
        The {meta.forecastSeason} season hasn't started yet. Grading begins after opening night.
      </p>
    )

  const all = a.groups.all
  const best = a.bestBaseline
  const [low, high] = a.gapRange
  const tooEarly = low <= 0 && high >= 0
  const fmt = (v: number) => v.toFixed(2)

  return (
    <article className="pt-10 pb-16">
      <p className="text-sm font-semibold tracking-widest text-accent uppercase">Accuracy</p>
      <h1 className="mt-2 font-display text-5xl leading-none font-extrabold tracking-tight uppercase">
        How are the forecasts doing?
      </h1>
      <p className="mt-4 max-w-2xl text-muted">
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
        <h2 className="font-display text-2xl font-bold uppercase">Average miss so far, by date</h2>
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
        <h2 className="font-display text-2xl font-bold uppercase">By group</h2>
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
        <h2 className="font-display text-2xl font-bold text-ink uppercase">How this is graded</h2>
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
    </article>
  )
}
