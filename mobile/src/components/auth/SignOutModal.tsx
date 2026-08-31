import React from 'react';
import { View, Text } from 'react-native';
import { SignOutIcon } from 'phosphor-react-native';
import { CustomModal } from '../modal';
import { useAppTheme, useThemedStyles } from '../../contexts';

interface SignOutModalProps {
  visible: boolean;
  isLoading?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

export function SignOutModal({ visible, isLoading = false, onConfirm, onClose }: SignOutModalProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    headerContainer: {
      alignItems: 'center',
      paddingVertical: theme.spacing.md,
    },
    icon: {
      marginBottom: theme.spacing.md,
    },
    title: {
      fontSize: theme.fontSize.xl,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      marginBottom: theme.spacing.sm,
      textAlign: 'center',
    },
    message: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
      lineHeight: 22,
    },
  }));
  return (
    <CustomModal
      visible={visible}
      onClose={onClose}
      showFooter={true}
      confirmLabel="Sign Out"
      onConfirm={onConfirm}
      confirmLoading={isLoading}
      confirmDisabled={isLoading}
    >
      <View style={styles.headerContainer}>
        <SignOutIcon
          size={theme.icon.sizes.xxl}
          color={theme.colors.status.warning.text}
          weight={theme.icon.weights.regular}
          style={styles.icon}
        />
        <Text style={styles.title}>Sign Out</Text>
        <Text style={styles.message}>
          Are you sure you want to sign out? You will need to sign in again to access your account.
        </Text>
      </View>
    </CustomModal>
  );
}
