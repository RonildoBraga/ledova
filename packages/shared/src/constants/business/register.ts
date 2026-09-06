export type HolderType = 'member' | 'treasury' | 'ambiguous' | 'unidentified';

export const HOLDER_TYPE_LABELS: Record<HolderType, string> = {
  member: 'Member',
  treasury: 'Treasury',
  ambiguous: 'Ambiguous',
  unidentified: 'Unidentified',
};

export const REGISTER_COPY = {
  TITLE: 'Register Of Members',
  DOWNLOAD: 'Download CSV',
  DOWNLOAD_FAILED: 'The register could not be downloaded. Try again.',
  PRIVACY_NOTE:
    'Names, holder types and holdings are shown here. Residential addresses are in the CSV only, and every ' +
    'download is logged.',
  AMBIGUOUS_NOTE:
    'Two wallets share this address, so the holder cannot be named. Resolve the duplicate wallet before relying ' +
    'on the register.',
  UNIDENTIFIED_NOTE:
    'This address has no whitelist entry, so no holder can be named against it. Ask the operator to add one.',
  SUBSCRIPTIONS_TITLE: 'Subscriptions',
  SUBSCRIPTIONS_EMPTY: 'No subscription has been made to this offering yet.',
  SUBSCRIPTIONS_NOTE:
    'Read-only. Payment confirmation and allotment are operator actions; this is where you watch them happen.',
} as const;
