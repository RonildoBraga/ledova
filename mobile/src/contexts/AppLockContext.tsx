import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { AppState, AppStateStatus } from 'react-native';
import * as LocalAuthentication from 'expo-local-authentication';
import * as SecureStore from 'expo-secure-store';
import {
  BiometricLoginState,
  deleteBiometricRefreshToken,
  disableBiometricLogin as disableBiometricLoginStorage,
  enableBiometricLogin as enableBiometricLoginStorage,
  getAccessToken,
  getBiometricLoginState,
  readBiometricRefreshToken as readGatedRefreshToken,
} from '../services/tokenStorage';

const STORAGE_KEY = 'settings.biometricsEnabled';
const LOCK_DELAY_MS = 3000;

export type BiometricRefreshTokenResult = { token: string; missing: false } | { token: null; missing: boolean };

interface AppLockContextType {
  isLocked: boolean;
  isEnabled: boolean;
  unlock: () => Promise<boolean>;
  setEnabled: (enabled: boolean) => Promise<boolean>;

  biometricLoginEnabled: boolean;
  hasBiometricLogin: boolean;
  enableBiometricLogin: () => Promise<boolean>;
  disableBiometricLogin: () => Promise<void>;
  readBiometricRefreshToken: () => Promise<BiometricRefreshTokenResult>;
  reloadBiometricLogin: () => Promise<void>;

  biometricsAvailable: boolean;
  biometricType: string;
  checkBiometrics: () => Promise<void>;
}

const AppLockContext = createContext<AppLockContextType | undefined>(undefined);

export function AppLockProvider({ children }: { children: React.ReactNode }) {
  const [isLocked, setIsLocked] = useState(false);
  const [isEnabled, setIsEnabled] = useState(false);

  const [biometricLogin, setBiometricLogin] = useState<BiometricLoginState>({ enabled: false, ready: false });

  const [biometricsAvailable, setBiometricsAvailable] = useState(false);
  const [biometricType, setBiometricType] = useState<string>('Biometrics');
  const [isInitialized, setIsInitialized] = useState(false);

  const appState = useRef(AppState.currentState);
  const backgroundTimestamp = useRef<number | null>(null);
  const isAuthenticating = useRef(false);
  const justUnlocked = useRef(false);

  const checkBiometrics = useCallback(async () => {
    try {
      const compatible = await LocalAuthentication.hasHardwareAsync();
      const enrolled = await LocalAuthentication.isEnrolledAsync();
      const available = compatible && enrolled;
      setBiometricsAvailable(available);

      if (compatible) {
        const types = await LocalAuthentication.supportedAuthenticationTypesAsync();
        if (types.includes(LocalAuthentication.AuthenticationType.FACIAL_RECOGNITION)) {
          setBiometricType('Face ID');
        } else if (types.includes(LocalAuthentication.AuthenticationType.FINGERPRINT)) {
          setBiometricType('Touch ID');
        }
      }
    } catch {
      setBiometricsAvailable(false);
    }
  }, []);

  const loadPreference = useCallback(async () => {
    try {
      const appLockSaved = await SecureStore.getItemAsync(STORAGE_KEY);
      const appLockEnabled = appLockSaved === 'true';
      setIsEnabled(appLockEnabled);

      setBiometricLogin(await getBiometricLoginState());
    } catch {}
  }, []);

  const reloadBiometricLogin = useCallback(async () => {
    try {
      setBiometricLogin(await getBiometricLoginState());
    } catch {}
  }, []);

  const isUserLoggedIn = useCallback(async (): Promise<boolean> => {
    try {
      const token = await getAccessToken();
      return !!token;
    } catch {
      return false;
    }
  }, []);

  const markJustUnlocked = useCallback(() => {
    justUnlocked.current = true;
    setTimeout(() => {
      justUnlocked.current = false;
    }, 2000);
  }, []);

  useEffect(() => {
    const initialize = async () => {
      await checkBiometrics();
      await loadPreference();
      setIsInitialized(true);
    };
    initialize();
  }, [checkBiometrics, loadPreference]);

  useEffect(() => {
    const handleAppStateChange = async (nextAppState: AppStateStatus) => {
      if (appState.current === 'active' && nextAppState.match(/inactive|background/)) {
        backgroundTimestamp.current = Date.now();
      }

      if (appState.current.match(/inactive|background/) && nextAppState === 'active') {
        if (justUnlocked.current) {
          justUnlocked.current = false;
          backgroundTimestamp.current = null;
          appState.current = nextAppState;
          return;
        }

        if (isAuthenticating.current) {
          backgroundTimestamp.current = null;
          appState.current = nextAppState;
          return;
        }

        const wasInBackground = backgroundTimestamp.current !== null;
        const timeInBackground = wasInBackground ? Date.now() - backgroundTimestamp.current! : 0;

        if (isEnabled && wasInBackground && timeInBackground > LOCK_DELAY_MS) {
          const loggedIn = await isUserLoggedIn();
          if (loggedIn) {
            setIsLocked(true);
          }
        }

        backgroundTimestamp.current = null;
      }

      appState.current = nextAppState;
    };

    const subscription = AppState.addEventListener('change', handleAppStateChange);
    return () => subscription.remove();
  }, [isEnabled, isUserLoggedIn]);

  const unlock = useCallback(async (): Promise<boolean> => {
    if (isAuthenticating.current) {
      return false;
    }

    isAuthenticating.current = true;

    try {
      const result = await LocalAuthentication.authenticateAsync({
        promptMessage: `Unlock with ${biometricType}`,
        fallbackLabel: 'Use passcode',
        disableDeviceFallback: false,
      });

      if (result.success) {
        justUnlocked.current = true;
        setIsLocked(false);

        setTimeout(() => {
          justUnlocked.current = false;
        }, 2000);

        return true;
      }
      return false;
    } catch {
      return false;
    } finally {
      isAuthenticating.current = false;
    }
  }, [biometricType]);

  const setEnabled = useCallback(
    async (enabled: boolean): Promise<boolean> => {
      if (isAuthenticating.current) {
        return false;
      }

      if (enabled) {
        isAuthenticating.current = true;

        try {
          const result = await LocalAuthentication.authenticateAsync({
            promptMessage: `Enable ${biometricType}`,
            fallbackLabel: 'Use passcode',
            disableDeviceFallback: false,
          });

          if (result.success) {
            await SecureStore.setItemAsync(STORAGE_KEY, 'true');
            setIsEnabled(true);
            justUnlocked.current = true;

            setTimeout(() => {
              justUnlocked.current = false;
            }, 2000);

            return true;
          }
          return false;
        } finally {
          isAuthenticating.current = false;
        }
      } else {
        await SecureStore.setItemAsync(STORAGE_KEY, 'false');
        setIsEnabled(false);
        setIsLocked(false);
        return true;
      }
    },
    [biometricType],
  );

  const enableBiometricLogin = useCallback(async (): Promise<boolean> => {
    if (isAuthenticating.current) {
      return false;
    }

    isAuthenticating.current = true;

    try {
      const enabled = await enableBiometricLoginStorage();
      setBiometricLogin(await getBiometricLoginState());
      if (enabled) {
        markJustUnlocked();
      }
      return enabled;
    } catch {
      return false;
    } finally {
      isAuthenticating.current = false;
    }
  }, [markJustUnlocked]);

  const disableBiometricLogin = useCallback(async (): Promise<void> => {
    try {
      await disableBiometricLoginStorage();
      setBiometricLogin(await getBiometricLoginState());
    } catch {}
  }, []);

  const readBiometricRefreshToken = useCallback(async (): Promise<BiometricRefreshTokenResult> => {
    if (isAuthenticating.current) {
      return { token: null, missing: false };
    }

    isAuthenticating.current = true;

    try {
      const token = await readGatedRefreshToken(`Sign in with ${biometricType}`);
      if (token) {
        markJustUnlocked();
        return { token, missing: false };
      }

      await deleteBiometricRefreshToken();
      setBiometricLogin(await getBiometricLoginState());
      return { token: null, missing: true };
    } catch {
      return { token: null, missing: false };
    } finally {
      isAuthenticating.current = false;
    }
  }, [biometricType, markJustUnlocked]);

  if (!isInitialized) {
    return null;
  }

  return (
    <AppLockContext.Provider
      value={{
        isLocked,
        isEnabled,
        unlock,
        setEnabled,

        biometricLoginEnabled: biometricLogin.enabled,
        hasBiometricLogin: biometricLogin.ready,
        enableBiometricLogin,
        disableBiometricLogin,
        readBiometricRefreshToken,
        reloadBiometricLogin,

        biometricsAvailable,
        biometricType,
        checkBiometrics,
      }}
    >
      {children}
    </AppLockContext.Provider>
  );
}

export function useAppLock() {
  const context = useContext(AppLockContext);
  if (context === undefined) {
    throw new Error('useAppLock must be used within an AppLockProvider');
  }
  return context;
}
