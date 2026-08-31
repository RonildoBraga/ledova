import React from 'react';
import { View, ScrollView } from 'react-native';
import { GradientBackground } from '../../components/GradientBackground';
import { useUserProfile } from './useUserProfile';
import { useAppTheme, useThemedStyles } from '../../contexts';
import { ProfileInfoSection } from './components/ProfileInfoSection';
import { AccountStatusSection } from './components/AccountStatusSection';

export const UserProfileScreen = () => {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      flex: 1,
    },
    scrollView: {
      flex: 1,
    },
    content: {
      paddingTop: theme.spacing.md,
      paddingHorizontal: theme.spacing.sm,
      gap: theme.spacing.md,
    },
  }));
  const { userProfile, isLoading, isError, refreshProfile } = useUserProfile();

  return (
    <GradientBackground>
      <View style={styles.container}>
        <ScrollView style={styles.scrollView} showsVerticalScrollIndicator={false}>
          <View style={styles.content}>
            <ProfileInfoSection
              userProfile={userProfile}
              isLoading={isLoading}
              isError={isError}
              onRefresh={refreshProfile}
            />

            <AccountStatusSection
              userProfile={userProfile}
              isLoading={isLoading}
              isError={isError}
              onRefresh={refreshProfile}
            />
          </View>
        </ScrollView>
      </View>
    </GradientBackground>
  );
};
