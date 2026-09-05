import type { BaseEntity } from '../common';

export interface FeatureFlag extends BaseEntity {
  name: string;
  description: string;
  enabled: boolean;
  platform: 'all' | 'ios' | 'android' | 'web' | 'mobile';
  minAppVersion: string;
}
