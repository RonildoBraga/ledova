import React from 'react';
import { View, Modal, ScrollView, TouchableOpacity, Text } from 'react-native';
import { overlayColors } from '../../contexts';
import { useAppTheme, useThemedStyles } from '../../contexts';

interface CustomModalProps {
  visible: boolean;
  onClose: () => void;
  children: React.ReactNode;
  showFooter?: boolean;
  showCancelButton?: boolean;
  cancelLabel?: string;
  confirmLabel?: string;
  onCancel?: () => void;
  onConfirm?: () => void;
  confirmDisabled?: boolean;
  confirmLoading?: boolean;
}

export function CustomModal({
  visible,
  onClose,
  children,
  showFooter = false,
  showCancelButton = true,
  cancelLabel = 'Cancel',
  confirmLabel = 'Confirm',
  onCancel,
  onConfirm,
  confirmDisabled = false,
  confirmLoading = false,
}: CustomModalProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    overlay: {
      flex: 1,
      backgroundColor: overlayColors.modal,
      justifyContent: 'center',
      alignItems: 'center',
    },
    modalContainer: {
      width: '90%',
      maxWidth: 400,
      borderRadius: theme.borderRadius.lg,
      // Shadow for iOS
      shadowColor: theme.colors.utility.black,
      shadowOffset: {
        width: 0,
        height: 8,
      },
      shadowOpacity: 0.5,
      shadowRadius: 12,
      // Elevation for Android
      elevation: 10,
    },
    modal: {
      backgroundColor: theme.colors.surface.raised,
      borderRadius: theme.borderRadius.lg,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      overflow: 'hidden',
      flexDirection: 'column',
    },
    modalContent: {
      flexShrink: 1,
    },
    modalContentContainer: {
      paddingHorizontal: theme.spacing.md,
      paddingTop: theme.spacing.md,
      paddingBottom: theme.spacing.md,
    },
    footer: {
      flexDirection: 'row',
      gap: theme.spacing.md,
      padding: theme.spacing.md,
      borderTopWidth: 1,
      borderTopColor: theme.colors.border.default,
      backgroundColor: theme.colors.surface.tertiary,
      marginTop: theme.spacing.lg,
    },
    button: {
      flex: 1,
      paddingVertical: theme.spacing.md,
      borderRadius: theme.borderRadius.md,
      alignItems: 'center',
      justifyContent: 'center',
    },
    cancelButton: {
      backgroundColor: theme.colors.surface.disabled,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
    },
    cancelButtonFullWidth: {
      flex: 0,
      width: '100%',
    },
    cancelButtonText: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    confirmButton: {
      backgroundColor: theme.colors.interactive.active,
    },
    confirmButtonFullWidth: {
      flex: 0,
      width: '100%',
    },
    confirmButtonDisabled: {
      backgroundColor: theme.colors.interactive.disabled,
      opacity: 0.5,
    },
    confirmButtonText: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.utility.white,
    },
    confirmButtonTextDisabled: {
      color: theme.colors.text.muted,
    },
  }));
  return (
    <Modal visible={visible} animationType="fade" transparent={true} onRequestClose={onClose}>
      <TouchableOpacity style={styles.overlay} activeOpacity={1} onPress={onClose}>
        <View style={styles.modalContainer}>
          <TouchableOpacity activeOpacity={1} style={styles.modal}>
            {/* Content */}
            <ScrollView
              style={styles.modalContent}
              contentContainerStyle={styles.modalContentContainer}
              showsVerticalScrollIndicator={false}
            >
              {children}
            </ScrollView>

            {/* Footer */}
            {showFooter && (
              <View style={styles.footer}>
                {showCancelButton && (
                  <TouchableOpacity
                    style={[styles.button, styles.cancelButton, !onConfirm && styles.cancelButtonFullWidth]}
                    onPress={onCancel ?? onClose}
                    disabled={confirmLoading}
                    activeOpacity={0.7}
                  >
                    <Text style={styles.cancelButtonText}>{cancelLabel}</Text>
                  </TouchableOpacity>
                )}
                {onConfirm && (
                  <TouchableOpacity
                    style={[
                      styles.button,
                      styles.confirmButton,
                      (confirmDisabled || confirmLoading) && styles.confirmButtonDisabled,
                      !showCancelButton && styles.confirmButtonFullWidth,
                    ]}
                    onPress={onConfirm}
                    disabled={confirmDisabled || confirmLoading}
                    activeOpacity={0.7}
                  >
                    <Text
                      style={[
                        styles.confirmButtonText,
                        (confirmDisabled || confirmLoading) && styles.confirmButtonTextDisabled,
                      ]}
                    >
                      {confirmLoading ? 'Loading...' : confirmLabel}
                    </Text>
                  </TouchableOpacity>
                )}
              </View>
            )}
          </TouchableOpacity>
        </View>
      </TouchableOpacity>
    </Modal>
  );
}
