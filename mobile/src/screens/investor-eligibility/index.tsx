import React, { useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator, Alert, TextInput } from 'react-native';
import {
  CheckCircleIcon,
  ClockIcon,
  InfoIcon,
  ShieldCheckIcon,
  TrashIcon,
  UploadSimpleIcon,
  WarningIcon,
  XCircleIcon,
} from 'phosphor-react-native';
import * as DocumentPicker from 'expo-document-picker';
import { useQuery } from '@tanstack/react-query';
import { getCompanies, getErrorMessage, formatDate } from '@ledova/shared';
import type { Company, CertifierBody, InvestorCategory, InvestorClassification } from '@ledova/shared';
import { useAppTheme, useThemedStyles } from '../../contexts';
import { GradientBackground } from '../../components/GradientBackground';
import { Panel } from '../../components/panel';
import { CustomModal } from '../../components/modal';
import { apiClient } from '../../services/apiClient';
import { CATEGORIES, CERTIFIER_BODIES, REASON_TEXT, WHOLESALE_ONLY_NOTICE } from './constants';
import { useInvestorEligibility } from './useInvestorEligibility';

type PickedFile = { uri: string; name: string; type: string };

const CLAIM_ERROR_FALLBACK = 'The claim was refused. Please check the details and try again.';

function claimState(claim: InvestorClassification) {
  if (claim.isLive) {
    return claim.expiresAt ? `Verified until ${formatDate(claim.expiresAt)}` : 'Verified';
  }
  if (claim.isExpired) return 'Expired';
  if (claim.status === 'submitted') return 'Awaiting review';
  return claim.statusDisplay;
}

export function InvestorEligibilityScreen() {
  const theme = useAppTheme();
  const styles = useStyles();
  const { eligibility, classifications, isLoading, submitClaim, isSubmitting, deleteClaim, isDeleting } =
    useInvestorEligibility();

  const [category, setCategory] = useState<InvestorCategory | null>(null);
  const [file, setFile] = useState<PickedFile | null>(null);
  const [declaredBasis, setDeclaredBasis] = useState('');
  const [company, setCompany] = useState('');
  const [certificateIssuedAt, setCertificateIssuedAt] = useState('');
  const [certifierName, setCertifierName] = useState('');
  const [certifierBody, setCertifierBody] = useState<CertifierBody | ''>('');
  const [certifierMembershipNumber, setCertifierMembershipNumber] = useState('');

  const needsCompany = category === 'associated_person';
  const needsCertifier = category === 'accountant_certificate';

  const { data: companiesData } = useQuery({
    queryKey: ['companies'],
    queryFn: () => getCompanies(apiClient),
    enabled: needsCompany,
  });
  const companies: Company[] = companiesData?.data?.results ?? [];

  const reset = () => {
    setCategory(null);
    setFile(null);
    setDeclaredBasis('');
    setCompany('');
    setCertificateIssuedAt('');
    setCertifierName('');
    setCertifierBody('');
    setCertifierMembershipNumber('');
  };

  const pickFile = async () => {
    const result = await DocumentPicker.getDocumentAsync({
      type: ['application/pdf', 'image/*'],
      copyToCacheDirectory: true,
    });
    if (result.canceled || !result.assets?.[0]) return;
    const asset = result.assets[0];
    setFile({ uri: asset.uri, name: asset.name, type: asset.mimeType || 'application/octet-stream' });
  };

  const isComplete =
    !!file &&
    !!category &&
    !!eligibility?.account &&
    declaredBasis.trim() !== '' &&
    (!needsCompany || company !== '') &&
    (!needsCertifier ||
      (certificateIssuedAt !== '' &&
        certifierName.trim() !== '' &&
        certifierBody !== '' &&
        certifierMembershipNumber.trim() !== ''));

  const handleSubmit = async () => {
    if (!isComplete || !category || !eligibility?.account) return;
    try {
      await submitClaim({
        userAccount: eligibility.account,
        category,
        declaredBasis: declaredBasis.trim(),
        file,
        company: needsCompany ? company : undefined,
        certificateIssuedAt: needsCertifier ? certificateIssuedAt : undefined,
        certifierName: needsCertifier ? certifierName.trim() : undefined,
        certifierBody: needsCertifier ? (certifierBody as CertifierBody) : undefined,
        certifierMembershipNumber: needsCertifier ? certifierMembershipNumber.trim() : undefined,
      });
      reset();
    } catch (error) {
      Alert.alert('Claim Refused', getErrorMessage(error, CLAIM_ERROR_FALLBACK) || CLAIM_ERROR_FALLBACK);
    }
  };

  if (isLoading) {
    return (
      <GradientBackground>
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={theme.colors.interactive.default} />
        </View>
      </GradientBackground>
    );
  }

  const isEligible = eligibility?.isEligible ?? false;
  const openClaim = classifications.find((claim) => claim.status === 'submitted');
  const claimed = new Set(
    classifications.filter((claim) => claim.isLive || claim.status === 'submitted').map((claim) => claim.category),
  );
  const spec = CATEGORIES.find((item) => item.category === category);

  return (
    <GradientBackground>
      <ScrollView style={styles.container} contentContainerStyle={styles.scrollContent}>
        <Panel title="Wholesale Investor Status" icon={<ShieldCheckIcon size={20} color={theme.colors.text.muted} />}>
          <View style={styles.statusRow}>
            {isEligible ? (
              <CheckCircleIcon size={24} color={theme.colors.status.success.icon} weight="fill" />
            ) : (
              <WarningIcon size={24} color={theme.colors.status.warning.icon} weight="fill" />
            )}
            <View style={styles.statusTextContainer}>
              <Text style={styles.statusTitle}>
                {isEligible ? 'You can see and subscribe to offerings' : 'You cannot subscribe to offerings yet'}
              </Text>
              {!isEligible &&
                (eligibility?.reasons ?? []).map((reason) => (
                  <Text key={reason} style={styles.statusReason}>
                    {REASON_TEXT[reason] ?? reason}
                  </Text>
                ))}
            </View>
          </View>
          <Text style={styles.notice}>{WHOLESALE_ONLY_NOTICE}</Text>
        </Panel>

        <Panel title="How You Qualify">
          {CATEGORIES.map((item) => (
            <View key={item.category} style={styles.row}>
              <View style={styles.rowLeft}>
                {claimed.has(item.category) ? (
                  <CheckCircleIcon size={20} color={theme.colors.status.success.icon} weight="fill" />
                ) : (
                  <View style={styles.emptyCircle} />
                )}
                <View style={styles.rowTextContainer}>
                  <Text style={styles.rowLabel}>
                    {item.label} ({item.section})
                  </Text>
                  <Text style={styles.rowHelper}>{item.evidence}</Text>
                </View>
              </View>
              <TouchableOpacity
                onPress={() => setCategory(item.category)}
                disabled={!!openClaim || !eligibility?.account}
                style={styles.rowAction}
              >
                <UploadSimpleIcon
                  size={18}
                  color={openClaim ? theme.colors.text.muted : theme.colors.interactive.active}
                />
              </TouchableOpacity>
            </View>
          ))}
        </Panel>

        <Panel title="Your Claims">
          {classifications.length === 0 ? (
            <Text style={styles.emptyText}>You have not made a claim yet.</Text>
          ) : (
            classifications.map((claim) => (
              <View key={claim.uuid} style={styles.row}>
                <View style={styles.rowLeft}>
                  {claim.isLive ? (
                    <CheckCircleIcon size={20} color={theme.colors.status.success.icon} weight="fill" />
                  ) : claim.status === 'submitted' ? (
                    <ClockIcon size={20} color={theme.colors.status.info.icon} weight="fill" />
                  ) : (
                    <XCircleIcon size={20} color={theme.colors.status.error.icon} weight="fill" />
                  )}
                  <View style={styles.rowTextContainer}>
                    <Text style={styles.rowLabel}>{claim.categoryDisplay}</Text>
                    <Text style={styles.rowHelper}>
                      {claimState(claim)}
                      {claim.rejectionReason ? ` — ${claim.rejectionReason}` : ''}
                    </Text>
                  </View>
                </View>
                {claim.status === 'submitted' && (
                  <TouchableOpacity
                    onPress={() => deleteClaim(claim.uuid)}
                    disabled={isDeleting}
                    style={styles.rowAction}
                  >
                    <TrashIcon size={18} color={theme.colors.status.error.icon} />
                  </TouchableOpacity>
                )}
              </View>
            ))
          )}
        </Panel>

        <Panel title="What Happens Next" icon={<InfoIcon size={20} color={theme.colors.text.muted} />}>
          {[
            'Pick the category that applies to you and attach the evidence for it',
            'The operator reviews your evidence and sets an expiry date',
            'Once verified, offerings become visible and you can subscribe',
            'Re-evidence your claim before it expires to stay eligible',
          ].map((step, index) => (
            <View key={step} style={styles.stepRow}>
              <Text style={styles.stepNumber}>{index + 1}.</Text>
              <Text style={styles.stepText}>{step}</Text>
            </View>
          ))}
        </Panel>
      </ScrollView>

      <CustomModal
        visible={category !== null}
        onClose={reset}
        showFooter
        confirmLabel="Submit for review"
        onConfirm={handleSubmit}
        confirmDisabled={!isComplete || isSubmitting}
        confirmLoading={isSubmitting}
      >
        <View style={styles.modalContent}>
          <Text style={styles.modalTitle}>{spec ? `Claim: ${spec.label}` : 'Claim'}</Text>
          <Text style={styles.modalText}>{spec?.evidence}</Text>

          {needsCompany && (
            <>
              <Text style={styles.fieldLabel}>Issuer</Text>
              {companies.map((item) => (
                <TouchableOpacity
                  key={item.uuid}
                  onPress={() => setCompany(item.uuid)}
                  style={[styles.optionRow, company === item.uuid && styles.optionRowSelected]}
                >
                  <Text style={styles.optionText}>{item.name}</Text>
                </TouchableOpacity>
              ))}
            </>
          )}

          {needsCertifier && (
            <>
              <Text style={styles.fieldLabel}>Certificate date (YYYY-MM-DD)</Text>
              <TextInput
                value={certificateIssuedAt}
                onChangeText={setCertificateIssuedAt}
                placeholder="2026-01-31"
                placeholderTextColor={theme.colors.text.muted}
                style={styles.input}
              />
              <Text style={styles.fieldLabel}>Professional body</Text>
              {CERTIFIER_BODIES.map((body) => (
                <TouchableOpacity
                  key={body.value}
                  onPress={() => setCertifierBody(body.value)}
                  style={[styles.optionRow, certifierBody === body.value && styles.optionRowSelected]}
                >
                  <Text style={styles.optionText}>{body.label}</Text>
                </TouchableOpacity>
              ))}
              <Text style={styles.fieldLabel}>Accountant name</Text>
              <TextInput
                value={certifierName}
                onChangeText={setCertifierName}
                placeholderTextColor={theme.colors.text.muted}
                style={styles.input}
              />
              <Text style={styles.fieldLabel}>Membership number</Text>
              <TextInput
                value={certifierMembershipNumber}
                onChangeText={setCertifierMembershipNumber}
                placeholderTextColor={theme.colors.text.muted}
                style={styles.input}
              />
            </>
          )}

          <Text style={styles.fieldLabel}>Basis for the claim</Text>
          <TextInput
            value={declaredBasis}
            onChangeText={setDeclaredBasis}
            placeholder="Describe why this category applies to you"
            placeholderTextColor={theme.colors.text.muted}
            style={styles.textArea}
            multiline
          />

          <TouchableOpacity onPress={pickFile} style={styles.filePicker}>
            <UploadSimpleIcon size={20} color={theme.colors.interactive.active} />
            <Text style={styles.filePickerText}>{file ? file.name : 'Attach evidence (PDF or image, max 10 MB)'}</Text>
          </TouchableOpacity>

          <Text style={styles.declaration}>
            Submitting declares that this category applies to you and that the evidence attached is genuine.{' '}
            {WHOLESALE_ONLY_NOTICE}
          </Text>
        </View>
      </CustomModal>
    </GradientBackground>
  );
}

function useStyles() {
  return useThemedStyles((theme) => ({
    container: {
      flex: 1,
    },
    scrollContent: {
      padding: theme.spacing.md,
      gap: theme.spacing.md,
      paddingBottom: theme.spacing.xxl,
    },
    centered: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
    },
    statusRow: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: theme.spacing.sm,
      paddingHorizontal: theme.spacing.sm,
    },
    statusTextContainer: {
      flex: 1,
    },
    statusTitle: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    statusReason: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      marginTop: theme.spacing.xs,
    },
    notice: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
      paddingHorizontal: theme.spacing.sm,
      paddingTop: theme.spacing.sm,
    },
    row: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingVertical: theme.spacing.sm,
      paddingHorizontal: theme.spacing.sm,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.subtle,
      gap: theme.spacing.sm,
    },
    rowLeft: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.sm,
      flex: 1,
    },
    rowTextContainer: {
      flex: 1,
    },
    rowLabel: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.primary,
    },
    rowHelper: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
    rowAction: {
      padding: theme.spacing.xs,
    },
    emptyCircle: {
      width: 20,
      height: 20,
      borderRadius: 10,
      borderWidth: 2,
      borderColor: theme.colors.border.default,
    },
    emptyText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      padding: theme.spacing.sm,
    },
    stepRow: {
      flexDirection: 'row',
      gap: theme.spacing.sm,
      paddingHorizontal: theme.spacing.sm,
      paddingVertical: theme.spacing.xs,
    },
    stepNumber: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    stepText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.secondary,
      flex: 1,
    },
    modalContent: {
      gap: theme.spacing.sm,
    },
    modalTitle: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    modalText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.secondary,
    },
    fieldLabel: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
      marginTop: theme.spacing.sm,
    },
    input: {
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
      paddingHorizontal: theme.spacing.sm,
      paddingVertical: theme.spacing.sm,
      color: theme.colors.text.primary,
      backgroundColor: theme.colors.surface.tertiary,
    },
    textArea: {
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
      paddingHorizontal: theme.spacing.sm,
      paddingVertical: theme.spacing.sm,
      color: theme.colors.text.primary,
      backgroundColor: theme.colors.surface.tertiary,
      minHeight: 80,
      textAlignVertical: 'top',
    },
    optionRow: {
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
      padding: theme.spacing.sm,
      marginTop: theme.spacing.xs,
    },
    optionRowSelected: {
      borderColor: theme.colors.interactive.active,
      backgroundColor: theme.colors.surface.tertiary,
    },
    optionText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.primary,
    },
    filePicker: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.sm,
      borderWidth: 1,
      borderStyle: 'dashed',
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
      padding: theme.spacing.md,
      marginTop: theme.spacing.sm,
    },
    filePickerText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.secondary,
      flex: 1,
    },
    declaration: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
      marginTop: theme.spacing.sm,
    },
  }));
}
