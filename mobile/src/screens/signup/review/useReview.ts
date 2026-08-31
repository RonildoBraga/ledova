import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigation, NavigationProp } from '@react-navigation/native';
import type { RootStackParamList } from '../../../navigation/AppNavigator';

import { getUserProfiles, updateUserProfileCompletion, getCompanies } from '@ledova/shared-services';
import { CACHE_TIMING } from '@ledova/shared-constants';
import { useFinancialProfile } from '../../../hooks/useFinancialProfile';
import { useRole } from '../../../hooks/useRole';
import { apiClient } from '../../../services/apiClient';

import type { ReviewData } from '@ledova/shared-types';

export const useReview = () => {
  const navigation = useNavigation<NavigationProp<RootStackParamList>>();
  const queryClient = useQueryClient();
  const { isCompany } = useRole();

  const userProfileQuery = useQuery({
    queryKey: ['userProfiles'],
    queryFn: () => getUserProfiles(apiClient),
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  const userProfile = userProfileQuery.data?.data?.results?.[0] || null;

  const { financialProfile, isLoading: financialProfileLoading, error: financialProfileError } = useFinancialProfile();

  const companyQuery = useQuery({
    queryKey: ['signup', 'company'],
    queryFn: () => getCompanies(apiClient),
    enabled: isCompany,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
  });

  const company = isCompany ? companyQuery.data?.data?.results?.[0] || null : null;

  const data: ReviewData = {
    userProfile,
    financialProfile: isCompany ? null : financialProfile,
  };

  const isLoading = Boolean(
    userProfileQuery.isLoading || (!isCompany && financialProfileLoading) || (isCompany && companyQuery.isLoading),
  );

  const error =
    userProfileQuery.error?.message ||
    (!isCompany ? financialProfileError?.message : null) ||
    companyQuery.error?.message ||
    null;

  const canCompleteSignup = isCompany ? Boolean(userProfile && company) : Boolean(userProfile && financialProfile);

  const completeSignupMutation = useMutation({
    mutationFn: async () => {
      if (!userProfile) throw new Error('No user profile found');

      const profileUpdateResponse = await updateUserProfileCompletion(apiClient, userProfile.uuid, {
        termsAndConditions: true,
        isSignupCompleted: true,
      });

      return profileUpdateResponse;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['userProfiles'] });
      queryClient.invalidateQueries({ queryKey: ['userPreferences'] });

      navigation.reset({
        index: 0,
        routes: [{ name: 'MainApp' }],
      });
    },
    onError: () => {},
  });

  const completeSignup = () => {
    if (canCompleteSignup) {
      completeSignupMutation.mutate();
    }
  };

  return {
    data,
    company,
    isCompany,
    isLoading,
    error,
    completeSignup,
    isSubmitting: completeSignupMutation.isPending,
    canCompleteSignup,
  };
};
