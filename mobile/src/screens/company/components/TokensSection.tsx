import React, { useState } from 'react';
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator } from 'react-native';
import { CoinIcon, PlusIcon, ArrowLeftIcon, ArrowRightIcon } from 'phosphor-react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { CustomModal } from '../../../components/modal';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import type { CompanyShareToken, TokenCreate, TokenStatus, TokenType } from '@ledova/shared';
import type { CompanyStackParamList } from '../../../navigation/CompanyStackNavigator';

const STATUS_LABELS: Record<TokenStatus, string> = {
  draft: 'Draft',
  deploying: 'Deploying',
  deployed: 'Deployed',
  paused: 'Paused',
};

const TOKEN_TYPE_LABELS: Record<TokenType, string> = {
  ordinary: 'Ordinary',
  preference: 'Preference',
  redeemable: 'Redeemable',
};

const TOKEN_TYPES = [
  { value: 'ordinary', label: 'Ordinary' },
  { value: 'preference', label: 'Preference' },
  { value: 'redeemable', label: 'Redeemable' },
];

function getStatusColors(theme: ReturnType<typeof useAppTheme>): Record<TokenStatus, { bg: string; text: string }> {
  return {
    draft: { bg: theme.colors.warning.default + '26', text: theme.colors.warning.light },
    deploying: { bg: theme.colors.brand.default + '26', text: theme.colors.brand.light },
    deployed: { bg: theme.colors.success.default + '26', text: theme.colors.success.light },
    paused: { bg: theme.colors.error.default + '26', text: theme.colors.error.light },
  };
}

interface TokensSectionProps {
  companyUuid?: string;
  tokens: CompanyShareToken[];
  totalCount: number;
  page: number;
  totalPages: number;
  isLoading: boolean;
  setPage: (page: number) => void;
  createToken: (data: TokenCreate) => Promise<unknown>;
  isCreating: boolean;
  createError: Error | null;
}

export function TokensSection({
  companyUuid,
  tokens,
  totalCount,
  page,
  totalPages,
  isLoading,
  setPage,
  createToken,
  isCreating,
  createError,
}: TokensSectionProps) {
  const theme = useAppTheme();
  const styles = useStyles();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newName, setNewName] = useState('');
  const [newSymbol, setNewSymbol] = useState('');
  const [newType, setNewType] = useState<TokenType>('ordinary');
  const [newSupply, setNewSupply] = useState('');

  const handleCreate = async () => {
    try {
      await createToken({
        company: companyUuid,
        name: newName,
        symbol: newSymbol.toUpperCase(),
        tokenType: newType,
        totalSupply: newSupply,
      });
      setShowCreateModal(false);
      setNewName('');
      setNewSymbol('');
      setNewType('ordinary');
      setNewSupply('');
    } catch {}
  };

  const isCreateValid =
    newName.trim() !== '' && newSymbol.trim() !== '' && newSupply.trim() !== '' && parseInt(newSupply) > 0;

  if (isLoading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="small" color={theme.colors.interactive.active} />
      </View>
    );
  }

  return (
    <>
      {tokens.length === 0 ? (
        <View style={styles.emptyState}>
          <CoinIcon size={32} color={theme.colors.text.muted} weight="regular" />
          <Text style={styles.emptyTitle}>{totalCount === 0 ? 'No Share Tokens Yet' : 'No Tokens Found'}</Text>
          <Text style={styles.emptySubtitle}>
            {totalCount === 0 ? 'Create your first share token to begin.' : 'Try adjusting your filter.'}
          </Text>
          {totalCount === 0 && (
            <TouchableOpacity style={styles.createButtonInline} onPress={() => setShowCreateModal(true)}>
              <PlusIcon size={16} color={theme.colors.utility.white} weight="bold" />
              <Text style={styles.createButtonText}>Create Share Token</Text>
            </TouchableOpacity>
          )}
        </View>
      ) : (
        <>
          {tokens.map((token: CompanyShareToken, index: number) => (
            <React.Fragment key={token.uuid}>
              <TokenRow token={token} />
              {index < tokens.length - 1 && <View style={styles.divider} />}
            </React.Fragment>
          ))}

          {totalCount > 10 && (
            <View style={styles.pagination}>
              <TouchableOpacity
                style={[styles.pageButton, page === 1 && styles.pageButtonDisabled]}
                onPress={() => setPage(Math.max(1, page - 1))}
                disabled={page === 1}
              >
                <ArrowLeftIcon size={14} color={page === 1 ? theme.colors.text.muted : theme.colors.text.primary} />
                <Text style={[styles.pageButtonText, page === 1 && styles.pageButtonTextDisabled]}>Prev</Text>
              </TouchableOpacity>
              <Text style={styles.pageInfo}>
                {page} / {totalPages}
              </Text>
              <TouchableOpacity
                style={[styles.pageButton, page === totalPages && styles.pageButtonDisabled]}
                onPress={() => setPage(Math.min(totalPages, page + 1))}
                disabled={page === totalPages}
              >
                <Text style={[styles.pageButtonText, page === totalPages && styles.pageButtonTextDisabled]}>Next</Text>
                <ArrowRightIcon
                  size={14}
                  color={page === totalPages ? theme.colors.text.muted : theme.colors.text.primary}
                />
              </TouchableOpacity>
            </View>
          )}
        </>
      )}

      <CustomModal
        visible={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        showFooter
        confirmLabel="Create Token"
        onConfirm={handleCreate}
        confirmDisabled={!isCreateValid || isCreating}
        confirmLoading={isCreating}
      >
        <View style={styles.formFields}>
          <Text style={styles.modalTitle}>Create Share Token</Text>
          {createError && (
            <View style={styles.errorBanner}>
              <Text style={styles.errorBannerText}>Failed to create token. Please try again.</Text>
            </View>
          )}
          <View style={styles.fieldContainer}>
            <Text style={styles.fieldLabel}>Token Name</Text>
            <TextInput
              style={styles.input}
              value={newName}
              onChangeText={setNewName}
              placeholder="e.g. Ordinary Shares"
              placeholderTextColor={theme.colors.text.muted}
            />
          </View>
          <View style={styles.fieldContainer}>
            <Text style={styles.fieldLabel}>Symbol</Text>
            <TextInput
              style={styles.input}
              value={newSymbol}
              onChangeText={(t) => setNewSymbol(t.toUpperCase())}
              placeholder="e.g. ORD"
              placeholderTextColor={theme.colors.text.muted}
              autoCapitalize="characters"
            />
          </View>
          <View style={styles.fieldContainer}>
            <Text style={styles.fieldLabel}>Type</Text>
            <View style={styles.typeRow}>
              {TOKEN_TYPES.map((t) => (
                <TouchableOpacity
                  key={t.value}
                  style={[styles.typeChip, newType === t.value && styles.typeChipSelected]}
                  onPress={() => setNewType(t.value as TokenType)}
                >
                  <Text style={[styles.typeChipText, newType === t.value && styles.typeChipTextSelected]}>
                    {t.label}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
          <View style={styles.fieldContainer}>
            <Text style={styles.fieldLabel}>Total Supply</Text>
            <TextInput
              style={styles.input}
              value={newSupply}
              onChangeText={setNewSupply}
              placeholder="e.g. 1000000"
              placeholderTextColor={theme.colors.text.muted}
              keyboardType="number-pad"
            />
          </View>
        </View>
      </CustomModal>
    </>
  );
}

function TokenRow({ token }: { token: CompanyShareToken }) {
  const theme = useAppTheme();
  const navigation = useNavigation<NativeStackNavigationProp<CompanyStackParamList>>();
  const styles = useThemedStyles((theme) => ({
    tokenRow: {
      flexDirection: 'row' as const,
      justifyContent: 'space-between' as const,
      alignItems: 'center' as const,
      paddingVertical: theme.spacing.sm,
      paddingHorizontal: theme.spacing.xs,
    },
    tokenInfo: { flex: 1, gap: theme.spacing.xs },
    tokenName: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    tokenMeta: { flexDirection: 'row' as const, gap: theme.spacing.sm },
    tokenSymbol: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
      fontFamily: 'monospace',
    },
    tokenType: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
    tokenStatus: {
      paddingHorizontal: theme.spacing.sm,
      paddingVertical: theme.spacing.xs,
      borderRadius: theme.borderRadius.full,
    },
    tokenStatusText: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.medium,
    },
  }));
  const statusColors = getStatusColors(theme);
  const statusColor = statusColors[token.status] || statusColors.draft;
  return (
    <TouchableOpacity
      style={styles.tokenRow}
      onPress={() => navigation.navigate('TokenDetail', { uuid: token.uuid, name: token.name })}
      activeOpacity={0.7}
    >
      <View style={styles.tokenInfo}>
        <Text style={styles.tokenName}>{token.name}</Text>
        <View style={styles.tokenMeta}>
          <Text style={styles.tokenSymbol}>{token.symbol}</Text>
          <Text style={styles.tokenType}>{TOKEN_TYPE_LABELS[token.tokenType] || token.tokenType}</Text>
        </View>
      </View>
      <View style={[styles.tokenStatus, { backgroundColor: statusColor.bg }]}>
        <Text style={[styles.tokenStatusText, { color: statusColor.text }]}>{STATUS_LABELS[token.status]}</Text>
      </View>
    </TouchableOpacity>
  );
}

function useStyles() {
  return useThemedStyles((theme) => ({
    centerContainer: {
      paddingVertical: theme.spacing.lg,
      alignItems: 'center' as const,
    },
    emptyState: {
      alignItems: 'center' as const,
      paddingVertical: theme.spacing.md,
      gap: theme.spacing.sm,
    },
    emptyTitle: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    emptySubtitle: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    createButtonInline: {
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      gap: theme.spacing.xs,
      backgroundColor: theme.colors.interactive.active,
      borderRadius: theme.borderRadius.md,
      paddingHorizontal: theme.spacing.lg,
      paddingVertical: theme.spacing.sm,
      marginTop: theme.spacing.sm,
    },
    createButtonText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.utility.white,
      fontWeight: theme.fontWeight.semibold,
    },
    divider: {
      height: 1,
      backgroundColor: theme.colors.border.default,
    },
    pagination: {
      flexDirection: 'row' as const,
      justifyContent: 'space-between' as const,
      alignItems: 'center' as const,
      paddingTop: theme.spacing.md,
      borderTopWidth: 1,
      borderTopColor: theme.colors.border.default,
      marginTop: theme.spacing.sm,
    },
    pageButton: {
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      gap: theme.spacing.xs,
      paddingVertical: theme.spacing.xs,
      paddingHorizontal: theme.spacing.sm,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
    },
    pageButtonDisabled: { opacity: 0.4 },
    pageButtonText: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.primary,
    },
    pageButtonTextDisabled: { color: theme.colors.text.muted },
    pageInfo: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
    formFields: { gap: theme.spacing.md },
    fieldContainer: { gap: theme.spacing.xs },
    fieldLabel: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    input: {
      backgroundColor: theme.colors.surface.tertiary,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
      paddingHorizontal: theme.spacing.md,
      paddingVertical: theme.spacing.sm,
      fontSize: theme.fontSize.base,
      color: theme.colors.text.primary,
    },
    modalTitle: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      marginBottom: theme.spacing.md,
    },
    typeRow: { flexDirection: 'row' as const, gap: theme.spacing.sm },
    typeChip: {
      flex: 1,
      paddingVertical: theme.spacing.sm,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
      alignItems: 'center' as const,
    },
    typeChipSelected: {
      borderColor: theme.colors.interactive.active,
      backgroundColor: theme.colors.interactive.active + '1A',
    },
    typeChipText: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.primary,
    },
    typeChipTextSelected: {
      color: theme.colors.interactive.active,
      fontWeight: theme.fontWeight.medium,
    },
    errorBanner: {
      backgroundColor: theme.colors.error.default + '1A',
      borderWidth: 1,
      borderColor: theme.colors.error.default + '33',
      borderRadius: theme.borderRadius.md,
      padding: theme.spacing.md,
    },
    errorBannerText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.status.error.text,
      textAlign: 'center' as const,
    },
  }));
}
