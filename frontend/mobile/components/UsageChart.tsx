import { View, Text, StyleSheet, useWindowDimensions } from 'react-native';
import Svg, { Path, Line, Text as SvgText, Circle, G } from 'react-native-svg';
import { COLORS, SPACING, RADIUS } from '../constants/theme';

const CHART_DATA = [
  { time: '00:00', commands: 240 },
  { time: '04:00', commands: 380 },
  { time: '08:00', commands: 1200 },
  { time: '12:00', commands: 2840 },
  { time: '16:00', commands: 2340 },
  { time: '20:00', commands: 3100 },
  { time: '23:59', commands: 1850 },
];

const Y_TICKS = [0, 1000, 2000, 3000];

const PAD_LEFT   = 38;
const PAD_RIGHT  = 12;
const PAD_TOP    = 10;
const PAD_BOTTOM = 28;
const SVG_HEIGHT = 200;

export function UsageChart() {
  // Full width minus the card's own horizontal padding (lg * 2) and screen padding (lg * 2)
  const { width } = useWindowDimensions();
  const svgWidth    = width - SPACING.lg * 4;   // screen pad + card pad on each side
  const innerW      = svgWidth - PAD_LEFT - PAD_RIGHT;
  const innerH      = SVG_HEIGHT - PAD_TOP - PAD_BOTTOM;

  const maxVal = Math.max(...CHART_DATA.map((d) => d.commands));

  const toX = (i: number) => PAD_LEFT + (i / (CHART_DATA.length - 1)) * innerW;
  const toY = (v: number) => PAD_TOP + innerH - (v / maxVal) * innerH;

  const points = CHART_DATA.map((d, i) => ({ ...d, x: toX(i), y: toY(d.commands) }));

  // Smooth line path
  const pathD = points
    .map((p, i) => {
      if (i === 0) return `M ${p.x} ${p.y}`;
      const prev = points[i - 1];
      const cpX = (prev.x + p.x) / 2;
      return `C ${cpX} ${prev.y} ${cpX} ${p.y} ${p.x} ${p.y}`;
    })
    .join(' ');

  return (
    <View style={styles.card}>
      <Text style={styles.title}>Voice Commands vs Time</Text>
      <Text style={styles.subtitle}>Voice command volume throughout the day</Text>

      <View style={styles.svgWrapper}>
        <Svg width={svgWidth} height={SVG_HEIGHT}>
          {/* Horizontal grid lines + Y labels */}
          {Y_TICKS.map((tick) => {
            const y = toY(tick);
            return (
              <G key={tick}>
                <Line
                  x1={PAD_LEFT}
                  y1={y}
                  x2={PAD_LEFT + innerW}
                  y2={y}
                  stroke={COLORS.border}
                  strokeWidth={1}
                  strokeDasharray="3 3"
                />
                <SvgText
                  x={PAD_LEFT - 4}
                  y={y + 4}
                  fontSize={9}
                  fill={COLORS.mutedForeground}
                  textAnchor="end"
                >
                  {tick >= 1000 ? `${tick / 1000}k` : String(tick)}
                </SvgText>
              </G>
            );
          })}

          {/* Chart line */}
          <Path
            d={pathD}
            stroke={COLORS.primary}
            strokeWidth={2.5}
            fill="none"
            strokeLinejoin="round"
            strokeLinecap="round"
          />

          {/* Data point dots */}
          {points.map((p, i) => (
            <Circle key={i} cx={p.x} cy={p.y} r={4} fill={COLORS.primary} />
          ))}

          {/* X axis labels */}
          {points.map((p, i) => (
            <SvgText
              key={i}
              x={p.x}
              y={SVG_HEIGHT - 4}
              fontSize={9}
              fill={COLORS.mutedForeground}
              textAnchor="middle"
            >
              {p.time}
            </SvgText>
          ))}
        </Svg>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: COLORS.card,
    borderRadius: RADIUS.xl,
    padding: SPACING.lg,
    borderWidth: 1,
    borderColor: COLORS.border,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 10,
    elevation: 2,
  },
  title: {
    fontSize: 18,
    fontWeight: '600',
    color: COLORS.foreground,
  },
  subtitle: {
    fontSize: 13,
    color: COLORS.mutedForeground,
    marginTop: 2,
    marginBottom: SPACING.md,
  },
  svgWrapper: {
    alignItems: 'center',
  },
});
