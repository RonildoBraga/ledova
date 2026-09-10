import { useState, useCallback, useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getUserProfiles,
  registerCompany,
  getCompanies,
  getCompany,
  updateCompany,
  readApiError,
} from '@ledova/shared';
import type { CompanyRegistration, CompanyType } from '@ledova/shared';
import apiClient from '@services/apiClient';

interface CompanyFormData {
  name: string;
  tradingName: string;
  companyType: string;
  acn: string;
  abn: string;
}

type FormErrors = Record<string, string[]>;

const COULD_NOT_SAVE = 'We could not save your company details. Please try again.';

const initialFormData: CompanyFormData = {
  name: '',
  tradingName: '',
  companyType: 'pty',
  acn: '',
  abn: '',
};

export const DISPLAYED_FIELDS = Object.keys(initialFormData) as (keyof CompanyFormData)[];

interface FormOwner {
  uuid: string | null | undefined;
}

interface FormState {
  owner: FormOwner;
  form: CompanyFormData;
  errors: FormErrors;
  generalError: string;
  dirty: Set<keyof CompanyFormData>;
  hydrated: boolean;
}

interface Submission {
  owner: FormOwner;
  owners: FormOwner[];
  cancelled: boolean;
}

const initialState = (owner: FormOwner): FormState => ({
  owner,
  form: { ...initialFormData },
  errors: {},
  generalError: '',
  dirty: new Set(),
  hydrated: owner.uuid === null,
});

export function useSignupCompanyRegistration() {
  const queryClient = useQueryClient();
  const profilesQuery = useQuery({
    queryKey: ['userProfiles'],
    queryFn: () => getUserProfiles(apiClient),
  });
  const companiesQuery = useQuery({
    queryKey: ['signup', 'company'],
    queryFn: () => getCompanies(apiClient),
    staleTime: 0,
  });
  const existingCompany = companiesQuery.data?.data.results[0] || null;
  const selectedUuid = companiesQuery.data ? (existingCompany?.uuid ?? null) : undefined;
  const detailQuery = useQuery({
    queryKey: ['signup', 'company-detail', selectedUuid],
    queryFn: () => getCompany(apiClient, selectedUuid!),
    enabled: Boolean(selectedUuid),
    staleTime: 0,
  });
  const detail = selectedUuid && detailQuery.data?.data.uuid === selectedUuid ? detailQuery.data.data : null;
  const owner = useMemo(() => ({ uuid: selectedUuid }), [selectedUuid]);
  const currentOwner = useRef(owner);
  currentOwner.current = owner;
  const mounted = useRef(true);
  const submission = useRef<Submission | null>(null);
  const pending = submission.current;
  if (pending && pending.owners[pending.owners.length - 1] !== owner) pending.owners.push(owner);

  useLayoutEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (submission.current) submission.current.cancelled = true;
    };
  }, []);

  const [storedState, setState] = useState(() => initialState(owner));
  const state = storedState.owner === owner ? storedState : initialState(owner);
  const { form, errors, generalError } = state;
  const updateState = useCallback(
    (update: (value: FormState) => FormState) => {
      setState((previous) =>
        currentOwner.current === owner ? update(previous.owner === owner ? previous : initialState(owner)) : previous,
      );
    },
    [owner],
  );
  const setErrors = useCallback(
    (value: FormErrors) => updateState((previous) => ({ ...previous, errors: value })),
    [updateState],
  );
  const setGeneralError = useCallback(
    (value: string) => updateState((previous) => ({ ...previous, generalError: value })),
    [updateState],
  );

  useEffect(() => {
    if (!detail) return;
    const saved: CompanyFormData = {
      name: detail.name || '',
      tradingName: detail.tradingName || '',
      companyType: detail.companyType || 'pty',
      acn: detail.acn || '',
      abn: detail.abn || '',
    };
    updateState((previous) => {
      const values = { ...previous.form };
      for (const field of DISPLAYED_FIELDS) if (!previous.dirty.has(field)) values[field] = saved[field];
      if (previous.hydrated && DISPLAYED_FIELDS.every((field) => values[field] === previous.form[field]))
        return previous;
      return { ...previous, form: values, hydrated: true };
    });
  }, [detail, updateState]);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const responseData = profilesQuery.data?.data as any;
  const userProfile = responseData?.results?.[0] || responseData?.[0] || null;
  const loadError =
    profilesQuery.error?.message ||
    companiesQuery.error?.message ||
    (selectedUuid
      ? detailQuery.error?.message ||
        (detailQuery.isSuccess && !detail
          ? 'Company details did not match the selected company. Please try again.'
          : null)
      : null) ||
    null;
  const hasLoadedForm = state.hydrated;
  const isLoading =
    profilesQuery.isLoading ||
    companiesQuery.isLoading ||
    Boolean(selectedUuid && detailQuery.isLoading) ||
    (!hasLoadedForm && !loadError);
  const canSubmit = hasLoadedForm && !loadError && !isLoading;

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
    onSuccess: (_response, data) => {
      queryClient.invalidateQueries({ queryKey: ['signup', 'company'] });
      queryClient.invalidateQueries({ queryKey: ['signup', 'company-detail', data.uuid] });
    },
  });

  const setFieldValue = useCallback(
    (field: keyof CompanyFormData, value: string) => {
      updateState((previous) => {
        const fieldErrors = { ...previous.errors };
        delete fieldErrors[field];
        return {
          ...previous,
          form: { ...previous.form, [field]: value },
          errors: fieldErrors,
          generalError: '',
          dirty: new Set(previous.dirty).add(field),
        };
      });
    },
    [updateState],
  );

  const isCurrentSubmission = useCallback(
    (attempt: Submission, registeredUuid?: string) =>
      mounted.current &&
      !attempt.cancelled &&
      submission.current === attempt &&
      attempt.owners.every(
        (seen) =>
          seen === attempt.owner ||
          (attempt.owner.uuid === null && registeredUuid !== undefined && seen.uuid === registeredUuid),
      ),
    [],
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
      setGeneralError(
        'Please ensure your full name (first and last) is set in your profile before registering a company.',
      );
      return false;
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }, [form, userProfile]);

  const handleSubmit = useCallback(
    async (onSuccess: () => void) => {
      if (currentOwner.current !== owner || !mounted.current || submission.current || !canSubmit || !validateForm())
        return;
      const attempt: Submission = { owner, owners: [owner], cancelled: false };
      submission.current = attempt;
      setGeneralError('');
      try {
        let registeredUuid: string | undefined;
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
          const response = await registerMutation.mutateAsync(data);
          registeredUuid = response.data.company.uuid;
        }

        if (isCurrentSubmission(attempt, registeredUuid)) onSuccess();
      } catch (err: unknown) {
        if (!isCurrentSubmission(attempt)) return;

        const reading = readApiError(err, { fallback: COULD_NOT_SAVE, displayedFields: DISPLAYED_FIELDS });
        setGeneralError(reading.generalError ?? '');
        setErrors(reading.fieldErrors ?? {});
      } finally {
        if (submission.current === attempt) submission.current = null;
      }
    },
    [
      owner,
      canSubmit,
      form,
      userProfile,
      existingCompany,
      validateForm,
      registerMutation,
      updateMutation,
      isCurrentSubmission,
      setGeneralError,
      setErrors,
    ],
  );

  const retryLoad = useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['userProfiles'] }),
      queryClient.invalidateQueries({ queryKey: ['signup', 'company'] }),
      ...(selectedUuid
        ? [queryClient.invalidateQueries({ queryKey: ['signup', 'company-detail', selectedUuid] })]
        : []),
    ]);
  }, [queryClient, selectedUuid]);

  return {
    form,
    errors,
    generalError,
    loadError,
    hasLoadedForm,
    canSubmit,
    isLoading,
    isSubmitting: registerMutation.isPending || updateMutation.isPending,
    setFieldValue,
    handleSubmit,
    retryLoad,
  };
}
