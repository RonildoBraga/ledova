import { useState } from 'react';
import {
  UserIcon,
  ShieldCheckIcon,
  CheckCircleIcon,
  ClockIcon,
  WarningCircleIcon,
  XCircleIcon,
  EnvelopeIcon,
  PhoneIcon,
  CalendarIcon,
  MapPinIcon,
  FlagIcon,
  CheckIcon,
  XIcon,
} from '@phosphor-icons/react';
import {
  formatDate,
  formatDateTime,
  getUserVerificationStatus,
  type VerificationStatusType,
} from '@ledova/shared-utils';
import { DESIGN_TOKENS } from '@ledova/shared-constants';
import { useUserProfile } from './useUserProfile';

const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;
const ICON_MD = DESIGN_TOKENS.icon.sizes.md;
import { Panel } from '@components/Panel';
import { DocumentsPanel } from '@components/DocumentsPanel';
import { IdentityVerificationModal } from './components/IdentityVerificationModal';

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

interface InfoRowProps {
  label: string;
  value: string | null | undefined;
  fallback?: string;
  icon: React.ReactNode;
  isLast?: boolean;
}

function InfoRow({ label, value, fallback = 'Not provided', icon, isLast }: InfoRowProps) {
  return (
    <div className={`flex items-center gap-3 px-4 py-3 ${!isLast ? 'border-b border-border-subtle' : ''}`}>
      <div className="flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center bg-surface-tertiary">
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-text-primary">{value || fallback}</p>
        <p className="text-xs text-text-muted mt-0.5">{label}</p>
      </div>
    </div>
  );
}

interface EditableInfoRowProps {
  label: string;
  value: string | null | undefined;
  fallback?: string;
  icon: React.ReactNode;
  isEditing: boolean;
  editValue: string;
  onEdit: () => void;
  onSave: () => void;
  onCancel: () => void;
  onChange: (value: string) => void;
  isSaving: boolean;
  inputType?: string;
  placeholder?: string;
  isLast?: boolean;
}

function EditableInfoRow({
  label,
  value,
  fallback = 'Not provided',
  icon,
  isEditing,
  editValue,
  onEdit,
  onSave,
  onCancel,
  onChange,
  isSaving,
  inputType = 'text',
  placeholder,
  isLast,
}: EditableInfoRowProps) {
  if (isEditing) {
    return (
      <div className={`flex items-center gap-3 px-4 py-3 ${!isLast ? 'border-b border-border-subtle' : ''}`}>
        <div className="flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center bg-surface-tertiary">
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <input
            type={inputType}
            value={editValue}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholder}
            className="w-full text-sm bg-surface-tertiary border border-border rounded-lg px-3 py-1.5 text-text-primary focus:outline-none focus:border-border-focus"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === 'Enter') onSave();
              if (e.key === 'Escape') onCancel();
            }}
          />
          <p className="text-xs text-text-muted mt-0.5">{label}</p>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            type="button"
            onClick={onSave}
            disabled={isSaving}
            className="p-1.5 text-success-light hover:text-success-light transition-colors disabled:opacity-50"
          >
            <CheckIcon size={ICON_SM} weight="bold" />
          </button>
          <button
            type="button"
            onClick={onCancel}
            disabled={isSaving}
            className="p-1.5 text-text-muted hover:text-text-secondary transition-colors disabled:opacity-50"
          >
            <XIcon size={ICON_SM} weight="bold" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onEdit}
      className={`w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-surface-tertiary/50 transition-colors ${!isLast ? 'border-b border-border-subtle' : ''}`}
    >
      <div className="flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center bg-surface-tertiary">
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-text-primary">{value || fallback}</p>
        <p className="text-xs text-text-muted mt-0.5">{label}</p>
      </div>
    </button>
  );
}

function getVerificationStatusColor(statusType: VerificationStatusType): string {
  switch (statusType) {
    case 'verified':
      return 'text-success-light';
    case 'rejected':
      return 'text-error-light';
    default:
      return 'text-warning-light';
  }
}

function getVerificationStatusBgColor(statusType: VerificationStatusType): string {
  switch (statusType) {
    case 'verified':
      return 'bg-success-light/10';
    case 'rejected':
      return 'bg-error-light/10';
    default:
      return 'bg-warning-light/10';
  }
}

function VerificationStatusIcon({ statusType }: { statusType: VerificationStatusType }) {
  const className = getVerificationStatusColor(statusType);

  switch (statusType) {
    case 'verified':
      return <CheckCircleIcon size={ICON_SM} className={className} weight="fill" />;
    case 'pending':
      return <ClockIcon size={ICON_SM} className={className} />;
    case 'rejected':
      return <XCircleIcon size={ICON_SM} className={className} weight="fill" />;
    default:
      return <WarningCircleIcon size={ICON_SM} className={className} />;
  }
}

export function UserProfilePage() {
  const { userProfile, isLoading, isError, refreshProfile, updateProfile, isUpdating } = useUserProfile();

  const verificationStatus = getUserVerificationStatus(userProfile);

  const [isEditingEmail, setIsEditingEmail] = useState(false);
  const [isEditingPhone, setIsEditingPhone] = useState(false);
  const [editEmail, setEditEmail] = useState('');
  const [editPhoneCode, setEditPhoneCode] = useState('');
  const [editPhoneNumber, setEditPhoneNumber] = useState('');
  const [showVerificationModal, setShowVerificationModal] = useState(false);

  const handleEditEmail = () => {
    setEditEmail(userProfile?.email || '');
    setIsEditingEmail(true);
  };

  const handleSaveEmail = () => {
    updateProfile({ email: editEmail });
    setIsEditingEmail(false);
  };

  const handleEditPhone = () => {
    setEditPhoneCode(userProfile?.phoneCountryCode || '');
    setEditPhoneNumber(userProfile?.phoneNumber || '');
    setIsEditingPhone(true);
  };

  const handleSavePhone = () => {
    updateProfile({ phoneCountryCode: editPhoneCode, phoneNumber: editPhoneNumber });
    setIsEditingPhone(false);
  };

  const phoneDisplay = userProfile?.phoneNumber
    ? `${userProfile.phoneCountryCode || ''} ${userProfile.phoneNumber}`.trim()
    : null;

  if (isLoading) {
    return (
      <div className="w-full max-w-6xl mx-auto px-4 pt-6 pb-16 sm:px-6 lg:px-8">
        <Panel title="Profile">
          <div className="space-y-0">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-3 border-b border-border-subtle last:border-b-0">
                <div className="w-9 h-9 bg-surface-tertiary rounded-lg animate-pulse" />
                <div className="flex-1">
                  <div className="h-4 w-32 bg-surface-tertiary rounded animate-pulse mb-1" />
                  <div className="h-3 w-20 bg-surface-tertiary rounded animate-pulse" />
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="w-full max-w-6xl mx-auto px-4 pt-6 pb-16 sm:px-6 lg:px-8">
        <Panel title="Profile">
          <p className="text-sm text-error-light text-center py-6">Error loading profile</p>
        </Panel>
      </div>
    );
  }

  return (
    <>
      <div className="w-full max-w-6xl mx-auto px-4 pt-6 pb-16 sm:px-6 lg:px-8">
        <Panel title="Profile">
          {userProfile ? (
            <>
              <Section title="Personal Information">
                <InfoRow
                  label="Full Name"
                  value={userProfile.fullName}
                  icon={<UserIcon size={ICON_MD} className="text-text-muted" />}
                />
                <EditableInfoRow
                  label="Email"
                  value={userProfile.email}
                  icon={<EnvelopeIcon size={ICON_MD} className="text-text-muted" />}
                  isEditing={isEditingEmail}
                  editValue={editEmail}
                  onEdit={handleEditEmail}
                  onSave={handleSaveEmail}
                  onCancel={() => setIsEditingEmail(false)}
                  onChange={setEditEmail}
                  isSaving={isUpdating}
                  inputType="email"
                  placeholder="email@example.com"
                />
                {isEditingPhone ? (
                  <div className="flex items-center gap-3 px-4 py-3 border-b border-border-subtle">
                    <div className="flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center bg-surface-tertiary">
                      <PhoneIcon size={ICON_MD} className="text-text-muted" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={editPhoneCode}
                          onChange={(e) => setEditPhoneCode(e.target.value)}
                          placeholder="+61"
                          className="w-16 text-sm bg-surface-tertiary border border-border rounded-lg px-3 py-1.5 text-text-primary focus:outline-none focus:border-border-focus"
                          autoFocus
                        />
                        <input
                          type="tel"
                          value={editPhoneNumber}
                          onChange={(e) => setEditPhoneNumber(e.target.value)}
                          placeholder="Phone number"
                          className="flex-1 text-sm bg-surface-tertiary border border-border rounded-lg px-3 py-1.5 text-text-primary focus:outline-none focus:border-border-focus"
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleSavePhone();
                            if (e.key === 'Escape') setIsEditingPhone(false);
                          }}
                        />
                      </div>
                      <p className="text-xs text-text-muted mt-0.5">Phone</p>
                    </div>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <button
                        type="button"
                        onClick={handleSavePhone}
                        disabled={isUpdating}
                        className="p-1.5 text-success-light hover:text-success-light transition-colors disabled:opacity-50"
                      >
                        <CheckIcon size={ICON_SM} weight="bold" />
                      </button>
                      <button
                        type="button"
                        onClick={() => setIsEditingPhone(false)}
                        disabled={isUpdating}
                        className="p-1.5 text-text-muted hover:text-text-secondary transition-colors disabled:opacity-50"
                      >
                        <XIcon size={ICON_SM} weight="bold" />
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={handleEditPhone}
                    className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-surface-tertiary/50 transition-colors border-b border-border-subtle"
                  >
                    <div className="flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center bg-surface-tertiary">
                      <PhoneIcon size={ICON_MD} className="text-text-muted" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-text-primary">{phoneDisplay || 'Not provided'}</p>
                      <p className="text-xs text-text-muted mt-0.5">Phone</p>
                    </div>
                  </button>
                )}
                <InfoRow
                  label="Date of Birth"
                  value={formatDate(userProfile.dateOfBirth, 'Not available')}
                  icon={<CalendarIcon size={ICON_MD} className="text-text-muted" />}
                />
                <InfoRow
                  label="Address"
                  value={userProfile.residentialAddress}
                  icon={<MapPinIcon size={ICON_MD} className="text-text-muted" />}
                />
                <InfoRow
                  label="Citizenship"
                  value={userProfile.citizenshipCountryName}
                  icon={<FlagIcon size={ICON_MD} className="text-text-muted" />}
                  isLast
                />
              </Section>

              <Section title="Account Status">
                <div className="flex items-center gap-3 px-4 py-3 border-b border-border-subtle">
                  <div className="flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center bg-surface-tertiary">
                    <ShieldCheckIcon size={ICON_MD} className="text-text-muted" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-text-primary">Identity Check</p>
                    <p className="text-xs text-text-muted mt-0.5">Verify your identity</p>
                  </div>
                  {verificationStatus.type === 'not_started' ? (
                    <button
                      type="button"
                      onClick={() => setShowVerificationModal(true)}
                      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium cursor-pointer hover:opacity-80 transition-opacity ${getVerificationStatusBgColor(verificationStatus.type)} ${getVerificationStatusColor(verificationStatus.type)}`}
                    >
                      {verificationStatus.label}
                      <VerificationStatusIcon statusType={verificationStatus.type} />
                    </button>
                  ) : (
                    <div
                      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${getVerificationStatusBgColor(verificationStatus.type)} ${getVerificationStatusColor(verificationStatus.type)}`}
                    >
                      {verificationStatus.label}
                      <VerificationStatusIcon statusType={verificationStatus.type} />
                    </div>
                  )}
                </div>
                <InfoRow
                  label="Member Since"
                  value={formatDate(userProfile.dateJoined, 'Not available')}
                  icon={<CalendarIcon size={ICON_MD} className="text-text-muted" />}
                />
                <InfoRow
                  label="Last Login"
                  value={formatDateTime(userProfile.lastLogin)}
                  icon={<ClockIcon size={ICON_MD} className="text-text-muted" />}
                  isLast
                />
              </Section>

              <Section title="Documents">
                <div className="p-3">
                  <DocumentsPanel />
                </div>
              </Section>
            </>
          ) : (
            <p className="text-sm text-text-muted italic text-center py-6">No profile data available</p>
          )}
        </Panel>
      </div>

      <IdentityVerificationModal
        isOpen={showVerificationModal}
        onClose={() => {
          setShowVerificationModal(false);
          refreshProfile();
        }}
      />
    </>
  );
}

export default UserProfilePage;
