import type { NoTierReason } from './types'

/** Plain-English explanations for the site's jargon, shared so every page says the same thing. */
export const GLOSSARY = {
  likelyRange:
    'When we tested on past seasons, 8 in 10 real outcomes landed inside this range. It narrows as the season goes on.',
  tier: (safe: number, risky: number) =>
    `How safe the games forecast is, judged from the low end of the likely range. Safe: even a bad outcome is ${safe}+ games. Risky: a bad outcome is under ${risky}. Moderate: in between. Only for players in a regular rotation.`,
  aboveReplacement: (pool: number) =>
    `Compared with the best player you could pick up for free (about the ${pool}th-best player per game). Zero means no better than a free agent.`,
  cat9: '9-category leagues score points, rebounds, assists, steals, blocks, threes, field goal %, free throw % and turnovers. Values are how far above average a player is across all nine.',
  durability:
    'Value lost to expected missed games: what the player would add by playing every game, minus their expected value.',
  noTier: {
    comeback:
      "Missed all of last season, so there's no recent role to judge how safe the forecast is. The forecast still counts the chance of a setback.",
    missed:
      "Played under a quarter of last season's games, so there's no steady recent role to judge how safe the forecast is. A tier appears once they've played a quarter of this season's games (after 5+ team games).",
    bench:
      'Played limited minutes, so games depend more on the coach than on health. Tiers are only for players in a regular rotation.',
    rookie: "No NBA history yet. Ranked from this season's games, blended with past rookies from the same draft range.",
  },
  preseason: 'Made before opening night and never changed, so it can be graded honestly at the end of the season.',
  expected: 'Games played so far plus a fresh forecast for the games left, updated every day.',
  perGameRank: 'Where the player ranks on production per game alone, ignoring games missed.',
  rankChange:
    'Per-game rank minus overall rank: ▲ means staying healthy lifts the player, ▼ means expected missed games pull them down.',
  b2b: 'How often the player sits the second night of back-to-back games (last three seasons, pulled toward the league average), and how many the team has left. Already counted in the forecast.',
} as const

/** Short labels for why a player has no availability tier. */
export const NO_TIER_LABEL: Record<NoTierReason, string> = {
  comeback: 'Returning from a missed season',
  missed: 'Missed most of last season',
  bench: 'Not in a regular rotation role',
  rookie: 'Rookie',
}
