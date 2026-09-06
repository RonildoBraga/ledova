import { mockDataEnabled } from './mockDataEnabled';

describe('mockDataEnabled', () => {
  const original = process.env.EXPO_PUBLIC_USE_MOCK_DATA;

  afterEach(() => {
    process.env.EXPO_PUBLIC_USE_MOCK_DATA = original;
  });

  function withEnv(value: string | undefined): boolean {
    if (value === undefined) {
      delete process.env.EXPO_PUBLIC_USE_MOCK_DATA;
    } else {
      process.env.EXPO_PUBLIC_USE_MOCK_DATA = value;
    }

    return mockDataEnabled();
  }

  it('stays off when the variable is absent, so a build that forgets it still broadcasts', () => {
    expect(withEnv(undefined)).toBe(false);
  });

  it('stays off for an empty value', () => {
    expect(withEnv('')).toBe(false);
  });

  it('turns on only for an explicit opt-in', () => {
    expect(withEnv('true')).toBe(true);
    expect(withEnv('TRUE')).toBe(true);
  });

  it('stays off for anything that is not true, including a plausible typo', () => {
    expect(withEnv('false')).toBe(false);
    expect(withEnv('1')).toBe(false);
    expect(withEnv('yes')).toBe(false);
    expect(withEnv('truthy')).toBe(false);
  });
});
