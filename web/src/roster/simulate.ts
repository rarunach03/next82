// Monte Carlo simulation of a roster's rest-of-season games.
//
// Each player's likely range is the 10th-90th percentile of the games they'll play
// from here on, around the updated forecast, which is the player's middle outcome
// (the model is trained on absolute error, so it predicts the median). Ranges have
// long low tails (injuries), so a roster's expected total is below the sum of its
// players' forecasts. One simulated season draws each
// player's games from a two-piece normal through those three points (so a range
// that's longer on the low side stays lopsided), rounds to whole games and clips to
// [0, team games left]. Season totals are games already played plus that draw, so
// they stay inside [played so far, played so far + games left]. Players are drawn
// independently. A seeded generator makes every run reproducible.

/** The 90th percentile of a standard normal: the range ends sit this many spreads from the forecast. */
export const Z90 = 1.2815515655446004
export const RUNS = 5000
/** Players without a likely range (rookies): this share of games left on each side of the forecast. */
export const DEFAULT_SPREAD = 0.3

/** Small, fast seeded generator (mulberry32): numbers in [0, 1). */
export function seededRandom(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Standard normal draws from a uniform generator (Box-Muller, both values used). */
export function normalDraws(random: () => number): () => number {
  let spare: number | null = null
  return () => {
    if (spare !== null) {
      const z = spare
      spare = null
      return z
    }
    const u = 1 - random() // in (0, 1], so the log is finite
    const r = Math.sqrt(-2 * Math.log(u))
    const theta = 2 * Math.PI * random()
    spare = r * Math.sin(theta)
    return r * Math.cos(theta)
  }
}

export interface PlayerGames {
  playedSoFar: number
  gamesLeft: number
  rest: number
  restLow: number | null
  restHigh: number | null
}

/** A player's rest-of-season distribution: forecast, 10th and 90th percentiles, and the cap. */
export interface Spread {
  point: number
  low: number
  high: number
  max: number
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

export function spread(p: PlayerGames): Spread {
  const max = Math.max(0, p.gamesLeft)
  const point = clamp(p.rest, 0, max)
  const low = p.restLow ?? point - DEFAULT_SPREAD * max
  const high = p.restHigh ?? point + DEFAULT_SPREAD * max
  // The range always contains the forecast and stays inside [0, games left].
  return { point, low: clamp(Math.min(low, point), 0, max), high: clamp(Math.max(high, point), 0, max), max }
}

/** Whole games for one standard-normal draw `z`: each side of the forecast has its own spread. */
export function drawGames(s: Spread, z: number): number {
  const sigma = (z < 0 ? s.point - s.low : s.high - s.point) / Z90
  return Math.round(clamp(s.point + z * sigma, 0, s.max))
}

/** Value at quantile q of sorted numbers (nearest rank). */
export function quantile(sorted: ArrayLike<number>, q: number): number {
  if (sorted.length === 0) return 0
  return sorted[clamp(Math.ceil(q * sorted.length) - 1, 0, sorted.length - 1)]
}

export interface Bin {
  from: number
  to: number
  count: number
}

/** Equal-width bins of whole-number values, at most `maxBins` of them. */
export function histogram(sorted: ArrayLike<number>, maxBins = 16): Bin[] {
  if (sorted.length === 0) return []
  const lo = sorted[0]
  const hi = sorted[sorted.length - 1]
  const width = Math.max(1, Math.ceil((hi - lo + 1) / maxBins))
  const bins: Bin[] = []
  for (let from = lo; from <= hi; from += width) bins.push({ from, to: from + width - 1, count: 0 })
  for (let i = 0; i < sorted.length; i++) bins[Math.floor((sorted[i] - lo) / width)].count++
  return bins
}

export interface Simulation {
  runs: number
  seed: number
  /** Most rest-of-season games the roster can play (team games left, summed) and games already played. */
  maxRest: number
  played: number
  /** The updated forecasts (each player's middle outcome), summed. */
  forecastSum: number
  /** Expected rest-of-season games: the average simulated total. */
  mean: number
  /** Simulated rest-of-season roster games: bad season (10th percentile), median, good season (90th). */
  low: number
  median: number
  high: number
  bins: Bin[]
  /** Every simulated total, sorted. */
  totals: Int32Array
}

export function simulate(players: PlayerGames[], seed: number, runs = RUNS): Simulation {
  const spreads = players.map(spread)
  const z = normalDraws(seededRandom(seed))
  const totals = new Int32Array(runs)
  for (let run = 0; run < runs; run++) {
    let total = 0
    for (const s of spreads) total += drawGames(s, z())
    totals[run] = total
  }
  let sum = 0
  for (let run = 0; run < runs; run++) sum += totals[run]
  totals.sort()
  return {
    runs,
    seed,
    maxRest: spreads.reduce((sum, s) => sum + s.max, 0),
    played: players.reduce((sum, p) => sum + p.playedSoFar, 0),
    forecastSum: spreads.reduce((total, s) => total + s.point, 0),
    mean: runs ? sum / runs : 0,
    low: quantile(totals, 0.1),
    median: quantile(totals, 0.5),
    high: quantile(totals, 0.9),
    bins: histogram(totals),
    totals,
  }
}
