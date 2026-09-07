import { Navigate } from 'react-router-dom';

import { useAuth } from '@hooks';

export function RootRedirect() {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return null;
  if (isAuthenticated) return <Navigate to="/home" replace />;
  return <Navigate to="/signin" replace />;
}
