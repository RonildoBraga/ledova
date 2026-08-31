import React, { useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator, Alert, Linking } from 'react-native';
import {
  CheckCircleIcon,
  CircleIcon,
  UploadSimpleIcon,
  TrashIcon,
  WarningIcon,
  InfoIcon,
  FileTextIcon,
  EyeIcon,
} from 'phosphor-react-native';
import * as DocumentPicker from 'expo-document-picker';
import type { DocumentType } from '@ledova/shared-types';
import { useAppTheme, useThemedStyles } from '../../contexts';
import { GradientBackground } from '../../components/GradientBackground';
import { Panel } from '../../components/panel';
import { CustomModal } from '../../components/modal';
import { PrimaryButton } from '../../components/buttons';
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
  } = useCompanyDocuments();
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const missingRequired = REQUIRED_DOCUMENTS.filter((d) => !uploadedTypes.has(d.type));
  const canSubmit = canEdit && missingRequired.length === 0;

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

  // Application already submitted
  if (!canEdit && company.status !== 'draft') {
    return (
      <GradientBackground>
        <ScrollView style={styles.container} contentContainerStyle={styles.scrollContent}>
          <Panel>
            <View style={styles.submittedContainer}>
              <CheckCircleIcon size={48} color={theme.colors.status.success.icon} weight="duotone" />
              <Text style={styles.submittedTitle}>Application Submitted</Text>
              <Text style={styles.submittedText}>
                Your listing application has been submitted and is currently{' '}
                <Text style={styles.statusHighlight}>{company.statusDisplay || company.status}</Text>.
              </Text>
            </View>
          </Panel>
        </ScrollView>
      </GradientBackground>
    );
  }

  return (
    <GradientBackground>
      <ScrollView style={styles.container} contentContainerStyle={styles.scrollContent}>
        {/* Info Required Warning */}
        {company.status === 'info_required' && company.infoRequestReason && (
          <View style={styles.warningBanner}>
            <WarningIcon size={20} color={theme.colors.status.warning.icon} weight="fill" />
            <View style={styles.warningTextContainer}>
              <Text style={styles.warningTitle}>Additional Information Required</Text>
              <Text style={styles.warningMessage}>{company.infoRequestReason}</Text>
            </View>
          </View>
        )}

        {/* Required Documents */}
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

        {/* Optional Documents */}
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

        {/* What Happens Next */}
        <Panel title="What Happens Next" icon={<InfoIcon />}>
          <View style={styles.stepsContainer}>
            {[
              'Submit your application with all required documents',
              'Ledova staff reviews your application (2-5 business days)',
              'We may contact you for additional information',
              'Once approved, your share token is created on the blockchain',
              'Your company is activated on the platform',
            ].map((step, i) => (
              <View key={i} style={styles.stepRow}>
                <Text style={styles.stepNumber}>{i + 1}.</Text>
                <Text style={styles.stepText}>{step}</Text>
              </View>
            ))}
          </View>
        </Panel>

        {/* Submit Button */}
        <View style={styles.submitSection}>
          <PrimaryButton
            onPress={() => {
              if (!canSubmit) {
                Alert.alert(
                  'Documents Required',
                  `Please upload all ${missingRequired.length} required document${missingRequired.length > 1 ? 's' : ''} before submitting your application.`,
                );
                return;
              }
              submitApplication();
            }}
            loading={isSubmitting}
            fullWidth
          >
            Submit Application
          </PrimaryButton>
        </View>

        {/* Delete Confirmation Modal */}
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
    </GradientBackground>
  );
}

// --- Sub-components ---

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

// --- Styles ---

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
    // Warning banner
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
    // Submitted state
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
    // Document rows
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
    // Steps
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
    // Submit section
    submitSection: {
      alignItems: 'center',
      gap: theme.spacing.sm,
      paddingTop: theme.spacing.sm,
    },
    // Modal
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
