import React from 'react';
import { View, Text, TextInput } from 'react-native';
import { ShieldCheckIcon } from 'phosphor-react-native';
import { useAppTheme, useThemedStyles } from '../../../contexts';

interface SeedPhraseConfirmProps {
  quizPositions: number[];
  quizAnswers: string[];
  quizError: string | null;
  onAnswerChange: (index: number, text: string) => void;
}

export function SeedPhraseConfirm({ quizPositions, quizAnswers, quizError, onAnswerChange }: SeedPhraseConfirmProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      flex: 1,
    },
    heroSection: {
      alignItems: 'center',
      gap: theme.spacing.sm,
      paddingTop: theme.spacing.sm,
      paddingBottom: theme.spacing.lg,
    },
    heroSubtitle: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
    },
    quizContainer: {
      gap: theme.spacing.md,
      marginBottom: theme.spacing.lg,
    },
    quizItem: {
      gap: theme.spacing.xs,
    },
    quizLabel: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.muted,
    },
    quizInput: {
      backgroundColor: theme.colors.surface.tertiary,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
      paddingVertical: theme.spacing.md,
      paddingHorizontal: theme.spacing.lg,
      fontSize: theme.fontSize.base,
      color: theme.colors.text.primary,
    },
    errorText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.status.error.text,
      marginTop: theme.spacing.sm,
    },
  }));
  return (
    <View style={styles.container}>
      <View style={styles.heroSection}>
        <ShieldCheckIcon
          size={theme.icon.sizes.xxl}
          color={theme.colors.status.info.icon}
          weight={theme.icon.weights.light}
        />
        <Text style={styles.heroSubtitle}>Enter the following words to confirm you saved your recovery phrase</Text>
      </View>

      <View style={styles.quizContainer}>
        {quizPositions.map((pos, i) => (
          <View key={pos} style={styles.quizItem}>
            <Text style={styles.quizLabel}>Word #{pos + 1}</Text>
            <TextInput
              style={styles.quizInput}
              value={quizAnswers[i]}
              onChangeText={(text) => onAnswerChange(i, text)}
              placeholder="Enter word"
              placeholderTextColor={theme.colors.text.subtle}
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>
        ))}
      </View>

      {quizError && <Text style={styles.errorText}>{quizError}</Text>}
    </View>
  );
}
