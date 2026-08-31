import { useNavigate } from 'react-router-dom';
import {
  ShieldCheckIcon,
  WarningIcon,
  CheckCircleIcon,
  ClockCountdownIcon,
  ArrowCounterClockwiseIcon,
} from '@phosphor-icons/react';
import LoadingState from '@components/signup/LoadingState';
import { useIdentityVerification } from '@hooks/useIdentityVerification';
import { AuthLayout } from '@components/AuthLayout';
import { DESIGN_TOKENS } from '@ledova/shared-constants';

const ICON_MD = DESIGN_TOKENS.icon.sizes.md;
const ICON_LG = DESIGN_TOKENS.icon.sizes.lg;

export function SignupIdentityVerification() {
  const navigate = useNavigate();

  const {
    status,
    isLoadingStatus,
    refetchStatus,
    isVerified,
    showPendingBanner,
    showOnHoldBanner,
    showRejectedBanner,
    showRetryBanner,
    showForm,
    showContinue,
    showSkip,
    launchVerification,
    formUrl,
    sdkActive,
    sdkError,
    tokenError,
    isLaunching,
  } = useIdentityVerification();

  const handleContinue = async () => {
    await refetchStatus();
    navigate('/signup/user-profile');
  };

  const handleSkipForNow = () => {
    navigate('/signup/user-profile');
  };

  const handleBack = () => {
    navigate('/signup/pre-screening');
  };

  if (isLoadingStatus && !status) {
    return <LoadingState message="Loading verification status..." />;
  }

  return (
    <AuthLayout>
      <div className="text-center mb-6">
        <div className="flex justify-center mb-3">
          <div className="p-2 rounded-full bg-surface-raised border border-border">
            <ShieldCheckIcon size={ICON_MD} className="text-text-muted" />
          </div>
        </div>
        <h1 className="text-xl font-semibold text-text-primary">Identity Verification</h1>
        <p className="text-sm text-text-muted mt-1 px-4">
          We need to verify your identity to comply with financial regulations and protect your account.
        </p>
      </div>

      <div className="bg-surface-raised rounded-lg border border-border">
        <div className="p-6">
          {(isLoadingStatus || isLaunching) && (
            <div className="flex flex-col items-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-light"></div>
              <p className="text-sm text-text-muted mt-4">
                {isLaunching ? 'Preparing verification...' : 'Loading status...'}
              </p>
            </div>
          )}

          {isVerified && (
            <div className="flex flex-col items-center py-8 px-6 bg-success/10 border border-success/20 rounded-lg mb-6">
              <CheckCircleIcon size={ICON_LG} className="text-success-light" />
              <h3 className="text-lg font-semibold text-success-light mt-2">Already Verified</h3>
              <p className="text-sm text-text-secondary text-center mt-1">
                Your identity has been verified successfully.
              </p>
            </div>
          )}

          {showPendingBanner && (
            <div className="flex flex-col items-center py-8 px-6 bg-brand-mid/10 border border-brand-mid/20 rounded-lg mb-6">
              <CheckCircleIcon size={ICON_LG} className="text-brand-light" />
              <h3 className="text-lg font-semibold text-brand-light mt-2">Verification Submitted</h3>
              <p className="text-sm text-text-secondary text-center mt-1">
                Your documents have been submitted. We&apos;ll review them shortly and notify you of the result.
              </p>
            </div>
          )}

          {showOnHoldBanner && (
            <div className="flex flex-col items-center py-8 px-6 bg-warning-light/10 border border-warning-light/30 rounded-lg mb-6">
              <ClockCountdownIcon size={ICON_LG} className="text-warning-light" />
              <h3 className="text-lg font-semibold text-warning-light mt-2">Verification On Hold</h3>
              <p className="text-sm text-text-secondary text-center mt-1">
                Your verification is currently on hold. We may need additional information. Please check back later or
                contact support.
              </p>
            </div>
          )}

          {showRejectedBanner && (
            <div className="flex flex-col items-center py-8 px-6 bg-error/10 border border-error/20 rounded-lg mb-6">
              <WarningIcon size={ICON_LG} className="text-error-light" />
              <h3 className="text-lg font-semibold text-error-light mt-2">Verification Rejected</h3>
              <p className="text-sm text-text-secondary text-center mt-1">
                Unfortunately, your verification was not approved. You may retry with different documents or contact
                support for assistance.
              </p>
              {status?.rejectionLabels && status.rejectionLabels.length > 0 && (
                <div className="mt-3 w-full">
                  <p className="text-xs text-text-muted uppercase mb-1">Reasons:</p>
                  {status.rejectionLabels.map((label, index) => (
                    <p key={index} className="text-sm text-text-secondary mt-1">
                      &bull; {label}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}

          {showRetryBanner && (
            <div className="flex flex-col items-center py-8 px-6 bg-warning-light/10 border border-warning-light/30 rounded-lg mb-6">
              <ArrowCounterClockwiseIcon size={ICON_LG} className="text-warning-light" />
              <h3 className="text-lg font-semibold text-warning-light mt-2">Retry Needed</h3>
              <p className="text-sm text-text-secondary text-center mt-1">
                Your previous verification attempt needs to be retried. Please try again with clearer documents.
              </p>
              {status?.rejectionLabels && status.rejectionLabels.length > 0 && (
                <div className="mt-3 w-full">
                  <p className="text-xs text-text-muted uppercase mb-1">Reasons:</p>
                  {status.rejectionLabels.map((label, index) => (
                    <p key={index} className="text-sm text-text-secondary mt-1">
                      &bull; {label}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}

          {(sdkError || tokenError) && (
            <div className="bg-error/10 border border-error/20 rounded-lg p-4 mb-6">
              <div className="flex items-start">
                <div className="flex-shrink-0">
                  <WarningIcon size={ICON_MD} className="text-error-light" />
                </div>
                <div className="ml-3">
                  <p className="text-sm text-error-light" role="alert">
                    {sdkError || (tokenError as Error)?.message || 'An error occurred'}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Info text when form is shown and not yet launched */}
          {showForm && !isLoadingStatus && !isLaunching && !formUrl && !sdkActive && (
            <div className="text-center py-2 mb-4">
              <p className="text-sm text-text-secondary">
                Click the button below to start the verification process. You will need a valid government-issued ID and
                good lighting for clear photos.
              </p>
            </div>
          )}

          {/* Sumsub WebSDK container — hidden until SDK launches into it */}
          {showForm && !formUrl && <div id="sumsub-websdk-container"></div>}

          {/* KYCAID hosted form iframe */}
          {formUrl && (
            <div className="mb-4">
              <iframe
                src={formUrl}
                title="Identity Verification"
                className="w-full rounded-lg border border-border"
                style={{ height: '800px' }}
                allow="camera; microphone"
              />
            </div>
          )}

          <div className="space-y-3">
            {showForm && !isLoadingStatus && !sdkActive && !formUrl && (
              <button
                type="button"
                onClick={() => launchVerification('#sumsub-websdk-container')}
                disabled={isLaunching || isLoadingStatus}
                className="w-full bg-brand-mid hover:bg-brand disabled:bg-surface-disabled disabled:cursor-not-allowed text-white font-semibold py-3 px-4 rounded-lg transition-colors shadow-lg shadow-brand-light/40 disabled:shadow-none focus:outline-none focus:ring-2 focus:ring-border-focus focus:ring-offset-2 focus:ring-offset-surface-base"
              >
                {isLaunching ? (
                  <div className="flex items-center justify-center space-x-2">
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                    <span>Preparing...</span>
                  </div>
                ) : (
                  'Start Verification'
                )}
              </button>
            )}

            {showRetryBanner && (
              <button
                type="button"
                onClick={() => launchVerification('#sumsub-websdk-container')}
                disabled={isLaunching || isLoadingStatus}
                className="w-full bg-warning hover:bg-warning disabled:bg-surface-disabled disabled:cursor-not-allowed text-white font-semibold py-3 px-4 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-border-focus focus:ring-offset-2 focus:ring-offset-surface-base"
              >
                {isLaunching ? (
                  <div className="flex items-center justify-center space-x-2">
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                    <span>Preparing...</span>
                  </div>
                ) : (
                  'Retry Verification'
                )}
              </button>
            )}

            {showContinue && (
              <button
                type="button"
                onClick={handleContinue}
                className="w-full bg-brand-mid hover:bg-brand text-white font-semibold py-3 px-4 rounded-lg transition-colors shadow-lg shadow-brand-light/40 focus:outline-none focus:ring-2 focus:ring-border-focus focus:ring-offset-2 focus:ring-offset-surface-base"
              >
                Continue
              </button>
            )}
          </div>
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

      <div className="text-center space-y-3">
        <p className="text-sm text-text-subtle">
          <button
            type="button"
            onClick={handleBack}
            disabled={isLaunching || isLoadingStatus}
            className="font-semibold text-brand-light hover:text-brand-subtle transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Go Back
          </button>
        </p>
        {showSkip && (
          <p className="text-sm text-text-subtle">
            <button
              type="button"
              onClick={handleSkipForNow}
              className="font-semibold text-brand-light hover:text-brand-subtle transition-colors"
            >
              Skip for Now
            </button>
          </p>
        )}
      </div>
    </AuthLayout>
  );
}
