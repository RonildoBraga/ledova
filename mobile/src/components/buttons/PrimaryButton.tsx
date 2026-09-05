import React from 'react';
import { Button } from './Button';
import type { ViewStyle, TextStyle } from 'react-native';

interface PrimaryButtonProps {
  disabled?: boolean;

  loading?: boolean;

  icon?: React.ReactNode;

  iconPosition?: 'left' | 'right';

  onPress: () => void;

  children: React.ReactNode;

  fullWidth?: boolean;

  size?: 'small' | 'medium' | 'large';

  style?: ViewStyle;

  textStyle?: TextStyle;
}

export function PrimaryButton(props: PrimaryButtonProps) {
  return <Button variant="primary" {...props} />;
}
