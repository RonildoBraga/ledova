import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';

import { getUserProfiles, updateUserProfileCompletion, getCompanies } from '@ledova/shared-services';
import { CACHE_TIMING } from '@ledova/shared-constants';
import { useFinancialProfile } from '@hooks/useFinancialProfile';
import { useAccountRole } from '@hooks/useAccountRole';
import apiClient from '@services/apiClient';

import type { ReviewData, Company } from '@ledova/shared-types';

export interface ReviewHookReturn {
  data: ReviewData;
  company: Company | null;
  signupRole: string;
  isLoading: boolean;
  error: string | null;
  completeSignup: () => void;
  isSubmitting: boolean;
  canCompleteSignup: boolean;
}

export const useReview = (): ReviewHookReturn => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { role: signupRole } = useAccountRole();

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
    enabled: signupRole === 'company',
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
  });

  const company: Company | null = signupRole === 'company' ? companyQuery.data?.data?.results?.[0] || null : null;

  const data: ReviewData = {
    userProfile,
    financialProfile: signupRole === 'investor' ? financialProfile : null,
  };

  const isLoading = Boolean(
    userProfileQuery.isLoading ||
    (signupRole === 'investor' && financialProfileLoading) ||
    (signupRole === 'company' && companyQuery.isLoading),
  );

  const error =
    userProfileQuery.error?.message ||
    (signupRole === 'investor' ? financialProfileError?.message : null) ||
    companyQuery.error?.message ||
    null;

  const canCompleteSignup =
    signupRole === 'company' ? Boolean(userProfile && company) : Boolean(userProfile && financialProfile);

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
      navigate(signupRole === 'company' ? '/company' : '/home');
    },
    onError: (error) => {
      console.error('Signup completion failed:', error);
    },
  });

  const completeSignup = () => {
    if (canCompleteSignup) {
      completeSignupMutation.mutate();
    }
  };

  return {
    data,
    company,
    signupRole,
    isLoading,
    error,
    completeSignup,
    isSubmitting: completeSignupMutation.isPending,
    canCompleteSignup,
  };
};
