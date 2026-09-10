import { useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';

import {
  getUserProfiles,
  updateUserProfileCompletion,
  getCompanies,
  getCompany,
  useFinancialProfile,
  CACHE_TIMING,
  describeFailure,
} from '@ledova/shared';
import { useAccountRole } from '@hooks/useAccountRole';
import { AUTH_QUERY_KEY } from '@hooks/useAuth';
import apiClient from '@services/apiClient';

import type { ReviewData, Company } from '@ledova/shared';

export interface ReviewHookReturn {
  data: ReviewData;
  company: Company | null;
  signupRole: string;
  isLoading: boolean;
  error: string | null;
  completeSignup: () => void;
  isSubmitting: boolean;
  canCompleteSignup: boolean;
  retryLoad: () => Promise<void>;
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

  const selectedUuid = signupRole === 'company' ? companyQuery.data?.data.results[0]?.uuid : undefined;
  const detailQuery = useQuery({
    queryKey: ['signup', 'company-detail', selectedUuid],
    queryFn: () => getCompany(apiClient, selectedUuid!),
    enabled: Boolean(selectedUuid),
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
  });
  const company = selectedUuid && detailQuery.data?.data.uuid === selectedUuid ? detailQuery.data.data : null;

  const data: ReviewData = {
    userProfile,
    financialProfile: signupRole === 'investor' ? financialProfile : null,
  };

  const isLoading = Boolean(
    userProfileQuery.isLoading ||
    (signupRole === 'investor' && financialProfileLoading) ||
    (signupRole === 'company' && (companyQuery.isLoading || detailQuery.isLoading)),
  );

  const error =
    userProfileQuery.error?.message ||
    (signupRole === 'investor' ? financialProfileError?.message : null) ||
    (signupRole === 'company'
      ? companyQuery.error?.message ||
        detailQuery.error?.message ||
        (selectedUuid && detailQuery.isSuccess && !company
          ? 'Company details did not match the selected company. Please try again.'
          : null)
      : null) ||
    null;

  const canCompleteSignup =
    !isLoading &&
    !error &&
    (signupRole === 'company' ? Boolean(userProfile && company) : Boolean(userProfile && financialProfile));

  const completeSignupMutation = useMutation({
    mutationFn: async () => {
      if (!userProfile) throw new Error('No user profile found');

      const profileUpdateResponse = await updateUserProfileCompletion(apiClient, userProfile.uuid, {
        termsAndConditions: true,
        isSignupCompleted: true,
      });

      return profileUpdateResponse;
    },
    onSuccess: async () => {
      queryClient.invalidateQueries({ queryKey: ['userProfiles'] });
      queryClient.invalidateQueries({ queryKey: ['userPreferences'] });
      await queryClient.refetchQueries({ queryKey: AUTH_QUERY_KEY, exact: true });
      navigate(signupRole === 'company' ? '/company' : '/home');
    },
    onError: (error) => {
      console.error(`Signup completion failed: ${describeFailure(error)}`);
    },
  });

  const completeSignup = () => {
    if (canCompleteSignup) {
      completeSignupMutation.mutate();
    }
  };

  const retryLoad = useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['userProfiles'] }),
      ...(signupRole === 'company' ? [queryClient.invalidateQueries({ queryKey: ['signup', 'company'] })] : []),
      ...(signupRole === 'investor' ? [queryClient.invalidateQueries({ queryKey: ['financialProfiles'] })] : []),
      ...(selectedUuid
        ? [queryClient.invalidateQueries({ queryKey: ['signup', 'company-detail', selectedUuid] })]
        : []),
    ]);
  }, [queryClient, signupRole, selectedUuid]);

  return {
    data,
    company,
    signupRole,
    isLoading,
    error,
    completeSignup,
    isSubmitting: completeSignupMutation.isPending,
    canCompleteSignup,
    retryLoad,
  };
};
