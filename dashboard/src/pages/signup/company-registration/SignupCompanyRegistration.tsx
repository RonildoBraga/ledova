import { useNavigate } from 'react-router-dom';
import { BuildingsIcon } from '@phosphor-icons/react';
import LoadingState from '@components/signup/LoadingState';
import ErrorState from '@components/signup/ErrorState';
import { CompanyRegistrationForm } from './components/CompanyRegistrationForm';
import { useSignupCompanyRegistration } from './useSignupCompanyRegistration';
import { AuthLayout } from '@components/AuthLayout';
import { DESIGN_TOKENS } from '@ledova/shared';

const ICON_MD = DESIGN_TOKENS.icon.sizes.md;

export function SignupCompanyRegistration() {
  const navigate = useNavigate();
  const { form, errors, generalError, isLoading, isSubmitting, setFieldValue, handleSubmit, retryLoad } =
    useSignupCompanyRegistration();

  const handleContinue = async (e: React.FormEvent) => {
    e.preventDefault();
    await handleSubmit(() => {
      navigate('/signup/review');
    });
  };

  const handleBack = () => {
    navigate('/signup/user-profile');
  };

  if (isLoading) {
    return <LoadingState message="Loading company data..." />;
  }

  if (generalError && !form.name && !isSubmitting) {
    return <ErrorState title="Unable to Load" message={generalError} onRetry={retryLoad} />;
  }

  return (
    <AuthLayout>
      <div className="text-center mb-6">
        <div className="flex justify-center mb-3">
          <div className="p-2 rounded-full bg-surface-raised border border-border">
            <BuildingsIcon size={ICON_MD} className="text-text-muted" />
          </div>
        </div>
        <h1 className="text-xl font-semibold text-text-primary">Company Details</h1>
        <p className="text-sm text-text-muted mt-1">Enter your company&apos;s basic information</p>
      </div>

      <CompanyRegistrationForm
        form={form}
        errors={errors}
        generalError={generalError}
        isSubmitting={isSubmitting}
        setFieldValue={setFieldValue}
        onSubmit={handleContinue}
        onBack={handleBack}
      />
    </AuthLayout>
  );
}
