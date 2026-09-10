// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CompanyRegistrationForm } from './CompanyRegistrationForm';
import { DISPLAYED_FIELDS } from '../useSignupCompanyRegistration';

const A_MESSAGE: Record<string, string> = {
  name: 'Enter the registered name.',
  tradingName: 'Trading name is too long.',
  companyType: 'Choose a company type.',
  acn: 'This is not a valid ACN: its last digit does not check out against the other eight.',
  abn: 'This is not a valid ABN.',
};

function formWith(errors: Record<string, string[]>, generalError = '') {
  return (
    <CompanyRegistrationForm
      form={{ name: '', tradingName: '', companyType: 'pty', acn: '', abn: '' }}
      errors={errors}
      generalError={generalError}
      isSubmitting={false}
      canSubmit
      setFieldValue={vi.fn()}
      onSubmit={vi.fn()}
      onBack={vi.fn()}
    />
  );
}

describe('every field DISPLAYED_FIELDS names is one this form actually renders', () => {
  afterEach(cleanup);

  it.each(DISPLAYED_FIELDS)('renders the error it is handed for %s', (field) => {
    render(formWith({ [field]: [A_MESSAGE[field]] }));

    expect(screen.getByText(A_MESSAGE[field])).toBeDefined();
  });

  it('shows every sentence a field was given, not only the first', () => {
    render(formWith({ acn: ['Company with this acn already exists.', 'Try another.'] }));

    expect(screen.getByText('Company with this acn already exists. Try another.')).toBeDefined();
  });
});
