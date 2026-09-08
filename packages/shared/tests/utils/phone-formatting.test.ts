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

  it('preserves an extra digit instead of treating formatting as validation', () => {
    expect(formatPhoneForDisplay('4123456789', AU)).toBe('4123456789');
  });
});

describe('the national form, which still has its leading zero', () => {
  it('keeps the four-three-three grouping a 0-prefixed number is written in', () => {
    expect(formatPhoneForDisplay('0412345678', AU)).toBe('0412 345 678');
  });

  it('keeps the national and international mobile presentations distinct', () => {
    expect(formatPhoneForDisplay('0412345678', AU)).toBe('0412 345 678');
    expect(formatPhoneForDisplay('412345678', AU)).toBe('412 345 678');
  });
});

describe.each([AU, undefined])('Australian service numbers with country %j', (country) => {
  it.each([
    ['1300123456', '1300 123 456'],
    ['1300 123 456', '1300 123 456'],
    ['1300-123-456', '1300 123 456'],
    ['1800123456', '1800 123 456'],
    ['1800 123 456', '1800 123 456'],
    ['1800-123-456', '1800 123 456'],
  ])('formats %s without changing the value cleaned for saving', (input, expected) => {
    const displayed = formatPhoneForDisplay(input, country);

    expect(displayed).toBe(expected);
    expect(cleanPhoneNumber(displayed)).toBe(cleanPhoneNumber(input));
    expect(formatPhoneForDisplay(displayed, country)).toBe(displayed);
    expect(cleanPhoneNumber(formatPhoneForDisplay(displayed, country))).toBe(cleanPhoneNumber(input));
  });

  it.each(['1300123456', '1800123456', '1300 123 456', '1800-123-456'])(
    'preserves every prefix while typing and pasting %s',
    (input) => {
      let displayed = '';

      for (let length = 1; length <= input.length; length += 1) {
        const prefix = input.slice(0, length);
        const pasted = formatPhoneForDisplay(prefix, country);
        displayed = formatPhoneForDisplay(displayed + input[length - 1], country);

        expect(cleanPhoneNumber(pasted)).toBe(cleanPhoneNumber(prefix));
        expect(cleanPhoneNumber(displayed)).toBe(cleanPhoneNumber(prefix));
        expect(formatPhoneForDisplay(pasted, country)).toBe(pasted);
      }
    },
  );

  it.each([' 4123456789 ', '04123456789', '212345678', '130012345', ' 00 1234 5678 9012 '])(
    'leaves unsupported input %s unchanged apart from surrounding whitespace',
    (input) => {
      expect(formatPhoneForDisplay(input, country)).toBe(input.trim());
      expect(cleanPhoneNumber(formatPhoneForDisplay(input, country))).toBe(cleanPhoneNumber(input));
    },
  );
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
