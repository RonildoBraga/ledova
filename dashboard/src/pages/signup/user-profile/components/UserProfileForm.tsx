import { Field, Label, Input, Textarea, Description } from '@headlessui/react';
import { UserIcon, HouseIcon, PhoneIcon, WarningIcon, CalendarIcon } from '@phosphor-icons/react';
import { CountrySelector } from './CountrySelector';
import type { FormErrors, UserProfileFormValidation, CountryData, UserProfileFormData } from '@ledova/shared-types';
import { DESIGN_TOKENS } from '@ledova/shared-constants';

const ICON_MD = DESIGN_TOKENS.icon.sizes.md;

interface UserProfileFormProps {
  form: UserProfileFormData;
  errors: FormErrors;
  generalError: string;
  isSubmitting: boolean;
  formValidation: UserProfileFormValidation;
  selectedCountry: CountryData;
  countries: CountryData[];
  setFieldValue: (field: keyof UserProfileFormData, value: string) => void;
  onCountryChange: (country: CountryData) => void;
  onSubmit: (e: React.FormEvent) => void;
  onBack: () => void;
}

export function UserProfileForm({
  form,
  errors,
  generalError,
  isSubmitting,
  formValidation,
  selectedCountry,
  countries,
  setFieldValue,
  onSubmit,
  onBack,
  onCountryChange,
}: UserProfileFormProps) {
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
              <Label className="block text-sm font-medium text-text-body">Full Name</Label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <UserIcon size={ICON_MD} className="text-text-subtle" />
                </div>
                <Input
                  type="text"
                  name="fullName"
                  value={form.fullName}
                  onChange={(e) => setFieldValue('fullName', e.target.value)}
                  className={`w-full bg-surface-tertiary border ${
                    (formValidation && !formValidation.fullName.isValid && form.fullName) || errors.fullName
                      ? 'border-error bg-error-subtle focus:ring-error'
                      : 'border-border focus:ring-border-focus'
                  } rounded-lg pl-10 pr-3 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:border-transparent transition-colors`}
                  placeholder="John Doe"
                  required
                  disabled={isSubmitting}
                />
              </div>
              {errors.fullName && !generalError && (
                <Description className="text-error-light text-xs mt-1" role="alert">
                  {errors.fullName.join(' ')}
                </Description>
              )}
            </Field>

            <Field className="space-y-1">
              <Label className="block text-sm font-medium text-text-body">Date of Birth</Label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <CalendarIcon size={ICON_MD} className="text-text-subtle" />
                </div>
                <Input
                  type="date"
                  name="dateOfBirth"
                  value={form.dateOfBirth || ''}
                  onChange={(e) => setFieldValue('dateOfBirth', e.target.value)}
                  className={`w-full bg-surface-tertiary border ${
                    errors.dateOfBirth
                      ? 'border-error bg-error-subtle focus:ring-error'
                      : 'border-border focus:ring-border-focus'
                  } rounded-lg pl-10 pr-3 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:border-transparent transition-colors`}
                  required
                  disabled={isSubmitting}
                />
              </div>
              {errors.dateOfBirth && !generalError && (
                <Description className="text-error-light text-xs mt-1" role="alert">
                  {errors.dateOfBirth.join(' ')}
                </Description>
              )}
            </Field>

            <Field className="space-y-1">
              <Label className="block text-sm font-medium text-text-body">Phone Number</Label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none z-10">
                  <PhoneIcon size={ICON_MD} className="text-text-subtle" />
                </div>
                <div className="flex focus-within:ring-2 focus-within:ring-border-focus rounded-lg">
                  {selectedCountry && countries && onCountryChange && (
                    <CountrySelector
                      countries={countries}
                      selectedCountry={selectedCountry}
                      onCountryChange={onCountryChange}
                      disabled={isSubmitting}
                    />
                  )}
                  <div className="relative flex-1">
                    <Input
                      type="tel"
                      name="phoneNumber"
                      value={form.phoneNumber}
                      onChange={(e) => setFieldValue('phoneNumber', e.target.value)}
                      className={`w-full bg-surface-tertiary border ${
                        (formValidation && !formValidation.phoneNumber.isValid && form.phoneNumber) ||
                        errors.phoneNumber
                          ? 'border-error bg-error-subtle focus:ring-error'
                          : 'border-border focus:ring-border-focus'
                      } ${
                        selectedCountry ? 'rounded-r-lg border-l-0 pl-2' : 'rounded-lg pl-3'
                      } pr-3 py-3 text-text-primary placeholder-text-muted focus:outline-none transition-colors h-12`}
                      placeholder="416 123 456"
                      required
                      disabled={isSubmitting}
                    />
                  </div>
                </div>
              </div>
              {errors.phoneNumber && !generalError && (
                <Description className="text-error-light text-xs mt-1" role="alert">
                  {errors.phoneNumber.join(' ')}
                </Description>
              )}
            </Field>

            <Field className="space-y-1">
              <Label className="block text-sm font-medium text-text-body">Residential Address</Label>
              <Description className="text-text-subtle text-xs">
                Include street number, city, state and postcode
              </Description>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 pt-3 flex items-start pointer-events-none">
                  <HouseIcon size={ICON_MD} className="text-text-subtle" />
                </div>
                <Textarea
                  name="residentialAddress"
                  value={form.residentialAddress}
                  onChange={(e) => setFieldValue('residentialAddress', e.target.value)}
                  rows={3}
                  className={`w-full bg-surface-tertiary border ${
                    (formValidation && !formValidation.residentialAddress.isValid && form.residentialAddress) ||
                    errors.residentialAddress
                      ? 'border-error bg-error-subtle focus:ring-error'
                      : 'border-border focus:ring-border-focus'
                  } rounded-lg pl-10 pr-3 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:border-transparent transition-colors resize-none`}
                  placeholder="123 Main Street&#10;Sydney NSW 2000"
                  required
                  disabled={isSubmitting}
                />
              </div>
              {errors.residentialAddress && !generalError && (
                <Description className="text-error-light text-xs mt-1" role="alert">
                  {errors.residentialAddress.join(' ')}
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
