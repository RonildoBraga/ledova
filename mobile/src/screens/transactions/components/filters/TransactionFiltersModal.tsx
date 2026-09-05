import React, { useState, useEffect, useRef } from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { Dropdown } from 'react-native-element-dropdown';
import { CurrencyBtcIcon, CurrencyEthIcon, CaretDownIcon, WalletIcon } from 'phosphor-react-native';
import { useAppTheme, useThemedStyles } from '../../../../contexts';
import { BLOCKCHAIN, formatWalletAddressShort } from '@ledova/shared';
import { CustomModal } from '../../../../components/modal';
import { DatePickerField } from '../../../../components/date-picker';
import { NumberField } from '../../../../components/number-field';
import type { TransactionQueryParams } from '../../useTransactions';
import type { Wallet } from '@ledova/shared';

interface TransactionFiltersModalProps {
  isOpen: boolean;
  filters: TransactionQueryParams;
  ethWallets: Wallet[];
  btcWallets: Wallet[];
  baseWallets: Wallet[];
  onClose: () => void;
  onUpdateFilters: (filters: TransactionQueryParams) => void;
  onApplyFilters: (filters: TransactionQueryParams) => void;
  onClearFilters: () => void;
}

type DirectionOption = 'all' | 'incoming' | 'outgoing';
type ChainOption = 'all' | typeof BLOCKCHAIN.BITCOIN | typeof BLOCKCHAIN.ETHEREUM | typeof BLOCKCHAIN.BASE;

export function TransactionFiltersModal({
  isOpen,
  filters,
  ethWallets,
  btcWallets,
  baseWallets,
  onClose,
  onUpdateFilters,
  onApplyFilters,
  onClearFilters,
}: TransactionFiltersModalProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    headerContainer: {
      alignItems: 'center',
      paddingVertical: theme.spacing.sm,
    },
    title: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      textAlign: 'center',
    },
    clearButton: {
      marginTop: theme.spacing.xs,
    },
    clearButtonText: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.interactive.active,
      textAlign: 'center',
    },
    filterSection: {
      marginTop: theme.spacing.md,
    },
    sectionTitle: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.muted,
      textTransform: 'uppercase',
      letterSpacing: 0.5,
      marginBottom: theme.spacing.sm,
    },
    buttonGroup: {
      flexDirection: 'row',
      gap: theme.spacing.xs,
    },
    filterButton: {
      flex: 1,
      paddingVertical: theme.spacing.sm,
      paddingHorizontal: theme.spacing.md,
      borderRadius: theme.borderRadius.md,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      backgroundColor: theme.colors.surface.tertiary,
      alignItems: 'center',
      justifyContent: 'center',
    },
    filterButtonActive: {
      backgroundColor: theme.colors.interactive.active,
      borderColor: theme.colors.interactive.active,
    },
    filterButtonContent: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.xs,
    },
    filterButtonText: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.secondary,
    },
    filterButtonTextActive: {
      color: theme.colors.text.primary,
    },
    iconActive: {
      opacity: 1,
    },
    iconInactive: {
      opacity: 0.6,
    },
    dropdown: {
      backgroundColor: theme.colors.surface.tertiary,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
      paddingHorizontal: theme.spacing.md,
      paddingVertical: theme.spacing.sm,
    },
    dropdownPlaceholder: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    dropdownSelectedText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.primary,
    },
    dropdownContainer: {
      backgroundColor: theme.colors.surface.raised,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
      marginTop: theme.spacing.xs,
    },
    dropdownItemContainer: {
      borderBottomWidth: 0,
    },
    dropdownItem: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.sm,
      paddingVertical: theme.spacing.sm,
      paddingHorizontal: theme.spacing.md,
    },
    dropdownItemText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.secondary,
    },
    dropdownLeftIcon: {
      marginRight: theme.spacing.sm,
    },
    rowFields: {
      flexDirection: 'row',
      gap: theme.spacing.md,
    },
    fieldHalf: {
      flex: 1,
    },
  }));
  const [localFilters, setLocalFilters] = useState<TransactionQueryParams>(filters);
  const [selectedDirection, setSelectedDirection] = useState<DirectionOption>('all');
  const [selectedChain, setSelectedChain] = useState<ChainOption>('all');
  const [selectedWallet, setSelectedWallet] = useState<string | undefined>();
  const [startDate, setStartDate] = useState<Date | undefined>();
  const [endDate, setEndDate] = useState<Date | undefined>();
  const prevIsOpenRef = useRef(isOpen);

  const allWallets = [...ethWallets, ...btcWallets, ...baseWallets];

  useEffect(() => {
    if (isOpen && !prevIsOpenRef.current) {
      setLocalFilters(filters);
      setSelectedDirection(filters.direction || 'all');
      setSelectedChain((filters.chain as ChainOption) || 'all');
      setSelectedWallet(filters.wallet);
      setStartDate(filters.start_date ? new Date(filters.start_date) : undefined);
      setEndDate(filters.end_date ? new Date(filters.end_date) : undefined);
    }
    prevIsOpenRef.current = isOpen;
  }, [isOpen, filters]);

  const hasActiveFilters =
    selectedDirection !== 'all' ||
    selectedChain !== 'all' ||
    !!selectedWallet ||
    !!localFilters.min_amount ||
    !!localFilters.max_amount ||
    !!startDate ||
    !!endDate;

  const formatDate = (date: Date) => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  const handleApply = () => {
    const updatedFilters: TransactionQueryParams = {
      ...localFilters,
      direction: selectedDirection !== 'all' ? selectedDirection : undefined,
      chain: selectedChain !== 'all' ? selectedChain : undefined,
      wallet: selectedWallet,
    };
    onUpdateFilters(updatedFilters);
    onApplyFilters(updatedFilters);
  };

  const handleClear = () => {
    setLocalFilters({});
    setSelectedDirection('all');
    setSelectedChain('all');
    setSelectedWallet(undefined);
    setStartDate(undefined);
    setEndDate(undefined);
    onClearFilters();
  };

  const handleClose = () => {
    setLocalFilters(filters);
    setSelectedDirection(filters.direction || 'all');
    setSelectedChain((filters.chain as ChainOption) || 'all');
    setSelectedWallet(filters.wallet);
    setStartDate(filters.start_date ? new Date(filters.start_date) : undefined);
    setEndDate(filters.end_date ? new Date(filters.end_date) : undefined);
    onClose();
  };

  const getWalletDisplayName = (wallet: Wallet) => {
    return wallet.name || formatWalletAddressShort(wallet.address);
  };

  const walletDropdownOptions = [
    { label: 'All Wallets', value: '', chain: '' },
    ...allWallets.map((wallet) => ({
      label: getWalletDisplayName(wallet),
      value: wallet.uuid,
      chain: wallet.chain,
    })),
  ];

  const directionOptions: { value: DirectionOption; label: string }[] = [
    { value: 'all', label: 'All' },
    { value: 'outgoing', label: 'Sent' },
    { value: 'incoming', label: 'Received' },
  ];

  const chainOptions: { value: ChainOption; label: string; icon?: React.ReactNode }[] = [
    { value: 'all', label: 'All' },
    {
      value: BLOCKCHAIN.BITCOIN,
      label: 'BTC',
      icon: <CurrencyBtcIcon size={14} weight={theme.icon.weights.bold} color="currentColor" />,
    },
    {
      value: BLOCKCHAIN.ETHEREUM,
      label: 'ETH',
      icon: <CurrencyEthIcon size={14} weight={theme.icon.weights.bold} color="currentColor" />,
    },
    {
      value: BLOCKCHAIN.BASE,
      label: 'BASE',
      icon: <CurrencyEthIcon size={14} weight={theme.icon.weights.bold} color="currentColor" />,
    },
  ];

  return (
    <CustomModal
      visible={isOpen}
      onClose={handleClose}
      showFooter={true}
      cancelLabel="Cancel"
      confirmLabel="Apply"
      onConfirm={handleApply}
    >
      <View style={styles.headerContainer}>
        <Text style={styles.title}>Filter Transactions</Text>
        {hasActiveFilters && (
          <TouchableOpacity onPress={handleClear} style={styles.clearButton}>
            <Text style={styles.clearButtonText}>Clear Filters</Text>
          </TouchableOpacity>
        )}
      </View>

      <View style={styles.filterSection}>
        <Text style={styles.sectionTitle}>Direction</Text>
        <View style={styles.buttonGroup}>
          {directionOptions.map((option) => (
            <TouchableOpacity
              key={option.value}
              style={[styles.filterButton, selectedDirection === option.value && styles.filterButtonActive]}
              onPress={() => setSelectedDirection(option.value)}
            >
              <Text
                style={[styles.filterButtonText, selectedDirection === option.value && styles.filterButtonTextActive]}
              >
                {option.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      <View style={styles.filterSection}>
        <Text style={styles.sectionTitle}>Chain</Text>
        <View style={styles.buttonGroup}>
          {chainOptions.map((option) => (
            <TouchableOpacity
              key={option.value}
              style={[styles.filterButton, selectedChain === option.value && styles.filterButtonActive]}
              onPress={() => setSelectedChain(option.value)}
            >
              <View style={styles.filterButtonContent}>
                {option.icon && (
                  <View style={selectedChain === option.value ? styles.iconActive : styles.iconInactive}>
                    {option.icon}
                  </View>
                )}
                <Text
                  style={[styles.filterButtonText, selectedChain === option.value && styles.filterButtonTextActive]}
                >
                  {option.label}
                </Text>
              </View>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {allWallets.length > 0 && (
        <View style={styles.filterSection}>
          <Text style={styles.sectionTitle}>Wallet</Text>
          <Dropdown
            style={styles.dropdown}
            placeholderStyle={styles.dropdownPlaceholder}
            selectedTextStyle={styles.dropdownSelectedText}
            containerStyle={styles.dropdownContainer}
            itemContainerStyle={styles.dropdownItemContainer}
            itemTextStyle={styles.dropdownItemText}
            activeColor={theme.colors.surface.tertiary}
            data={walletDropdownOptions}
            maxHeight={250}
            labelField="label"
            valueField="value"
            placeholder="All Wallets"
            value={selectedWallet || ''}
            onChange={(item) => setSelectedWallet(item.value || undefined)}
            renderLeftIcon={() => (
              <WalletIcon
                size={16}
                color={theme.colors.text.muted}
                weight={theme.icon.weights.regular}
                style={styles.dropdownLeftIcon}
              />
            )}
            renderRightIcon={() => (
              <CaretDownIcon size={16} color={theme.colors.text.muted} weight={theme.icon.weights.regular} />
            )}
            renderItem={(item) => (
              <View style={styles.dropdownItem}>
                {item.chain === BLOCKCHAIN.ETHEREUM || item.chain === BLOCKCHAIN.BASE ? (
                  <CurrencyEthIcon size={14} color={theme.colors.text.muted} weight={theme.icon.weights.regular} />
                ) : item.chain === BLOCKCHAIN.BITCOIN ? (
                  <CurrencyBtcIcon size={14} color={theme.colors.text.muted} weight={theme.icon.weights.regular} />
                ) : (
                  <WalletIcon size={14} color={theme.colors.text.muted} weight={theme.icon.weights.regular} />
                )}
                <Text style={styles.dropdownItemText}>{item.label}</Text>
              </View>
            )}
          />
        </View>
      )}

      <View style={styles.filterSection}>
        <Text style={styles.sectionTitle}>Amount Range</Text>
        <View style={styles.rowFields}>
          <View style={styles.fieldHalf}>
            <NumberField
              label="Min"
              value={localFilters.min_amount}
              onChange={(value) => setLocalFilters((prev) => ({ ...prev, min_amount: value }))}
              placeholder="0.00"
              minimumValue={0}
              maximumValue={localFilters.max_amount}
            />
          </View>
          <View style={styles.fieldHalf}>
            <NumberField
              label="Max"
              value={localFilters.max_amount}
              onChange={(value) => setLocalFilters((prev) => ({ ...prev, max_amount: value }))}
              placeholder="0.00"
              minimumValue={localFilters.min_amount || 0}
            />
          </View>
        </View>
      </View>

      <View style={styles.filterSection}>
        <Text style={styles.sectionTitle}>Date Range</Text>
        <View style={styles.rowFields}>
          <View style={styles.fieldHalf}>
            <DatePickerField
              label="Start"
              value={startDate}
              onChange={(date) => {
                setStartDate(date);
                setLocalFilters((prev) => ({
                  ...prev,
                  start_date: date ? formatDate(date) : undefined,
                }));
              }}
              maximumDate={endDate || new Date()}
            />
          </View>
          <View style={styles.fieldHalf}>
            <DatePickerField
              label="End"
              value={endDate}
              onChange={(date) => {
                setEndDate(date);
                setLocalFilters((prev) => ({
                  ...prev,
                  end_date: date ? formatDate(date) : undefined,
                }));
              }}
              minimumDate={startDate}
              maximumDate={new Date()}
            />
          </View>
        </View>
      </View>
    </CustomModal>
  );
}
