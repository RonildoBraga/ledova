import { Link, useNavigate } from 'react-router-dom';
import { useSignupUser } from './useSignupUser';
import { Field, Label, Input, Description } from '@headlessui/react';
import { EyeIcon, EyeSlashIcon, EnvelopeIcon, LockIcon, UserIcon, WarningIcon } from '@phosphor-icons/react';
import { AuthLayout } from '@components/AuthLayout';
import { DESIGN_TOKENS } from '@ledova/shared';

const ICON_MD = DESIGN_TOKENS.icon.sizes.md;

export function SignupUser() {
  const navigate = useNavigate();
  const {
    form,
    errors,
    generalError,
    isLoading,
    showPassword,
    passwordValidation,
    setFieldValue,
    togglePassword,
    handleSubmit,
  } = useSignupUser();

  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    await handleSubmit(() => {
      navigate('/signup/email-confirmation');
    });
  };

  return (
    <AuthLayout>
      <div className="text-center mb-6">
        <div className="flex justify-center mb-3">
          <div className="p-2 rounded-full bg-surface-raised border border-border">
            <UserIcon size={ICON_MD} className="text-text-muted" />
          </div>
        </div>
        <h1 className="text-xl font-semibold text-text-primary">Create Your Account</h1>
      </div>

      <div className="bg-surface-raised rounded-lg border border-border">
        <div className="p-6">
          <form onSubmit={handleSignUp} className="space-y-6">
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

            <Field className="space-y-2">
              <Label className="block text-sm font-medium text-text-body">Email</Label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <EnvelopeIcon size={ICON_MD} className="text-text-subtle" />
                </div>
                <Input
                  type="email"
                  name="email"
                  value={form.email}
                  onChange={(e) => setFieldValue('email', e.target.value)}
                  className="w-full bg-surface-tertiary border border-border rounded-lg pl-10 pr-3 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-brand-mid focus:border-transparent transition-colors"
                  placeholder="your@email.com"
                  required
                  disabled={isLoading}
                />
              </div>
              {errors.email && !generalError && errors.email.length > 0 && (
                <Description className="text-error-light text-sm mt-1" role="alert">
                  {errors.email.map((error, index) => (
                    <span key={index}>
                      {error.includes('already registered') ? (
                        <>
                          {error.split('Please')[0]}Please{' '}
                          <Link to="/signin" className="underline hover:text-error-light">
                            sign in
                          </Link>
                          {' or use a different email.'}
                        </>
                      ) : (
                        error
                      )}
                    </span>
                  ))}
                </Description>
              )}
            </Field>

            <Field className="space-y-3">
              <Label className="block text-sm font-medium text-text-body">Password</Label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <LockIcon size={ICON_MD} className="text-text-subtle" />
                </div>
                <Input
                  type={showPassword ? 'text' : 'password'}
                  name="password"
                  value={form.password}
                  onChange={(e) => setFieldValue('password', e.target.value)}
                  className={`w-full bg-surface-tertiary border ${
                    (!passwordValidation.lengthValid || !passwordValidation.notNumeric) && form.password
                      ? 'border-error focus:ring-error'
                      : 'border-border focus:ring-brand-mid'
                  } rounded-lg pl-10 pr-12 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:border-transparent transition-colors`}
                  placeholder="••••••••"
                  minLength={8}
                  required
                  disabled={isLoading}
                />
                <button
                  type="button"
                  onClick={togglePassword}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-text-subtle hover:text-text-body transition-colors"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  disabled={isLoading}
                >
                  {showPassword ? <EyeSlashIcon size={ICON_MD} /> : <EyeIcon size={ICON_MD} />}
                </button>
              </div>

              <div className="bg-surface-tertiary rounded-md p-3 border border-border">
                <p className="text-xs font-medium text-text-body mb-2">Password must:</p>
                <ul className="space-y-1">
                  <li className="flex items-center space-x-2 text-xs">
                    <div
                      className={`w-1.5 h-1.5 rounded-full ${
                        form.password && !passwordValidation.lengthValid ? 'bg-error-light' : 'bg-text-subtle'
                      }`}
                    />
                    <span
                      className={
                        form.password && !passwordValidation.lengthValid ? 'text-error-light' : 'text-text-muted'
                      }
                    >
                      Be at least 8 characters long
                    </span>
                  </li>
                  <li className="flex items-center space-x-2 text-xs">
                    <div
                      className={`w-1.5 h-1.5 rounded-full ${
                        form.password && !passwordValidation.notNumeric ? 'bg-error-light' : 'bg-text-subtle'
                      }`}
                    />
                    <span
                      className={
                        form.password && !passwordValidation.notNumeric ? 'text-error-light' : 'text-text-muted'
                      }
                    >
                      Not be entirely numeric
                    </span>
                  </li>
                </ul>
              </div>

              {errors.password && !generalError && errors.password.length > 0 && (
                <Description className="text-error-light text-sm mt-1" role="alert">
                  {errors.password.join(' ')}
                </Description>
              )}
            </Field>

            <button
              type="submit"
              disabled={
                isLoading ||
                (!passwordValidation.lengthValid && form.password.length > 0) ||
                (!passwordValidation.notNumeric && form.password.length > 0)
              }
              className="w-full bg-brand-mid hover:bg-brand disabled:bg-surface-disabled disabled:cursor-not-allowed text-white font-semibold py-3 px-4 rounded-lg transition-colors shadow-lg shadow-brand-light/40 disabled:shadow-none focus:outline-none focus:ring-2 focus:ring-border-focus focus:ring-offset-2 focus:ring-offset-surface-base"
            >
              {isLoading ? (
                <div className="flex items-center justify-center space-x-2">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                  <span>Creating account...</span>
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
          Already have an account?{' '}
          <Link to="/signin" className="font-semibold text-brand-light hover:text-brand-subtle transition-colors">
            Sign In
          </Link>
        </p>
      </div>
    </AuthLayout>
  );
}
