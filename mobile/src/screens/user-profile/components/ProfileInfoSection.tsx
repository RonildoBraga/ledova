import React from 'react';
import { View, Text } from 'react-native';
import { UserIcon } from 'phosphor-react-native';
import { formatDate } from '@ledova/shared-utils';
import { Panel } from '../../../components/panel';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import type { UserProfile } from '@ledova/shared-types';

interface ProfileInfoSectionProps {
  userProfile: UserProfile | null | undefined;
  isLoading: boolean;
  isError: boolean;
  onRefresh: () => void;
}

export function ProfileInfoSection({ userProfile, isLoading, isError }: ProfileInfoSectionProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    profileInfo: {
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
  const renderContent = () => {
    if (isLoading && !userProfile) {
      return <Text style={styles.placeholder}>Loading profile...</Text>;
    }

    if (isError) {
      return <Text style={styles.error}>Error loading profile</Text>;
    }

    if (!userProfile) {
      return <Text style={styles.placeholder}>No profile data available</Text>;
    }

    return (
      <View style={styles.profileInfo}>
        <View style={styles.infoRow}>
          <Text style={styles.label}>Name:</Text>
          <Text style={styles.value}>{userProfile.fullName}</Text>
        </View>

        <View style={styles.infoRow}>
          <Text style={styles.label}>Email:</Text>
          <Text style={styles.value}>{userProfile.email}</Text>
        </View>

        <View style={styles.infoRow}>
          <Text style={styles.label}>Phone:</Text>
          <Text style={styles.value}>
            {userProfile.phoneNumber ? `${userProfile.phoneCountryCode} ${userProfile.phoneNumber}` : 'Not provided'}
          </Text>
        </View>

        <View style={styles.infoRow}>
          <Text style={styles.label}>Date of Birth:</Text>
          <Text style={styles.value}>{formatDate(userProfile.dateOfBirth, 'Not available')}</Text>
        </View>

        <View style={styles.infoRow}>
          <Text style={styles.label}>Address:</Text>
          <Text style={styles.value}>{userProfile.residentialAddress || 'Not provided'}</Text>
        </View>

        <View style={styles.infoRow}>
          <Text style={styles.label}>Citizenship:</Text>
          <Text style={styles.value}>{userProfile.citizenshipCountryName || 'Not provided'}</Text>
        </View>
      </View>
    );
  };

  return (
    <Panel title="Profile Information" icon={<UserIcon />}>
      {renderContent()}
    </Panel>
  );
}
