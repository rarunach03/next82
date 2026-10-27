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
  preseason: 'Made before opening night and never changed, so it can be graded honestly at the end of the season.',
  expected: 'Games played so far plus a fresh forecast for the games left, updated every day.',
  perGameRank: 'Where the player ranks on production per game alone, ignoring games missed.',
  rankChange:
    'Per-game rank minus overall rank: ▲ means staying healthy lifts the player, ▼ means expected missed games pull them down.',
  b2b: 'How often the player sits the second night of back-to-back games (last three seasons, pulled toward the league average), and how many the team has left. Already counted in the forecast.',
} as const
