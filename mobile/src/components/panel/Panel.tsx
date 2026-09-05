/* eslint-disable @typescript-eslint/no-explicit-any */
import React from 'react';
import { View, Text, StyleProp, ViewStyle } from 'react-native';
import { useAppTheme, useThemedStyles } from '../../contexts';

interface PanelProps {
  title?: string | React.ReactNode;
  icon?: React.ReactNode;

  actions?: React.ReactNode;

  style?: StyleProp<ViewStyle>;

  fullHeight?: boolean;

  children: React.ReactNode;
}

export function Panel({ title, icon, actions, style, fullHeight = false, children }: PanelProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      backgroundColor: theme.colors.surface.raised,
      borderRadius: theme.borderRadius.md,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
    },
    header: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingVertical: theme.spacing.md,
      paddingHorizontal: theme.spacing.md,
      backgroundColor: theme.colors.surface.raised,
      borderRadius: theme.borderRadius.md,
    },
    titleContainer: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.sm,
      flex: 1,
    },
    actionsContainer: {
      flexDirection: 'row',
      alignItems: 'center',
    },
    title: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    content: {
      flex: 1,
      paddingHorizontal: theme.spacing.sm,
      paddingBottom: theme.spacing.md,
    },
    contentWithoutTitle: {
      flex: 1,
      paddingHorizontal: theme.spacing.sm,
      paddingTop: theme.spacing.md,
      paddingBottom: theme.spacing.md,
    },
  }));

  const styledIcon =
    icon && React.isValidElement(icon)
      ? React.cloneElement(icon as React.ReactElement<any>, {
          size: (icon as any).props.size ?? theme.icon.sizes.sm,
          color: (icon as any).props.color ?? theme.colors.text.muted,
          weight: (icon as any).props.weight ?? theme.icon.weights.light,
        })
      : icon;

  const contentStyle = title ? styles.content : styles.contentWithoutTitle;

  return (
    <View style={[styles.container, fullHeight ? { height: '99%' } : undefined, style]}>
      {title && (
        <View style={styles.header}>
          <View style={styles.titleContainer}>
            {styledIcon}
            {typeof title === 'string' ? <Text style={styles.title}>{title}</Text> : title}
          </View>
          {actions && <View style={styles.actionsContainer}>{actions}</View>}
        </View>
      )}

      <View style={contentStyle}>{children}</View>
    </View>
  );
}
