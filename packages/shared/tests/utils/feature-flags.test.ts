import type { FeatureFlag } from '../../src/types';
import { readFeatureFlags } from '../../src/utils/feature-flags';

function flag(overrides: Partial<FeatureFlag> = {}): FeatureFlag {
  return {
    uuid: 'synthetic-flag',
    name: 'trading_enabled',
    description: '',
    enabled: true,
    platform: 'all',
    minAppVersion: '',
    ...overrides,
  };
}

describe('shared feature-flag meaning', () => {
  it('requires an enabled matching name and treats absent flags as disabled', () => {
    const { isEnabled } = readFeatureFlags([flag({ name: 'enabled' }), flag({ name: 'disabled', enabled: false })]);

    expect(isEnabled('enabled')).toBe(true);
    expect(isEnabled('disabled')).toBe(false);
    expect(isEnabled('absent')).toBe(false);
    expect(readFeatureFlags([]).isEnabled('enabled')).toBe(false);
  });

  it.each([
    [false, true],
    [true, false],
  ] as const)('preserves any-enabled-match for duplicate names (%s, %s)', (first, second) => {
    const { isEnabled } = readFeatureFlags([flag({ enabled: first }), flag({ enabled: second })]);
    expect(isEnabled('trading_enabled')).toBe(true);
  });

  it.each(['ios', 'android'])('selects all, mobile and matching %s flags', (mobilePlatform) => {
    const platforms: FeatureFlag['platform'][] = ['all', 'mobile', 'ios', 'android', 'web'];
    const { flags } = readFeatureFlags(
      platforms.map((platform) => flag({ platform })),
      { mobilePlatform },
    );

    expect(flags.map((entry) => entry.platform)).toEqual(['all', 'mobile', mobilePlatform]);
  });

  it.each(['web', 'windows'])('preserves the mobile reader on a %s runtime', (mobilePlatform) => {
    const platforms: FeatureFlag['platform'][] = ['all', 'mobile', 'ios', 'android', 'web'];
    const { flags } = readFeatureFlags(
      platforms.map((platform) => flag({ platform })),
      { mobilePlatform },
    );

    expect(flags.map((entry) => entry.platform)).toEqual(['all', 'mobile']);
  });

  it('leaves targeting unrestricted when the dashboard supplies no mobile inputs', () => {
    const platforms: FeatureFlag['platform'][] = ['all', 'mobile', 'ios', 'android', 'web'];
    for (const platform of platforms) {
      expect(readFeatureFlags([flag({ platform, minAppVersion: '99.0.0' })]).isEnabled('trading_enabled')).toBe(true);
    }
  });

  it('keeps eligible disabled entries in flags without enabling them or mutating the input', () => {
    const disabled = flag({ enabled: false });
    const input = Object.freeze([disabled, flag({ platform: 'web' })]);
    const { flags, isEnabled } = readFeatureFlags(input, { mobilePlatform: 'ios' });

    expect(flags).toEqual([disabled]);
    expect(flags[0]).toBe(disabled);
    expect(input).toHaveLength(2);
    expect(isEnabled('trading_enabled')).toBe(false);
  });

  it.each([
    ['1.2.3', '1.2.3', true],
    ['1.2.2', '1.2.3', false],
    ['1.2.10', '1.2.3', true],
    ['1.1.99', '1.2.0', false],
    ['2.0.0', '1.99.99', true],
    ['1.99.99', '2.0.0', false],
    ['1.2', '1.2.0', true],
    ['1.2', '1.2.1', false],
    ['1.2.3.99', '1.2.3.100', true],
    ['1.bad.3', '1.0.3', true],
  ] as const)('preserves the existing comparison of %s against %s', (appVersion, minAppVersion, enabled) => {
    expect(
      readFeatureFlags([flag({ minAppVersion })], { mobilePlatform: 'ios', appVersion }).isEnabled('trading_enabled'),
    ).toBe(enabled);
  });

  it.each([undefined, null, ''])('does not apply a minimum when the current version is %s', (appVersion) => {
    expect(
      readFeatureFlags([flag({ minAppVersion: '99.0.0' })], { mobilePlatform: 'ios', appVersion }).isEnabled(
        'trading_enabled',
      ),
    ).toBe(true);
  });

  it('permits a flag without a minimum on an older app', () => {
    expect(
      readFeatureFlags([flag()], { mobilePlatform: 'android', appVersion: '0.0.1' }).isEnabled('trading_enabled'),
    ).toBe(true);
  });

  it('reads the current version only for a matching flag with a minimum', () => {
    const readVersion = jest.fn(() => {
      throw new Error('Synthetic manifest unavailable');
    });
    const inputs = {
      mobilePlatform: 'ios',
      get appVersion() {
        return readVersion();
      },
    };

    expect(readFeatureFlags([], inputs).flags).toEqual([]);
    const { isEnabled } = readFeatureFlags([flag(), flag({ platform: 'web', minAppVersion: '2.0.0' })], inputs);
    expect(isEnabled('trading_enabled')).toBe(true);
    expect(readVersion).not.toHaveBeenCalled();

    expect(() => readFeatureFlags([flag({ minAppVersion: '1.0.0' })], inputs)).toThrow(
      'Synthetic manifest unavailable',
    );
    expect(readVersion).toHaveBeenCalledTimes(1);
  });
});
