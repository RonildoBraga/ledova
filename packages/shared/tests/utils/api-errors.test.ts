import { readApiError, apiErrorSentence } from '../../src/utils/errors';

function refusal(status: number, data: unknown) {
  return { response: { status, data }, message: `Request failed with status code ${status}` };
}

const FALLBACK = 'We could not save that. Please try again.';

describe('a field the backend named', () => {
  it('comes back as a field error, so the form can mark it', () => {
    const reading = readApiError(
      refusal(400, { acn: ['This is not a valid ACN: its last digit does not check out against the other eight.'] }),
      { fallback: FALLBACK },
    );

    expect(reading.fieldErrors).toEqual({
      acn: ['This is not a valid ACN: its last digit does not check out against the other eight.'],
    });
    expect(reading.generalError).toBeUndefined();
  });

  it('is announced instead when the form has nowhere to mark it', () => {
    const reading = readApiError(refusal(400, { primaryContact: ['Enter a contact phone number.'] }), {
      fallback: FALLBACK,
      displayedFields: ['name', 'acn'],
    });

    expect(reading.generalError).toBe('Enter a contact phone number.');
    expect(reading.fieldErrors).toBeUndefined();
  });

  it('keeps the fields the form does display while announcing the ones it does not', () => {
    const reading = readApiError(
      refusal(400, { acn: ['Company with this acn already exists.'], primaryContact: ['Missing.'] }),
      {
        fallback: FALLBACK,
        displayedFields: ['acn'],
      },
    );

    expect(reading.fieldErrors).toEqual({ acn: ['Company with this acn already exists.'] });
    expect(reading.generalError).toBe('Missing.');
  });

  it('announces non_field_errors, which belong to no field by definition', () => {
    const reading = readApiError(refusal(400, { nonFieldErrors: ['The two dates overlap.'] }), { fallback: FALLBACK });

    expect(reading.generalError).toBe('The two dates overlap.');
    expect(reading.fieldErrors).toBeUndefined();
  });
});

describe('what it refuses to say', () => {
  it('never repeats axios, whose string is about HTTP and not about the person', () => {
    const reading = readApiError(refusal(400, undefined), { fallback: FALLBACK });

    expect(reading.generalError).toBe(FALLBACK);
    expect(apiErrorSentence(refusal(400, undefined), FALLBACK)).not.toContain('status code');
  });

  it('does not read a bare string under an unrecognised key as a message for a person', () => {
    const reading = readApiError(refusal(400, { requestId: 'ab93f1', somethingNew: 'a value' }), {
      fallback: FALLBACK,
    });

    expect(reading.generalError).toBe(FALLBACK);
    expect(reading.fieldErrors).toBeUndefined();
  });

  it('announces once when a body carries both a label and a sentence', () => {
    const reading = readApiError(refusal(503, { error: 'Database error', detail: 'A database error occurred.' }), {
      fallback: FALLBACK,
    });

    expect(reading.generalError).toBe('A database error occurred.');
  });
});

describe('the flattened sentence, for a banner with no field to mark', () => {
  it('carries the backend reason rather than the status code', () => {
    expect(apiErrorSentence(refusal(400, { symbol: ['Symbol must contain only letters.'] }), FALLBACK)).toBe(
      'Symbol must contain only letters.',
    );
  });

  it('joins every field, because one banner is all there is', () => {
    const sentence = apiErrorSentence(
      refusal(400, { symbol: ['Symbol must contain only letters.'], totalSupply: ['Must be positive.'] }),
      FALLBACK,
    );

    expect(sentence).toContain('Symbol must contain only letters.');
    expect(sentence).toContain('Must be positive.');
  });

  it('falls back when the response says nothing at all', () => {
    expect(apiErrorSentence(new Error('network down'), FALLBACK)).toBe(FALLBACK);
  });
});
