import React from 'react';
import { TouchableOpacity, Text, ActivityIndicator, View, ViewStyle, TextStyle } from 'react-native';
import { useAppTheme, useThemedStyles } from '../../contexts';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
type ButtonSize = 'small' | 'medium' | 'large';

const BUTTON_SIZES = {
  small: { height: 40, paddingHorizontal: 16, fontSize: 14, iconSize: 16, gap: 6 },
  medium: { height: 48, paddingHorizontal: 24, fontSize: 16, iconSize: 20, gap: 8 },
  large: { height: 56, paddingHorizontal: 32, fontSize: 18, iconSize: 24, gap: 10 },
} as const;

function getButtonVariants(theme: ReturnType<typeof useAppTheme>) {
  return {
    primary: {
      background: theme.colors.interactive.active,
      backgroundDisabled: theme.colors.interactive.disabled,
      text: theme.colors.utility.white,
      textDisabled: theme.colors.text.subtle,
      borderColor: 'transparent',
    },
    secondary: {
      background: theme.colors.surface.disabled,
      backgroundDisabled: theme.colors.surface.disabled,
      text: theme.colors.text.primary,
      textDisabled: theme.colors.text.subtle,
      borderColor: theme.colors.border.default,
    },
    ghost: {
      background: 'transparent',
      backgroundDisabled: 'transparent',
      text: theme.colors.interactive.default,
      textDisabled: theme.colors.text.subtle,
      borderColor: 'transparent',
    },
    danger: {
      background: theme.colors.error.default,
      backgroundDisabled: theme.colors.interactive.disabled,
      text: theme.colors.utility.white,
      textDisabled: theme.colors.text.subtle,
      borderColor: 'transparent',
    },
  };
}

interface ButtonProps {
  variant?: ButtonVariant;

  size?: ButtonSize;

  disabled?: boolean;

  loading?: boolean;

  icon?: React.ReactNode;

  iconPosition?: 'left' | 'right';

  onPress: () => void;

  children: React.ReactNode;

  fullWidth?: boolean;

  style?: ViewStyle;

  textStyle?: TextStyle;
}

export function Button({
  variant = 'primary',
  size = 'medium',
  disabled = false,
  loading = false,
  icon,
  iconPosition = 'left',
  onPress,
  children,
  fullWidth = false,
  style: customStyle,
  textStyle: customTextStyle,
}: ButtonProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    button: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
    },
    content: {
      flexDirection: 'row',
      alignItems: 'center',
    },
    text: {
      textAlign: 'center',
    },
    icon: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
    },
  }));
  const sizeConfig = BUTTON_SIZES[size];
  const variantConfig = getButtonVariants(theme)[variant];

  const isDisabled = disabled || loading;

  const buttonStyle: ViewStyle = {
    ...styles.button,
    height: sizeConfig.height,
    paddingHorizontal: sizeConfig.paddingHorizontal,
    backgroundColor: isDisabled ? variantConfig.backgroundDisabled : variantConfig.background,
    borderRadius: theme.borderRadius.lg,
    borderWidth: 1,
    borderColor: variant === 'secondary' ? variantConfig.borderColor : 'transparent',
    ...(fullWidth && { width: '100%' }),
    ...customStyle,
  };

  const textStyle: TextStyle = {
    ...styles.text,
    fontSize: sizeConfig.fontSize,
    fontWeight: theme.fontWeight.semibold as TextStyle['fontWeight'],
    color: isDisabled ? variantConfig.textDisabled : variantConfig.text,
    ...customTextStyle,
  };

  const contentStyle: ViewStyle = {
    gap: sizeConfig.gap,
  };

  return (
    <TouchableOpacity style={buttonStyle} onPress={onPress} disabled={isDisabled} activeOpacity={0.7}>
      {loading ? (
        <ActivityIndicator size="small" color={variantConfig.text} />
      ) : (
        <View style={[styles.content, contentStyle]}>
          {icon && iconPosition === 'left' && <View style={styles.icon}>{icon}</View>}
          <Text style={textStyle}>{children}</Text>
          {icon && iconPosition === 'right' && <View style={styles.icon}>{icon}</View>}
        </View>
      )}
    </TouchableOpacity>
  );
}
