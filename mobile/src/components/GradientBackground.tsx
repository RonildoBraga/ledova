import React from 'react';
import { View, ViewStyle } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { StyleSheet } from 'react-native';
import { useAppTheme, useThemeMode } from '../contexts';

interface GradientBackgroundProps {
  children: React.ReactNode;
  style?: ViewStyle;
}

export function GradientBackground({ children, style }: GradientBackgroundProps) {
  const theme = useAppTheme();
  const { themeMode } = useThemeMode();

  if (themeMode === 'light') {
    return <View style={[styles.container, { backgroundColor: theme.colors.surface.base }, style]}>{children}</View>;
  }

  return (
    <View style={[styles.container, style]}>
      <LinearGradient
        colors={['#080d18', '#0a0f1a', '#0c121e', '#0e1624', '#121c30', '#182640', '#1e2f50', '#2b3d68']}
        locations={[0, 0.2, 0.4, 0.55, 0.68, 0.8, 0.92, 1]}
        style={styles.gradient}
      />
      <LinearGradient
        colors={['transparent', 'transparent', 'rgba(99, 102, 241, 0.08)', 'rgba(99, 102, 241, 0.12)']}
        locations={[0, 0.6, 0.85, 1]}
        style={styles.accentOverlay}
      />
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  gradient: {
    position: 'absolute',
    left: 0,
    right: 0,
    top: 0,
    bottom: 0,
  },
  accentOverlay: {
    position: 'absolute',
    left: 0,
    right: 0,
    top: 0,
    bottom: 0,
    opacity: 0.1,
  },
});
