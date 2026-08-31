import React from 'react';
import { Button } from './Button';
import type { ViewStyle, TextStyle } from 'react-native';

interface PrimaryButtonProps {
  /** Whether the button is disabled */
  disabled?: boolean;
  /** Whether the button is in a loading state (shows spinner) */
  loading?: boolean;
  /** Optional icon to display in the button */
  icon?: React.ReactNode;
  /** Position of the icon relative to text */
  iconPosition?: 'left' | 'right';
  /** Button press handler */
  onPress: () => void;
  /** Button text content */
  children: React.ReactNode;
  /** Whether the button should take full width of container */
  fullWidth?: boolean;
  /** Size of the button */
  size?: 'small' | 'medium' | 'large';
  /** Optional custom style override */
  style?: ViewStyle;
  /** Optional custom text style override */
  textStyle?: TextStyle;
}

/**
 * Primary button component - used for main call-to-action buttons
 * Examples: "Sign In", "Continue", "Submit", "Add Wallet"
 */
export function PrimaryButton(props: PrimaryButtonProps) {
  return <Button variant="primary" {...props} />;
}
