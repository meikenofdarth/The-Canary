// The Canary — Design Tokens (matching frontend/web DESIGN_SYSTEM.md exactly)

export const COLORS = {
  // Core palette
  background: '#fafaf8',       // warm off-white
  foreground: '#1a1a1a',       // near-black text
  card: '#ffffff',             // card backgrounds
  cardForeground: '#1a1a1a',   // card text
  primary: '#fcd34d',          // brand yellow
  primaryForeground: '#1a1a1a',// text on yellow
  secondary: '#f3f0eb',        // input bg, secondary surfaces
  secondaryForeground: '#1a1a1a',
  muted: '#e5e0d8',            // muted borders
  mutedForeground: '#6b7280',  // secondary text (gray-500)
  accent: '#fcd34d',           // same as primary
  destructive: '#ef4444',      // error/delete red
  border: '#e5e0d8',           // all borders
  input: '#f3f0eb',            // input backgrounds
  ring: '#fcd34d',             // focus ring

  // Status colors
  success: '#22c55e',          // green-500
  successLight: '#dcfce7',     // green-100
  successText: '#166534',      // green-800
  scheduled: '#3b82f6',        // blue-500
  scheduledLight: '#dbeafe',   // blue-100
  scheduledText: '#1e40af',    // blue-800
  completed: '#f3f4f6',       // gray-100
  completedText: '#1f2937',   // gray-800

  // Chart colors
  chart1: '#fcd34d',
  chart2: '#fbbf24',
  chart3: '#f59e0b',
  chart4: '#d97706',
  chart5: '#b45309',

  // Recording
  recordingRed: '#dc2626',     // red-600
  recordingRedLight: '#fef2f2',// red-50
} as const;

export const RADIUS = {
  sm: 6,
  md: 10,      // base radius (0.625rem)
  lg: 12,
  xl: 16,
  '2xl': 20,
  full: 999,
} as const;

export const SPACING = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  '2xl': 48,
  '3xl': 64,
} as const;

export const FONTS = {
  heading: 'ComicRelief',
  headingBold: 'ComicRelief-Bold',
  body: 'System',
  manrope: 'Manrope',
  mulish: 'Mulish',
} as const;

export const FONT_SIZES = {
  xs: 12,
  sm: 14,
  base: 16,
  lg: 18,
  xl: 20,
  '2xl': 24,
  '3xl': 30,
  '4xl': 36,
  '5xl': 48,
} as const;
