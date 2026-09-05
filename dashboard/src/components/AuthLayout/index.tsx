import { ReactNode } from 'react';
import { BrandingPanel } from './BrandingPanel';

interface AuthLayoutProps {
  children: ReactNode;
}

export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="min-h-screen flex flex-col lg:flex-row">
      <div className="hidden lg:flex lg:w-1/2 lg:min-h-screen">
        <BrandingPanel />
      </div>

      <div className="flex-1 flex flex-col justify-center py-12 lg:py-0">
        <div className="w-full max-w-lg mx-auto px-4 sm:px-6 lg:px-8">{children}</div>
      </div>
    </div>
  );
}
