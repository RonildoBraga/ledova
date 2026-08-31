import { useNavigate } from 'react-router-dom';
import { ShieldCheckIcon, WarningIcon, CheckCircleIcon } from '@phosphor-icons/react';
import LoadingState from '@components/signup/LoadingState';
import ErrorState from '@components/signup/ErrorState';
import { useSignupPreScreening } from './useSignupPreScreening';
import { AuthLayout } from '@components/AuthLayout';
import { DESIGN_TOKENS } from '@ledova/shared-constants';

const ICON_MD = DESIGN_TOKENS.icon.sizes.md;

export function SignupPreScreening() {
  const navigate = useNavigate();
  const { form, generalError, isLoading, isSubmitting, isFormValid, setFieldValue, handleSubmit, retryLoad } =
    useSignupPreScreening();

  const handleContinue = async (e: React.FormEvent) => {
    e.preventDefault();
    await handleSubmit(() => {
      navigate('/signup/identity-verification');
    });
  };

  const handleBack = () => {
    navigate('/signup/email-confirmation');
  };

  if (isLoading) {
    return <LoadingState message="Loading..." />;
  }

  if (generalError && !isSubmitting) {
    return <ErrorState title="Unable to Load" message={generalError} onRetry={retryLoad} />;
  }

  return (
    <AuthLayout>
      <div className="text-center mb-6">
        <div className="flex justify-center mb-3">
          <div className="p-2 rounded-full bg-surface-raised border border-border">
            <ShieldCheckIcon size={ICON_MD} className="text-text-muted" />
          </div>
        </div>
        <h1 className="text-xl font-semibold text-text-primary">Eligibility Check</h1>
        <p className="text-sm text-text-muted mt-1 px-4">
          Before we continue, please confirm the following requirements to comply with Australian regulations.
        </p>
      </div>

      <div className="bg-surface-raised rounded-lg border border-border">
        <div className="p-6">
          <form onSubmit={handleContinue} className="space-y-6">
            {generalError && (
              <div className="bg-error-subtle border border-error-dark rounded-lg p-4">
                <div className="flex items-start">
                  <div className="flex-shrink-0">
                    <WarningIcon size={ICON_MD} className="text-error-light" />
                  </div>
                  <div className="ml-3">
                    <p className="text-sm text-error-light" role="alert">
                      {generalError}
                    </p>
                  </div>
                </div>
              </div>
            )}

            <label
              className="flex items-start cursor-pointer"
              onClick={() => !isSubmitting && setFieldValue('confirmedOver18', !form.confirmedOver18)}
            >
              <div className="flex items-center h-6">
                <div
                  className={`w-6 h-6 rounded-sm border-2 flex items-center justify-center transition-colors ${
                    form.confirmedOver18 ? 'bg-brand-mid border-brand-mid' : 'bg-surface-tertiary border-border'
                  }`}
                >
                  {form.confirmedOver18 && <CheckCircleIcon size={ICON_MD} className="text-white" />}
                </div>
              </div>
              <div className="ml-3 flex-1">
                <p className="text-base font-medium text-text-primary mb-1">I am 18 years or older</p>
                <p className="text-xs text-text-subtle">You must be at least 18 to use our platform</p>
              </div>
            </label>

            <label
              className="flex items-start cursor-pointer"
              onClick={() =>
                !isSubmitting && setFieldValue('confirmedAustralianResident', !form.confirmedAustralianResident)
              }
            >
              <div className="flex items-center h-6">
                <div
                  className={`w-6 h-6 rounded-sm border-2 flex items-center justify-center transition-colors ${
                    form.confirmedAustralianResident
                      ? 'bg-brand-mid border-brand-mid'
                      : 'bg-surface-tertiary border-border'
                  }`}
                >
                  {form.confirmedAustralianResident && <CheckCircleIcon size={ICON_MD} className="text-white" />}
                </div>
              </div>
              <div className="ml-3 flex-1">
                <p className="text-base font-medium text-text-primary mb-1">I am currently an Australian resident</p>
                <p className="text-xs text-text-subtle">
                  Our services are currently only available to Australian residents
                </p>
              </div>
            </label>

            <label
              className="flex items-start cursor-pointer"
              onClick={() =>
                !isSubmitting && setFieldValue('confirmedIndividualAccount', !form.confirmedIndividualAccount)
              }
            >
              <div className="flex items-center h-6">
                <div
                  className={`w-6 h-6 rounded-sm border-2 flex items-center justify-center transition-colors ${
                    form.confirmedIndividualAccount
                      ? 'bg-brand-mid border-brand-mid'
                      : 'bg-surface-tertiary border-border'
                  }`}
                >
                  {form.confirmedIndividualAccount && <CheckCircleIcon size={ICON_MD} className="text-white" />}
                </div>
              </div>
              <div className="ml-3 flex-1">
                <p className="text-base font-medium text-text-primary mb-1">I am acting on my own behalf</p>
                <p className="text-xs text-text-subtle">Not for a business, trust, or on behalf of someone else</p>
              </div>
            </label>

            <button
              type="submit"
              disabled={!isFormValid || isSubmitting}
              className="w-full bg-brand-mid hover:bg-brand disabled:bg-surface-disabled disabled:cursor-not-allowed text-white font-semibold py-3 px-4 rounded-lg transition-colors shadow-lg shadow-brand-light/40 disabled:shadow-none focus:outline-none focus:ring-2 focus:ring-border-focus focus:ring-offset-2 focus:ring-offset-surface-base"
            >
              {isSubmitting ? (
                <div className="flex items-center justify-center space-x-2">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                  <span>Saving...</span>
                </div>
              ) : (
                'Continue'
              )}
            </button>
          </form>
        </div>
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
            className="font-semibold text-brand-light hover:text-brand-subtle transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Go Back
          </button>
        </p>
      </div>
    </AuthLayout>
  );
}
