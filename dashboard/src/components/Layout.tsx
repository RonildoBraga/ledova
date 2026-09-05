import { Sidebar } from './Sidebar';
import { DesktopHeader } from './DesktopHeader';
import { MobileHeader } from './MobileHeader';
import Footer from './Footer';
import { useLocation } from 'react-router-dom';
import type { LayoutProps } from '@ledova/shared-types';
import { gradients } from '../styles/theme';
import { HeaderActionsProvider } from '@hooks/useHeaderActions';
import { BuyCryptoProvider } from '@hooks/useBuyCrypto';
import { SendTransferProvider } from '@hooks/useSendTransfer';
import { PageTitleContext, usePageTitleProvider } from '@hooks/usePageTitle';

export default function Layout({ children }: LayoutProps) {
  const location = useLocation();

  const pageTitleCtx = usePageTitleProvider();

  const isPublicPage =
    location.pathname === '/' || location.pathname === '/signin' || location.pathname.startsWith('/signup');

  if (isPublicPage) {
    return (
      <div className="relative flex flex-col min-h-screen min-w-[390px]">
        <div className="fixed inset-0 -z-10" style={{ background: gradients.appBackground }} />
        <div className="fixed inset-0 -z-10 opacity-10" style={{ background: gradients.accentOverlay }} />
        <div className="flex-grow">{children}</div>
        <Footer />
      </div>
    );
  }

  return (
    <PageTitleContext.Provider value={pageTitleCtx}>
      <HeaderActionsProvider>
        <BuyCryptoProvider>
          <SendTransferProvider>
            <div className="relative flex min-h-screen min-w-[390px]">
              <div className="fixed inset-0 -z-10" style={{ background: gradients.appBackground }} />
              <div className="fixed inset-0 -z-10 opacity-10" style={{ background: gradients.accentOverlay }} />

              <div className="hidden lg:block">
                <div className="fixed left-0 top-0 bottom-0 z-40">
                  <Sidebar />
                </div>
              </div>

              <div className="fixed top-0 left-0 right-0 z-40 lg:hidden">
                <MobileHeader />
              </div>

              <div className="flex-1 flex flex-col lg:ml-60">
                <div className="hidden lg:block">
                  <DesktopHeader />
                </div>

                <main className="flex-grow pt-16 lg:pt-0">{children}</main>
                <Footer minimal />
              </div>
            </div>
          </SendTransferProvider>
        </BuyCryptoProvider>
      </HeaderActionsProvider>
    </PageTitleContext.Provider>
  );
}
