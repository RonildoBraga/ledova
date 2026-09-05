import { useState } from 'react';
import {
  BellIcon,
  UserCircleIcon,
  CaretRightIcon,
  TrashIcon,
  ExportIcon,
  LockIcon,
  EyeIcon,
  EyeSlashIcon,
  CircleNotchIcon,
  CurrencyCircleDollarIcon,
} from '@phosphor-icons/react';
import { useNavigate } from 'react-router-dom';
import {
  DESIGN_TOKENS,
  deleteAccount,
  changePassword,
  exportAccountData,
  getCurrentUserPreferences,
  upsertCurrentUserPreferences,
  CACHE_TIMING,
} from '@ledova/shared';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useQuery } from '@tanstack/react-query';
import type { DisplayCurrency } from '@ledova/shared';
import apiClient from '@services/apiClient';
import { Panel } from '@components/Panel';
import { Modal } from '@components/Modal';
import { useAuth } from '@hooks/useAuth';
import { useNotificationPreferences } from './useNotificationPreferences';

const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;
const ICON_MD = DESIGN_TOKENS.icon.sizes.md;
const ICON_XL = DESIGN_TOKENS.icon.sizes.xl;

interface SettingsItemProps {
  icon: React.ReactNode;
  title: string;
  description?: string;
  onClick?: () => void;
  badge?: string;
  disabled?: boolean;
  danger?: boolean;
  isLast?: boolean;
}

function SettingsItem({ icon, title, description, onClick, badge, disabled, danger, isLast }: SettingsItemProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`w-full flex items-center gap-3 px-4 py-3 transition-colors text-left ${
        !isLast ? 'border-b border-border-subtle' : ''
      } ${disabled ? 'opacity-50 cursor-not-allowed' : 'hover:bg-surface-tertiary/50'}`}
    >
      <div
        className={`flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center ${
          danger ? 'bg-error-light/10' : 'bg-surface-tertiary'
        }`}
      >
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className={`text-sm font-medium ${danger ? 'text-error-light' : 'text-text-primary'}`}>{title}</span>
          {badge && (
            <span className="px-2 py-0.5 text-xs font-medium bg-brand-mid/20 text-brand-light rounded">{badge}</span>
          )}
        </div>
        {description && <p className="text-xs text-text-muted truncate mt-0.5">{description}</p>}
      </div>
      <CaretRightIcon size={ICON_SM} className="text-text-subtle flex-shrink-0" />
    </button>
  );
}

interface SectionProps {
  title: string;
  children: React.ReactNode;
}

function Section({ title, children }: SectionProps) {
  return (
    <div className="mb-5">
      <p className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2 px-1">{title}</p>
      <div className="bg-surface-tertiary/50 rounded-lg overflow-hidden border border-border-subtle">{children}</div>
    </div>
  );
}

interface ToggleRowProps {
  label: string;
  description: string;
  value: boolean;
  onToggle: (value: boolean) => void;
  disabled?: boolean;
  isLast?: boolean;
}

function ToggleRow({ label, description, value, onToggle, disabled, isLast }: ToggleRowProps) {
  return (
    <div
      className={`flex items-center gap-3 px-4 py-3 ${!isLast ? 'border-b border-border-subtle' : ''} ${disabled ? 'opacity-50' : ''}`}
    >
      <div className="flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center bg-surface-tertiary">
        <BellIcon size={ICON_MD} className="text-text-muted" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-text-primary">{label}</p>
        <p className="text-xs text-text-muted mt-0.5">{description}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={value}
        onClick={() => onToggle(!value)}
        disabled={disabled}
        className={`relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition-colors ${value ? 'bg-brand-mid' : 'bg-surface-disabled'} ${disabled ? 'cursor-not-allowed' : 'cursor-pointer'}`}
      >
        <span
          className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${value ? 'translate-x-6' : 'translate-x-1'}`}
        />
      </button>
    </div>
  );
}

export function SettingsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { isAuthenticated } = useAuth();

  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);

  // Currency preference
  const preferencesQuery = useQuery({
    queryKey: ['userPreferences'],
    queryFn: () => getCurrentUserPreferences(apiClient),
    enabled: isAuthenticated,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });
  const displayCurrency: DisplayCurrency = preferencesQuery.data?.data?.displayCurrency ?? 'AUD';

  const currencyMutation = useMutation({
    mutationFn: (currency: DisplayCurrency) => upsertCurrentUserPreferences(apiClient, { displayCurrency: currency }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['userPreferences'] });
      queryClient.invalidateQueries({ queryKey: ['exchangeRate'] });
    },
  });

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [passwordError, setPasswordError] = useState('');

  const {
    transactionAlerts,
    priceAlerts,
    marketing,
    isLoading: notificationsLoading,
    isUpdating,
    toggleTransactionAlerts,
    togglePriceAlerts,
    toggleMarketing,
  } = useNotificationPreferences();

  const deleteAccountMutation = useMutation({
    mutationFn: () => deleteAccount(apiClient),
    onSuccess: () => {
      queryClient.clear();
      navigate('/signin');
    },
  });

  const changePasswordMutation = useMutation({
    mutationFn: () =>
      changePassword(apiClient, {
        currentPassword,
        newPassword,
        newPasswordConfirm: confirmPassword,
      }),
    onSuccess: () => {
      closePasswordModal();
    },
    onError: (error: unknown) => {
      const err = error as { response?: { data?: Record<string, string[]> } };
      const data = err.response?.data;
      if (data?.current_password) {
        setPasswordError('Current password is incorrect');
      } else if (data?.new_password) {
        setPasswordError('Invalid new password');
      } else if (data?.new_password_confirm) {
        setPasswordError('Passwords do not match');
      } else {
        setPasswordError('Failed to change password. Please try again.');
      }
    },
  });

  const exportDataMutation = useMutation({
    mutationFn: () => exportAccountData(apiClient),
    onSuccess: (response) => {
      const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ledova-data-export-${new Date().toISOString().split('T')[0]}.json`;
      a.click();
      URL.revokeObjectURL(url);
      setShowExportModal(false);
    },
  });

  const closePasswordModal = () => {
    setShowPasswordModal(false);
    setCurrentPassword('');
    setNewPassword('');
    setConfirmPassword('');
    setShowCurrentPassword(false);
    setShowNewPassword(false);
    setShowConfirmPassword(false);
    setPasswordError('');
    changePasswordMutation.reset();
  };

  const handleChangePassword = () => {
    setPasswordError('');
    if (!currentPassword || !newPassword || !confirmPassword) {
      setPasswordError('All fields are required');
      return;
    }
    if (newPassword.length < 8) {
      setPasswordError('New password must be at least 8 characters');
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError('Passwords do not match');
      return;
    }
    changePasswordMutation.mutate();
  };

  return (
    <>
      <div className="w-full max-w-6xl mx-auto px-4 pt-6 pb-16 sm:px-6 lg:px-8">
        <Panel title="Account">
          <Section title="Profile & Security">
            <SettingsItem
              icon={<UserCircleIcon size={ICON_MD} className="text-text-muted" />}
              title="Profile"
              description="Manage your personal information"
              onClick={() => navigate('/user-profile')}
            />
            <SettingsItem
              icon={<LockIcon size={ICON_MD} className="text-text-muted" />}
              title="Password"
              description="Change your account password"
              onClick={() => setShowPasswordModal(true)}
              isLast
            />
          </Section>

          <Section title="Notifications">
            <ToggleRow
              label="Transaction Alerts"
              description="Notifications for transaction status changes"
              value={transactionAlerts}
              onToggle={toggleTransactionAlerts}
              disabled={notificationsLoading || isUpdating}
            />
            <ToggleRow
              label="Price Alerts"
              description="Notifications for price threshold alerts"
              value={priceAlerts}
              onToggle={togglePriceAlerts}
              disabled={notificationsLoading || isUpdating}
            />
            <ToggleRow
              label="Marketing"
              description="Marketing and promotional notifications"
              value={marketing}
              onToggle={toggleMarketing}
              disabled={notificationsLoading || isUpdating}
              isLast
            />
          </Section>

          <Section title="Display">
            <div className="flex items-center gap-3 px-4 py-3">
              <div className="flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center bg-surface-tertiary">
                <CurrencyCircleDollarIcon size={ICON_MD} className="text-text-muted" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-text-primary">Display Currency</p>
                <p className="text-xs text-text-muted mt-0.5">All values are converted from USD</p>
              </div>
              <div className="flex rounded-lg border border-border-subtle overflow-hidden">
                {(['AUD', 'USD'] as DisplayCurrency[]).map((currency) => (
                  <button
                    key={currency}
                    type="button"
                    onClick={() => currencyMutation.mutate(currency)}
                    disabled={currencyMutation.isPending}
                    className={`px-4 py-1.5 text-sm font-medium transition-colors ${
                      displayCurrency === currency
                        ? 'bg-brand-mid text-white'
                        : 'text-text-muted hover:text-text-primary'
                    } ${currencyMutation.isPending ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
                  >
                    {currency}
                  </button>
                ))}
              </div>
            </div>
          </Section>

          <Section title="Data & Privacy">
            <SettingsItem
              icon={<ExportIcon size={ICON_MD} className="text-text-muted" />}
              title="Export Data"
              description="Download a copy of your data"
              onClick={() => setShowExportModal(true)}
            />
            <SettingsItem
              icon={<TrashIcon size={ICON_MD} className="text-error-light" />}
              title="Delete Account"
              description="Permanently delete your account"
              onClick={() => setShowDeleteModal(true)}
              danger
              isLast
            />
          </Section>
        </Panel>
      </div>

      <Modal
        isOpen={showPasswordModal}
        onClose={closePasswordModal}
        title="Change Password"
        showFooter
        confirmLabel="Change Password"
        onConfirm={handleChangePassword}
        confirmLoading={changePasswordMutation.isPending}
        confirmDisabled={!currentPassword || !newPassword || !confirmPassword}
      >
        <div className="space-y-4 py-2">
          <div>
            <label className="block text-sm font-medium text-text-primary mb-1.5">Current Password</label>
            <div className="relative">
              <input
                type={showCurrentPassword ? 'text' : 'password'}
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className="w-full px-3 py-2.5 pr-10 bg-surface-tertiary border border-border-subtle rounded-lg text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-border-focus"
                placeholder="Enter current password"
              />
              <button
                type="button"
                onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
              >
                {showCurrentPassword ? <EyeSlashIcon size={ICON_MD} /> : <EyeIcon size={ICON_MD} />}
              </button>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-text-primary mb-1.5">New Password</label>
            <div className="relative">
              <input
                type={showNewPassword ? 'text' : 'password'}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full px-3 py-2.5 pr-10 bg-surface-tertiary border border-border-subtle rounded-lg text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-border-focus"
                placeholder="Enter new password"
              />
              <button
                type="button"
                onClick={() => setShowNewPassword(!showNewPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
              >
                {showNewPassword ? <EyeSlashIcon size={ICON_MD} /> : <EyeIcon size={ICON_MD} />}
              </button>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-text-primary mb-1.5">Confirm New Password</label>
            <div className="relative">
              <input
                type={showConfirmPassword ? 'text' : 'password'}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full px-3 py-2.5 pr-10 bg-surface-tertiary border border-border-subtle rounded-lg text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-border-focus"
                placeholder="Confirm new password"
              />
              <button
                type="button"
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
              >
                {showConfirmPassword ? <EyeSlashIcon size={ICON_MD} /> : <EyeIcon size={ICON_MD} />}
              </button>
            </div>
          </div>

          {passwordError && (
            <div className="bg-error-light/10 border border-error-light/20 rounded-lg p-3">
              <p className="text-sm text-error-light">{passwordError}</p>
            </div>
          )}
        </div>
      </Modal>

      <Modal
        isOpen={showExportModal}
        onClose={() => setShowExportModal(false)}
        title="Export Data"
        showFooter
        confirmLabel={exportDataMutation.isPending ? 'Exporting...' : 'Export'}
        onConfirm={() => exportDataMutation.mutate()}
        confirmLoading={exportDataMutation.isPending}
      >
        <div className="py-4">
          <div className="w-16 h-16 rounded-full bg-brand-mid/10 flex items-center justify-center mx-auto mb-4">
            {exportDataMutation.isPending ? (
              <CircleNotchIcon size={ICON_XL} className="text-brand-mid animate-spin" />
            ) : (
              <ExportIcon size={ICON_XL} className="text-brand-mid" />
            )}
          </div>
          <p className="text-text-primary font-medium text-center mb-2">Download your data</p>
          <p className="text-sm text-text-muted text-center">
            This will export your account data as a JSON file. The download will start automatically.
          </p>
          {exportDataMutation.isError && (
            <div className="bg-error-light/10 border border-error-light/20 rounded-lg p-3 mt-4">
              <p className="text-sm text-error-light text-center">Failed to export data. Please try again.</p>
            </div>
          )}
        </div>
      </Modal>

      <Modal
        isOpen={showDeleteModal}
        onClose={() => setShowDeleteModal(false)}
        title="Delete Account"
        showFooter
        cancelLabel="Cancel"
        confirmLabel="Delete Account"
        onConfirm={() => deleteAccountMutation.mutate()}
        confirmLoading={deleteAccountMutation.isPending}
      >
        <div className="py-4">
          <div className="w-16 h-16 rounded-full bg-error-light/10 flex items-center justify-center mx-auto mb-4">
            <TrashIcon size={ICON_XL} className="text-error-light" />
          </div>
          <p className="text-text-primary font-medium text-center mb-2">This action cannot be undone</p>
          <p className="text-sm text-text-muted text-center mb-4">
            This experimental flow deactivates the account and removes profile fields. Review and test the configured
            retention behavior before using it with any data.
          </p>
          <p className="text-sm text-text-muted text-center">Are you sure you want to delete your account?</p>
          {deleteAccountMutation.isError && (
            <div className="bg-error-light/10 border border-error-light/20 rounded-lg p-3 mt-4">
              <p className="text-sm text-error-light text-center">
                Failed to delete account. Please try again or contact the deployment operator.
              </p>
            </div>
          )}
        </div>
      </Modal>
    </>
  );
}

export default SettingsPage;
