import { createContext, useContext, useState, useCallback } from 'react';
import { useLocation } from 'react-router-dom';

interface PageInfo {
  title: string;
  subtitle?: string;
}

const PAGE_INFO: Record<string, PageInfo> = {
  '/home': { title: 'Home', subtitle: 'Overview of your portfolio' },
  '/wallets': { title: 'Wallets', subtitle: 'Manage your digital asset wallets' },
  '/trading': { title: 'Trading', subtitle: 'Buy and sell assets' },
  '/transactions': { title: 'Transactions', subtitle: 'View your transaction history' },
  '/asset-prices': { title: 'Market', subtitle: 'Browse asset prices' },
  '/user-profile': { title: 'Profile', subtitle: 'Manage your account' },
  '/settings': { title: 'Settings', subtitle: 'Configure your preferences' },
  '/signin': { title: 'Sign In' },
  '/signup': { title: 'Sign Up' },
  '/signup/email-confirmation': { title: 'Email Confirmation' },
  '/signup/account-type': { title: 'Account Type' },
  '/signup/pre-screening': { title: 'Eligibility Check' },
  '/signup/identity-verification': { title: 'Identity Verification' },
  '/signup/user-profile': { title: 'Profile Setup' },
  '/signup/financial-profile': { title: 'Financial Profile' },
  '/signup/company-registration': { title: 'Company Registration' },
  '/signup/review': { title: 'Review' },
  '/company': { title: 'Company', subtitle: 'Manage your company profile' },
  '/company/listing': { title: 'Listing Application', subtitle: 'Upload documents and submit for review' },
};

interface PageTitleContextType {
  override: PageInfo | null;
  setOverride: (info: PageInfo | null) => void;
}

export const PageTitleContext = createContext<PageTitleContextType>({
  override: null,
  setOverride: () => {},
});

export function usePageTitleProvider() {
  const [override, setOverride] = useState<PageInfo | null>(null);
  return { override, setOverride };
}

export function usePageTitle(): PageInfo {
  const location = useLocation();
  const { override } = useContext(PageTitleContext);

  if (override) {
    return override;
  }

  return PAGE_INFO[location.pathname] || { title: 'Ledova' };
}

export function useSetPageTitle() {
  const { setOverride } = useContext(PageTitleContext);
  return useCallback(
    (title: string, subtitle?: string) => {
      setOverride({ title, subtitle });
    },
    [setOverride],
  );
}
