import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  CACHE_TIMING,
  deleteInvestorClassification,
  getInvestorClassifications,
  getInvestorEligibility,
  submitInvestorClassification,
} from '@ledova/shared';
import type { InvestorClassification, InvestorClassificationSubmission } from '@ledova/shared';
import { apiClient } from '../../services/apiClient';

type Submission = Omit<InvestorClassificationSubmission, 'file'> & { file: unknown };

export function useInvestorEligibility() {
  const queryClient = useQueryClient();

  const eligibilityQuery = useQuery({
    queryKey: ['investor-eligibility'],
    queryFn: () => getInvestorEligibility(apiClient),
    staleTime: CACHE_TIMING.SHORT_STALE_TIME,
  });

  const classificationsQuery = useQuery({
    queryKey: ['investor-classifications'],
    queryFn: () => getInvestorClassifications(apiClient),
    staleTime: CACHE_TIMING.SHORT_STALE_TIME,
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['investor-eligibility'] });
    queryClient.invalidateQueries({ queryKey: ['investor-classifications'] });
  };

  const submitMutation = useMutation({
    mutationFn: (data: Submission) => submitInvestorClassification(apiClient, data as InvestorClassificationSubmission),
    onSuccess: refresh,
  });

  const deleteMutation = useMutation({
    mutationFn: (uuid: string) => deleteInvestorClassification(apiClient, uuid),
    onSuccess: refresh,
  });

  const responseData = classificationsQuery.data?.data;
  const classifications: InvestorClassification[] = Array.isArray(responseData)
    ? responseData
    : responseData?.results || [];

  return {
    eligibility: eligibilityQuery.data?.data,
    classifications,
    isLoading: eligibilityQuery.isLoading || classificationsQuery.isLoading,
    refresh,
    submitClaim: submitMutation.mutateAsync,
    isSubmitting: submitMutation.isPending,
    deleteClaim: deleteMutation.mutate,
    isDeleting: deleteMutation.isPending,
  };
}
