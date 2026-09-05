import React, { useState } from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { CheckCircleIcon, ClockIcon, ShieldCheckIcon, WarningCircleIcon, XCircleIcon } from 'phosphor-react-native';
import { formatDate, formatDateTime, getUserVerificationStatus, type VerificationStatusType } from '@ledova/shared';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import type { UserProfile } from '@ledova/shared';
import { Panel } from '../../../components/panel';
import { VerificationModal } from './VerificationModal';

interface AccountStatusSectionProps {
  userProfile: UserProfile | null | undefined;
  isLoading: boolean;
  isError: boolean;
  onRefresh: () => void;
}

export function AccountStatusSection({ userProfile, isLoading, isError, onRefresh }: AccountStatusSectionProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    statusInfo: {
      gap: theme.spacing.sm,
    },
    infoRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: theme.spacing.sm,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.subtle,
    },
    clickableRow: {},
    label: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      flex: 0,
      minWidth: 100,
    },
    value: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.primary,
      fontWeight: theme.fontWeight.medium,
      flex: 1,
      textAlign: 'right',
    },
    statusContainer: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.sm,
    },
    statusBadge: {
      borderRadius: theme.borderRadius.sm,
      paddingHorizontal: 8,
      paddingVertical: 4,
    },
    statusText: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
    },
    placeholder: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      fontStyle: 'italic',
      textAlign: 'center',
      paddingVertical: theme.spacing.lg,
    },
    error: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.status.error.text,
      textAlign: 'center',
      paddingVertical: theme.spacing.lg,
    },
  }));
  const [showVerificationModal, setShowVerificationModal] = useState(false);

  const renderContent = () => {
    if (isLoading && !userProfile) {
      return <Text style={styles.placeholder}>Loading account status...</Text>;
    }

    if (isError) {
      return <Text style={styles.error}>Error loading account status</Text>;
    }

    if (!userProfile) {
      return <Text style={styles.placeholder}>No account data available</Text>;
    }

    const renderIdentityCheckRow = () => {
      const verificationStatus = getUserVerificationStatus(userProfile);
      const getVerificationStatusColor = (statusType: VerificationStatusType): string => {
        switch (statusType) {
          case 'verified':
            return theme.colors.status.success.text;
          case 'rejected':
            return theme.colors.status.error.text;
          default:
            return theme.colors.status.warning.text;
        }
      };

      const triggerIdentityCheck = verificationStatus.type != 'verified';
      const iconSize = 20;
      const statusType = verificationStatus.type;
      const statusLabel = verificationStatus.label;
      const statusColor = getVerificationStatusColor(statusType);

      const statusContent = (
        <>
          <Text style={styles.label}>Identity check:</Text>
          <View
            id="identityStatus"
            style={[
              styles.statusContainer,
              statusType !== 'verified' && styles.statusBadge,
              statusType !== 'verified' && { backgroundColor: `${statusColor}15` },
            ]}
          >
            <Text style={[styles.statusText, { color: statusColor }]}>{statusLabel}</Text>
            {statusType === 'not_verified' ? (
              <WarningCircleIcon size={iconSize} color={statusColor} weight="regular" />
            ) : statusType === 'verified' ? (
              <CheckCircleIcon size={iconSize} color={statusColor} weight="fill" />
            ) : statusType === 'pending' ? (
              <ClockIcon size={iconSize} color={statusColor} weight="regular" />
            ) : statusType === 'rejected' ? (
              <XCircleIcon size={iconSize} color={statusColor} weight="fill" />
            ) : (
              <WarningCircleIcon size={iconSize} color={statusColor} weight="regular" />
            )}
          </View>
        </>
      );

      if (triggerIdentityCheck) {
        return (
          <TouchableOpacity
            style={[styles.infoRow, styles.clickableRow]}
            onPress={() => setShowVerificationModal(true)}
            activeOpacity={0.7}
          >
            {statusContent}
          </TouchableOpacity>
        );
      }

      return <View style={styles.infoRow}>{statusContent}</View>;
    };

    return (
      <View style={styles.statusInfo}>
        {renderIdentityCheckRow()}

        <View style={styles.infoRow}>
          <Text style={styles.label}>Member Since:</Text>
          <Text style={styles.value}>{formatDate(userProfile.dateJoined, 'Not available')}</Text>
        </View>

        <View style={styles.infoRow}>
          <Text style={styles.label}>Last Login:</Text>
          <Text style={styles.value}>{formatDateTime(userProfile.lastLogin)}</Text>
        </View>
      </View>
    );
  };

  return (
    <>
      <Panel title="Account Status" icon={<ShieldCheckIcon />}>
        {renderContent()}
      </Panel>

      <VerificationModal
        visible={showVerificationModal}
        onClose={() => setShowVerificationModal(false)}
        onRefresh={onRefresh}
      />
    </>
  );
}
