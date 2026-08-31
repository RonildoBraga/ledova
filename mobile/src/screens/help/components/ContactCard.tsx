import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { useAppTheme, useThemedStyles } from '../../../contexts';

interface ContactCardProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  actionLabel?: string;
  actionType?: 'link' | 'button';
  onAction?: () => void;
  children?: React.ReactNode;
}

export function ContactCard({
  icon,
  title,
  description,
  actionLabel,
  actionType = 'link',
  onAction,
  children,
}: ContactCardProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    card: {
      backgroundColor: theme.colors.surface.raised,
      borderRadius: theme.borderRadius.lg,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      padding: theme.spacing.md,
    },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.sm,
      marginBottom: theme.spacing.xs,
    },
    title: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    description: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.body,
      lineHeight: 20,
      marginBottom: theme.spacing.sm,
    },
    linkText: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.info.light,
    },
    button: {
      backgroundColor: theme.colors.info.default,
      paddingVertical: theme.spacing.sm,
      paddingHorizontal: theme.spacing.md,
      borderRadius: theme.borderRadius.md,
      alignSelf: 'flex-start',
    },
    buttonText: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
  }));
  // Clone the icon with soft, calming styling - smaller for inline display
  const styledIcon =
    icon && React.isValidElement(icon)
      ? React.cloneElement(icon as React.ReactElement<{ size?: number; color?: string; weight?: string }>, {
          size: 20,
          color: theme.colors.info.light,
          weight: 'regular',
        })
      : icon;

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        {styledIcon}
        <Text style={styles.title}>{title}</Text>
      </View>

      {description ? <Text style={styles.description}>{description}</Text> : null}

      {children}

      {actionLabel && onAction && (
        <>
          {actionType === 'button' ? (
            <TouchableOpacity style={styles.button} onPress={onAction} activeOpacity={0.8}>
              <Text style={styles.buttonText}>{actionLabel}</Text>
            </TouchableOpacity>
          ) : (
            <TouchableOpacity onPress={onAction} activeOpacity={0.7}>
              <Text style={styles.linkText}>{actionLabel}</Text>
            </TouchableOpacity>
          )}
        </>
      )}
    </View>
  );
}
