import React from 'react';
import { View, Text, TextInput, TouchableOpacity, ScrollView } from 'react-native';
import { KeyIcon } from 'phosphor-react-native';
import { useAppTheme, useThemedStyles } from '../../../contexts';

type InputMode = 'create' | 'import';

interface SeedPhraseGenerateProps {
  inputMode: InputMode;
  words: string[];
  importWords: string[];
  importError: string | null;
  onInputModeChange: (mode: InputMode) => void;
  onImportWordChange: (index: number, value: string) => void;
}

export function SeedPhraseGenerate({
  inputMode,
  words,
  importWords,
  importError,
  onInputModeChange,
  onImportWordChange,
}: SeedPhraseGenerateProps) {
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
    scrollView: {
      flex: 1,
    },
    tabContainer: {
      flexDirection: 'row',
      marginBottom: theme.spacing.lg,
      borderRadius: theme.borderRadius.md,
      backgroundColor: theme.colors.surface.tertiary,
      padding: theme.spacing.xs,
    },
    tab: {
      flex: 1,
      paddingVertical: theme.spacing.sm,
      alignItems: 'center',
      borderRadius: theme.borderRadius.md,
    },
    tabActive: {
      backgroundColor: theme.colors.interactive.default,
    },
    tabText: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.muted,
    },
    tabTextActive: {
      color: theme.colors.utility.white,
    },
    wordGrid: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      justifyContent: 'space-between',
      rowGap: theme.spacing.sm,
    },
    wordItem: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: theme.colors.surface.tertiary,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
      paddingVertical: theme.spacing.sm,
      paddingHorizontal: theme.spacing.md,
      width: '48%',
      gap: theme.spacing.sm,
    },
    wordIndex: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
      minWidth: 18,
    },
    wordText: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    importGrid: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      justifyContent: 'space-between',
      rowGap: theme.spacing.sm,
    },
    importWordItem: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: theme.colors.surface.tertiary,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
      paddingVertical: theme.spacing.xs,
      paddingHorizontal: theme.spacing.sm,
      width: '48%',
      gap: theme.spacing.xs,
    },
    importWordIndex: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
      minWidth: 18,
    },
    importWordInput: {
      flex: 1,
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.primary,
      paddingVertical: theme.spacing.xs,
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
        <KeyIcon size={theme.icon.sizes.xxl} color={theme.colors.status.info.icon} weight={theme.icon.weights.light} />
        <Text style={styles.heroSubtitle}>
          {inputMode === 'create' ? 'Your recovery phrase' : 'Enter your 12-word recovery phrase'}
        </Text>
      </View>

      <View style={styles.tabContainer}>
        <TouchableOpacity
          style={[styles.tab, inputMode === 'create' && styles.tabActive]}
          onPress={() => onInputModeChange('create')}
        >
          <Text style={[styles.tabText, inputMode === 'create' && styles.tabTextActive]}>New</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, inputMode === 'import' && styles.tabActive]}
          onPress={() => onInputModeChange('import')}
        >
          <Text style={[styles.tabText, inputMode === 'import' && styles.tabTextActive]}>Import</Text>
        </TouchableOpacity>
      </View>

      <ScrollView showsVerticalScrollIndicator={false} style={styles.scrollView}>
        {inputMode === 'create' ? (
          <View style={styles.wordGrid}>
            {words.map((word, index) => (
              <View key={index} style={styles.wordItem}>
                <Text style={styles.wordIndex}>{index + 1}</Text>
                <Text style={styles.wordText}>{word}</Text>
              </View>
            ))}
          </View>
        ) : (
          <>
            <View style={styles.importGrid}>
              {importWords.map((word, index) => (
                <View key={index} style={styles.importWordItem}>
                  <Text style={styles.importWordIndex}>{index + 1}</Text>
                  <TextInput
                    style={styles.importWordInput}
                    value={word}
                    onChangeText={(text) => onImportWordChange(index, text)}
                    placeholder="word"
                    placeholderTextColor={theme.colors.text.subtle}
                    autoCapitalize="none"
                    autoCorrect={false}
                  />
                </View>
              ))}
            </View>
            {importError && <Text style={styles.errorText}>{importError}</Text>}
          </>
        )}
      </ScrollView>
    </View>
  );
}
