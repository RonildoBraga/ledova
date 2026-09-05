import { useState, useEffect, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import { ListIcon, XIcon } from '@phosphor-icons/react';
import { usePageTitle } from '@hooks/usePageTitle';
import { NotificationBell } from '@components/NotificationBell';
import { Sidebar } from '@components/Sidebar';
import { DESIGN_TOKENS } from '@ledova/shared';

const ICON_MD = DESIGN_TOKENS.icon.sizes.md;

export function MobileHeader() {
  const [isOpen, setIsOpen] = useState(false);
  const { title: pageTitle } = usePageTitle();
  const location = useLocation();

  // Close drawer on route change
  useEffect(() => {
    setIsOpen(false);
  }, [location.pathname]);

  const handleClose = useCallback(() => setIsOpen(false), []);

  return (
    <>
      {/* Top bar */}
      <div className="bg-surface-base/95 backdrop-blur-md">
        <div className="w-full max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="relative">
            <div className="flex items-center h-14">
              <button
                onClick={() => setIsOpen(true)}
                className="inline-flex items-center justify-center w-10 h-10 rounded-full text-text-muted hover:text-text-primary hover:bg-surface-raised/50 focus:outline-none focus:ring-2 focus:ring-brand-mid/30 transition-all duration-200"
                aria-label="Open navigation"
              >
                <ListIcon size={ICON_MD} />
              </button>

              <div className="flex-1 flex justify-center">
                <h1 className="text-base font-normal text-text-secondary tracking-wide">{pageTitle}</h1>
              </div>

              <NotificationBell iconSize={ICON_MD} />
            </div>
            <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-border-subtle to-transparent" />
          </div>
        </div>
      </div>

      {/* Backdrop */}
      <div
        className={`fixed inset-0 z-50 bg-black/40 backdrop-blur-sm transition-opacity duration-300 ${
          isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
        onClick={handleClose}
        aria-hidden="true"
      />

      {/* Slide-out drawer */}
      <div
        className={`fixed inset-y-0 left-0 z-50 w-60 transform transition-transform duration-300 ease-out ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Close button overlaid on top-right of drawer */}
        <button
          onClick={handleClose}
          className="absolute top-4 right-3 z-10 inline-flex items-center justify-center w-8 h-8 rounded-full text-text-muted hover:text-text-primary hover:bg-surface-raised/50 transition-all duration-200"
          aria-label="Close navigation"
        >
          <XIcon size={ICON_MD} />
        </button>

        <Sidebar onNavigate={handleClose} />
      </div>
    </>
  );
}

export default MobileHeader;
