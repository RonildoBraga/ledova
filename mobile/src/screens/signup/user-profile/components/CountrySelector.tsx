import React, { useState } from 'react';
import { View, Text, TouchableOpacity, Modal, ScrollView } from 'react-native';
import { CaretDownIcon } from 'phosphor-react-native';
import type { CountryData } from '@ledova/shared-constants';
import { overlayColors } from '../../../../contexts';
import { useAppTheme, useThemedStyles } from '../../../../contexts';

interface CountrySelectorProps {
  countries: CountryData[];
  selectedCountry: CountryData;
  onCountryChange: (country: CountryData) => void;
  disabled?: boolean;
}

export function CountrySelector({
  countries,
  selectedCountry,
  onCountryChange,
  disabled = false,
}: CountrySelectorProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    selector: {
      backgroundColor: theme.colors.surface.tertiary,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderTopLeftRadius: theme.borderRadius.md,
      borderBottomLeftRadius: theme.borderRadius.md,
      borderTopRightRadius: 0,
      borderBottomRightRadius: 0,
      borderRightWidth: 0,
      height: 48,
      paddingLeft: 44,
      paddingRight: theme.spacing.sm,
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.xs,
    },
    selectorDisabled: {
      opacity: 0.5,
    },
    flag: {
      fontSize: theme.fontSize.xl,
    },
    modalOverlay: {
      flex: 1,
      backgroundColor: overlayColors.modal,
      justifyContent: 'center',
      alignItems: 'center',
    },
    modalContent: {
      backgroundColor: theme.colors.surface.raised,
      borderRadius: theme.borderRadius.lg,
      marginHorizontal: theme.spacing.lg,
      marginVertical: theme.spacing.xxxxl,
      maxHeight: '70%',
      minHeight: 400,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      width: '85%',
      overflow: 'hidden',
    },
    countryItem: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingHorizontal: theme.spacing.xl,
      paddingVertical: theme.spacing.lg,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.subtle,
    },
    countryFlag: {
      fontSize: theme.fontSize.xxl,
      marginRight: theme.spacing.md,
    },
    countryName: {
      fontSize: theme.fontSize.lg,
      color: theme.colors.text.primary,
      flex: 1,
      fontWeight: theme.fontWeight.medium,
    },
    countryPhoneCode: {
      fontSize: theme.fontSize.base,
      color: theme.colors.text.muted,
      fontWeight: theme.fontWeight.medium,
    },
  }));
  const [isOpen, setIsOpen] = useState(false);

  const handleCountrySelect = (country: CountryData) => {
    onCountryChange(country);
    setIsOpen(false);
  };

  return (
    <>
      <TouchableOpacity
        style={[styles.selector, disabled && styles.selectorDisabled]}
        onPress={() => !disabled && setIsOpen(true)}
        disabled={disabled}
      >
        <Text style={styles.flag}>{selectedCountry.flag}</Text>
        <CaretDownIcon
          size={theme.icon.sizes.md}
          color={theme.colors.text.subtle}
          weight={theme.icon.weights.regular}
        />
      </TouchableOpacity>

      <Modal visible={isOpen} transparent animationType="fade" onRequestClose={() => setIsOpen(false)}>
        <TouchableOpacity style={styles.modalOverlay} activeOpacity={1} onPress={() => setIsOpen(false)}>
          <View style={styles.modalContent}>
            <TouchableOpacity activeOpacity={1}>
              <ScrollView showsVerticalScrollIndicator={false}>
                {countries.map((country) => (
                  <TouchableOpacity
                    key={country.code}
                    style={styles.countryItem}
                    onPress={() => handleCountrySelect(country)}
                  >
                    <Text style={styles.countryFlag}>{country.flag}</Text>
                    <Text style={styles.countryName}>{country.name}</Text>
                    <Text style={styles.countryPhoneCode}>{country.phoneCode}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </TouchableOpacity>
          </View>
        </TouchableOpacity>
      </Modal>
    </>
  );
}
