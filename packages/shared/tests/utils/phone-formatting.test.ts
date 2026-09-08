import { formatPhoneForDisplay, cleanPhoneNumber } from '../../src/utils/phoneFormatting';

const AU = { phoneCode: '+61', code: 'AU' };
const US = { phoneCode: '+1', code: 'US' };

describe('an Australian number typed beside a +61 selector', () => {
  it('groups the placeholder the field shows, which is what a user types', () => {
    expect(formatPhoneForDisplay('416123456', AU)).toBe('416 123 456');
  });

  it('groups a mobile the same way whatever separators were typed', () => {
    expect(formatPhoneForDisplay('412 345 678', AU)).toBe('412 345 678');
    expect(formatPhoneForDisplay('412-345-678', AU)).toBe('412 345 678');
  });

  it('stops at nine digits, because the country code is shown separately', () => {
    expect(formatPhoneForDisplay('4123456789', AU)).toBe('412 345 678');
  });
});

describe('the national form, which still has its leading zero', () => {
  it('keeps the four-three-three grouping a 0-prefixed number is written in', () => {
    expect(formatPhoneForDisplay('0412345678', AU)).toBe('0412 345 678');
  });

  it('is told apart from the international form by that zero and nothing else', () => {
    expect(formatPhoneForDisplay('0412345678', AU)).toBe('0412 345 678');
    expect(formatPhoneForDisplay('412345678', AU)).toBe('412 345 678');
  });
});

describe('what the formatter leaves alone', () => {
  it('returns an empty string for nothing', () => {
    expect(formatPhoneForDisplay('', AU)).toBe('');
  });

  it('leaves a number too short to group as it was typed', () => {
    expect(formatPhoneForDisplay('4161234', AU)).toBe('4161234');
  });

  it('defaults to Australia when no country is given, as the field does', () => {
    expect(formatPhoneForDisplay('416123456')).toBe('416 123 456');
  });

  it('still groups a United States number its own way', () => {
    expect(formatPhoneForDisplay('4155550123', US)).toBe('(415) 555-0123');
  });

  it('leaves a country it has no rule for as it was typed', () => {
    expect(formatPhoneForDisplay('20 7946 0958', { phoneCode: '+44' })).toBe('20 7946 0958');
  });
});

describe('cleanPhoneNumber, which is what is stored', () => {
  it('keeps the digits and nothing else', () => {
    expect(cleanPhoneNumber('416 123 456')).toBe('416123456');
    expect(cleanPhoneNumber('+61 (412) 345-678')).toBe('61412345678');
  });
});
