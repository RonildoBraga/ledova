import { Routes, Route, Navigate } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useAuth, useFeatureFlags } from '@hooks';
import NotFoundPage from '@pages/NotFound';
import HomePage from '@pages/home';

const MARKETING_URL = import.meta.env.VITE_MARKETING_URL || 'http://localhost:5173';
import SignInPage from '@pages/signin';
import { SignupUser } from '@pages/signup/user';
import { SignupEmailConfirmation } from '@pages/signup/email-confirmation';
import { SignupPreScreening } from '@pages/signup/pre-screening';
import { SignupIdentityVerification } from '@pages/signup/identity-verification';
import { SignupUserProfile } from '@pages/signup/user-profile/SignupUserProfile';
import { SignupFinancialProfile } from '@pages/signup/financial-profile';
import { SignupReview } from '@pages/signup/review';
import UserProfilePage from '@pages/user-profile';
import WalletsPage from '@pages/wallets';
import TransactionsPage from '@pages/transactions';
import AssetPricesPage from '@pages/asset-prices';
import SettingsPage from '@pages/settings';
import TradingPage from '@pages/trading';
import CompanyPage from '@pages/company';

import ListingPage from '@pages/company/listing';
import { SignupAccountType } from '@pages/signup/account-type';
import { SignupCompanyRegistration } from '@pages/signup/company-registration';
import Layout from '@components/Layout';

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-surface-raised">
      <div className="h-8 w-8 border-4 border-brand-subtle border-t-brand rounded-full animate-spin" />
    </div>
  );
}

interface RouteGuardProps {
  children: ReactNode;
}

function ProtectedRoute({ children }: RouteGuardProps) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return <LoadingSpinner />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/signin" replace />;
  }

  return <>{children}</>;
}

function TradingRoute() {
  const { tradingEnabled, isLoading } = useFeatureFlags();

  if (isLoading) {
    return <LoadingSpinner />;
  }

  if (!tradingEnabled) {
    return <Navigate to="/home" replace />;
  }

  return <TradingPage />;
}

function PublicOnlyRoute({ children }: RouteGuardProps) {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return <LoadingSpinner />;
  if (isAuthenticated) return <Navigate to="/home" replace />;
  return <>{children}</>;
}

function RootRedirect() {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return null;
  if (isAuthenticated) return <Navigate to="/home" replace />;
  window.location.href = MARKETING_URL;
  return null;
}

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<RootRedirect />} />

        <Route
          path="/signin"
          element={
            <PublicOnlyRoute>
              <SignInPage />
            </PublicOnlyRoute>
          }
        />

        <Route
          path="/signup"
          element={
            <PublicOnlyRoute>
              <SignupUser />
            </PublicOnlyRoute>
          }
        />
        <Route path="/signup/email-confirmation" element={<SignupEmailConfirmation />} />
        <Route path="/signup/account-type" element={<SignupAccountType />} />
        <Route path="/signup/pre-screening" element={<SignupPreScreening />} />
        <Route path="/signup/identity-verification" element={<SignupIdentityVerification />} />
        <Route path="/signup/user-profile" element={<SignupUserProfile />} />
        <Route path="/signup/financial-profile" element={<SignupFinancialProfile />} />
        <Route path="/signup/company-registration" element={<SignupCompanyRegistration />} />
        <Route path="/signup/review" element={<SignupReview />} />

        <Route
          path="/home"
          element={
            <ProtectedRoute>
              <HomePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/wallets"
          element={
            <ProtectedRoute>
              <WalletsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/transactions"
          element={
            <ProtectedRoute>
              <TransactionsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/asset-prices"
          element={
            <ProtectedRoute>
              <AssetPricesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/settings"
          element={
            <ProtectedRoute>
              <SettingsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/user-profile"
          element={
            <ProtectedRoute>
              <UserProfilePage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/trading"
          element={
            <ProtectedRoute>
              <TradingRoute />
            </ProtectedRoute>
          }
        />
        <Route
          path="/company"
          element={
            <ProtectedRoute>
              <CompanyPage />
            </ProtectedRoute>
          }
        />
        {/* Redirect old standalone routes to company page */}
        <Route path="/company/tokens" element={<Navigate to="/company" replace />} />
        <Route path="/company/shareholders" element={<Navigate to="/company" replace />} />
        <Route path="/company/tokens/:uuid" element={<Navigate to="/company" replace />} />
        <Route
          path="/company/listing"
          element={
            <ProtectedRoute>
              <ListingPage />
            </ProtectedRoute>
          }
        />

        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Layout>
  );
}

export default App;
