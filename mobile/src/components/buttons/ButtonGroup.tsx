import React from 'react';
import { View, ViewStyle } from 'react-native';
import { PrimaryButton } from './PrimaryButton';
import { SecondaryButton } from './SecondaryButton';
import { useAppTheme, useThemedStyles } from '../../contexts';

interface ButtonGroupProps {
  secondaryButton?: {
    label: string;
    onPress: () => void;
    disabled?: boolean;
    loading?: boolean;
    icon?: React.ReactNode;
    smallText?: boolean;
  };

  primaryButton: {
    label: string;
    onPress: () => void;
    disabled?: boolean;
    loading?: boolean;
    icon?: React.ReactNode;
    smallText?: boolean;
  };

  size?: 'small' | 'medium' | 'large';

  style?: ViewStyle;
}

export function ButtonGroup({ secondaryButton, primaryButton, size = 'medium', style }: ButtonGroupProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      gap: theme.spacing.md,
    },
    button: {
      flex: 1,
    },
    buttonFullWidth: {
      flex: 1,
    },
    smallText: {
      fontSize: theme.fontSize.sm,
    },
  }));
  const buttonStyle = secondaryButton ? styles.button : styles.buttonFullWidth;

  return (
    <View style={[styles.container, style]}>
      {secondaryButton && (
        <SecondaryButton
          onPress={secondaryButton.onPress}
          disabled={secondaryButton.disabled}
          loading={secondaryButton.loading}
          icon={secondaryButton.icon}
          size={size}
          style={buttonStyle}
          textStyle={secondaryButton.smallText ? styles.smallText : undefined}
        >
          {secondaryButton.label}
        </SecondaryButton>
      )}
      <PrimaryButton
        onPress={primaryButton.onPress}
        disabled={primaryButton.disabled}
        loading={primaryButton.loading}
        icon={primaryButton.icon}
        size={size}
        style={buttonStyle}
        textStyle={primaryButton.smallText ? styles.smallText : undefined}
      >
        {primaryButton.label}
      </PrimaryButton>
    </View>
  );
}
