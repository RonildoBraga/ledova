import React, { useState } from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { useAppTheme, useThemedStyles } from '../../contexts';

interface AccordionProps {
  title: string | React.ReactNode;
  icon?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  defaultExpanded?: boolean;
}

export function Accordion({ title, icon, actions, children, defaultExpanded = true }: AccordionProps) {
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
  }));
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  const toggleSection = () => {
    setIsExpanded(!isExpanded);
  };

  const styledIcon =
    icon && React.isValidElement(icon)
      ? React.cloneElement(icon as React.ReactElement<Record<string, unknown>>, {
          size: (icon as React.ReactElement<Record<string, unknown>>).props.size ?? theme.icon.sizes.sm,
          color: (icon as React.ReactElement<Record<string, unknown>>).props.color ?? theme.colors.text.muted,
          weight: (icon as React.ReactElement<Record<string, unknown>>).props.weight ?? theme.icon.weights.light,
        })
      : icon;

  return (
    <View style={styles.container}>
      <TouchableOpacity
        style={styles.header}
        onPress={toggleSection}
        activeOpacity={0.7}
        accessibilityRole="button"
        accessibilityLabel={`${typeof title === 'string' ? title : 'Section'}, ${isExpanded ? 'expanded' : 'collapsed'}`}
        accessibilityHint="Double tap to toggle section"
      >
        <View style={styles.titleContainer}>
          {styledIcon}
          {typeof title === 'string' ? <Text style={styles.title}>{title}</Text> : title}
        </View>
        {actions && <View style={styles.actionsContainer}>{actions}</View>}
      </TouchableOpacity>

      {isExpanded && <View style={styles.content}>{children}</View>}
    </View>
  );
}
