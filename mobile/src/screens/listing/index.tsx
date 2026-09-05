import React, { useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator, Alert, Linking, TextInput } from 'react-native';
import {
  CheckCircleIcon,
  CircleIcon,
  UploadSimpleIcon,
  TrashIcon,
  WarningIcon,
  InfoIcon,
  FileTextIcon,
  EyeIcon,
  ClockIcon,
  XCircleIcon,
} from 'phosphor-react-native';
import * as DocumentPicker from 'expo-document-picker';
import { useQuery } from '@tanstack/react-query';
import { getOperator, getErrorMessage, CACHE_TIMING } from '@ledova/shared';
import type { Company, DocumentType } from '@ledova/shared';
import { useAppTheme, useThemedStyles } from '../../contexts';
import { GradientBackground } from '../../components/GradientBackground';
import { Panel } from '../../components/panel';
import { CustomModal } from '../../components/modal';
import { PrimaryButton, SecondaryButton } from '../../components/buttons';
import { apiClient } from '../../services/apiClient';
import { useCompanyDocuments } from './useCompanyDocuments';

const REQUIRED_DOCUMENTS: { type: DocumentType; label: string }[] = [
  { type: 'cert_inc', label: 'Certificate of Incorporation' },
  { type: 'asic', label: 'ASIC Company Extract' },
  { type: 'constitution', label: 'Company Constitution' },
  { type: 'share_register', label: 'Current Share Register' },
  { type: 'financials', label: 'Financial Statements' },
  { type: 'director_id', label: 'Director Identification' },
  { type: 'beneficial_ownership', label: 'Beneficial Ownership Declaration' },
  { type: 'business_plan', label: 'Business Plan' },
  { type: 'risk_disclosure', label: 'Risk Disclosure Statement' },
];

const OPTIONAL_DOCUMENTS: { type: DocumentType; label: string }[] = [
  { type: 'auditor_report', label: 'Auditor Report' },
  { type: 'shareholder', label: 'Shareholder Agreement' },
  { type: 'prospectus', label: 'Prospectus' },
  { type: 'legal_opinion', label: 'Legal Opinion' },
  { type: 'tax_return', label: 'Tax Return' },
  { type: 'bank_statement', label: 'Bank Statement' },
];

const WITHDRAWABLE_STATUSES: Company['status'][] = ['submitted', 'info_required'];

const ACTION_ERROR_FALLBACK = 'The request was refused. Please try again.';

export function ListingScreen() {
  const theme = useAppTheme();
  const styles = useStyles();
  const {
    company,
    documents,
    uploadedTypes,
    canEdit,
    isLoading,
    upload,
    isUploading,
    deleteDocument,
    isDeleting,
    submitApplication,
    isSubmitting,
    resubmitApplication,
    isResubmitting,
    withdrawApplication,
    isWithdrawing,
  } = useCompanyDocuments();
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [infoResponse, setInfoResponse] = useState('');
  const [showWithdrawModal, setShowWithdrawModal] = useState(false);
  const [withdrawReason, setWithdrawReason] = useState('');

  const { data: operator } = useQuery({
    queryKey: ['operator'],
    queryFn: () => getOperator(apiClient).then((res) => res.data),
    staleTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });
  const operatorName = operator?.name || 'The operator';

  const status = company?.status;
  const isInfoRequired = status === 'info_required';
  const canWithdraw = !!status && WITHDRAWABLE_STATUSES.includes(status);
  const missingRequired = REQUIRED_DOCUMENTS.filter((d) => !uploadedTypes.has(d.type));
  const hasRequiredDocuments = missingRequired.length === 0;
  const isActing = isSubmitting || isResubmitting || isWithdrawing;

  const showRefusal = (error: unknown) =>
    Alert.alert('Request Refused', getErrorMessage(error, ACTION_ERROR_FALLBACK) || ACTION_ERROR_FALLBACK);

  const handlePickAndUpload = async (documentType: DocumentType) => {
    const result = await DocumentPicker.getDocumentAsync({
      type: ['application/pdf', 'image/*'],
      copyToCacheDirectory: true,
    });

    if (result.canceled || !result.assets?.[0]) return;

    const asset = result.assets[0];
    const file = {
      uri: asset.uri,
      name: asset.name,
      type: asset.mimeType || 'application/octet-stream',
    };

    try {
      await upload({ documentType, name: asset.name, file });
    } catch {
      Alert.alert('Upload Failed', 'Could not upload the document. Please try again.');
    }
  };

  const handleDelete = (docUuid: string) => {
    setDeleteTarget(docUuid);
  };

  const confirmDelete = () => {
    if (deleteTarget) {
      deleteDocument(deleteTarget);
      setDeleteTarget(null);
    }
  };

  const handleSubmit = async () => {
    if (!hasRequiredDocuments) {
      Alert.alert(
        'Documents Required',
        `Please upload all ${missingRequired.length} required document${missingRequired.length > 1 ? 's' : ''} before submitting your application.`,
      );
      return;
    }
    try {
      await submitApplication();
    } catch (error) {
      showRefusal(error);
    }
  };

  const handleResubmit = async () => {
    if (!hasRequiredDocuments) {
      Alert.alert(
        'Documents Required',
        `Please upload all ${missingRequired.length} required document${missingRequired.length > 1 ? 's' : ''} before resubmitting your application.`,
      );
      return;
    }
    if (!infoResponse.trim()) {
      Alert.alert('Response Required', 'Describe how you addressed the information request before resubmitting.');
      return;
    }
    try {
      await resubmitApplication(infoResponse.trim());
      setInfoResponse('');
    } catch (error) {
      showRefusal(error);
    }
  };

  const confirmWithdraw = async () => {
    setShowWithdrawModal(false);
    try {
      await withdrawApplication(withdrawReason.trim());
      setWithdrawReason('');
    } catch (error) {
      showRefusal(error);
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

  if (!company) {
    return (
      <GradientBackground>
        <View style={styles.centered}>
          <FileTextIcon size={48} color={theme.colors.text.muted} weight="regular" />
          <Text style={styles.emptyText}>No company found. Please register your company first.</Text>
        </View>
      </GradientBackground>
    );
  }

  const withdrawModal = (
    <CustomModal
      visible={showWithdrawModal}
      onClose={() => setShowWithdrawModal(false)}
      showFooter
      confirmLabel="Withdraw"
      onConfirm={confirmWithdraw}
      confirmLoading={isWithdrawing}
    >
      <View style={styles.modalContent}>
        <Text style={styles.modalTitle}>Withdraw Application</Text>
        <Text style={styles.modalText}>
          Withdrawing takes your application out of the review queue. You will need to register again to list your
          company later.
        </Text>
        <Text style={styles.fieldLabel}>Reason (optional)</Text>
        <TextInput
          value={withdrawReason}
          onChangeText={setWithdrawReason}
          placeholder="Let the operator know why you are withdrawing"
          placeholderTextColor={theme.colors.text.muted}
          style={styles.textArea}
          multiline
        />
      </View>
    </CustomModal>
  );

  if (!canEdit) {
    return (
      <GradientBackground>
        <ScrollView style={styles.container} contentContainerStyle={styles.scrollContent}>
          <Panel>
            <ApplicationStatusView company={company} operatorName={operatorName} theme={theme} styles={styles} />
            {canWithdraw && (
              <View style={styles.submittedActions}>
                <SecondaryButton onPress={() => setShowWithdrawModal(true)} loading={isWithdrawing} fullWidth>
                  Withdraw Application
                </SecondaryButton>
              </View>
            )}
          </Panel>
        </ScrollView>
        {withdrawModal}
      </GradientBackground>
    );
  }

  return (
    <GradientBackground>
      <ScrollView style={styles.container} contentContainerStyle={styles.scrollContent}>
        {isInfoRequired && (
          <View style={styles.warningBanner}>
            <WarningIcon size={20} color={theme.colors.status.warning.icon} weight="fill" />
            <View style={styles.warningTextContainer}>
              <Text style={styles.warningTitle}>Additional Information Required</Text>
              {company.infoRequestReason ? (
                <Text style={styles.warningMessage}>{company.infoRequestReason}</Text>
              ) : null}
            </View>
          </View>
        )}

        <Panel title="Required Documents">
          {REQUIRED_DOCUMENTS.map((doc, index) => {
            const uploaded = documents.find((d) => d.documentType === doc.type);
            return (
              <DocumentRow
                key={doc.type}
                label={doc.label}
                uploaded={uploaded}
                onUpload={() => handlePickAndUpload(doc.type)}
                onDelete={() => handleDelete(uploaded!.uuid)}
                isUploading={isUploading}
                isDeleting={isDeleting}
                canEdit={canEdit}
                isLast={index === REQUIRED_DOCUMENTS.length - 1}
                theme={theme}
              />
            );
          })}
        </Panel>

        <Panel title="Optional Documents">
          {OPTIONAL_DOCUMENTS.map((doc, index) => {
            const uploaded = documents.find((d) => d.documentType === doc.type);
            return (
              <DocumentRow
                key={doc.type}
                label={doc.label}
                uploaded={uploaded}
                onUpload={() => handlePickAndUpload(doc.type)}
                onDelete={() => handleDelete(uploaded!.uuid)}
                isUploading={isUploading}
                isDeleting={isDeleting}
                canEdit={canEdit}
                isLast={index === OPTIONAL_DOCUMENTS.length - 1}
                theme={theme}
              />
            );
          })}
        </Panel>

        {isInfoRequired && (
          <Panel title="Your Response">
            <View style={styles.responseContainer}>
              <Text style={styles.responseHint}>
                Answer the request above, upload any documents it asks for, then resubmit your application.
              </Text>
              <TextInput
                value={infoResponse}
                onChangeText={setInfoResponse}
                placeholder="Describe what you changed or provide the information requested"
                placeholderTextColor={theme.colors.text.muted}
                style={styles.textArea}
                multiline
              />
            </View>
          </Panel>
        )}

        <Panel title="What Happens Next" icon={<InfoIcon />}>
          <View style={styles.stepsContainer}>
            {[
              'Submit your application with all required documents',
              `${operatorName} reviews your application (2-5 business days)`,
              'You may be asked for additional information',
              'Once approved, you deploy your share token on the blockchain',
              'Your company is activated on the platform',
            ].map((step, i) => (
              <View key={i} style={styles.stepRow}>
                <Text style={styles.stepNumber}>{i + 1}.</Text>
                <Text style={styles.stepText}>{step}</Text>
              </View>
            ))}
          </View>
        </Panel>

        <View style={styles.submitSection}>
          {isInfoRequired ? (
            <PrimaryButton onPress={handleResubmit} loading={isResubmitting} disabled={isActing} fullWidth>
              Resubmit Application
            </PrimaryButton>
          ) : (
            <PrimaryButton onPress={handleSubmit} loading={isSubmitting} disabled={isActing} fullWidth>
              Submit Application
            </PrimaryButton>
          )}
          {canWithdraw && (
            <TouchableOpacity onPress={() => setShowWithdrawModal(true)} disabled={isActing} hitSlop={8}>
              <Text style={styles.withdrawLink}>Withdraw application</Text>
            </TouchableOpacity>
          )}
        </View>

        <CustomModal
          visible={!!deleteTarget}
          onClose={() => setDeleteTarget(null)}
          showFooter
          confirmLabel="Delete"
          onConfirm={confirmDelete}
        >
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>Delete Document</Text>
            <Text style={styles.modalText}>
              Are you sure you want to delete this document? This action cannot be undone.
            </Text>
          </View>
        </CustomModal>
      </ScrollView>
      {withdrawModal}
    </GradientBackground>
  );
}

function ApplicationStatusView({
  company,
  operatorName,
  theme,
  styles,
}: {
  company: Company;
  operatorName: string;
  theme: ReturnType<typeof useAppTheme>;
  styles: ReturnType<typeof useStyles>;
}) {
  const statusLabel = company.statusDisplay || company.status;
  const outcome = (() => {
    switch (company.status) {
      case 'approved':
      case 'active':
        return {
          icon: <CheckCircleIcon size={48} color={theme.colors.status.success.icon} weight="duotone" />,
          title: company.status === 'active' ? 'Company Active' : 'Application Approved',
          body: `Your listing application was approved and your company is ${statusLabel}.`,
        };
      case 'rejected':
        return {
          icon: <XCircleIcon size={48} color={theme.colors.status.error.icon} weight="duotone" />,
          title: 'Application Rejected',
          body: company.rejectionReason
            ? `${operatorName} rejected the application: ${company.rejectionReason}`
            : `${operatorName} rejected the application.`,
        };
      case 'withdrawn':
        return {
          icon: <XCircleIcon size={48} color={theme.colors.text.muted} weight="duotone" />,
          title: 'Application Withdrawn',
          body: company.withdrawalReason
            ? `You withdrew this application: ${company.withdrawalReason}`
            : 'You withdrew this application.',
        };
      case 'review':
        return {
          icon: <ClockIcon size={48} color={theme.colors.status.info.icon} weight="duotone" />,
          title: 'Under Review',
          body: `${operatorName} is reviewing your application. Withdrawal is no longer available once the review has started.`,
        };
      case 'submitted':
        return {
          icon: <ClockIcon size={48} color={theme.colors.status.info.icon} weight="duotone" />,
          title: 'Application Submitted',
          body: `Your listing application is waiting for ${operatorName} to start the review.`,
        };
      default:
        return {
          icon: <InfoIcon size={48} color={theme.colors.text.muted} weight="duotone" />,
          title: statusLabel,
          body: `Your company is currently ${statusLabel}.`,
        };
    }
  })();

  return (
    <View style={styles.submittedContainer}>
      {outcome.icon}
      <Text style={styles.submittedTitle}>{outcome.title}</Text>
      <Text style={styles.submittedText}>{outcome.body}</Text>
      {company.additionalInfoResponse ? (
        <View style={styles.previousResponse}>
          {company.infoRequestReason ? (
            <>
              <Text style={styles.previousResponseLabel}>Information requested</Text>
              <Text style={styles.previousResponseText}>{company.infoRequestReason}</Text>
            </>
          ) : null}
          <Text style={styles.previousResponseLabel}>Your response</Text>
          <Text style={styles.previousResponseText}>{company.additionalInfoResponse}</Text>
        </View>
      ) : null}
    </View>
  );
}

interface DocumentRowProps {
  label: string;
  uploaded?: { uuid: string; name?: string; fileUrl?: string } | undefined;
  onUpload: () => void;
  onDelete: () => void;
  isUploading: boolean;
  isDeleting: boolean;
  canEdit: boolean;
  isLast: boolean;
  theme: ReturnType<typeof useAppTheme>;
}

function DocumentRow({
  label,
  uploaded,
  onUpload,
  onDelete,
  isUploading,
  isDeleting,
  canEdit,
  isLast,
  theme,
}: DocumentRowProps) {
  const styles = useStyles();

  const handleView = () => {
    if (uploaded?.fileUrl) {
      Linking.openURL(uploaded.fileUrl);
    }
  };

  return (
    <View style={[styles.docRow, !isLast && styles.rowBorder]}>
      <View style={styles.docRowLeft}>
        {uploaded ? (
          <CheckCircleIcon size={20} color={theme.colors.status.success.icon} weight="fill" />
        ) : (
          <CircleIcon size={20} color={theme.colors.border.default} weight="regular" />
        )}
        <View style={styles.docLabelContainer}>
          <Text style={styles.docLabel} numberOfLines={1}>
            {label}
          </Text>
          {uploaded?.name && (
            <Text style={styles.docFilename} numberOfLines={1}>
              {uploaded.name}
            </Text>
          )}
        </View>
      </View>
      <View style={styles.docRowRight}>
        {uploaded ? (
          <>
            {uploaded.fileUrl && (
              <TouchableOpacity onPress={handleView} hitSlop={8}>
                <EyeIcon size={18} color={theme.colors.interactive.default} weight="regular" />
              </TouchableOpacity>
            )}
            {canEdit && (
              <TouchableOpacity onPress={onDelete} disabled={isDeleting} hitSlop={8}>
                <TrashIcon size={18} color={theme.colors.status.error.icon} weight="regular" />
              </TouchableOpacity>
            )}
          </>
        ) : canEdit ? (
          <TouchableOpacity onPress={onUpload} disabled={isUploading} hitSlop={8} activeOpacity={0.7}>
            <UploadSimpleIcon size={18} color={theme.colors.interactive.default} weight="bold" />
          </TouchableOpacity>
        ) : null}
      </View>
    </View>
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
      paddingBottom: theme.spacing.xl,
    },
    centered: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
      padding: theme.spacing.lg,
      gap: theme.spacing.sm,
    },
    emptyText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
    },

    warningBanner: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      padding: theme.spacing.md,
      borderRadius: theme.borderRadius.md,
      backgroundColor: theme.colors.status.warning.icon + '1A',
      borderWidth: 1,
      borderColor: theme.colors.status.warning.icon + '4D',
      gap: theme.spacing.sm,
    },
    warningTextContainer: {
      flex: 1,
    },
    warningTitle: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.status.warning.icon,
    },
    warningMessage: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      marginTop: theme.spacing.xs,
    },

    submittedContainer: {
      alignItems: 'center',
      padding: theme.spacing.xl,
      gap: theme.spacing.md,
    },
    submittedTitle: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    submittedText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
      lineHeight: theme.lineHeight.normal,
    },
    statusHighlight: {
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },

    docRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: theme.spacing.md,
      paddingVertical: theme.spacing.sm,
    },
    docRowLeft: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.sm,
      flex: 1,
      marginRight: theme.spacing.sm,
    },
    docRowRight: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.sm,
    },
    docLabelContainer: {
      flex: 1,
    },
    docLabel: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.primary,
    },
    docFilename: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
      marginTop: 2,
    },
    uploadButtonText: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.interactive.default,
    },
    rowBorder: {
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.default,
    },

    stepsContainer: {
      padding: theme.spacing.md,
      gap: theme.spacing.xs,
    },
    stepRow: {
      flexDirection: 'row',
      gap: theme.spacing.xs,
    },
    stepNumber: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      width: 20,
    },
    stepText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.secondary,
      flex: 1,
    },

    submitSection: {
      alignItems: 'center',
      gap: theme.spacing.sm,
      paddingTop: theme.spacing.sm,
    },
    submittedActions: {
      paddingHorizontal: theme.spacing.md,
      paddingBottom: theme.spacing.md,
    },
    withdrawLink: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.muted,
      paddingVertical: theme.spacing.xs,
    },

    previousResponse: {
      marginTop: theme.spacing.sm,
      padding: theme.spacing.sm,
      borderRadius: theme.borderRadius.md,
      backgroundColor: theme.colors.surface.tertiary,
      gap: theme.spacing.xs,
      alignSelf: 'stretch',
    },
    previousResponseLabel: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.muted,
    },
    previousResponseText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.secondary,
    },
    responseContainer: {
      padding: theme.spacing.md,
      gap: theme.spacing.sm,
    },
    responseHint: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.secondary,
    },
    fieldLabel: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    textArea: {
      minHeight: 96,
      textAlignVertical: 'top',
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
      backgroundColor: theme.colors.surface.tertiary,
      paddingHorizontal: theme.spacing.sm,
      paddingVertical: theme.spacing.sm,
      color: theme.colors.text.primary,
      fontSize: theme.fontSize.sm,
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
      color: theme.colors.text.muted,
      lineHeight: theme.lineHeight.normal,
    },
  }));
}
