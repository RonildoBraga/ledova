import { useState, useCallback, useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getUserProfiles, registerCompany, getCompanies, updateCompany, CACHE_TIMING } from '@ledova/shared';
import type { CompanyRegistration, CompanyType } from '@ledova/shared';
import { apiClient } from '../../../services/apiClient';

interface CompanyFormData {
  name: string;
  tradingName: string;
  companyType: string;
  acn: string;
  abn: string;
}

type FormErrors = Record<string, string[]>;

const initialFormData: CompanyFormData = {
  name: '',
  tradingName: '',
  companyType: 'pty',
  acn: '',
  abn: '',
};

export function useCompanyRegistration() {
  const queryClient = useQueryClient();

  const [form, setForm] = useState<CompanyFormData>(initialFormData);
  const [errors, setErrors] = useState<FormErrors>({});
  const [generalError, setGeneralError] = useState('');
  const lastPopulatedUuid = useRef<string | null>(null);

  const { data: profilesResponse, isLoading: isLoadingProfiles } = useQuery({
    queryKey: ['userProfiles'],
    queryFn: () => getUserProfiles(apiClient),
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
  });

  const { data: companiesResponse, isLoading: isLoadingCompany } = useQuery({
    queryKey: ['signup', 'company'],
    queryFn: () => getCompanies(apiClient),
    staleTime: 0,
  });

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const responseData = profilesResponse?.data as any;
  const userProfile = responseData?.results?.[0] || responseData?.[0] || null;

  const existingCompany = companiesResponse?.data?.results?.[0] || null;

  useEffect(() => {
    if (existingCompany && existingCompany.uuid !== lastPopulatedUuid.current) {
      lastPopulatedUuid.current = existingCompany.uuid;
      setForm({
        name: existingCompany.name || '',
        tradingName: existingCompany.tradingName || '',
        companyType: existingCompany.companyType || 'pty',
        acn: existingCompany.acn || '',
        abn: existingCompany.abn || '',
      });
    }
  }, [existingCompany]);

  const isLoading = isLoadingProfiles || isLoadingCompany;

  const registerMutation = useMutation({
    mutationFn: (data: CompanyRegistration) => registerCompany(apiClient, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auth'] });
      queryClient.invalidateQueries({ queryKey: ['userPreferences'] });
      queryClient.invalidateQueries({ queryKey: ['signup', 'company'] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: (data: { uuid: string; update: Partial<CompanyRegistration> }) =>
      updateCompany(apiClient, data.uuid, data.update),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['signup', 'company'] });
    },
  });

  const setFieldValue = useCallback(
    (field: keyof CompanyFormData, value: string) => {
      setForm((prev) => ({ ...prev, [field]: value }));
      if (errors[field]) {
        setErrors((prev) => {
          const next = { ...prev };
          delete next[field];
          return next;
        });
      }
      setGeneralError('');
    },
    [errors],
  );

  const validateForm = useCallback((): boolean => {
    const newErrors: FormErrors = {};

    if (!form.name.trim()) {
      newErrors.name = ['Company name is required'];
    }

    const acnDigits = form.acn.replace(/\s/g, '');
    if (!acnDigits) {
      newErrors.acn = ['ACN is required'];
    } else if (acnDigits.length !== 9) {
      newErrors.acn = ['ACN must be exactly 9 digits'];
    } else if (!/^\d+$/.test(acnDigits)) {
      newErrors.acn = ['ACN must contain only numbers'];
    }

    const abnDigits = form.abn.replace(/\s/g, '');
    if (abnDigits && abnDigits.length !== 11) {
      newErrors.abn = ['ABN must be exactly 11 digits'];
    } else if (abnDigits && !/^\d+$/.test(abnDigits)) {
      newErrors.abn = ['ABN must contain only numbers'];
    }

    const fullName = userProfile?.fullName || '';
    const nameParts = fullName.trim().split(/\s+/);
    if (nameParts.length < 2 || !nameParts[1]) {
      setGeneralError('Please ensure your full name is set in your profile before registering a company.');
      return false;
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }, [form, userProfile]);

  const handleSubmit = useCallback(
    async (onSuccess: () => void) => {
      if (!validateForm()) return;

      setGeneralError('');

      try {
        const fullName = userProfile?.fullName || '';
        const nameParts = fullName.trim().split(/\s+/);
        const firstName = nameParts[0] || '';
        const lastName = nameParts.slice(1).join(' ') || '';
        const phone = userProfile?.phoneNumber
          ? `${userProfile.phoneCountryCode || ''} ${userProfile.phoneNumber}`.trim()
          : undefined;

        if (existingCompany) {
          await updateMutation.mutateAsync({
            uuid: existingCompany.uuid,
            update: {
              name: form.name,
              tradingName: form.tradingName || undefined,
              companyType: form.companyType as CompanyType,
              acn: form.acn.replace(/\s/g, ''),
              abn: form.abn ? form.abn.replace(/\s/g, '') : undefined,
            },
          });
        } else {
          const data: CompanyRegistration = {
            name: form.name,
            tradingName: form.tradingName || undefined,
            companyType: form.companyType as CompanyType,
            acn: form.acn.replace(/\s/g, ''),
            abn: form.abn ? form.abn.replace(/\s/g, '') : undefined,
            primaryContact: { firstName, lastName, phone },
          };
          await registerMutation.mutateAsync(data);
        }

        onSuccess();
      } catch (err: unknown) {
        const error = err as { response?: { data?: Record<string, unknown> } };
        const data = error?.response?.data;
        if (data) {
          const detail = (data.detail as string) || (data.error as string) || (data.message as string);
          if (detail) {
            setGeneralError(detail);
          } else {
            setGeneralError('An error occurred. Please try again.');
          }
        } else {
          setGeneralError('An error occurred. Please try again.');
        }
      }
    },
    [form, userProfile, existingCompany, validateForm, registerMutation, updateMutation],
  );

  const retryLoad = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['userProfiles'] });
    queryClient.invalidateQueries({ queryKey: ['signup', 'company'] });
  }, [queryClient]);

  return {
    form,
    errors,
    generalError,
    isLoading,
    isSubmitting: registerMutation.isPending || updateMutation.isPending,
    setFieldValue,
    handleSubmit,
    retryLoad,
  };
}
