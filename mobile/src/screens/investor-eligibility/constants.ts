import type { CertifierBody, InvestorCategory, InvestorEligibilityReason } from '@ledova/shared';

export const CATEGORIES: {
  category: InvestorCategory;
  label: string;
  section: string;
  evidence: string;
}[] = [
  {
    category: 'product_value',
    label: 'Large investment',
    section: 's708(8)(a)',
    evidence: 'Proof that at least AUD 500,000 is payable on acceptance, such as a bank statement.',
  },
  {
    category: 'accountant_certificate',
    label: "Qualified accountant's certificate",
    section: 's708(8)(c)',
    evidence: 'A certificate issued in the last two years by a CA ANZ, CPA Australia or IPA member.',
  },
  {
    category: 'professional_investor',
    label: 'Professional investor',
    section: 's708(11)',
    evidence: 'Your AFS licence, your regulator registration, or proof of AUD 10 million under management.',
  },
  {
    category: 'associated_person',
    label: 'Associated with the issuer',
    section: 's708(12)',
    evidence: 'Proof of your role with the named issuer, such as an ASIC extract naming you.',
  },
];

export const CERTIFIER_BODIES: { value: CertifierBody; label: string }[] = [
  { value: 'ca_anz', label: 'Chartered Accountants ANZ' },
  { value: 'cpa_australia', label: 'CPA Australia' },
  { value: 'ipa', label: 'Institute of Public Accountants' },
];

export const REASON_TEXT: Record<InvestorEligibilityReason, string> = {
  no_investor_account: 'This login has no investor account.',
  account_not_in_good_standing: 'Your account is not in good standing.',
  identity_not_verified: 'Every holder on the account must finish identity verification.',
  no_live_classification: 'No verified wholesale investor classification is in force.',
  amount_below_product_value_threshold: 'This subscription is below the AUD 500,000 threshold you rely on.',
};

export const WHOLESALE_ONLY_NOTICE =
  'Offerings on this platform are made to wholesale and sophisticated investors only. They are not made under ' +
  'a disclosure document, and retail investors cannot subscribe.';
