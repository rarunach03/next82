import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { SeasonGames } from '../types'

interface Point {
  season: string
  games: number
  note: string
  kind: 'played' | 'missed' | 'forecast'
}

const COLORS = { played: 'var(--color-played)', missed: 'var(--color-line)', forecast: 'var(--color-accent)' }

/** Games played per season, ending with the forecast bar in the accent color. */
export default function HistoryChart({
  history,
  forecast,
  forecastSeason,
  forecastLabel,
}: {
  history: SeasonGames[]
  forecast: number
  forecastSeason: string
  forecastLabel: string
}) {
  const data: Point[] = [
    ...history.map((h): Point => ({
      season: h.season,
      games: h.games,
      kind: h.missed ? 'missed' : 'played',
      note: h.missed ? 'Missed season' : `${h.games} of ${h.seasonGames} games`,
    })),
    { season: forecastSeason, games: Math.round(forecast), kind: 'forecast', note: `${forecastLabel}: ${Math.round(forecast)} of 82` },
  ]
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 16, right: 4, left: -24, bottom: 0 }}>
          <XAxis
            dataKey="season"
            // "2025-26" -> "25-26": fans name seasons by both years, or the year they end.
            tickFormatter={(s: string) => s.slice(2)}
            tick={{ fill: 'var(--color-faint)', fontSize: 11 }}
            axisLine={{ stroke: 'var(--color-line)' }}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={[0, 82]}
            ticks={[0, 20, 40, 60, 82]}
            tick={{ fill: 'var(--color-faint)', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: 'rgba(255,255,255,0.04)' }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const p = payload[0].payload as Point
              return (
                <div className="rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm shadow-xl">
                  <div className="font-semibold">{p.season}</div>
                  <div className="text-muted">{p.note}</div>
                </div>
              )
            }}
          />
          <Bar dataKey="games" radius={[3, 3, 0, 0]} minPointSize={2} isAnimationActive={false}>
            {data.map((d) => (
              <Cell key={d.season} fill={COLORS[d.kind]} />
            ))}
            <LabelList
              dataKey="games"
              position="top"
              content={({ x, y, width, index }) => {
                const d = data[index as number]
                const cx = Number(x) + Number(width) / 2
                if (d.kind === 'missed')
                  return (
                    <text x={cx} y={Number(y) - 6} textAnchor="middle" fill="var(--color-faint)" fontSize={10}>
                      Missed
                    </text>
                  )
                if (d.kind !== 'forecast') return null
                return (
                  <text x={cx} y={Number(y) - 6} textAnchor="middle" fill="var(--color-accent)" fontSize={12} fontWeight={700}>
                    {d.games}
                  </text>
                )
              }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
