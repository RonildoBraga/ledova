import React, { useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  ActivityIndicator,
  TouchableOpacity,
  RefreshControl,
  TextInput,
  Alert,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';
import {
  CoinIcon,
  CopyIcon,
  CheckCircleIcon,
  UsersThreeIcon,
  ListBulletsIcon,
  TrendUpIcon,
  InfoIcon,
} from 'phosphor-react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type {
  TokenStatus,
  TokenType,
  TokenHolder,
  TokenIssuance,
  IssuanceStatus,
  CapitalIncreaseRequest,
  CapitalIncreaseStatus,
} from '@ledova/shared-types';
import { GradientBackground } from '../../components/GradientBackground';
import { PrimaryButton } from '../../components/buttons';
import { CustomModal } from '../../components/modal';
import { useAppTheme, useThemedStyles } from '../../contexts';
import { useTokenDetail } from './useTokenDetail';
import type { CompanyStackParamList } from '../../navigation/CompanyStackNavigator';

type Props = NativeStackScreenProps<CompanyStackParamList, 'TokenDetail'>;
type ActiveTab = 'shares' | 'holders' | 'issuances';

function getStatusColors(theme: ReturnType<typeof useAppTheme>): Record<TokenStatus, { bg: string; text: string }> {
  return {
    draft: { bg: theme.colors.warning.default + '26', text: theme.colors.warning.light },
    deploying: { bg: theme.colors.brand.default + '26', text: theme.colors.brand.light },
    deployed: { bg: theme.colors.success.default + '26', text: theme.colors.success.light },
    paused: { bg: theme.colors.error.default + '26', text: theme.colors.error.light },
  };
}

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

const ISSUANCE_STATUS_LABELS: Record<IssuanceStatus, string> = {
  pending: 'Pending',
  processing: 'Processing',
  completed: 'Completed',
  failed: 'Failed',
};

const CAPITAL_INCREASE_STATUS_LABELS: Record<CapitalIncreaseStatus, string> = {
  draft: 'Draft',
  submitted: 'Submitted',
  under_review: 'Under Review',
  approved: 'Approved',
  rejected: 'Rejected',
  executing: 'Executing',
  executed: 'Executed',
  failed: 'Failed',
};

function formatNumber(value: string | number): string {
  return Number(value).toLocaleString();
}

function truncateAddress(address: string): string {
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

export function TokenDetailScreen({ route }: Props) {
  const { uuid } = route.params;
  const theme = useAppTheme();
  const styles = useStyles();
  const {
    token,
    isLoading,
    holders,
    totalHolders,
    issuances,
    issuanceCount,
    capitalIncreases,
    capitalIncreaseCount,
    issueShares,
    isIssuing,
    resetIssueError,
    refetch,
  } = useTokenDetail(uuid);

  const [activeTab, setActiveTab] = useState<ActiveTab>('shares');
  const [refreshing, setRefreshing] = useState(false);
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [showInfoModal, setShowInfoModal] = useState(false);
  const [showIssueModal, setShowIssueModal] = useState(false);
  const [issueRecipient, setIssueRecipient] = useState('');
  const [issueAmount, setIssueAmount] = useState('');
  const [issueReason, setIssueReason] = useState('');

  const handleCopy = async (value: string, field: string) => {
    await Clipboard.setStringAsync(value);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const handleIssue = async () => {
    try {
      await issueShares({
        recipient: issueRecipient.trim(),
        amount: parseInt(issueAmount),
        reason: issueReason.trim() || undefined,
      });
      setShowIssueModal(false);
      setIssueRecipient('');
      setIssueAmount('');
      setIssueReason('');
      Alert.alert('Request Submitted', 'Your issuance request has been submitted for review by operations.');
    } catch {
      Alert.alert('Error', 'Failed to submit issuance request. Please try again.');
    }
  };

  const handleCloseIssueModal = () => {
    setShowIssueModal(false);
    setIssueRecipient('');
    setIssueAmount('');
    setIssueReason('');
    resetIssueError();
  };

  const isIssueValid =
    issueRecipient.trim().startsWith('0x') && issueRecipient.trim().length === 42 && parseInt(issueAmount) > 0;

  const handleRefresh = React.useCallback(async () => {
    setRefreshing(true);
    await refetch();
    setRefreshing(false);
  }, [refetch]);

  if (isLoading) {
    return (
      <GradientBackground>
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={theme.colors.interactive.active} />
        </View>
      </GradientBackground>
    );
  }

  if (!token) {
    return (
      <GradientBackground>
        <View style={styles.centered}>
          <CoinIcon size={48} color={theme.colors.text.muted} weight="regular" />
          <Text style={styles.emptyText}>Token not found.</Text>
        </View>
      </GradientBackground>
    );
  }

  const statusColors = getStatusColors(theme);
  const statusColor = statusColors[token.status];
  const isDeployed = token.status === 'deployed';

  return (
    <GradientBackground>
      <ScrollView
        style={styles.container}
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor={theme.colors.text.muted} />
        }
      >
        {/* Compact Token Header */}
        <View style={styles.headerCard}>
          <View style={styles.headerRow}>
            <View style={styles.headerIcon}>
              <CoinIcon size={22} color={theme.colors.text.primary} weight="regular" />
            </View>
            <View style={styles.headerInfo}>
              <Text style={styles.tokenName} numberOfLines={1}>
                {token.name}
              </Text>
              <Text style={styles.tokenMeta} numberOfLines={1}>
                {token.symbol} · {TOKEN_TYPE_LABELS[token.tokenType]}
              </Text>
            </View>
            <View style={[styles.statusBadge, { backgroundColor: statusColor.bg }]}>
              <Text style={[styles.statusText, { color: statusColor.text }]}>{STATUS_LABELS[token.status]}</Text>
            </View>
            <TouchableOpacity style={styles.infoButton} onPress={() => setShowInfoModal(true)} activeOpacity={0.7}>
              <InfoIcon size={18} color={theme.colors.interactive.active} weight="regular" />
            </TouchableOpacity>
          </View>
        </View>

        {/* Stat Tabs */}
        <View style={styles.statsRow}>
          <StatTab
            icon={<CoinIcon />}
            label="Shares"
            value={formatNumber(token.totalSupply)}
            active={activeTab === 'shares'}
            onPress={() => setActiveTab('shares')}
          />
          <StatTab
            icon={<UsersThreeIcon />}
            label="Holders"
            value={String(totalHolders)}
            active={activeTab === 'holders'}
            onPress={() => setActiveTab('holders')}
          />
          <StatTab
            icon={<ListBulletsIcon />}
            label="Issuances"
            value={String(issuanceCount)}
            active={activeTab === 'issuances'}
            onPress={() => setActiveTab('issuances')}
          />
        </View>

        {/* Dynamic Content */}
        <View style={styles.contentCard}>
          {activeTab === 'shares' && (
            <SharesContent
              token={token}
              capitalIncreases={capitalIncreases}
              capitalIncreaseCount={capitalIncreaseCount}
              styles={styles}
              theme={theme}
            />
          )}
          {activeTab === 'holders' && (
            <HoldersContent
              holders={holders}
              isDeployed={isDeployed}
              styles={styles}
              theme={theme}
              copiedField={copiedField}
              onCopy={handleCopy}
            />
          )}
          {activeTab === 'issuances' && (
            <IssuancesContent
              issuances={issuances}
              styles={styles}
              theme={theme}
              copiedField={copiedField}
              onCopy={handleCopy}
            />
          )}
        </View>

        {/* Request Issuance Button */}
        {isDeployed && (
          <PrimaryButton onPress={() => setShowIssueModal(true)} fullWidth>
            Request Issuance
          </PrimaryButton>
        )}
      </ScrollView>

      {/* Token Info Modal */}
      <CustomModal visible={showInfoModal} onClose={() => setShowInfoModal(false)}>
        <View style={styles.modalContent}>
          <Text style={styles.modalTitle}>Token Details</Text>
          <ModalInfoRow label="Name" value={token.name} />
          <ModalInfoRow label="Symbol" value={token.symbol} />
          <ModalInfoRow label="Type" value={TOKEN_TYPE_LABELS[token.tokenType]} />
          <ModalInfoRow label="Status" value={STATUS_LABELS[token.status]} />
          <ModalInfoRow label="Authorized Shares" value={formatNumber(token.totalSupply)} />
          <ModalInfoRow label="Decimals" value={String(token.decimals)} />
          <ModalInfoRow label="Transferable" value={token.isTransferable ? 'Yes' : 'No'} />
          <ModalInfoRow label="Divisible" value={token.isDivisible ? 'Yes' : 'No'} />
          {token.contractAddress && (
            <TouchableOpacity onPress={() => handleCopy(token.contractAddress!, 'contract')}>
              <ModalInfoRow
                label="Contract"
                value={truncateAddress(token.contractAddress)}
                icon={
                  copiedField === 'contract' ? (
                    <CheckCircleIcon size={14} color={theme.colors.status.success.icon} />
                  ) : (
                    <CopyIcon size={14} color={theme.colors.text.muted} />
                  )
                }
              />
            </TouchableOpacity>
          )}
          {token.deployedAt && (
            <ModalInfoRow label="Deployed" value={new Date(token.deployedAt).toLocaleDateString()} />
          )}
        </View>
      </CustomModal>

      {/* Request Issuance Modal */}
      <CustomModal
        visible={showIssueModal}
        onClose={handleCloseIssueModal}
        showFooter
        confirmLabel={isIssuing ? 'Submitting...' : 'Submit Request'}
        onConfirm={handleIssue}
        confirmDisabled={!isIssueValid}
        confirmLoading={isIssuing}
        onCancel={handleCloseIssueModal}
      >
        <View style={styles.modalContent}>
          <Text style={styles.modalTitle}>Request Issuance</Text>
          <Text style={styles.modalSubtitle}>Request {token.symbol} shares to be issued to a whitelisted wallet</Text>
          <View style={styles.fieldContainer}>
            <Text style={styles.fieldLabel}>Recipient Address</Text>
            <TextInput
              value={issueRecipient}
              onChangeText={setIssueRecipient}
              placeholder="0x..."
              placeholderTextColor={theme.colors.text.muted}
              style={styles.fieldInput}
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>
          <View style={styles.fieldContainer}>
            <Text style={styles.fieldLabel}>Amount</Text>
            <TextInput
              value={issueAmount}
              onChangeText={setIssueAmount}
              placeholder="Number of shares"
              placeholderTextColor={theme.colors.text.muted}
              style={styles.fieldInput}
              keyboardType="number-pad"
            />
          </View>
          <View style={styles.fieldContainer}>
            <Text style={styles.fieldLabel}>Reason (optional)</Text>
            <TextInput
              value={issueReason}
              onChangeText={setIssueReason}
              placeholder="e.g. Investment round"
              placeholderTextColor={theme.colors.text.muted}
              style={styles.fieldInput}
            />
          </View>
        </View>
      </CustomModal>
    </GradientBackground>
  );
}

// --- Tab Content Components ---

function SharesContent({
  token,
  capitalIncreases,
  capitalIncreaseCount,
  styles,
  theme,
}: {
  token: { totalSupply: string; decimals: number; isTransferable: boolean; isDivisible: boolean };
  capitalIncreases: CapitalIncreaseRequest[];
  capitalIncreaseCount: number;
  styles: ReturnType<typeof useStyles>;
  theme: ReturnType<typeof useAppTheme>;
}) {
  return (
    <View style={styles.tabContent}>
      <ContentRow label="Authorized Shares" value={formatNumber(token.totalSupply)} styles={styles} />
      <ContentRow label="Transferable" value={token.isTransferable ? 'Yes' : 'No'} styles={styles} />
      <ContentRow
        label="Divisible"
        value={token.isDivisible ? 'Yes' : 'No'}
        styles={styles}
        isLast={capitalIncreaseCount === 0}
      />
      {capitalIncreaseCount > 0 && (
        <>
          <View style={styles.sectionDivider}>
            <TrendUpIcon size={14} color={theme.colors.text.muted} weight="regular" />
            <Text style={styles.sectionLabel}>Capital Increases ({capitalIncreaseCount})</Text>
          </View>
          {capitalIncreases.map((request, index) => (
            <CapitalIncreaseRow
              key={request.uuid}
              request={request}
              styles={styles}
              theme={theme}
              isLast={index === capitalIncreases.length - 1}
            />
          ))}
        </>
      )}
    </View>
  );
}

function HoldersContent({
  holders,
  isDeployed,
  styles,
  theme,
  copiedField,
  onCopy,
}: {
  holders: TokenHolder[];
  isDeployed: boolean;
  styles: ReturnType<typeof useStyles>;
  theme: ReturnType<typeof useAppTheme>;
  copiedField: string | null;
  onCopy: (value: string, field: string) => void;
}) {
  if (!isDeployed) {
    return (
      <View style={styles.emptyState}>
        <UsersThreeIcon size={32} color={theme.colors.text.muted} weight="regular" />
        <Text style={styles.emptyTitle}>Not Deployed</Text>
        <Text style={styles.emptySubtitle}>Deploy the token to track holders.</Text>
      </View>
    );
  }

  if (holders.length === 0) {
    return (
      <View style={styles.emptyState}>
        <UsersThreeIcon size={32} color={theme.colors.text.muted} weight="regular" />
        <Text style={styles.emptyTitle}>No Holders</Text>
        <Text style={styles.emptySubtitle}>Request issuance to add holders.</Text>
      </View>
    );
  }

  return (
    <>
      {holders.map((holder, index) => (
        <View key={holder.address} style={[styles.holderRow, index < holders.length - 1 && styles.rowBorder]}>
          <View style={styles.holderLeft}>
            <TouchableOpacity style={styles.copyRow} onPress={() => onCopy(holder.address, holder.address)}>
              <Text style={styles.holderName}>{holder.name || truncateAddress(holder.address)}</Text>
              {copiedField === holder.address ? (
                <CheckCircleIcon size={14} color={theme.colors.status.success.icon} />
              ) : (
                <CopyIcon size={14} color={theme.colors.text.muted} />
              )}
            </TouchableOpacity>
            {holder.name && <Text style={styles.holderAddress}>{truncateAddress(holder.address)}</Text>}
          </View>
          <View style={styles.holderRight}>
            <Text style={styles.holderBalance}>{formatNumber(holder.balance)}</Text>
            <Text style={styles.holderPercentage}>{holder.percentage.toFixed(1)}%</Text>
          </View>
        </View>
      ))}
    </>
  );
}

function IssuancesContent({
  issuances,
  styles,
  theme,
  copiedField,
  onCopy,
}: {
  issuances: TokenIssuance[];
  styles: ReturnType<typeof useStyles>;
  theme: ReturnType<typeof useAppTheme>;
  copiedField: string | null;
  onCopy: (value: string, field: string) => void;
}) {
  if (issuances.length === 0) {
    return (
      <View style={styles.emptyState}>
        <ListBulletsIcon size={32} color={theme.colors.text.muted} weight="regular" />
        <Text style={styles.emptyTitle}>No Issuances</Text>
        <Text style={styles.emptySubtitle}>Request issuance to see history here.</Text>
      </View>
    );
  }

  return (
    <>
      {issuances.map((issuance, index) => {
        const statusColor = getIssuanceStatusColor(issuance.status, theme);
        const field = `issuance-${issuance.uuid}`;
        return (
          <View key={issuance.uuid} style={[styles.issuanceRow, index < issuances.length - 1 && styles.rowBorder]}>
            <View style={styles.issuanceTop}>
              <View style={styles.issuanceLeft}>
                <TouchableOpacity style={styles.copyRow} onPress={() => onCopy(issuance.recipientAddress, field)}>
                  <Text style={styles.issuanceName}>
                    {issuance.recipientName || truncateAddress(issuance.recipientAddress)}
                  </Text>
                  {copiedField === field ? (
                    <CheckCircleIcon size={14} color={theme.colors.status.success.icon} />
                  ) : (
                    <CopyIcon size={14} color={theme.colors.text.muted} />
                  )}
                </TouchableOpacity>
              </View>
              <Text style={styles.issuanceAmount}>+{formatNumber(issuance.amount)}</Text>
            </View>
            <View style={styles.issuanceBottom}>
              <Text style={styles.issuanceDate}>{new Date(issuance.createdAt).toLocaleDateString()}</Text>
              <Text style={styles.issuanceType}>{issuance.issuanceTypeDisplay}</Text>
              <View style={[styles.statusBadgeSm, { backgroundColor: statusColor.bg }]}>
                <Text style={[styles.statusTextSm, { color: statusColor.text }]}>
                  {ISSUANCE_STATUS_LABELS[issuance.status]}
                </Text>
              </View>
            </View>
          </View>
        );
      })}
    </>
  );
}

// --- Sub-components ---

function ModalInfoRow({ label, value, icon }: { label: string; value: string; icon?: React.ReactNode }) {
  const styles = useThemedStyles((theme) => ({
    row: {
      flexDirection: 'row' as const,
      justifyContent: 'space-between' as const,
      alignItems: 'center' as const,
      paddingVertical: 6,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.subtle,
    },
    label: { fontSize: theme.fontSize.sm, color: theme.colors.text.muted },
    valueRow: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 4 },
    value: { fontSize: theme.fontSize.sm, fontWeight: '500' as const, color: theme.colors.text.primary },
  }));

  return (
    <View style={styles.row}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.valueRow}>
        <Text style={styles.value}>{value}</Text>
        {icon}
      </View>
    </View>
  );
}

function ContentRow({
  label,
  value,
  styles,
  isLast,
}: {
  label: string;
  value: string;
  styles: ReturnType<typeof useStyles>;
  isLast?: boolean;
}) {
  return (
    <View style={[styles.contentRow, !isLast && styles.rowBorder]}>
      <Text style={styles.contentLabel}>{label}</Text>
      <Text style={styles.contentValue}>{value}</Text>
    </View>
  );
}

function StatTab({
  icon,
  label,
  value,
  active,
  onPress,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  active: boolean;
  onPress: () => void;
}) {
  const theme = useAppTheme();
  const styles = useThemedStyles((t) => ({
    card: {
      flex: 1,
      backgroundColor: t.colors.surface.raised,
      borderRadius: t.borderRadius.md,
      borderWidth: 1.5,
      borderColor: t.colors.border.default,
      padding: t.spacing.sm,
      alignItems: 'center' as const,
      gap: 2,
    },
    cardActive: {
      borderColor: t.colors.interactive.active,
      backgroundColor: t.colors.interactive.active + '0D',
    },
    value: {
      fontSize: t.fontSize.sm,
      fontWeight: t.fontWeight.bold as '700',
      color: t.colors.text.primary,
    },
    valueActive: { color: t.colors.interactive.active },
    label: { fontSize: t.fontSize.xs, color: t.colors.text.muted },
    labelActive: { color: t.colors.interactive.active },
  }));

  const styledIcon =
    icon && React.isValidElement(icon)
      ? React.cloneElement(icon as React.ReactElement<Record<string, unknown>>, {
          size: 14,
          color: active ? theme.colors.interactive.active : theme.colors.text.muted,
          weight: 'regular',
        })
      : icon;

  return (
    <TouchableOpacity style={[styles.card, active && styles.cardActive]} onPress={onPress} activeOpacity={0.7}>
      {styledIcon}
      <Text style={[styles.value, active && styles.valueActive]}>{value}</Text>
      <Text style={[styles.label, active && styles.labelActive]}>{label}</Text>
    </TouchableOpacity>
  );
}

function CapitalIncreaseRow({
  request,
  styles,
  theme,
  isLast,
}: {
  request: CapitalIncreaseRequest;
  styles: ReturnType<typeof useStyles>;
  theme: ReturnType<typeof useAppTheme>;
  isLast: boolean;
}) {
  const statusColor = getCapitalIncreaseStatusColor(request.status, theme);
  return (
    <View style={[styles.capitalRow, !isLast && styles.rowBorder]}>
      <View style={styles.capitalTop}>
        <Text style={[styles.capitalShares, { color: theme.colors.success.light }]}>
          +{request.additionalShares.toLocaleString()}
        </Text>
        <View style={[styles.statusBadgeSm, { backgroundColor: statusColor.bg }]}>
          <Text style={[styles.statusTextSm, { color: statusColor.text }]}>
            {CAPITAL_INCREASE_STATUS_LABELS[request.status]}
          </Text>
        </View>
      </View>
      <Text style={styles.capitalMeta}>
        New total: {request.newAuthorizedTotal.toLocaleString()}
        {request.dilutionPercentage !== null ? ` · Dilution: ${request.dilutionPercentage}%` : ''}
      </Text>
      <Text style={styles.capitalDate}>{new Date(request.createdAt).toLocaleDateString()}</Text>
    </View>
  );
}

// --- Helpers ---

function getIssuanceStatusColor(
  status: IssuanceStatus,
  theme: ReturnType<typeof useAppTheme>,
): { bg: string; text: string } {
  switch (status) {
    case 'completed':
      return { bg: theme.colors.success.default + '26', text: theme.colors.success.light };
    case 'failed':
      return { bg: theme.colors.error.default + '26', text: theme.colors.error.light };
    case 'processing':
      return { bg: theme.colors.info.default + '26', text: theme.colors.info.light };
    case 'pending':
      return { bg: theme.colors.warning.default + '26', text: theme.colors.warning.light };
  }
}

function getCapitalIncreaseStatusColor(
  status: CapitalIncreaseStatus,
  theme: ReturnType<typeof useAppTheme>,
): { bg: string; text: string } {
  switch (status) {
    case 'executed':
    case 'approved':
      return { bg: theme.colors.success.default + '26', text: theme.colors.success.light };
    case 'rejected':
    case 'failed':
      return { bg: theme.colors.error.default + '26', text: theme.colors.error.light };
    case 'submitted':
    case 'under_review':
    case 'executing':
      return { bg: theme.colors.info.default + '26', text: theme.colors.info.light };
    case 'draft':
      return { bg: theme.colors.warning.default + '26', text: theme.colors.warning.light };
  }
}

// --- Styles ---

function useStyles() {
  return useThemedStyles((theme) => ({
    container: { flex: 1 },
    scrollContent: {
      padding: theme.spacing.md,
      gap: theme.spacing.md,
      paddingBottom: theme.spacing.xl,
    },
    centered: {
      flex: 1,
      justifyContent: 'center' as const,
      alignItems: 'center' as const,
      gap: theme.spacing.sm,
    },
    emptyText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center' as const,
    },
    // Header
    headerCard: {
      backgroundColor: theme.colors.surface.raised,
      borderRadius: theme.borderRadius.md,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      padding: theme.spacing.md,
    },
    headerRow: {
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      gap: theme.spacing.sm,
    },
    headerIcon: {
      width: 40,
      height: 40,
      borderRadius: 20,
      backgroundColor: theme.colors.surface.tertiary,
      alignItems: 'center' as const,
      justifyContent: 'center' as const,
    },
    headerInfo: { flex: 1, gap: 2 },
    tokenName: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.bold,
      color: theme.colors.text.primary,
    },
    tokenMeta: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
    statusBadge: {
      paddingHorizontal: 8,
      paddingVertical: 2,
      borderRadius: 10,
    },
    statusText: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.semibold,
    },
    infoButton: {
      width: 36,
      height: 36,
      borderRadius: 18,
      backgroundColor: theme.colors.surface.tertiary,
      alignItems: 'center' as const,
      justifyContent: 'center' as const,
    },
    // Stats
    statsRow: {
      flexDirection: 'row' as const,
      gap: theme.spacing.sm,
    },
    // Content card
    contentCard: {
      backgroundColor: theme.colors.surface.raised,
      borderRadius: theme.borderRadius.md,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      padding: theme.spacing.sm,
    },
    tabContent: {},
    // Content rows
    contentRow: {
      flexDirection: 'row' as const,
      justifyContent: 'space-between' as const,
      alignItems: 'center' as const,
      paddingHorizontal: theme.spacing.xs,
      paddingVertical: theme.spacing.sm,
    },
    contentLabel: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    contentValue: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    rowBorder: {
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.default,
    },
    // Section divider (within content)
    sectionDivider: {
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      gap: theme.spacing.xs,
      paddingVertical: theme.spacing.sm,
      paddingHorizontal: theme.spacing.xs,
      marginTop: theme.spacing.xs,
    },
    sectionLabel: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.muted,
      textTransform: 'uppercase' as const,
      letterSpacing: 0.5,
    },
    // Empty states
    emptyState: {
      alignItems: 'center' as const,
      paddingVertical: theme.spacing.xl,
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
    // Holders
    holderRow: {
      flexDirection: 'row' as const,
      justifyContent: 'space-between' as const,
      alignItems: 'center' as const,
      paddingHorizontal: theme.spacing.xs,
      paddingVertical: theme.spacing.sm,
    },
    holderLeft: { flex: 1, marginRight: theme.spacing.sm },
    copyRow: {
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      gap: theme.spacing.xs,
    },
    holderName: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.primary,
    },
    holderAddress: {
      fontSize: theme.fontSize.xs,
      fontFamily: 'monospace',
      color: theme.colors.text.muted,
      marginTop: 2,
    },
    holderRight: { alignItems: 'flex-end' as const },
    holderBalance: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    holderPercentage: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
    // Issuances
    issuanceRow: {
      paddingHorizontal: theme.spacing.xs,
      paddingVertical: theme.spacing.sm,
      gap: theme.spacing.xs,
    },
    issuanceTop: {
      flexDirection: 'row' as const,
      justifyContent: 'space-between' as const,
      alignItems: 'center' as const,
    },
    issuanceLeft: { flex: 1, marginRight: theme.spacing.sm },
    issuanceName: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.primary,
    },
    issuanceAmount: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.success.light,
    },
    issuanceBottom: {
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      gap: theme.spacing.sm,
    },
    issuanceDate: { fontSize: theme.fontSize.xs, color: theme.colors.text.muted },
    issuanceType: { fontSize: theme.fontSize.xs, color: theme.colors.text.muted },
    statusBadgeSm: {
      paddingHorizontal: 6,
      paddingVertical: 2,
      borderRadius: theme.borderRadius.full,
    },
    statusTextSm: {
      fontSize: 10,
      fontWeight: theme.fontWeight.semibold,
    },
    // Capital increases
    capitalRow: {
      paddingHorizontal: theme.spacing.xs,
      paddingVertical: theme.spacing.sm,
      gap: 2,
    },
    capitalTop: {
      flexDirection: 'row' as const,
      justifyContent: 'space-between' as const,
      alignItems: 'center' as const,
    },
    capitalShares: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
    },
    capitalMeta: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
    capitalDate: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
    // Modal
    modalContent: { gap: theme.spacing.md },
    modalTitle: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.bold,
      color: theme.colors.text.primary,
    },
    modalSubtitle: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    fieldContainer: { gap: 4 },
    fieldLabel: { fontSize: theme.fontSize.sm, color: theme.colors.text.muted },
    fieldInput: {
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
      backgroundColor: theme.colors.surface.tertiary,
      paddingHorizontal: theme.spacing.sm,
      paddingVertical: theme.spacing.xs,
      color: theme.colors.text.primary,
      fontSize: theme.fontSize.sm,
    },
  }));
}
