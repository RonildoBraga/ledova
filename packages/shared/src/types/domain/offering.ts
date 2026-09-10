import type { OfferingExemption, OfferingStatus } from '../../constants';
import type { ShareToken } from './trading';

export interface DirectoryCompany {
  displayName: string;
  industry: string;
  city: string;
  state: string;
}

export interface DirectoryOpenOffering {
  uuid: string;
  pricePerShare: string;
  priceCurrency: string;
  opensAt: string;
  closesAt: string | null;
}

export interface DirectoryToken extends ShareToken {
  company: DirectoryCompany;
  issuedShares: number;
  openOffering: DirectoryOpenOffering | null;
}

export interface Offering {
  uuid: string;
  tokenUuid: string;
  tokenSymbol: string;
  tokenName: string;
  status: OfferingStatus;
  statusDisplay: string;
  exemption: OfferingExemption;
  exemptionDisplay: string;
  pricePerShare: string;
  priceCurrency: string;
  minimumShares: number;
  targetShares: number;
  capShares: number;
  maximumShares: number | null;
  opensAt: string;
  closesAt: string | null;
  isOpen: boolean;
  createdAt: string;
  settlementAssets: string[];
  acceptsBankTransfer: boolean;
  summary: string;
  useOfProceeds: string;
  documents: string[];
  submittedByEmail: string | null;
  submittedAt: string | null;
  reviewedByEmail: string | null;
  reviewedAt: string | null;
  reviewNotes: string;
  rejectionReason: string;
  closedAt: string | null;
  closeReason: string;
  canBeEdited: boolean;
  canBeDeleted: boolean;
  updatedAt: string;
}

export interface OfferingListItem {
  uuid: string;
  tokenUuid: string;
  tokenSymbol: string;
  tokenName: string;
  status: OfferingStatus;
  statusDisplay: string;
  exemption: OfferingExemption;
  exemptionDisplay: string;
  pricePerShare: string;
  priceCurrency: string;
  minimumShares: number;
  targetShares: number;
  capShares: number;
  maximumShares: number | null;
  opensAt: string;
  closesAt: string | null;
  isOpen: boolean;
  canBeEdited: boolean;
  canBeDeleted: boolean;
  rejectionReason: string;
  closeReason: string;
  createdAt: string;
}

export interface OfferingInput {
  token: string;
  exemption: OfferingExemption;
  pricePerShare: string;
  priceCurrency?: string;
  settlementAssets?: string[];
  acceptsBankTransfer?: boolean;
  minimumShares: number;
  targetShares: number;
  capShares: number;
  maximumShares?: number | null;
  opensAt: string;
  closesAt?: string | null;
  summary?: string;
  useOfProceeds?: string;
  documents?: string[];
}
