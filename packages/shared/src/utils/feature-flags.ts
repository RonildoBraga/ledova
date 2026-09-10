import type { FeatureFlag } from '../types';

export interface FeatureFlagInputs {
  mobilePlatform?: string;
  appVersion?: string | null;
}

function isVersionAtLeast(current: string, minimum: string): boolean {
  const currentParts = current.split('.').map(Number);
  const minimumParts = minimum.split('.').map(Number);

  for (let i = 0; i < 3; i++) {
    const cur = currentParts[i] || 0;
    const min = minimumParts[i] || 0;
    if (cur > min) return true;
    if (cur < min) return false;
  }
  return true;
}

function matchesPlatform(flag: FeatureFlag, mobilePlatform: string | undefined): boolean {
  if (mobilePlatform === undefined) return true;

  switch (flag.platform) {
    case 'all':
    case 'mobile':
      return true;
    case 'ios':
    case 'android':
      return flag.platform === mobilePlatform;
    default:
      return false;
  }
}

function matchesVersion(flag: FeatureFlag, inputs: FeatureFlagInputs): boolean {
  if (!flag.minAppVersion) return true;

  const appVersion = inputs.appVersion;
  return !appVersion || isVersionAtLeast(appVersion, flag.minAppVersion);
}

export function readFeatureFlags(allFlags: readonly FeatureFlag[], inputs: FeatureFlagInputs = {}) {
  const flags = allFlags.filter((flag) => matchesPlatform(flag, inputs.mobilePlatform) && matchesVersion(flag, inputs));

  const isEnabled = (name: string): boolean => flags.some((flag) => flag.name === name && flag.enabled);

  return { flags, isEnabled };
}
