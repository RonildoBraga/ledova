import { useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  HouseIcon,
  WalletIcon,
  CurrencyCircleDollarIcon,
  ArrowsClockwiseIcon,
  LinkIcon,
  ChartBarIcon,
  UserIcon,
  GearIcon,
  QuestionIcon,
  SignOutIcon,
  EnvelopeIcon,
  PaperPlaneTiltIcon,
  BuildingsIcon,
  FileTextIcon,
} from '@phosphor-icons/react';
import { signout, DESIGN_TOKENS } from '@ledova/shared';
import apiClient from '@services/apiClient';
import { useFeatureFlags, useRole } from '@hooks';
import { useBuyCrypto } from '@hooks/useBuyCrypto';
import { useSendTransfer } from '@hooks/useSendTransfer';
import { useUserProfile } from '@pages/user-profile/useUserProfile';

const MARKETING_URL = import.meta.env.VITE_MARKETING_URL || 'http://localhost:5173';
const ICON_MD = DESIGN_TOKENS.icon.sizes.md;

interface NavItem {
  label: string;
  path: string;
  icon: React.ComponentType<{ size?: number; weight?: 'regular' | 'fill' }>;
}

const secondaryNavItems: NavItem[] = [
  { label: 'Profile', path: '/user-profile', icon: UserIcon },
  { label: 'Settings', path: '/settings', icon: GearIcon },
];

interface SidebarProps {
  onNavigate?: () => void;
}

export function Sidebar({ onNavigate }: SidebarProps = {}) {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { tradingEnabled } = useFeatureFlags();
  const { isInvestor, isCompany } = useRole();
  const { openBuyCrypto } = useBuyCrypto();
  const { openSendTransfer } = useSendTransfer();
  const { userProfile } = useUserProfile();

  const investorNavItems = useMemo(
    (): NavItem[] => [
      { label: 'Home', path: '/home', icon: HouseIcon },
      { label: 'Wallets', path: '/wallets', icon: WalletIcon },
    ],
    [],
  );

  const companyNavItems = useMemo(
    (): NavItem[] => [
      { label: 'Company', path: '/company', icon: BuildingsIcon },
      { label: 'Listing', path: '/company/listing', icon: FileTextIcon },
      { label: 'Wallets', path: '/wallets', icon: WalletIcon },
    ],
    [],
  );

  const navItemsBeforeActions = isCompany && !isInvestor ? companyNavItems : investorNavItems;

  const navItemsAfterActions = useMemo((): NavItem[] => {
    const items: NavItem[] = [];

    if (tradingEnabled) {
      items.push({ label: 'Trading', path: '/trading', icon: ArrowsClockwiseIcon });
    }

    if (isInvestor) {
      items.push(
        { label: 'Transactions', path: '/transactions', icon: LinkIcon },
        { label: 'Market', path: '/asset-prices', icon: ChartBarIcon },
      );
    }

    if (isCompany && isInvestor) {
      items.push({ label: 'Company', path: '/company', icon: BuildingsIcon });
    }

    return items;
  }, [tradingEnabled, isCompany]);

  const signoutMutation = useMutation({
    mutationFn: () => signout(apiClient),
    onSettled: () => {
      queryClient.setQueryData(['auth', 'verify'], { data: { valid: false } });
      queryClient.clear();
      navigate('/signin');
    },
  });

  const isActive = (path: string) => location.pathname === path;

  const handleSignOut = () => {
    signoutMutation.mutate();
  };

  const handleNav = (path: string) => {
    navigate(path);
    onNavigate?.();
  };

  const handleAction = (action: () => void) => {
    action();
    onNavigate?.();
  };

  return (
    <aside className="w-60 bg-surface-base border-r border-border-subtle/30 flex flex-col h-full">
      <div className="h-16 flex items-center px-5 border-b border-border-subtle/30">
        <div className="flex items-center gap-2.5">
          <img src="/icons/logo.png" alt="Ledova" className="w-8 h-8 object-contain" />
          <span className="text-lg font-semibold text-text-primary">Ledova</span>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        <div className="mb-2">
          <span className="px-3 text-xs font-medium text-text-muted uppercase tracking-wider">Menu</span>
        </div>
        {navItemsBeforeActions.map((item) => {
          const Icon = item.icon;
          const active = isActive(item.path);
          return (
            <button
              key={item.path}
              onClick={() => handleNav(item.path)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150
                ${
                  active
                    ? 'bg-brand-mid/10 text-brand-light'
                    : 'text-text-secondary hover:bg-surface-raised hover:text-text-primary'
                }`}
            >
              <Icon size={ICON_MD} weight={active ? 'fill' : 'regular'} />
              <span>{item.label}</span>
            </button>
          );
        })}

        <button
          onClick={() => handleAction(openBuyCrypto)}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 text-text-secondary hover:bg-surface-raised hover:text-text-primary"
        >
          <CurrencyCircleDollarIcon size={ICON_MD} />
          <span>Buy</span>
        </button>

        <button
          onClick={() => handleAction(openSendTransfer)}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 text-text-secondary hover:bg-surface-raised hover:text-text-primary"
        >
          <PaperPlaneTiltIcon size={ICON_MD} />
          <span>Send</span>
        </button>

        {navItemsAfterActions.map((item) => {
          const Icon = item.icon;
          const active = isActive(item.path);
          return (
            <button
              key={item.path}
              onClick={() => handleNav(item.path)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150
                ${
                  active
                    ? 'bg-brand-mid/10 text-brand-light'
                    : 'text-text-secondary hover:bg-surface-raised hover:text-text-primary'
                }`}
            >
              <Icon size={ICON_MD} weight={active ? 'fill' : 'regular'} />
              <span>{item.label}</span>
            </button>
          );
        })}

        <div className="my-4 mx-3">
          <div className="h-px bg-gradient-to-r from-transparent via-border-subtle/50 to-transparent" />
        </div>

        <div className="mb-2">
          <span className="px-3 text-xs font-medium text-text-muted uppercase tracking-wider">Account</span>
        </div>
        {secondaryNavItems.map((item) => {
          const Icon = item.icon;
          const active = isActive(item.path);
          return (
            <button
              key={item.path}
              onClick={() => handleNav(item.path)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150
                ${
                  active
                    ? 'bg-brand-mid/10 text-brand-light'
                    : 'text-text-secondary hover:bg-surface-raised hover:text-text-primary'
                }`}
            >
              <Icon size={ICON_MD} weight={active ? 'fill' : 'regular'} />
              <span>{item.label}</span>
            </button>
          );
        })}
        <a
          href={`${MARKETING_URL}/contact`}
          target="_blank"
          rel="noopener noreferrer"
          onClick={() => onNavigate?.()}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 text-text-secondary hover:bg-surface-raised hover:text-text-primary"
        >
          <QuestionIcon size={ICON_MD} />
          <span>Help & Support</span>
        </a>
      </nav>

      <div className="p-3 border-t border-border-subtle/30 space-y-2">
        {userProfile?.email && (
          <div className="flex items-center gap-3 px-3 py-2 rounded-lg bg-surface-raised/50">
            <EnvelopeIcon size={ICON_MD} className="text-text-muted flex-shrink-0" />
            <span className="text-sm text-text-secondary truncate">{userProfile.email}</span>
          </div>
        )}
        <button
          onClick={handleSignOut}
          disabled={signoutMutation.isPending}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-text-secondary hover:bg-error/10 hover:text-error-light transition-all duration-150 disabled:opacity-50"
        >
          <SignOutIcon size={ICON_MD} />
          <span>{signoutMutation.isPending ? 'Signing out...' : 'Sign Out'}</span>
        </button>
      </div>
    </aside>
  );
}

export default Sidebar;
