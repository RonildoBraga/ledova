import { useSignupFinancialProfile } from './useSignupFinancialProfile';
import { FinancialProfileForm } from './components/FinancialProfileForm';
import LoadingState from '@components/signup/LoadingState';
import ErrorState from '@components/signup/ErrorState';
import { useNavigate } from 'react-router-dom';
import { ChartBarIcon } from '@phosphor-icons/react';
import { AuthLayout } from '@components/AuthLayout';
import { DESIGN_TOKENS } from '@ledova/shared-constants';

const ICON_MD = DESIGN_TOKENS.icon.sizes.md;

export function SignupFinancialProfile() {
  const navigate = useNavigate();

  const { form, errors, generalError, isLoading, isSubmitting, userProfileId, setFieldValue, handleSubmit, retryLoad } =
    useSignupFinancialProfile();

  const handleSubmitProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    await handleSubmit(() => {
      navigate('/signup/review');
    });
  };

  const handleBack = () => {
    navigate('/signup/user-profile');
  };

  if (isLoading) {
    return <LoadingState message="Loading financial profile..." />;
  }

  if (generalError && !userProfileId) {
    return (
      <ErrorState message="We encountered an issue while loading your financial profile data." onRetry={retryLoad} />
    );
  }

  if (!userProfileId) {
    return (
      <ErrorState
        title="Profile Not Found"
        message="Please complete your user profile before setting your financial profile."
        retryLabel="Go to Profile"
        onRetry={() => navigate('/signup/user-profile')}
      />
    );
  }

  return (
    <AuthLayout>
      <div className="text-center mb-6">
        <div className="flex justify-center mb-3">
          <div className="p-2 rounded-full bg-surface-raised border border-border">
            <ChartBarIcon size={ICON_MD} className="text-text-muted" />
          </div>
        </div>
        <h1 className="text-xl font-semibold text-text-primary">Financial Profile</h1>
        <p className="text-sm text-text-muted mt-1">AML/CTF compliance information</p>
      </div>

      <FinancialProfileForm
        form={form}
        errors={errors}
        generalError={generalError}
        isSubmitting={isSubmitting}
        setFieldValue={setFieldValue}
        onSubmit={handleSubmitProfile}
        onBack={handleBack}
      />
    </AuthLayout>
  );
}
