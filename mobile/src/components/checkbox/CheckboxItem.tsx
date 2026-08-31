import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { CheckIcon } from 'phosphor-react-native';
import { useAppTheme, useThemedStyles } from '../../contexts';

interface CheckboxItemProps {
  label: string;
  description: string;
  icon: React.ReactNode;
  checked: boolean;
  onPress: () => void;
}

export function CheckboxItem({ label, description, icon, checked, onPress }: CheckboxItemProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.xs,
      paddingVertical: theme.spacing.sm,
      paddingHorizontal: theme.spacing.sm,
      backgroundColor: theme.colors.surface.tertiary,
      borderRadius: theme.borderRadius.md,
      borderWidth: 1,
      borderColor: theme.colors.border.strong,
    },
    iconContainer: {
      justifyContent: 'center',
      alignItems: 'center',
    },
    textContainer: {
      flex: 1,
      flexDirection: 'row',
      alignItems: 'center',
      gap: 4,
    },
    label: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    description: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
    },
    checkbox: {
      width: 20,
      height: 20,
      borderRadius: theme.borderRadius.sm,
      borderWidth: 2,
      borderColor: theme.colors.border.strong,
      backgroundColor: theme.colors.surface.raised,
      justifyContent: 'center',
      alignItems: 'center',
    },
    checkboxChecked: {
      backgroundColor: theme.colors.interactive.default,
      borderColor: theme.colors.interactive.active,
    },
  }));
  return (
    <TouchableOpacity style={styles.container} onPress={onPress} activeOpacity={0.7}>
      <View style={styles.iconContainer}>{icon}</View>
      <View style={styles.textContainer}>
        <Text style={styles.label}>{label}</Text>
        <Text style={styles.description}>{description}</Text>
      </View>
      <View style={[styles.checkbox, checked && styles.checkboxChecked]}>
        {checked && <CheckIcon size={16} color={theme.colors.utility.white} weight={theme.icon.weights.bold} />}
      </View>
    </TouchableOpacity>
  );
}
