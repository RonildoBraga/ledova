import React from 'react';
import { View, Text } from 'react-native';
import { useAppTheme, useThemedStyles } from '../../contexts';

interface ScreenHeaderProps {
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
}

export function ScreenHeader({ icon, title, subtitle }: ScreenHeaderProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    header: {
      alignItems: 'center',
      marginTop: theme.spacing.xs,
      marginBottom: theme.spacing.md,
    },
    iconContainer: {
      padding: theme.spacing.xs,
      marginBottom: theme.spacing.sm,
    },
    title: {
      fontSize: theme.fontSize.xl,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      marginBottom: theme.spacing.sm,
    },
    subtitle: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
      paddingHorizontal: theme.spacing.md,
    },
  }));
  return (
    <View style={styles.header}>
      <View style={styles.iconContainer}>{icon}</View>
      <Text style={styles.title}>{title}</Text>
      {subtitle && <Text style={styles.subtitle}>{subtitle}</Text>}
    </View>
  );
}
