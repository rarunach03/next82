import { Link } from 'react-router'
import { baselineText } from '../data'
import type { Meta } from '../types'

/** What's on the site, how the forecasts are made, how accurate they are, and what they can't do. */
export default function About({ meta }: { meta: Meta }) {
  const a = meta.accuracy
  return (
    <article className="max-w-2xl pt-10 pb-16">
      <p className="text-sm font-semibold tracking-widest text-accent uppercase">About</p>
      <h1 className="mt-2 font-display text-5xl leading-none font-extrabold tracking-tight uppercase">How Next82 works</h1>
      <p className="mt-4 text-lg text-muted">
        Next82 forecasts how many games every NBA player will play in {meta.forecastSeason}, shows what's driving each
        number, and turns it into fantasy rankings. Availability shapes team decisions, fantasy leagues and what fans
        can expect, but most tools only report injuries after they happen.
      </p>

      <Section title="Two forecasts">
        <p>
          <strong className="text-ink">The preseason forecast</strong> was made before opening night and is frozen: it
          never changes, so it can be graded honestly. Each one comes with the factors behind it, in games.
        </p>
        <p>
          <strong className="text-ink">The updated forecast</strong> is refreshed every day: games played so far plus a
          fresh prediction for the games left. If a player gets hurt in November, the updated forecast drops; the
          preseason one doesn't.
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

      <Section title="How accurate is it?">
        <p>
          The preseason model was trained on seasons up to 2022-23 and tested on {a.testSeasons.join(' and ')}, which it
          never saw. Settings were chosen on separate validation seasons, so the test seasons only measure accuracy.
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
          The{' '}
          <Link to="/accuracy" className="text-accent">
            accuracy page
          </Link>{' '}
          grades this season's preseason forecasts every day against games played so far, next to two simple guesses,
          and says plainly when it's too early to tell.
        </p>
      </Section>

      <Section title="The data">
        <p>
          Thirty regular seasons of NBA stats, from 1996-97 through {meta.dataThrough}, plus this season's games, from
          stats.nba.com via the open-source nba_api library. There's no public injury data, so long absences are worked
          out by matching each player's games against their team's schedule.
        </p>
      </Section>

      <Section title="What it can't do">
        <ul className="list-disc space-y-2 pl-5">
          <li>It can't see injury reports, so it can't tell an injury from rest, a benching, a suspension or an unsigned season.</li>
          <li>Forecasts assume the player is in the league; players not on a roster who haven't played get no updated forecast.</li>
          <li>The edge over simple guessing is real but modest. Much of availability is unpredictable without injury data.</li>
        </ul>
      </Section>

      <p className="mt-12">
        <Link to="/" className="font-medium text-accent">
          ← See the forecasts
        </Link>
      </p>
    </article>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-10">
      <h2 className="font-display text-2xl font-bold uppercase">{title}</h2>
      <div className="mt-3 space-y-4 text-muted [&_dt]:text-ink [&_li]:text-muted">{children}</div>
    </section>
  )
}
