import { View, ActivityIndicator, Text } from 'react-native';
import { useAppTheme, useThemedStyles } from '../../../contexts';

export type ChartState = 'loading' | 'error' | 'empty';

interface ChartStateViewProps {
  state: ChartState;
  loadingText: string;
  errorText: string;
  errorSubtext: string;
  emptyText: string;
  emptySubtext: string;
}

export function ChartStateView({
  state,
  loadingText,
  errorText,
  errorSubtext,
  emptyText,
  emptySubtext,
}: ChartStateViewProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    centerContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingVertical: theme.spacing.lg },
    loadingText: { marginTop: theme.spacing.sm, fontSize: theme.fontSize.base, color: theme.colors.text.muted },
    errorText: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.status.error.text,
      marginBottom: theme.spacing.xs,
    },
    subtextError: { fontSize: theme.fontSize.sm, color: theme.colors.text.muted, textAlign: 'center' },
    emptyText: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.muted,
      marginBottom: theme.spacing.xs,
    },
    subtext: { fontSize: theme.fontSize.sm, color: theme.colors.text.subtle, textAlign: 'center' },
  }));
  if (state === 'loading') {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color={theme.colors.interactive.default} />
        <Text style={styles.loadingText}>{loadingText}</Text>
      </View>
    );
  }

  if (state === 'error') {
    return (
      <View style={styles.centerContainer}>
        <Text style={styles.errorText}>{errorText}</Text>
        <Text style={styles.subtextError}>{errorSubtext}</Text>
      </View>
    );
  }

  return (
    <View style={styles.centerContainer}>
      <Text style={styles.emptyText}>{emptyText}</Text>
      <Text style={styles.subtext}>{emptySubtext}</Text>
    </View>
  );
}
