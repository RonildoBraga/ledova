import React, { useState, useEffect, useCallback, useRef } from 'react';
import { View, Text, ScrollView, ActivityIndicator } from 'react-native';
import { ShieldWarningIcon, EyeSlashIcon } from 'phosphor-react-native';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { GradientBackground } from '../../../components/GradientBackground';
import { Panel } from '../../../components/panel';
import { ButtonGroup } from '../../../components/buttons';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { getSeedPhrase } from '../../../services/secureKeyStorage';
import type { WalletsStackParamList } from '../../../navigation/WalletsStackNavigator';

type SeedPhraseBackupRouteProp = RouteProp<WalletsStackParamList, 'SeedPhraseBackup'>;

type BackupState = 'authenticating' | 'visible' | 'hidden' | 'error';

const AUTO_HIDE_SECONDS = 60;

export function SeedPhraseBackupScreen() {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      flex: 1,
    },
    content: {
      paddingTop: theme.spacing.md,
      paddingHorizontal: theme.spacing.sm,
    },
    panelContent: {
      flex: 1,
      flexDirection: 'column',
    },
    scrollWrapper: {
      flex: 1,
      padding: theme.spacing.sm,
    },
    footer: {
      paddingVertical: theme.spacing.sm,
      paddingHorizontal: theme.spacing.xs,
    },
    centerContainer: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      gap: theme.spacing.md,
      paddingHorizontal: theme.spacing.lg,
    },
    loadingText: {
      fontSize: theme.fontSize.base,
      color: theme.colors.text.muted,
    },
    errorTitle: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.status.error.text,
    },
    errorText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
    },
    hiddenTitle: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    hiddenText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
      lineHeight: 20,
    },
    warningBanner: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: theme.spacing.sm,
      backgroundColor: theme.colors.surface.tertiary,
      padding: theme.spacing.md,
      borderRadius: theme.borderRadius.md,
      marginBottom: theme.spacing.lg,
    },
    warningText: {
      flex: 1,
      fontSize: theme.fontSize.sm,
      color: theme.colors.status.warning.text,
      lineHeight: 20,
    },
    countdown: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
      textAlign: 'center',
      marginBottom: theme.spacing.md,
    },
    wordGrid: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: theme.spacing.sm,
      justifyContent: 'center',
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
      width: '47%',
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
  }));
  const navigation = useNavigation();
  const route = useRoute<SeedPhraseBackupRouteProp>();
  const { seedIdentifier } = route.params;

  const [backupState, setBackupState] = useState<BackupState>('authenticating');
  const [words, setWords] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(AUTO_HIDE_SECONDS);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadSeedPhrase = useCallback(async () => {
    setBackupState('authenticating');
    try {
      const mnemonic = await getSeedPhrase(seedIdentifier);
      if (!mnemonic) {
        navigation.goBack();
        return;
      }
      setWords(mnemonic.split(' '));
      setBackupState('visible');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retrieve recovery phrase');
      setBackupState('error');
    }
  }, [seedIdentifier, navigation]);

  useEffect(() => {
    loadSeedPhrase();

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      setWords([]);
    };
  }, [loadSeedPhrase]);

  useEffect(() => {
    if (backupState === 'visible') {
      setCountdown(AUTO_HIDE_SECONDS);
      timerRef.current = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            setBackupState('hidden');
            setWords([]);
            if (timerRef.current) clearInterval(timerRef.current);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);

      return () => {
        if (timerRef.current) clearInterval(timerRef.current);
      };
    }
  }, [backupState]);

  const handleRevealAgain = useCallback(() => {
    loadSeedPhrase();
  }, [loadSeedPhrase]);

  const renderContent = () => {
    if (backupState === 'authenticating') {
      return (
        <View style={styles.centerContainer}>
          <ActivityIndicator size="large" color={theme.colors.interactive.default} />
          <Text style={styles.loadingText}>Authenticating...</Text>
        </View>
      );
    }

    if (backupState === 'error') {
      return (
        <View style={styles.centerContainer}>
          <ShieldWarningIcon size={theme.icon.sizes.xxl} color={theme.colors.status.error.icon} weight="light" />
          <Text style={styles.errorTitle}>Unable to Load</Text>
          {error && <Text style={styles.errorText}>{error}</Text>}
        </View>
      );
    }

    if (backupState === 'hidden') {
      return (
        <View style={styles.centerContainer}>
          <EyeSlashIcon size={theme.icon.sizes.xxl} color={theme.colors.text.muted} weight="light" />
          <Text style={styles.hiddenTitle}>Recovery Phrase Hidden</Text>
          <Text style={styles.hiddenText}>
            The phrase was automatically hidden for security. Authenticate again to reveal it.
          </Text>
        </View>
      );
    }

    return (
      <ScrollView showsVerticalScrollIndicator={false}>
        <View style={styles.warningBanner}>
          <ShieldWarningIcon size={theme.icon.sizes.md} color={theme.colors.status.warning.icon} weight="fill" />
          <Text style={styles.warningText}>
            Never share your recovery phrase. Anyone with these words can access your funds.
          </Text>
        </View>

        <Text style={styles.countdown}>Auto-hiding in {countdown}s</Text>

        <View style={styles.wordGrid}>
          {words.map((word, index) => (
            <View key={index} style={styles.wordItem}>
              <Text style={styles.wordIndex}>{index + 1}</Text>
              <Text style={styles.wordText}>{word}</Text>
            </View>
          ))}
        </View>
      </ScrollView>
    );
  };

  return (
    <GradientBackground>
      <View style={styles.container}>
        <View style={styles.content}>
          <Panel fullHeight>
            <View style={styles.panelContent}>
              <View style={styles.scrollWrapper}>{renderContent()}</View>

              <View style={styles.footer}>
                <ButtonGroup
                  secondaryButton={
                    backupState === 'hidden'
                      ? {
                          label: 'Reveal Again',
                          onPress: handleRevealAgain,
                        }
                      : undefined
                  }
                  primaryButton={{
                    label: 'Done',
                    onPress: () => navigation.goBack(),
                  }}
                  size="medium"
                />
              </View>
            </View>
          </Panel>
        </View>
      </View>
    </GradientBackground>
  );
}
