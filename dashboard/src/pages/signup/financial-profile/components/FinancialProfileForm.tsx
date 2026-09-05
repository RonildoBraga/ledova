import React from 'react';
import { FormErrors, SOURCE_OF_FUNDS_OPTIONS, INTENDED_USE_OPTIONS, DESIGN_TOKENS } from '@ledova/shared';
import { FinancialProfileFormState } from '../useSignupFinancialProfile';
import { Field, Label, Input, Description } from '@headlessui/react';
import { WarningIcon } from '@phosphor-icons/react';
import RadioGroupField from './RadioGroupField';
import CheckboxGroupField from './CheckboxGroupField';

const ICON_MD = DESIGN_TOKENS.icon.sizes.md;

export interface FinancialProfileFormProps {
  form: FinancialProfileFormState;
  errors: FormErrors;
  generalError: string;
  isSubmitting: boolean;
  setFieldValue: (field: keyof FinancialProfileFormState, value: string | string[] | number) => void;
  onSubmit: (e: React.FormEvent) => void;
  onBack?: () => void;
}

export function FinancialProfileForm({
  form,
  errors,
  generalError,
  isSubmitting,
  setFieldValue,
  onSubmit,
  onBack,
}: FinancialProfileFormProps) {
  const handleSourceOfFundsChange = (values: string[]) => {
    setFieldValue('sourceOfFunds', values);
  };

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

            <CheckboxGroupField
              label="What is your primary source of funds?"
              value={form.sourceOfFunds}
              options={SOURCE_OF_FUNDS_OPTIONS}
              error={errors.sourceOfFunds}
              onChange={handleSourceOfFundsChange}
            />

            {form.sourceOfFunds.includes('other') && (
              <Field className="space-y-2">
                <Label className="block text-sm font-medium text-text-body">Please specify your source of funds</Label>
                <Input
                  type="text"
                  name="sourceOfFundsOtherText"
                  value={form.sourceOfFundsOtherText || ''}
                  onChange={(e) => setFieldValue('sourceOfFundsOtherText', e.target.value)}
                  className={`w-full bg-surface-tertiary border ${
                    errors.sourceOfFundsOtherText
                      ? 'border-error bg-error-subtle focus:ring-error'
                      : 'border-border focus:ring-border-focus'
                  } rounded-lg px-3 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:border-transparent transition-colors`}
                  placeholder="Enter details"
                  disabled={isSubmitting}
                />
                {errors.sourceOfFundsOtherText && (
                  <Description className="text-error-light text-xs mt-1" role="alert">
                    {errors.sourceOfFundsOtherText.join(' ')}
                  </Description>
                )}
              </Field>
            )}

            <RadioGroupField
              label="What is your intended use of the platform?"
              value={form.intendedUse}
              options={INTENDED_USE_OPTIONS}
              error={errors.intendedUse}
              onChange={(value) => setFieldValue('intendedUse', value)}
            />

            {form.intendedUse === 'other' && (
              <Field className="space-y-2">
                <Label className="block text-sm font-medium text-text-body">Please specify your intended use</Label>
                <Input
                  type="text"
                  name="intendedUseOtherText"
                  value={form.intendedUseOtherText || ''}
                  onChange={(e) => setFieldValue('intendedUseOtherText', e.target.value)}
                  className={`w-full bg-surface-tertiary border ${
                    errors.intendedUseOtherText
                      ? 'border-error bg-error-subtle focus:ring-error'
                      : 'border-border focus:ring-border-focus'
                  } rounded-lg px-3 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:border-transparent transition-colors`}
                  placeholder="Enter details"
                  disabled={isSubmitting}
                />
                {errors.intendedUseOtherText && (
                  <Description className="text-error-light text-xs mt-1" role="alert">
                    {errors.intendedUseOtherText.join(' ')}
                  </Description>
                )}
              </Field>
            )}

            <Field className="space-y-2">
              <Label className="block text-sm font-medium text-text-body">What is your occupation?</Label>
              <Input
                type="text"
                name="occupation"
                value={form.occupation || ''}
                onChange={(e) => setFieldValue('occupation', e.target.value)}
                className={`w-full bg-surface-tertiary border ${
                  errors.occupation
                    ? 'border-error bg-error-subtle focus:ring-error'
                    : 'border-border focus:ring-border-focus'
                } rounded-lg px-3 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:border-transparent transition-colors`}
                placeholder="Enter your occupation"
                disabled={isSubmitting}
              />
              {errors.occupation && (
                <Description className="text-error-light text-xs mt-1" role="alert">
                  {errors.occupation.join(' ')}
                </Description>
              )}
            </Field>

            <button
              type="submit"
              disabled={isSubmitting}
              onClick={onSubmit}
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
        {onBack && (
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
        )}
      </div>
    </>
  );
}
