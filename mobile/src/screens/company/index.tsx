import React, { useState, useCallback } from 'react';
import { View, Text, ScrollView, RefreshControl, TouchableOpacity, ActivityIndicator, TextInput } from 'react-native';
import { BuildingsIcon, CoinIcon, UsersThreeIcon, ClockIcon, WarningIcon } from 'phosphor-react-native';
import { GradientBackground } from '../../components/GradientBackground';
import { PrimaryButton } from '../../components/buttons';
import { CustomModal } from '../../components/modal';
import { useCompanyProfile } from '../../hooks/useCompanyProfile';
import { useCompanyTokensList, useCompanyShareholders } from '../../hooks/useCompanyTokens';
import { useAppTheme, useThemedStyles } from '../../contexts';
import { TokensSection } from './components/TokensSection';
import { ShareholdersSection } from './components/ShareholdersSection';
import type { CompanyStatus, CompanyUpdate } from '@ledova/shared-types';

type ActiveTab = 'tokens' | 'shareholders' | 'pending';

const STATUS_LABELS: Record<CompanyStatus, string> = {
  draft: 'Draft',
  submitted: 'Submitted',
  review: 'Under Review',
  info_required: 'Info Required',
  approved: 'Approved',
  active: 'Active',
  warning: 'Warning',
  suspended: 'Suspended',
  delisted: 'Delisted',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
};

function getStatusColors(theme: ReturnType<typeof useAppTheme>): Record<CompanyStatus, { bg: string; text: string }> {
  return {
    draft: { bg: theme.colors.surface.tertiary, text: theme.colors.text.muted },
    submitted: { bg: theme.colors.info.default + '26', text: theme.colors.info.light },
    review: { bg: theme.colors.info.default + '26', text: theme.colors.info.light },
    info_required: { bg: theme.colors.warning.default + '26', text: theme.colors.warning.light },
    approved: { bg: theme.colors.success.default + '26', text: theme.colors.success.light },
    active: { bg: theme.colors.success.default + '26', text: theme.colors.success.light },
    warning: { bg: theme.colors.warning.default + '26', text: theme.colors.warning.light },
    suspended: { bg: theme.colors.error.default + '26', text: theme.colors.error.light },
    delisted: { bg: theme.colors.error.default + '26', text: theme.colors.error.light },
    rejected: { bg: theme.colors.error.default + '26', text: theme.colors.error.light },
    withdrawn: { bg: theme.colors.surface.tertiary, text: theme.colors.text.muted },
  };
}

export function CompanyScreen() {
  const theme = useAppTheme();
  const styles = useStyles();
  const { company, stats, isLoading, error, refetch, updateCompany, isUpdating } = useCompanyProfile();
  const tokensHook = useCompanyTokensList();
  const shareholdersHook = useCompanyShareholders();

  const [activeTab, setActiveTab] = useState<ActiveTab>('tokens');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [formData, setFormData] = useState<CompanyUpdate>({});

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      await Promise.all([refetch(), tokensHook.refetch(), shareholdersHook.refetch()]);
    } finally {
      setIsRefreshing(false);
    }
  }, [refetch, tokensHook.refetch, shareholdersHook.refetch]);

  const handleOpenEdit = () => {
    if (!company) return;
    setFormData({
      name: company.name || '',
      tradingName: company.tradingName || '',
      addressLine1: company.addressLine1 || '',
      addressLine2: company.addressLine2 || '',
      city: company.city || '',
      state: company.state || '',
      postcode: company.postcode || '',
      phone: company.phone || '',
    });
    setShowEditModal(true);
  };

  const handleSave = async () => {
    try {
      await updateCompany(formData);
      setShowEditModal(false);
      setFormData({});
    } catch {
      // Error handled by hook
    }
  };

  const updateField = (field: keyof CompanyUpdate, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  if (isLoading && !company) {
    return (
      <GradientBackground>
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={theme.colors.interactive.active} />
        </View>
      </GradientBackground>
    );
  }

  if (error && !company) {
    return (
      <GradientBackground>
        <View style={styles.centered}>
          <WarningIcon size={48} color={theme.colors.status.error.text} weight="regular" />
          <Text style={styles.errorText}>Unable to load company</Text>
          <TouchableOpacity onPress={handleRefresh}>
            <Text style={styles.retryText}>Try Again</Text>
          </TouchableOpacity>
        </View>
      </GradientBackground>
    );
  }

  if (!company) {
    return (
      <GradientBackground>
        <View style={styles.centered}>
          <BuildingsIcon size={48} color={theme.colors.text.muted} weight="regular" />
          <Text style={styles.errorText}>No Company Registered</Text>
          <Text style={styles.noCompanyText}>
            Your account does not have a company profile yet. Contact support to set up your company.
          </Text>
        </View>
      </GradientBackground>
    );
  }

  const statusColors = getStatusColors(theme);
  const statusColor = statusColors[company.status as CompanyStatus] || statusColors.draft;

  return (
    <GradientBackground>
      <ScrollView
        style={styles.container}
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={handleRefresh}
            tintColor={theme.colors.interactive.active}
          />
        }
      >
        {/* Compact Company Header */}
        <View style={styles.headerCard}>
          <View style={styles.headerRow}>
            <View style={styles.headerIcon}>
              <BuildingsIcon size={22} color={theme.colors.text.primary} weight="regular" />
            </View>
            <View style={styles.headerInfo}>
              <Text style={styles.companyName} numberOfLines={1}>
                {company.displayName || company.name}
              </Text>
              {company.tradingName && company.tradingName !== company.name ? (
                <Text style={styles.subtitle} numberOfLines={1}>
                  Trading as {company.tradingName}
                </Text>
              ) : null}
            </View>
            <View style={[styles.badge, { backgroundColor: statusColor.bg }]}>
              <Text style={[styles.badgeText, { color: statusColor.text }]}>
                {STATUS_LABELS[company.status as CompanyStatus] || company.status}
              </Text>
            </View>
          </View>
        </View>

        {/* Interactive Stat Tabs */}
        {stats ? (
          <View style={styles.statsRow}>
            <StatTab
              icon={<CoinIcon />}
              label="Tokens"
              value={stats.totalTokens}
              active={activeTab === 'tokens'}
              onPress={() => setActiveTab('tokens')}
            />
            <StatTab
              icon={<UsersThreeIcon />}
              label="Holders"
              value={stats.totalShareholders}
              active={activeTab === 'shareholders'}
              onPress={() => setActiveTab('shareholders')}
            />
            <StatTab
              icon={<ClockIcon />}
              label="Pending"
              value={stats.pendingActions}
              active={activeTab === 'pending'}
              onPress={() => setActiveTab('pending')}
            />
          </View>
        ) : null}

        {/* Dynamic Content Area */}
        <View style={styles.contentCard}>
          {activeTab === 'tokens' && (
            <TokensSection
              tokens={tokensHook.tokens}
              totalCount={tokensHook.totalCount}
              page={tokensHook.page}
              totalPages={tokensHook.totalPages}
              isLoading={tokensHook.isLoading}
              setPage={tokensHook.setPage}
              createToken={tokensHook.createToken}
              isCreating={tokensHook.isCreating}
              createError={tokensHook.createError}
            />
          )}
          {activeTab === 'shareholders' && (
            <ShareholdersSection holders={shareholdersHook.holders} deployedTokens={shareholdersHook.deployedTokens} />
          )}
          {activeTab === 'pending' && (
            <View style={styles.pendingEmpty}>
              <ClockIcon size={32} color={theme.colors.text.muted} weight="regular" />
              <Text style={styles.pendingTitle}>No Pending Actions</Text>
              <Text style={styles.pendingSubtitle}>All actions are up to date.</Text>
            </View>
          )}
        </View>

        {/* Edit Company Button */}
        <PrimaryButton onPress={handleOpenEdit} fullWidth>
          Edit Company
        </PrimaryButton>
      </ScrollView>

      {/* Edit Company Modal */}
      <CustomModal
        visible={showEditModal}
        onClose={() => setShowEditModal(false)}
        showFooter
        confirmLabel="Save"
        onConfirm={handleSave}
        confirmLoading={isUpdating}
      >
        <View style={styles.formFields}>
          <Text style={styles.modalTitle}>Edit Company</Text>
          <EditField label="Company Name" value={formData.name || ''} onChangeText={(v) => updateField('name', v)} />
          <EditField
            label="Trading Name"
            value={formData.tradingName || ''}
            onChangeText={(v) => updateField('tradingName', v)}
          />
          <EditField
            label="Address Line 1"
            value={formData.addressLine1 || ''}
            onChangeText={(v) => updateField('addressLine1', v)}
          />
          <EditField
            label="Address Line 2"
            value={formData.addressLine2 || ''}
            onChangeText={(v) => updateField('addressLine2', v)}
          />
          <View style={styles.formRow}>
            <View style={styles.formRowItem}>
              <EditField label="City" value={formData.city || ''} onChangeText={(v) => updateField('city', v)} />
            </View>
            <View style={styles.formRowItem}>
              <EditField label="State" value={formData.state || ''} onChangeText={(v) => updateField('state', v)} />
            </View>
          </View>
          <View style={styles.formRow}>
            <View style={styles.formRowItem}>
              <EditField
                label="Postcode"
                value={formData.postcode || ''}
                onChangeText={(v) => updateField('postcode', v)}
              />
            </View>
            <View style={styles.formRowItem}>
              <EditField label="Phone" value={formData.phone || ''} onChangeText={(v) => updateField('phone', v)} />
            </View>
          </View>
        </View>
      </CustomModal>
    </GradientBackground>
  );
}

function EditField({
  label,
  value,
  onChangeText,
}: {
  label: string;
  value: string;
  onChangeText: (v: string) => void;
}) {
  const styles = useThemedStyles((theme) => ({
    container: { gap: 4 },
    label: { fontSize: theme.fontSize.sm, color: theme.colors.text.muted },
    input: {
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

  return (
    <View style={styles.container}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        style={styles.input}
        placeholderTextColor={styles.label.color}
      />
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
  value: number;
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
      fontSize: t.fontSize.lg,
      fontWeight: t.fontWeight.bold as '700',
      color: t.colors.text.primary,
    },
    valueActive: {
      color: t.colors.interactive.active,
    },
    label: {
      fontSize: t.fontSize.xs,
      color: t.colors.text.muted,
    },
    labelActive: {
      color: t.colors.interactive.active,
    },
  }));

  const styledIcon =
    icon && React.isValidElement(icon)
      ? React.cloneElement(icon as React.ReactElement<Record<string, unknown>>, {
          size: 16,
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
      gap: theme.spacing.md,
    },
    errorText: {
      fontSize: theme.fontSize.base,
      color: theme.colors.text.primary,
      fontWeight: theme.fontWeight.medium,
    },
    retryText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.interactive.active,
      fontWeight: theme.fontWeight.semibold,
    },
    noCompanyText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center' as const,
      paddingHorizontal: theme.spacing.xl,
    },
    // Compact header
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
      borderRadius: theme.borderRadius.full,
      backgroundColor: theme.colors.surface.tertiary,
      alignItems: 'center' as const,
      justifyContent: 'center' as const,
    },
    headerInfo: {
      flex: 1,
      gap: 2,
    },
    companyName: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.bold,
      color: theme.colors.text.primary,
    },
    subtitle: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
    badge: {
      paddingHorizontal: 8,
      paddingVertical: 2,
      borderRadius: theme.borderRadius.lg,
    },
    badgeText: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.semibold,
    },
    // Stats
    statsRow: {
      flexDirection: 'row' as const,
      gap: theme.spacing.sm,
    },
    // Content area
    contentCard: {
      backgroundColor: theme.colors.surface.raised,
      borderRadius: theme.borderRadius.md,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      padding: theme.spacing.sm,
    },
    // Pending empty state
    pendingEmpty: {
      alignItems: 'center' as const,
      paddingVertical: theme.spacing.xl,
      gap: theme.spacing.sm,
    },
    pendingTitle: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    pendingSubtitle: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    // Modal form
    modalTitle: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      marginBottom: theme.spacing.sm,
    },
    formFields: {
      gap: theme.spacing.md,
    },
    formRow: {
      flexDirection: 'row' as const,
      gap: theme.spacing.sm,
    },
    formRowItem: {
      flex: 1,
    },
  }));
}
