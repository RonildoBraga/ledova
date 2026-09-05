import { useNavigate } from 'react-router-dom';
import { UserIcon } from '@phosphor-icons/react';
import LoadingState from '@components/signup/LoadingState';
import ErrorState from '@components/signup/ErrorState';
import { UserProfileForm } from './components/UserProfileForm';
import { useSignupUserProfile } from './useSignupUserProfile';
import { useAccountRole } from '@hooks/useAccountRole';
import { AuthLayout } from '@components/AuthLayout';
import { DESIGN_TOKENS } from '@ledova/shared';

const ICON_MD = DESIGN_TOKENS.icon.sizes.md;

function SignupUserProfile() {
  const navigate = useNavigate();
  const { isCompany } = useAccountRole();
  const {
    form,
    errors,
    generalError,
    isLoading,
    isSubmitting,
    formValidation,
    selectedCountry,
    countries,
    setFieldValue,
    handleCountryChange,
    handleSubmit,
    retryLoad,
  } = useSignupUserProfile();

  const handleSubmitProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    await handleSubmit(() => {
      if (isCompany) {
        navigate('/signup/company-registration');
      } else {
        navigate('/signup/financial-profile');
      }
    });
  };

  const handleBack = () => {
    navigate('/signup/identity-verification');
  };

  if (isLoading) {
    return <LoadingState message="Loading profile data..." />;
  }

  if (generalError && !form.fullName) {
    return <ErrorState message="We encountered an issue while loading your profile data." onRetry={retryLoad} />;
  }

  return (
    <AuthLayout>
      <div className="text-center mb-6">
        <div className="flex justify-center mb-3">
          <div className="p-2 rounded-full bg-surface-raised border border-border">
            <UserIcon size={ICON_MD} className="text-text-muted" />
          </div>
        </div>
        <h1 className="text-xl font-semibold text-text-primary">Personal Details</h1>
      </div>

      <UserProfileForm
        form={form}
        errors={errors}
        generalError={generalError}
        isSubmitting={isSubmitting}
        formValidation={formValidation}
        selectedCountry={selectedCountry}
        countries={countries}
        setFieldValue={setFieldValue}
        onCountryChange={handleCountryChange}
        onSubmit={handleSubmitProfile}
        onBack={handleBack}
      />
    </AuthLayout>
  );
}

export { SignupUserProfile };
export default SignupUserProfile;
