import type { ReviewAnswer, UserProfile, VerificationStatus } from '@ledova/shared-types';
import { getUserVerificationStatus } from '../src/user-verification';

const profile = (overrides: Partial<UserProfile>): UserProfile =>
  ({ isIdVerified: false, verificationStatus: null, reviewResult: null, ...overrides }) as UserProfile;

describe('getUserVerificationStatus', () => {
  it('trusts isIdVerified before any provider status', () => {
    const status = getUserVerificationStatus(profile({ isIdVerified: true, verificationStatus: 'init' }));

    expect(status).toEqual({ type: 'verified', label: 'Verified' });
  });

  it.each<VerificationStatus>([null, 'init'])('reads %s as not started', (verificationStatus) => {
    expect(getUserVerificationStatus(profile({ verificationStatus })).type).toBe('not_started');
  });

  it.each<VerificationStatus>(['pending', 'queued', 'prechecked', 'onHold'])(
    'reads %s as pending',
    (verificationStatus) => {
      expect(getUserVerificationStatus(profile({ verificationStatus })).type).toBe('pending');
    },
  );

  it.each<[ReviewAnswer, string]>([
    ['GREEN', 'verified'],
    ['YELLOW', 'pending'],
    ['RED', 'rejected'],
    [null, 'unknown'],
  ])('maps a completed check reviewed %s to %s', (reviewResult, expected) => {
    expect(getUserVerificationStatus(profile({ verificationStatus: 'completed', reviewResult })).type).toBe(expected);
  });

  it('reads a missing profile as not started and a bare status string as the status', () => {
    expect(getUserVerificationStatus(undefined)).toEqual({ type: 'not_started', label: 'Not Started' });
    expect(getUserVerificationStatus(null).type).toBe('not_started');
    expect(getUserVerificationStatus('onHold').type).toBe('pending');
  });
});
