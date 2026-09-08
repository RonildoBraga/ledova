import { readSignInError } from '../../src/utils/errors';

function refusal(status: number, data: unknown, headers: Record<string, string> = {}) {
  return { response: { status, data, headers } };
}

describe('a throttled sign-in', () => {
  const THROTTLED = { detail: 'Request was throttled. Expected available in 3471 seconds.' };

  it('says it is throttled rather than that the password is wrong', () => {
    const reading = readSignInError(refusal(429, THROTTLED, { 'retry-after': '3471' }));

    expect(reading.generalError).toContain('Too many sign-in attempts');
    expect(reading.generalError).not.toContain('password');
    expect(reading.fieldErrors).toBeUndefined();
  });

  it('says how long in minutes, because seconds is a number to do arithmetic on', () => {
    const reading = readSignInError(refusal(429, THROTTLED, { 'retry-after': '3471' }));

    expect(reading.generalError).toBe('Too many sign-in attempts. Please try again in about 58 minutes.');
  });

  it('reads the window out of the message when the header is absent', () => {
    const reading = readSignInError(refusal(429, THROTTLED));

    expect(reading.generalError).toBe('Too many sign-in attempts. Please try again in about 58 minutes.');
  });

  it('counts one minute as one minute', () => {
    const reading = readSignInError(refusal(429, { detail: 'throttled' }, { 'retry-after': '30' }));

    expect(reading.generalError).toBe('Too many sign-in attempts. Please try again in about 1 minute.');
  });

  it('counts hours once minutes stop being useful', () => {
    const reading = readSignInError(refusal(429, { detail: 'throttled' }, { 'retry-after': '7200' }));

    expect(reading.generalError).toBe('Too many sign-in attempts. Please try again in about 2 hours.');
  });

  it('still says it is throttled when nothing says for how long', () => {
    const reading = readSignInError(refusal(429, { detail: 'Request was throttled.' }));

    expect(reading.generalError).toBe('Too many sign-in attempts. Please wait before trying again.');
  });
});

describe('the other refusals DRF answers with a detail and no error key', () => {
  it('shows a permission refusal rather than a credentials message', () => {
    const reading = readSignInError(refusal(403, { detail: 'You do not have permission to perform this action.' }));

    expect(reading.generalError).toBe('You do not have permission to perform this action.');
  });

  it('shows the sentence rather than the label when a body carries both', () => {
    const reading = readSignInError(
      refusal(503, { error: 'Database error', detail: 'A database error occurred. Please try again later.' }),
    );

    expect(reading.generalError).toBe('A database error occurred. Please try again later.');
  });

  it('falls back to the label when that is all there is', () => {
    const reading = readSignInError(refusal(400, { error: 'Invalid email or password.' }));

    expect(reading.generalError).toBe('Invalid email or password.');
  });
});

describe('a wrong password, which is the shape this endpoint actually sends', () => {
  const CREDENTIALS = { error: ['Invalid email or password.'] };

  it('announces it, rather than marking a field nothing renders', () => {
    const reading = readSignInError(refusal(400, CREDENTIALS));

    expect(reading.generalError).toBe('Invalid email or password.');
    expect(reading.fieldErrors).toBeUndefined();
  });

  it('announces it on a 401 too', () => {
    const reading = readSignInError(refusal(401, CREDENTIALS));

    expect(reading.generalError).toBe('Invalid email or password.');
  });

  it('joins an error that carries more than one sentence', () => {
    const reading = readSignInError(refusal(400, { error: ['Invalid email or password.', 'Two left.'] }));

    expect(reading.generalError).toBe('Invalid email or password. Two left.');
  });

  it('announces a detail that arrives as a list, for the same reason', () => {
    const reading = readSignInError(refusal(400, { detail: ['Something went wrong.'] }));

    expect(reading.generalError).toBe('Something went wrong.');
  });
});

describe('what the form should mark rather than announce', () => {
  it('hands field errors back as field errors', () => {
    const reading = readSignInError(refusal(400, { email: ['Enter a valid email address.'] }));

    expect(reading.fieldErrors).toEqual({ email: ['Enter a valid email address.'] });
    expect(reading.generalError).toBeUndefined();
  });
});

describe('a shape nothing recognises', () => {
  it('does not claim the password was wrong, because nothing said so', () => {
    const reading = readSignInError(refusal(400, { somethingNew: 'a value' }));

    expect(reading.generalError).toBe('Unable to sign in at the moment. Please try again later.');
  });

  it('says the same when there is no response at all', () => {
    expect(readSignInError(new Error('network down')).generalError).toBe(
      'Unable to sign in at the moment. Please try again later.',
    );
  });

  it('shows a string body as it stands', () => {
    expect(readSignInError(refusal(500, 'Service unavailable')).generalError).toBe('Service unavailable');
  });

  it('joins an array body', () => {
    expect(readSignInError(refusal(400, ['One thing.', 'And another.'])).generalError).toBe('One thing. And another.');
  });
});
