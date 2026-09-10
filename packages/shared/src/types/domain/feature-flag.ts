export interface FeatureFlag {
  uuid: string;
  name: string;
  description: string;
  enabled: boolean;
  platform: 'all' | 'ios' | 'android' | 'web' | 'mobile';
  minAppVersion: string;
}
