import React from 'react';
import { View, Text } from 'react-native';
import { CheckCircleIcon } from 'phosphor-react-native';
import { CustomModal } from '../../../components/modal';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { getBlockchainDisplayName } from '@ledova/shared-constants';

interface SuccessModalProps {
  visible: boolean;
  txHash: string | null;
  chainShortName: string;
  onDone: () => void;
}

export function SuccessModal({ visible, txHash, chainShortName, onDone }: SuccessModalProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      alignItems: 'center',
      justifyContent: 'center',
      paddingVertical: theme.spacing.xl,
      gap: theme.spacing.md,
    },
    title: {
      fontSize: theme.fontSize.xl,
      fontWeight: theme.fontWeight.bold,
      color: theme.colors.text.primary,
      textAlign: 'center',
    },
    subtitle: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
    },
    section: {
      gap: theme.spacing.sm,
      marginTop: theme.spacing.sm,
    },
    sectionTitle: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.secondary,
      textTransform: 'uppercase',
      letterSpacing: 0.5,
    },
    hashCard: {
      backgroundColor: theme.colors.surface.raised,
      borderRadius: theme.borderRadius.md,
      padding: theme.spacing.md,
      borderWidth: 1,
      borderColor: theme.colors.border.subtle,
    },
    hashValue: {
      fontSize: theme.fontSize.xs,
      fontFamily: 'monospace',
      color: theme.colors.text.primary,
    },
  }));
  const handleOverlayClose = () => {};

  return (
    <CustomModal
      visible={visible}
      onClose={handleOverlayClose}
      showFooter={true}
      showCancelButton={false}
      confirmLabel="Done"
      onConfirm={onDone}
    >
      <View style={styles.container}>
        <CheckCircleIcon
          size={theme.icon.sizes.xxl}
          color={theme.colors.status.success.icon}
          weight={theme.icon.weights.light}
        />
        <Text style={styles.title}>Transaction Sent</Text>
        <Text style={styles.subtitle}>
          Your transaction is being processed by the {getBlockchainDisplayName(chainShortName)} network
        </Text>
      </View>

      {txHash && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Transaction Hash</Text>
          <View style={styles.hashCard}>
            <Text style={styles.hashValue} numberOfLines={1} ellipsizeMode="middle">
              {txHash}
            </Text>
          </View>
        </View>
      )}
    </CustomModal>
  );
}
