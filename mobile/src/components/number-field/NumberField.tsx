import React from 'react';
import { View, Text, TouchableOpacity, TextInput } from 'react-native';
import { HashIcon } from 'phosphor-react-native';
import { useAppTheme, useThemedStyles } from '../../contexts';

interface NumberFieldProps {
  label: string;
  value?: number;
  onChange: (value: number | undefined) => void;
  placeholder?: string;
  minimumValue?: number;
  maximumValue?: number;
}

export function NumberField({
  label,
  value,
  onChange,
  placeholder = '0.00',
  minimumValue,
  maximumValue,
}: NumberFieldProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      gap: theme.spacing.xs,
    },
    label: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.subtle,
    },
    inputContainer: {
      backgroundColor: theme.colors.surface.tertiary,
      borderColor: theme.colors.border.default,
      borderWidth: 1,
      borderRadius: theme.borderRadius.md,
      paddingHorizontal: theme.spacing.md,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      height: 56,
    },
    input: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.primary,
      fontWeight: theme.fontWeight.medium,
      flex: 1,
    },
    clearButton: {
      alignSelf: 'flex-start',
    },
    clearButtonText: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.interactive.active,
    },
  }));
  const [inputText, setInputText] = React.useState<string>('');

  React.useEffect(() => {
    if (value !== undefined) {
      setInputText(value.toString());
    } else {
      setInputText('');
    }
  }, [value]);

  const handleClear = () => {
    setInputText('');
    onChange(undefined);
  };

  const handleChangeText = (text: string) => {
    if (text === '') {
      setInputText('');
      onChange(undefined);
      return;
    }

    const validPattern = /^-?\d*\.?\d*$/;
    if (validPattern.test(text)) {
      setInputText(text);

      const numValue = parseFloat(text);
      if (!isNaN(numValue)) {
        onChange(numValue);
      }
    }
  };

  const handleBlur = () => {
    const numValue = parseFloat(inputText);

    if (isNaN(numValue) || inputText === '') {
      setInputText('');
      onChange(undefined);
      return;
    }

    let finalValue = numValue;
    if (minimumValue !== undefined && numValue < minimumValue) {
      finalValue = minimumValue;
    }
    if (maximumValue !== undefined && numValue > maximumValue) {
      finalValue = maximumValue;
    }

    setInputText(finalValue.toString());
    onChange(finalValue);
  };

  return (
    <View style={styles.container}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.inputContainer}>
        <TextInput
          style={styles.input}
          value={inputText}
          onChangeText={handleChangeText}
          onBlur={handleBlur}
          keyboardType="decimal-pad"
          placeholder={placeholder}
          placeholderTextColor={theme.colors.text.muted}
          selectTextOnFocus
        />
        <HashIcon size={theme.icon.sizes.md} color={theme.colors.text.muted} weight={theme.icon.weights.regular} />
      </View>

      {inputText !== '' && (
        <TouchableOpacity onPress={handleClear} style={styles.clearButton}>
          <Text style={styles.clearButtonText}>Clear</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}
