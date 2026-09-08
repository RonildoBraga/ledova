import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';

import { useAuth } from '@hooks/useAuth';

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading, isFetching } = useAuth();

  if (isLoading || (!isAuthenticated && isFetching)) {
    return (
      <div
        role="status"
        aria-label="Checking your session"
        className="flex items-center justify-center min-h-screen bg-surface-raised"
      >
        <div className="h-8 w-8 border-4 border-brand-subtle border-t-brand rounded-full animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) return <Navigate to="/signin" replace />;

  return <>{children}</>;
}
