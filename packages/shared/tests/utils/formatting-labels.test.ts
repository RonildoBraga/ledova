import { formatSourceOfFunds } from '../../src/utils/formatting-labels';

describe('source of funds review labels', () => {
  it('keeps selected labels and unknown string choices in their original order', () => {
    expect(formatSourceOfFunds(['savings', 'historical choice', 'employment_income'])).toBe(
      'Savings, historical choice, Employment income',
    );
  });

  it.each([null, false, 7, 'savings', { savings: true }])('does not treat the JSON value %j as choices', (funds) => {
    expect(Reflect.apply(formatSourceOfFunds, undefined, [funds])).toBe('');
  });

  it('renders string choices without exposing nested JSON as review text', () => {
    expect(
      Reflect.apply(formatSourceOfFunds, undefined, [
        ['savings', null, 4, { other: 'legacy' }, ['gift'], 'inheritance'],
      ]),
    ).toBe('Savings, Inheritance');
  });
});
