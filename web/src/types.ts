// Shapes of the JSON written by `python -m next82.export` into public/data/.

export interface Accuracy {
  modelMae: number
  /** Half of forecasts miss by less than this many games. */
  modelMedianError: number
  shareWithin16: number
  bestBaseline: string
  bestBaselineMae: number
  comebackHealthyMae: number
  testSeasons: [string, string]
  /** Rest-of-season model: average miss in rest-of-season games on test seasons. */
  updatedMae?: number
  updatedBestBaseline?: string
  updatedBestBaselineMae?: number
}

export interface Meta {
  forecastSeason: string
  dataThrough: string
  previousSeason: string
  latestFinishedSeason: string
  rostersAsOf: string | null
  /** The forecast season is underway (games so far are available). */
  seasonStarted: boolean
  /** Date of the latest game counted in "so far" numbers. */
  soFarThrough: string | null
  /** Date of the latest games used by the updated forecast. */
  updatedAsOf: string | null
  generatedAt: string
  games: number
  setbackGames: number
  /** Tier cutoffs on the low end of the likely range: Safe at this many games or more. */
  tierSafeLow: number
  accuracy: Accuracy
}

export type Tier = 'Safe' | 'Moderate' | 'Risky'

/** A manual injury adjustment to the updated forecast (data/overrides.csv). */
export interface Override {
  status: string
  note: string
  sourceUrl: string
  sourceUrl2: string | null
  /** The earliest return is our own estimate (e.g. typical recovery time), not a team timeline. */
  estimated: boolean
  dateAdded: string | null
  reviewBy: string | null
  earliestReturn: string | null
  latestReturn: string | null
  /** No return window known: shown as "Out indefinitely". */
  indefinite: boolean
}

export interface Team {
  abbr: string
  name: string
  /** Rostered players without a forecast (mostly rookies). */
  noForecast: string[]
}

export interface PlayerSummary {
  id: number
  name: string
  /** Lowercase, accent-free name for search. */
  search: string
  /** Current team, or null if not on a roster. */
  team: string | null
  lastTeam: string
  age: number
  games: number
  seasonGames: number
  /** Returning from a missed season: show ifHealthy + setbackChance instead of forecast. */
  comeback: boolean
  forecast: number
  ifHealthy: number | null
  setbackChance: number | null
  /** The number to display and sort by: ifHealthy for comebacks, forecast otherwise. */
  shown: number
  /** Minutes in the last season played; used to rank search suggestions. */
  recentMinutes: number
  /** Games played so far this season, and the player's current team's games so far. */
  playedSoFar: number | null
  teamGamesSoFar: number | null
  /** Updated forecast: games so far + predicted games still to come. */
  updated: number | null
  updatedRest: number | null
  gamesLeft: number | null
  /** Team games since the player's last game (null if they haven't played this season). */
  absenceStreak: number | null
  /** Likely ranges (10th-90th percentile) of the preseason and updated forecasts. */
  preLow: number | null
  preHigh: number | null
  updatedLow: number | null
  updatedHigh: number | null
  /** Availability tier from the low end of the updated forecast's range. Only for
   * players in a rotation role; null otherwise. */
  tier: Tier | null
  rotationRole: boolean
  /** Not on any current roster. */
  notOnRoster: boolean
  override: Override | null
}

export interface Factor {
  label: string
  value: string
  /** Effect on the forecast, in games. */
  games: number
}

export interface SeasonGames {
  season: string
  games: number
  seasonGames: number
  missed: boolean
}

export interface SimilarComeback {
  name: string
  seasonMissed: string
  age: number
  before: string
  comebackGames: number
}

export interface PlayerDetail extends PlayerSummary {
  teamName: string | null
  /** Average forecast the factors start from, in games. */
  factorBase: number
  factors: Factor[]
  history: SeasonGames[]
  similar: SimilarComeback[]
}

export interface Index {
  meta: Meta
  teams: Team[]
  players: PlayerSummary[]
}

// fantasy.json, written by `python -m next82.export`.
export type FantasyFormat = 'espn' | 'yahoo' | 'cat9'

export interface FantasyPlayer {
  id: number
  name: string
  team: string | null
  tier: Tier | null
  /** In their first NBA season: ranked from this season's games plus a draft-range baseline. */
  rookie: boolean
  draftRange: string | null
  override: Override | null
  playedSoFar: number | null
  /** Team games left, and the games the updated forecast expects the player to play. */
  gamesLeft: number
  restGames: number
  /** Updated forecast for the whole season (played so far + rest). */
  seasonGames: number
  /** Per-game value: ESPN and Yahoo points, and total 9-category z-score. */
  perGame: Record<FantasyFormat, number>
  cats: Record<string, number>
  stats: Record<string, number | null>
}

export interface Fantasy {
  season: string
  /** This season's stats are blended with the prior as if the prior were this many games. */
  shrinkGames: number
  /** Rookies: shrunk toward a draft-range baseline, and ranked after this many games. */
  rookieShrinkGames: number | null
  rookieMinGames: number
  poolSize: number
  /** Per-game score of the 156th-best player per game, by format. Value is measured above it. */
  replacement: Record<FantasyFormat, number>
  players: FantasyPlayer[]
}

// accuracy.json, written by `python -m next82.export`.
export type AccuracyMethod = 'model' | 'last_season' | 'three_year'

export interface AccuracyGroup extends Record<AccuracyMethod, number> {
  n: number
}

export interface AccuracyPoint extends Record<AccuracyMethod, number> {
  date: string
  avgTeamGames: number
}

export interface SeasonAccuracy {
  asOf: string
  avgTeamGames: number
  methods: Record<AccuracyMethod, string>
  groups: Record<string, AccuracyGroup>
  bestBaseline: AccuracyMethod
  /** 95% range for (best baseline miss - model miss); spanning 0 means it could be luck. */
  gapRange: [number, number]
  excludedNotOnRoster: number
  trend: AccuracyPoint[]
  seasonGames: number
  testSeasons: { seasons: [string, string]; model: number; bestBaseline: number }
}
