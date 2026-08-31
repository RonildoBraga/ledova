import { useNavigate } from 'react-router-dom';
import { EnvelopeIcon } from '@phosphor-icons/react';
import { EmailConfirmationForm } from './components/EmailConfirmationForm';
import { useSignupEmailConfirmation } from './useSignupEmailConfirmation';
import { AuthLayout } from '@components/AuthLayout';
import { DESIGN_TOKENS } from '@ledova/shared-constants';

const ICON_MD = DESIGN_TOKENS.icon.sizes.md;

export function SignupEmailConfirmation() {
  const navigate = useNavigate();
  const {
    email,
    verificationCode,
    errors,
    generalError,
    successMessage,
    isLoading,
    isResending,
    setVerificationCode,
    handleVerify,
    handleResend,
  } = useSignupEmailConfirmation();

  const handleSubmitVerification = async (e: React.FormEvent) => {
    e.preventDefault();
    await handleVerify(() => {
      navigate('/signup/account-type');
    });
  };

  const handleBack = () => {
    navigate('/signup');
  };

  return (
    <AuthLayout>
      <div className="text-center mb-6">
        <div className="flex justify-center mb-3">
          <div className="p-2 rounded-full bg-surface-raised border border-border">
            <EnvelopeIcon size={ICON_MD} className="text-text-muted" />
          </div>
        </div>
        <h1 className="text-xl font-semibold text-text-primary">Verify Your Email</h1>
        {email && <p className="text-sm text-text-muted mt-2">Code sent to {email}</p>}
      </div>

      <EmailConfirmationForm
        verificationCode={verificationCode}
        errors={errors}
        generalError={generalError}
        successMessage={successMessage}
        isLoading={isLoading}
        isResending={isResending}
        setVerificationCode={setVerificationCode}
        onSubmit={handleSubmitVerification}
        onResendCode={handleResend}
        onBack={handleBack}
      />
    </AuthLayout>
  );
}
