import { Link } from 'react-router'
import { baselineText } from '../data'
import type { Meta } from '../types'

/** How the forecasts are made, how accurate they are, and what they can't do. */
export default function About({ meta }: { meta: Meta }) {
  const a = meta.accuracy
  return (
    <article className="max-w-2xl pt-10 pb-16">
      <p className="text-sm font-semibold tracking-widest text-accent uppercase">About</p>
      <h1 className="mt-2 font-display text-5xl leading-none font-extrabold tracking-tight uppercase">How Next82 works</h1>
      <p className="mt-4 text-lg text-muted">
        Next82 forecasts how many games every NBA player will play in {meta.forecastSeason}, and shows what's driving
        each number. Availability shapes team decisions, fantasy leagues and what fans can expect, but most tools only
        report injuries after they happen.
      </p>

      <Section title="The data">
        <p>
          Thirty regular seasons of NBA stats, from 1996-97 through {meta.dataThrough}, downloaded from stats.nba.com
          with the open-source nba_api library: season totals, player bios, every game each player played, and every
          team's schedule.
        </p>
        <p>
          There's no public injury data, so long absences are worked out by matching each player's games against their
          team's schedule. A run of missed games while on a roster counts as an absence.
        </p>
      </Section>

      <Section title="The model">
        <p>
          A gradient-boosted tree model (LightGBM) learned from about 12,300 past player-seasons what tends to happen
          next. It looks at age and experience, minutes played, games played in each of the last three seasons, long
          absences, and games missed at the start or end of a season.
        </p>
        <p>
          The target is the share of the schedule a player plays, so the shortened lockout and COVID seasons compare
          fairly with 82-game seasons. Each forecast is explained with SHAP values: how many games each factor adds or
          takes away from the average forecast.
        </p>
      </Section>

      <Section title="Players coming back from a lost season">
        <p>
          Comebacks tend to go one of two ways: the player plays a lot, or barely plays. A single number lands in between
          and is rarely right, so these players get two: a forecast if they stay healthy, and the chance of a setback
          (fewer than {meta.setbackGames} games). Each comeback page also lists the most similar past comebacks.
        </p>
      </Section>

      <Section title="How accurate is it?">
        <p>
          The model was trained on seasons up to 2022-23 and tested on {a.testSeasons.join(' and ')}, which it never
          saw. Settings were chosen on a separate validation season, so the test seasons only measure accuracy.
        </p>
        <dl className="grid gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-2">
          <div className="bg-surface px-4 py-4">
            <dd className="font-display text-3xl font-bold text-accent">{a.modelMae} games</dd>
            <dt className="mt-1 text-sm">our average miss</dt>
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
        <p>
          For comeback players who stayed healthy, the if-healthy forecast missed by {a.comebackHealthyMae} games on
          average. Forecasts for {meta.forecastSeason} were made before the season started and stay fixed, so they can be
          checked against what actually happens.
        </p>
        <p>
          Likely ranges for the preseason forecasts were added on October 26, 2026, a week into the season. They were
          computed from preseason data only, so they use nothing the season has shown since.
        </p>
      </Section>

      <Section title="What it can't do">
        <ul className="list-disc space-y-2 pl-5">
          <li>It can't see injury reports, so it can't tell an injury from rest, a benching, a suspension or an unsigned season.</li>
          <li>Rookies have no NBA games to learn from, so they don't get a forecast.</li>
          <li>Every forecast assumes the player is in the league for the season.</li>
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
