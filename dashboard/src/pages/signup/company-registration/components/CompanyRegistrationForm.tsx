import { Field, Label, Input, Description } from '@headlessui/react';
import { BuildingsIcon, WarningIcon, CaretDownIcon } from '@phosphor-icons/react';
import { DESIGN_TOKENS } from '@ledova/shared';
import { COMPANY_TYPES } from '../constants';

const ICON_MD = DESIGN_TOKENS.icon.sizes.md;

interface CompanyFormData {
  name: string;
  tradingName: string;
  companyType: string;
  acn: string;
  abn: string;
}

type FormErrors = Record<string, string[]>;

interface CompanyRegistrationFormProps {
  form: CompanyFormData;
  errors: FormErrors;
  generalError: string;
  isSubmitting: boolean;
  setFieldValue: (field: keyof CompanyFormData, value: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  onBack: () => void;
}

const inputClassName = (hasError: boolean) =>
  `w-full bg-surface-tertiary border ${
    hasError ? 'border-error bg-error-subtle focus:ring-error' : 'border-border focus:ring-border-focus'
  } rounded-lg px-3 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:border-transparent transition-colors`;

export function CompanyRegistrationForm({
  form,
  errors,
  generalError,
  isSubmitting,
  setFieldValue,
  onSubmit,
  onBack,
}: CompanyRegistrationFormProps) {
  return (
    <>
      <div className="bg-surface-raised rounded-lg border border-border">
        <div className="p-6">
          <form onSubmit={onSubmit} className="space-y-6">
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

            <Field className="space-y-1">
              <Label className="block text-sm font-medium text-text-body">Company Name *</Label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <BuildingsIcon size={ICON_MD} className="text-text-subtle" />
                </div>
                <Input
                  type="text"
                  name="name"
                  value={form.name}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFieldValue('name', e.target.value)}
                  className={`${inputClassName(!!errors.name)} pl-10`}
                  placeholder="Your Company Pty Ltd"
                  required
                  disabled={isSubmitting}
                />
              </div>
              {errors.name && (
                <Description className="text-error-light text-xs mt-1" role="alert">
                  {errors.name.join(' ')}
                </Description>
              )}
            </Field>

            <Field className="space-y-1">
              <Label className="block text-sm font-medium text-text-body">Trading Name (optional)</Label>
              <Input
                type="text"
                name="tradingName"
                value={form.tradingName}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFieldValue('tradingName', e.target.value)}
                className={inputClassName(!!errors.tradingName)}
                placeholder="Trading as..."
                disabled={isSubmitting}
              />
              {errors.tradingName && (
                <Description className="text-error-light text-xs mt-1" role="alert">
                  {errors.tradingName.join(' ')}
                </Description>
              )}
            </Field>

            <Field className="space-y-1">
              <Label className="block text-sm font-medium text-text-body">Company Type *</Label>
              <div className="relative">
                <select
                  name="companyType"
                  value={form.companyType}
                  onChange={(e) => setFieldValue('companyType', e.target.value)}
                  disabled={isSubmitting}
                  className={`${inputClassName(!!errors.companyType)} appearance-none pr-10`}
                >
                  {COMPANY_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
                <CaretDownIcon className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted pointer-events-none" />
              </div>
              {errors.companyType && (
                <Description className="text-error-light text-xs mt-1" role="alert">
                  {errors.companyType.join(' ')}
                </Description>
              )}
            </Field>

            <div className="grid grid-cols-2 gap-4">
              <Field className="space-y-1">
                <Label className="block text-sm font-medium text-text-body">ACN *</Label>
                <Input
                  type="text"
                  name="acn"
                  value={form.acn}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFieldValue('acn', e.target.value)}
                  className={inputClassName(!!errors.acn)}
                  placeholder="123 456 789"
                  required
                  disabled={isSubmitting}
                  maxLength={11}
                />
                {errors.acn && (
                  <Description className="text-error-light text-xs mt-1" role="alert">
                    {errors.acn.join(' ')}
                  </Description>
                )}
              </Field>

              <Field className="space-y-1">
                <Label className="block text-sm font-medium text-text-body">ABN (optional)</Label>
                <Input
                  type="text"
                  name="abn"
                  value={form.abn}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFieldValue('abn', e.target.value)}
                  className={inputClassName(!!errors.abn)}
                  placeholder="12 345 678 901"
                  disabled={isSubmitting}
                  maxLength={14}
                />
                {errors.abn && (
                  <Description className="text-error-light text-xs mt-1" role="alert">
                    {errors.abn.join(' ')}
                  </Description>
                )}
              </Field>
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
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
            onClick={onBack}
            disabled={isSubmitting}
            className="font-semibold text-brand-light hover:text-brand-subtle transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Go Back
          </button>
        </p>
      </div>
    </>
  );
}
