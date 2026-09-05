const PALETTE = {
  navy: {
    950: '#0c1426',
    900: '#1a2332',
    800: '#2a3441',
    750: '#243247',
    600: '#4a5568',
  },
  slate: {
    800: '#1e293b',
    700: '#334155',
    600: '#475569',
    500: '#64748b',
    400: '#94a3b8',
    300: '#cbd5e1',
  },
  gray: {
    800: '#1f2937',
    700: '#374151',
    600: '#4b5563',
    500: '#6B7280',
    400: '#8b95a1',
    200: '#cbd2d8',
    100: '#e4e7ea',
    50: '#fafbfc',
  },
  indigo: {
    700: '#4338ca',
    600: '#4f46e5',
    500: '#6366f1',
    400: '#818cf8',
    300: '#a5b4fc',
  },
  green: {
    800: '#166534',
    600: '#16a34a',
    400: '#4ade80',
  },
  red: {
    800: '#991b1b',
    600: '#dc2626',
    400: '#f87171',
  },
  amber: {
    600: '#d97706',
    400: '#fbbf24',
  },
  sky: {
    600: '#0284c7',
    400: '#38bdf8',
  },

  zinc: {
    300: '#d4d4d8',
    200: '#e4e4e7',
    100: '#ececee',
    50: '#f5f5f7',
  },

  coolGray: {
    400: '#9CA3AF',
    300: '#d1d5db',
    200: '#E5E7EB',
    100: '#f3f4f6',
  },
  white: '#ffffff',
  black: '#000000',
} as const;

function buildColors(p: {
  surface: { base: string; raised: string; tertiary: string; overlay: string; disabled: string };
  text: { primary: string; secondary: string; body: string; muted: string; subtle: string };
  brand: { subtle: string; light: string; mid: string; default: string; hover: string };
  border: { default: string; subtle: string; strong: string; focus: string };
  success: { light: string; default: string; dark: string };
  error: { light: string; default: string; dark: string; subtle: string; backgroundSubtle: string };
  warning: { light: string; default: string };
  info: { light: string; default: string };
  chartUI: {
    pointerStrip: string;
    tickColor: string;
    gridColor: string;
    lineBackground: string;
    tooltipBg: string;
    tooltipTitle: string;
    tooltipBody: string;
    tooltipBorder: string;
  };
  badge: { successBg: string; infoBg: string };
  interactive: { selectedBg: string };
}) {
  const colors = {
    surface: { ...p.surface, transparent: 'transparent' },
    text: p.text,
    brand: p.brand,
    border: p.border,
    success: p.success,
    error: p.error,
    warning: p.warning,
    info: p.info,
    utility: { white: PALETTE.white, black: PALETTE.black, transparent: 'transparent' },
    chart: ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899'] as readonly string[],

    status: {
      success: { icon: p.success.light, text: p.success.default },
      error: { icon: p.error.light, text: p.error.light },
      warning: { icon: p.warning.light, text: p.warning.light },
      info: { icon: p.info.light, text: p.info.light },
    },
    interactive: {
      default: p.brand.default,
      defaultSubtle: p.brand.mid,
      active: p.brand.light,
      disabled: p.surface.disabled,
      selected: {
        background: p.interactive.selectedBg,
        border: p.brand.default,
      },
    },
    badge: {
      success: { background: `${p.success.dark}80`, text: p.success.light },
      warning: { text: p.warning.light },
      info: { background: p.badge.infoBg, text: p.text.secondary },
    },
    form: {
      placeholder: p.text.muted,
      error: p.error.light,
      errorBackground: `${p.error.dark}80`,
      borderError: p.error.default,
    },
    chartUI: {
      portfolioLine: p.info.light,
      pointerStrip: p.chartUI.pointerStrip,
      tickColor: p.chartUI.tickColor,
      gridColor: p.chartUI.gridColor,
      lineColor: '#60A5FA',
      lineBackground: p.chartUI.lineBackground,
      tooltip: {
        background: p.chartUI.tooltipBg,
        titleColor: p.chartUI.tooltipTitle,
        bodyColor: p.chartUI.tooltipBody,
        borderColor: p.chartUI.tooltipBorder,
      },
    },
    chain: {
      ethereum: '#627eea',
      bitcoin: '#f7931a',
      base: '#0052FF',
    },
  } as const;
  return colors;
}

const DARK_COLORS = buildColors({
  surface: {
    base: PALETTE.navy[950],
    raised: PALETTE.navy[900],
    tertiary: PALETTE.navy[800],
    overlay: PALETTE.navy[750],
    disabled: PALETTE.navy[600],
  },
  text: {
    primary: PALETTE.gray[50],
    secondary: PALETTE.gray[100],
    body: PALETTE.gray[200],
    muted: PALETTE.gray[400],
    subtle: PALETTE.slate[500],
  },
  brand: {
    subtle: PALETTE.indigo[300],
    light: PALETTE.indigo[400],
    mid: PALETTE.indigo[500],
    default: PALETTE.indigo[600],
    hover: PALETTE.indigo[700],
  },
  border: {
    default: PALETTE.slate[700],
    subtle: PALETTE.slate[800],
    strong: PALETTE.slate[600],
    focus: PALETTE.indigo[500],
  },
  success: { light: PALETTE.green[400], default: PALETTE.green[600], dark: PALETTE.green[800] },
  error: {
    light: PALETTE.red[400],
    default: PALETTE.red[600],
    dark: PALETTE.red[800],
    subtle: '#fef2f2',
    backgroundSubtle: PALETTE.red[600] + '1A',
  },
  warning: { light: PALETTE.amber[400], default: PALETTE.amber[600] },
  info: { light: PALETTE.sky[400], default: PALETTE.sky[600] },
  chartUI: {
    pointerStrip: PALETTE.white + '26',
    tickColor: PALETTE.coolGray[400],
    gridColor: PALETTE.gray[700],
    lineBackground: 'rgba(96, 165, 250, 0.1)',
    tooltipBg: PALETTE.gray[700],
    tooltipTitle: PALETTE.coolGray[100],
    tooltipBody: PALETTE.coolGray[300],
    tooltipBorder: PALETTE.gray[500],
  },
  badge: { successBg: `${PALETTE.green[800]}80`, infoBg: PALETTE.navy[800] },
  interactive: { selectedBg: PALETTE.indigo[600] + '4D' },
});

const LIGHT_COLORS = buildColors({
  surface: {
    base: PALETTE.zinc[50],
    raised: PALETTE.white,
    tertiary: PALETTE.zinc[100],
    overlay: PALETTE.zinc[200],
    disabled: PALETTE.slate[300],
  },
  text: {
    primary: '#1a1a2e',
    secondary: PALETTE.gray[800],
    body: PALETTE.gray[700],
    muted: PALETTE.gray[500],
    subtle: PALETTE.slate[400],
  },
  brand: {
    subtle: PALETTE.indigo[300],
    light: PALETTE.indigo[500],
    mid: PALETTE.indigo[600],
    default: PALETTE.indigo[600],
    hover: PALETTE.indigo[700],
  },
  border: {
    default: PALETTE.zinc[300],
    subtle: PALETTE.zinc[200],
    strong: PALETTE.slate[400],
    focus: PALETTE.indigo[500],
  },
  success: { light: PALETTE.green[600], default: PALETTE.green[600], dark: PALETTE.green[800] },
  error: {
    light: PALETTE.red[600],
    default: PALETTE.red[600],
    dark: PALETTE.red[800],
    subtle: '#fef2f2',
    backgroundSubtle: PALETTE.red[600] + '14',
  },
  warning: { light: PALETTE.amber[600], default: PALETTE.amber[600] },
  info: { light: PALETTE.sky[600], default: PALETTE.sky[600] },
  chartUI: {
    pointerStrip: PALETTE.black + '14',
    tickColor: PALETTE.gray[500],
    gridColor: PALETTE.coolGray[200],
    lineBackground: 'rgba(96, 165, 250, 0.08)',
    tooltipBg: PALETTE.white,
    tooltipTitle: '#1a1a2e',
    tooltipBody: PALETTE.gray[600],
    tooltipBorder: PALETTE.zinc[300],
  },
  badge: { successBg: `${PALETTE.green[600]}20`, infoBg: PALETTE.zinc[100] },
  interactive: { selectedBg: PALETTE.indigo[600] + '1A' },
});

function shadow(offsetY: number, blurRadius: number, opacity: number, elevation: number) {
  return {
    shadowColor: PALETTE.black,
    shadowOffset: { width: 0, height: offsetY },
    shadowOpacity: opacity,
    shadowRadius: blurRadius,
    elevation,
    web: `0 ${offsetY}px ${blurRadius}px 0 rgba(0, 0, 0, ${opacity})`,
  } as const;
}

export const DESIGN_TOKENS = {
  colors: DARK_COLORS,

  spacing: {
    xs: 4,
    sm: 8,
    md: 16,
    lg: 24,
    xl: 32,
    xxl: 48,
    xxxl: 64,
    xxxxl: 80,
  },

  borderRadius: {
    none: 0,
    sm: 4,
    md: 8,
    lg: 12,
    xl: 16,
    xxl: 24,
    full: 9999,
  },

  fontSize: {
    xs: 12,
    sm: 14,
    base: 16,
    lg: 18,
    xl: 20,
    xxl: 24,
    xxxl: 30,
    xxxxl: 36,
    xxxxxl: 48,
  },

  fontWeight: {
    normal: '400' as const,
    medium: '500' as const,
    semibold: '600' as const,
    bold: '700' as const,
  },

  lineHeight: {
    tight: 1.25,
    normal: 1.5,
    relaxed: 1.75,
    loose: 2,
  },

  layout: {
    transparentHeaderPadding: 110,
    screenBottomPadding: 40,
    bottomTabBarHeight: 100,
    screenHeaderHeight: 160,
  },

  zIndex: {
    base: 0,
    dropdown: 1000,
    sticky: 1020,
    fixed: 1030,
    backdrop: 1040,
    modal: 1050,
    popover: 1060,
    tooltip: 1070,
  },

  animation: {
    duration: { instant: 0, fast: 150, normal: 300, slow: 500 },
    easing: {
      linear: 'linear' as const,
      easeIn: 'ease-in' as const,
      easeOut: 'ease-out' as const,
      easeInOut: 'ease-in-out' as const,
    },
  },

  shadows: {
    sm: shadow(1, 2, 0.05, 1),
    md: shadow(2, 4, 0.1, 3),
    lg: shadow(4, 8, 0.15, 5),
    xl: shadow(8, 16, 0.2, 8),
  },

  icon: {
    sizes: { xs: 12, sm: 16, md: 20, lg: 24, xl: 32, xxl: 48, hero: 40, display: 64 },
    weights: {
      thin: 'thin' as const,
      light: 'light' as const,
      regular: 'regular' as const,
      bold: 'bold' as const,
      fill: 'fill' as const,
    },
    colors: {
      primary: DARK_COLORS.text.primary,
      muted: DARK_COLORS.text.subtle,
    },
  },
} as const;

export { LIGHT_COLORS };

export type Shadow = typeof DESIGN_TOKENS.shadows;
export type Icon = typeof DESIGN_TOKENS.icon;
