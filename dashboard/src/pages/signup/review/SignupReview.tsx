import { useNavigate } from 'react-router-dom';

const MARKETING_URL = import.meta.env.VITE_MARKETING_URL || 'http://localhost:5173';
import { ClipboardTextIcon } from '@phosphor-icons/react';
import {
  formatPhoneNumber,
  getAddressDisplayLines,
  parseAddress,
  formatSourceOfFunds,
  formatIntendedUse,
  DESIGN_TOKENS,
} from '@ledova/shared';
import { useReview } from './useReview';
import { AuthLayout } from '@components/AuthLayout';

const ICON_LG = DESIGN_TOKENS.icon.sizes.lg;

export function SignupReview() {
  const navigate = useNavigate();
  const { data, company, signupRole, isLoading, error, completeSignup, isSubmitting, canCompleteSignup } = useReview();

  const handleBack = () => {
    if (signupRole === 'company') {
      navigate('/signup/company-registration');
    } else {
      navigate('/signup/financial-profile');
    }
  };

  if (isLoading) {
    return (
      <AuthLayout>
        <div className="flex flex-col items-center justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand mb-4"></div>
          <p className="text-text-muted">Loading review data...</p>
        </div>
      </AuthLayout>
    );
  }

  if (error) {
    return (
      <AuthLayout>
        <div className="flex flex-col items-center justify-center py-8">
          <div className="text-center">
            <h3 className="text-lg font-medium text-error mb-2">Error Loading Data</h3>
            <p className="text-error">{error}</p>
          </div>
        </div>
      </AuthLayout>
    );
  }

  const { userProfile, financialProfile } = data;
  const isCompany = signupRole === 'company';

  return (
    <AuthLayout>
      <div className="text-center mb-8">
        <div className="flex justify-center mb-4">
          <div className="p-3 rounded-full bg-surface-raised border border-border">
            <ClipboardTextIcon size={ICON_LG} className="text-text-muted" />
          </div>
        </div>
        <h1 className="text-2xl font-semibold text-text-primary mb-2">Review & Confirm</h1>
        <p className="text-sm text-text-muted">Please review your information before completing signup</p>
      </div>

      <div className="space-y-4">
        <div className="bg-surface-raised rounded-lg border border-border overflow-hidden">
          <div className="px-5 py-4 border-b border-border-subtle">
            <h3 className="text-base font-semibold text-text-primary">Personal Information</h3>
          </div>
          <div className="px-5 py-4">
            {userProfile ? (
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-sm text-text-muted">Full Name:</span>
                  <span className="text-sm text-text-primary font-medium">{userProfile.fullName}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-text-muted">Phone:</span>
                  <span className="text-sm text-text-primary font-medium">
                    {formatPhoneNumber(userProfile.phoneNumber)}
                  </span>
                </div>
                {getAddressDisplayLines(parseAddress(userProfile.residentialAddress)).map((line, index) => (
                  <div key={index} className="flex justify-between items-center">
                    <span className="text-sm text-text-muted">{line.label}</span>
                    <span className="text-sm text-text-primary font-medium">{line.value}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-error-light">No personal information found.</p>
            )}
          </div>
        </div>

        {isCompany ? (
          <div className="bg-surface-raised rounded-lg border border-border overflow-hidden">
            <div className="px-5 py-4 border-b border-border-subtle">
              <h3 className="text-base font-semibold text-text-primary">Company Information</h3>
            </div>
            <div className="px-5 py-4">
              {company ? (
                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-text-muted">Company Name:</span>
                    <span className="text-sm text-text-primary font-medium">{company.name}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-text-muted">ACN:</span>
                    <span className="text-sm text-text-primary font-medium">{company.acn}</span>
                  </div>
                  {company.abn && (
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-text-muted">ABN:</span>
                      <span className="text-sm text-text-primary font-medium">{company.abn}</span>
                    </div>
                  )}
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-text-muted">Type:</span>
                    <span className="text-sm text-text-primary font-medium">{company.companyType}</span>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-error-light">No company information found.</p>
              )}
            </div>
          </div>
        ) : (
          <div className="bg-surface-raised rounded-lg border border-border overflow-hidden">
            <div className="px-5 py-4 border-b border-border-subtle">
              <h3 className="text-base font-semibold text-text-primary">Financial Profile</h3>
            </div>
            <div className="px-5 py-4">
              {financialProfile ? (
                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-text-muted">Source of Funds:</span>
                    <span className="text-sm text-text-primary font-medium">
                      {formatSourceOfFunds(financialProfile.sourceOfFunds)}
                    </span>
                  </div>
                  {financialProfile.sourceOfFundsOtherText && (
                    <div className="flex justify-between items-start">
                      <span className="text-sm text-text-muted">Source (Other):</span>
                      <span className="text-sm text-text-primary font-medium text-right max-w-[200px]">
                        {financialProfile.sourceOfFundsOtherText}
                      </span>
                    </div>
                  )}
                  {financialProfile.intendedUse && (
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-text-muted">Intended Use:</span>
                      <span className="text-sm text-text-primary font-medium">
                        {formatIntendedUse(financialProfile.intendedUse)}
                      </span>
                    </div>
                  )}
                  {financialProfile.intendedUseOtherText && (
                    <div className="flex justify-between items-start">
                      <span className="text-sm text-text-muted">Intended Use (Other):</span>
                      <span className="text-sm text-text-primary font-medium text-right max-w-[200px]">
                        {financialProfile.intendedUseOtherText}
                      </span>
                    </div>
                  )}
                  {financialProfile.occupation && (
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-text-muted">Occupation:</span>
                      <span className="text-sm text-text-primary font-medium">{financialProfile.occupation}</span>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-sm text-error-light">No financial profile found.</p>
              )}
            </div>
          </div>
        )}

        <div className="bg-surface-raised rounded-lg border border-border overflow-hidden">
          <div className="px-5 py-4">
            <p className="text-sm text-text-body leading-relaxed mb-4">
              By completing signup, you accept the{' '}
              <a
                href={`${MARKETING_URL}/terms-of-service`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-brand-light hover:text-brand-subtle underline"
              >
                Terms of Service
              </a>{' '}
              and{' '}
              <a
                href={`${MARKETING_URL}/privacy-policy`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-brand-light hover:text-brand-subtle underline"
              >
                Privacy Policy
              </a>
              . This experimental flow is for synthetic data in a development environment; it does not create a live
              customer relationship or perform a regulated verification service.
            </p>
            {!canCompleteSignup && (
              <p className="text-sm text-error-light text-center mb-4">
                Please ensure all information is complete to proceed.
              </p>
            )}
            <button
              type="button"
              onClick={completeSignup}
              disabled={!canCompleteSignup || isSubmitting}
              className="w-full bg-brand-mid hover:bg-brand disabled:bg-surface-disabled disabled:cursor-not-allowed text-white font-semibold py-3 px-4 rounded-lg transition-colors shadow-lg shadow-brand-light/40 disabled:shadow-none focus:outline-none focus:ring-2 focus:ring-border-focus focus:ring-offset-2 focus:ring-offset-surface-base"
            >
              {isSubmitting ? (
                <div className="flex items-center justify-center space-x-2">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                  <span>Completing...</span>
                </div>
              ) : (
                'Complete Signup'
              )}
            </button>
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
