import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { UserIcon, BuildingsIcon } from '@phosphor-icons/react';
import { CACHE_TIMING, DESIGN_TOKENS } from '@ledova/shared';
import { AuthLayout } from '@components/AuthLayout';
import apiClient from '@services/apiClient';

const ICON_LG = DESIGN_TOKENS.icon.sizes.lg;

type AccountRole = 'investor' | 'company';

interface AccountTypeOption {
  role: AccountRole;
  title: string;
  description: string;
  icon: typeof UserIcon;
}

const ACCOUNT_TYPES: AccountTypeOption[] = [
  {
    role: 'investor',
    title: 'Individual Investor',
    description: 'Manage your personal portfolio, buy and sell crypto, and trade tokenized securities.',
    icon: UserIcon,
  },
  {
    role: 'company',
    title: 'Company Representative',
    description: 'Register your company to issue tokenized shares and manage shareholders on-chain.',
    icon: BuildingsIcon,
  },
];

export function SignupAccountType() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { data: accountsResponse } = useQuery({
    queryKey: ['userAccounts'],
    queryFn: () => apiClient.get('/api/user-accounts/'),
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
  });

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const accountsData = accountsResponse?.data as any;
  const account = accountsData?.results?.[0] || accountsData?.[0] || null;

  const updateRoleMutation = useMutation({
    mutationFn: (role: AccountRole) => apiClient.patch(`/api/user-accounts/${account?.uuid}/`, { role }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['userAccounts'] });
      queryClient.invalidateQueries({ queryKey: ['userPreferences'] });
    },
  });

  const handleSelect = async (role: AccountRole) => {
    if (!account || isSubmitting) return;

    setIsSubmitting(true);
    try {
      await updateRoleMutation.mutateAsync(role);
      if (role === 'investor') {
        navigate('/signup/pre-screening');
      } else {
        navigate('/signup/identity-verification');
      }
    } catch (error) {
      console.error('Failed to update account role:', error);
      setIsSubmitting(false);
    }
  };

  const handleBack = () => {
    navigate('/signup/email-confirmation');
  };

  return (
    <AuthLayout>
      <div className="text-center mb-6">
        <h1 className="text-xl font-semibold text-text-primary">Choose Account Type</h1>
        <p className="text-sm text-text-muted mt-1 px-4">How will you be using Ledova?</p>
      </div>

      <div className="space-y-3">
        {ACCOUNT_TYPES.map((option) => {
          const Icon = option.icon;
          return (
            <button
              key={option.role}
              onClick={() => handleSelect(option.role)}
              disabled={isSubmitting || !account}
              className="w-full text-left bg-surface-raised rounded-lg border border-border p-5 hover:border-brand-light hover:bg-brand-mid/5 transition-all duration-150 group disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <div className="flex items-start gap-4">
                <div className="p-2 rounded-full bg-surface-tertiary border border-border group-hover:border-brand-light group-hover:bg-brand-mid/10 transition-colors">
                  <Icon size={ICON_LG} className="text-text-muted group-hover:text-brand-light transition-colors" />
                </div>
                <div className="flex-1">
                  <h3 className="text-base font-semibold text-text-primary">{option.title}</h3>
                  <p className="text-sm text-text-muted mt-1">{option.description}</p>
                  {option.role === 'company' && (
                    <span className="inline-block mt-1.5 px-1.5 py-0.5 text-[9px] font-medium tracking-wide text-purple-400/70 bg-purple-500/12 rounded">
                      Early Access
                    </span>
                  )}
                </div>
              </div>
            </button>
          );
        })}
      </div>

      <div className="relative my-6">
        <div className="absolute inset-0 flex items-center">
          <div className="w-full border-t border-border"></div>
        </div>
        <div className="relative flex justify-center text-sm">
          <span className="px-4 bg-surface-base text-text-subtle font-medium">or</span>
        </div>
      </div>

      <div className="text-center">
        <p className="text-sm text-text-subtle">
          <button
            type="button"
            onClick={handleBack}
            disabled={isSubmitting}
            className="font-semibold text-brand-light hover:text-brand-subtle transition-colors disabled:opacity-50"
          >
            Go Back
          </button>
        </p>
      </div>
    </AuthLayout>
  );
}
