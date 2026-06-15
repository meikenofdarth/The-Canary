export const COLORS = {
  background: "#0a0a0f",
  surface: "#111118",
  surface2: "#1a1a28",
  border: "#2a2a3a",
  accent: "#f5a623",
  accent2: "#ff6b35",
  textPrimary: "#f0f0f8",
  textSecondary: "#8888aa",
  textMuted: "#555570",
  success: "#34d399",
  warning: "#fbbf24",
  error: "#f87171",
  purple: "#a78bfa",
  blue: "#60a5fa",
} as const;

export const FONTS = {
  regular: { fontWeight: "400" as const },
  medium: { fontWeight: "500" as const },
  semibold: { fontWeight: "600" as const },
  bold: { fontWeight: "700" as const },
  extrabold: { fontWeight: "800" as const },
};

export const RADIUS = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  full: 999,
} as const;

export const SPACING = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
} as const;
