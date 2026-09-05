import React, { useEffect, useRef } from 'react';
import { View, Text, TouchableOpacity, Image, StyleSheet } from 'react-native';
import { LockKeyIcon } from 'phosphor-react-native';
import { useAppLock } from '../../contexts/AppLockContext';
import { GradientBackground } from '../GradientBackground';
import { useAppTheme, useThemedStyles } from '../../contexts';

export function AppLockScreen() {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
      padding: theme.spacing.xl,
    },
    content: {
      alignItems: 'center',
      width: '100%',
      maxWidth: 300,
    },
    logoContainer: {
      marginBottom: theme.spacing.xl,
    },
    logo: {
      width: 80,
      height: 80,
      borderRadius: theme.borderRadius.lg,
    },
    lockIconContainer: {
      width: 120,
      height: 120,
      borderRadius: 60,
      backgroundColor: theme.colors.brand.default + '1A',
      justifyContent: 'center',
      alignItems: 'center',
      marginBottom: theme.spacing.xl,
    },
    title: {
      fontSize: theme.fontSize.xxl,
      fontWeight: theme.fontWeight.bold,
      color: theme.colors.text.primary,
      marginBottom: theme.spacing.sm,
      textAlign: 'center',
    },
    subtitle: {
      fontSize: theme.fontSize.base,
      color: theme.colors.text.muted,
      textAlign: 'center',
      marginBottom: theme.spacing.xxl,
    },
    unlockButton: {
      backgroundColor: theme.colors.interactive.default,
      paddingVertical: theme.spacing.md,
      paddingHorizontal: theme.spacing.xl,
      borderRadius: theme.borderRadius.md,
      width: '100%',
    },
    unlockButtonText: {
      color: theme.colors.utility.white,
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.semibold,
      textAlign: 'center',
    },
  }));
  const { isLocked, unlock, biometricType } = useAppLock();
  const hasAutoPrompted = useRef(false);

  useEffect(() => {
    if (isLocked && !hasAutoPrompted.current) {
      hasAutoPrompted.current = true;

      const timer = setTimeout(() => {
        unlock();
      }, 500);
      return () => clearTimeout(timer);
    }

    if (!isLocked) {
      hasAutoPrompted.current = false;
    }
  }, [isLocked, unlock]);

  if (!isLocked) {
    return null;
  }

  const handleUnlock = async () => {
    await unlock();
  };

  return (
    <View style={StyleSheet.absoluteFill}>
      <GradientBackground>
        <View style={styles.container}>
          <View style={styles.content}>
            <View style={styles.logoContainer}>
              {/* eslint-disable-next-line @typescript-eslint/no-require-imports */}
              <Image source={require('../../../assets/icon.png')} style={styles.logo} resizeMode="contain" />
            </View>

            <View style={styles.lockIconContainer}>
              <LockKeyIcon size={64} color={theme.colors.interactive.default} weight="regular" />
            </View>

            <Text style={styles.title}>App Locked</Text>
            <Text style={styles.subtitle}>Use {biometricType} to unlock Ledova</Text>

            <TouchableOpacity style={styles.unlockButton} onPress={handleUnlock} activeOpacity={0.8}>
              <Text style={styles.unlockButtonText}>Unlock with {biometricType}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </GradientBackground>
    </View>
  );
}
