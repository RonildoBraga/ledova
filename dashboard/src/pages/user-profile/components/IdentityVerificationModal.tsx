import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  ShieldCheckIcon,
  WarningIcon,
  CheckCircleIcon,
  ClockCountdownIcon,
  ArrowCounterClockwiseIcon,
} from '@phosphor-icons/react';
import { DESIGN_TOKENS } from '@ledova/shared-constants';
import { useIdentityVerification } from '@hooks/useIdentityVerification';
import { Modal } from '@components/Modal';

const ICON_MD = DESIGN_TOKENS.icon.sizes.md;
const ICON_LG = DESIGN_TOKENS.icon.sizes.lg;

interface IdentityVerificationModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function IdentityVerificationModal({ isOpen, onClose }: IdentityVerificationModalProps) {
  const queryClient = useQueryClient();

  const {
    status,
    isLoadingStatus,
    isVerified,
    showPendingBanner,
    showOnHoldBanner,
    showRejectedBanner,
    showRetryBanner,
    showForm,
    launchVerification,
    formUrl,
    sdkActive,
    justSubmitted,
    sdkError,
    tokenError,
    isLaunching,
    resetState,
  } = useIdentityVerification();

  useEffect(() => {
    if (justSubmitted && !isVerified) {
      const timer = setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['user', 'profile'] });
        onClose();
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [justSubmitted, isVerified, queryClient, onClose]);

  useEffect(() => {
    if (isOpen) {
      resetState();
    }
  }, [isOpen, resetState]);

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Identity Verification" size="lg" fullHeight={!!formUrl}>
      <div className="space-y-4">
        {(isLoadingStatus || isLaunching) && (
          <div className="flex flex-col items-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-light"></div>
            <p className="text-sm text-text-muted mt-4">
              {isLaunching ? 'Preparing verification...' : 'Loading status...'}
            </p>
          </div>
        )}

        {isVerified && (
          <div className="flex flex-col items-center py-8 px-6 bg-success/10 border border-success/20 rounded-lg">
            <CheckCircleIcon size={ICON_LG} className="text-success-light" />
            <h3 className="text-lg font-semibold text-success-light mt-2">Already Verified</h3>
            <p className="text-sm text-text-secondary text-center mt-1">
              Your identity has been verified successfully.
            </p>
          </div>
        )}

        {showPendingBanner && (
          <div className="flex flex-col items-center py-8 px-6 bg-brand-mid/10 border border-brand-mid/20 rounded-lg">
            <CheckCircleIcon size={ICON_LG} className="text-brand-light" />
            <h3 className="text-lg font-semibold text-brand-light mt-2">Verification Submitted</h3>
            <p className="text-sm text-text-secondary text-center mt-1">
              Your documents have been submitted. We&apos;ll review them shortly and notify you of the result.
            </p>
          </div>
        )}

        {showOnHoldBanner && (
          <div className="flex flex-col items-center py-8 px-6 bg-warning-light/10 border border-warning-light/30 rounded-lg">
            <ClockCountdownIcon size={ICON_LG} className="text-warning-light" />
            <h3 className="text-lg font-semibold text-warning-light mt-2">Verification On Hold</h3>
            <p className="text-sm text-text-secondary text-center mt-1">
              Your verification is currently on hold. We may need additional information. Please check back later or
              contact support.
            </p>
          </div>
        )}

        {showRejectedBanner && (
          <div className="flex flex-col items-center py-8 px-6 bg-error/10 border border-error/20 rounded-lg">
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
          <div className="flex flex-col items-center py-8 px-6 bg-warning-light/10 border border-warning-light/30 rounded-lg">
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
          <div className="bg-error/10 border border-error/20 rounded-lg p-4">
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

        {showForm && !isLoadingStatus && !isLaunching && !sdkActive && !formUrl && (
          <>
            <div className="flex justify-center">
              <div className="p-3 rounded-full bg-surface-tertiary border border-border">
                <ShieldCheckIcon size={ICON_LG} className="text-text-muted" />
              </div>
            </div>
            <p className="text-sm text-text-muted text-center">
              Verify your identity to comply with financial regulations and unlock full account features.
            </p>
          </>
        )}

        {showForm && !isLoadingStatus && !formUrl && <div id="sumsub-profile-websdk-container"></div>}

        {formUrl && (
          <div>
            <iframe
              src={formUrl}
              title="Identity Verification"
              className="w-full rounded-lg border border-border"
              style={{ height: '800px' }}
              allow="camera; microphone"
            />
          </div>
        )}

        {showForm && !isLoadingStatus && !sdkActive && !formUrl && (
          <button
            type="button"
            onClick={() => launchVerification('#sumsub-profile-websdk-container')}
            disabled={isLaunching}
            className="w-full bg-brand-mid hover:bg-brand disabled:bg-surface-disabled disabled:cursor-not-allowed text-white font-semibold py-3 px-4 rounded-lg transition-colors shadow-lg shadow-brand-light/40 disabled:shadow-none"
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
            onClick={() => launchVerification('#sumsub-profile-websdk-container')}
            disabled={isLaunching}
            className="w-full bg-warning hover:bg-warning disabled:bg-surface-disabled disabled:cursor-not-allowed text-white font-semibold py-3 px-4 rounded-lg transition-colors"
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
      </div>
    </Modal>
  );
}
