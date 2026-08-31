import React from 'react';
import { View, Text, ActivityIndicator } from 'react-native';
import { useAppTheme, useThemedStyles } from '../../../contexts';

interface SoftwareSignMessageProps {
  statusTitle: string;
  statusDescription: string;
}

export function SoftwareSignMessage({ statusTitle }: SoftwareSignMessageProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      alignItems: 'center',
      justifyContent: 'center',
      paddingVertical: theme.spacing.xl,
      gap: theme.spacing.md,
    },
    title: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      textAlign: 'center',
    },
  }));

  return (
    <View style={styles.container}>
      <ActivityIndicator size="large" color={theme.colors.interactive.default} />
      <Text style={styles.title}>{statusTitle}</Text>
    </View>
  );
}
