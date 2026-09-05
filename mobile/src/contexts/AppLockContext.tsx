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
const LOCK_DELAY_MS = 3000; // Lock after 3 seconds in background

export type BiometricRefreshTokenResult = { token: string; missing: false } | { token: null; missing: boolean };

interface AppLockContextType {
  // App Lock (session protection)
  isLocked: boolean;
  isEnabled: boolean;
  unlock: () => Promise<boolean>;
  setEnabled: (enabled: boolean) => Promise<boolean>;

  // Biometric Login (a biometric-gated copy of the refresh token; the password is never stored)
  biometricLoginEnabled: boolean;
  hasBiometricLogin: boolean;
  enableBiometricLogin: () => Promise<boolean>;
  disableBiometricLogin: () => Promise<void>;
  readBiometricRefreshToken: () => Promise<BiometricRefreshTokenResult>;
  reloadBiometricLogin: () => Promise<void>;

  // Shared
  biometricsAvailable: boolean;
  biometricType: string;
  checkBiometrics: () => Promise<void>;
}

const AppLockContext = createContext<AppLockContextType | undefined>(undefined);

export function AppLockProvider({ children }: { children: React.ReactNode }) {
  // App Lock state
  const [isLocked, setIsLocked] = useState(false);
  const [isEnabled, setIsEnabled] = useState(false);

  // Biometric Login state
  const [biometricLogin, setBiometricLogin] = useState<BiometricLoginState>({ enabled: false, ready: false });

  // Shared state
  const [biometricsAvailable, setBiometricsAvailable] = useState(false);
  const [biometricType, setBiometricType] = useState<string>('Biometrics');
  const [isInitialized, setIsInitialized] = useState(false);

  const appState = useRef(AppState.currentState);
  const backgroundTimestamp = useRef<number | null>(null);
  const isAuthenticating = useRef(false);
  const justUnlocked = useRef(false);

  // Check biometric capabilities
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

  // Load saved preferences
  const loadPreference = useCallback(async () => {
    try {
      // Load app lock preference
      const appLockSaved = await SecureStore.getItemAsync(STORAGE_KEY);
      const appLockEnabled = appLockSaved === 'true';
      setIsEnabled(appLockEnabled);

      // Load the biometric login preference and whether a gated refresh token is on the device
      setBiometricLogin(await getBiometricLoginState());
    } catch {
      // Silently handle preference loading errors
    }
  }, []);

  // Re-read after sign-out or a failed biometric sign in changed what is on the device
  const reloadBiometricLogin = useCallback(async () => {
    try {
      setBiometricLogin(await getBiometricLoginState());
    } catch {
      // Keep the last known state
    }
  }, []);

  // Check if user is logged in
  const isUserLoggedIn = useCallback(async (): Promise<boolean> => {
    try {
      const token = await getAccessToken();
      return !!token;
    } catch {
      return false;
    }
  }, []);

  // A system prompt sends the app through inactive/active; don't treat the return as a background lock
  const markJustUnlocked = useCallback(() => {
    justUnlocked.current = true;
    setTimeout(() => {
      justUnlocked.current = false;
    }, 2000);
  }, []);

  // Initialize on mount
  useEffect(() => {
    const initialize = async () => {
      await checkBiometrics();
      await loadPreference();
      setIsInitialized(true);
    };
    initialize();
  }, [checkBiometrics, loadPreference]);

  // Handle app state changes
  useEffect(() => {
    const handleAppStateChange = async (nextAppState: AppStateStatus) => {
      // App going to background
      if (appState.current === 'active' && nextAppState.match(/inactive|background/)) {
        backgroundTimestamp.current = Date.now();
      }

      // App coming to foreground
      if (appState.current.match(/inactive|background/) && nextAppState === 'active') {
        // Don't lock if we just unlocked (prevents infinite loop)
        if (justUnlocked.current) {
          justUnlocked.current = false;
          backgroundTimestamp.current = null;
          appState.current = nextAppState;
          return;
        }

        // Don't lock if currently authenticating
        if (isAuthenticating.current) {
          backgroundTimestamp.current = null;
          appState.current = nextAppState;
          return;
        }

        const wasInBackground = backgroundTimestamp.current !== null;
        const timeInBackground = wasInBackground ? Date.now() - backgroundTimestamp.current! : 0;

        // Lock if enabled and was in background for more than LOCK_DELAY_MS
        if (isEnabled && wasInBackground && timeInBackground > LOCK_DELAY_MS) {
          // Only lock if user is logged in
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

  // Unlock with biometrics
  const unlock = useCallback(async (): Promise<boolean> => {
    // Prevent multiple simultaneous auth attempts
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

        // Reset justUnlocked after a delay
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

  // Enable/disable app lock
  const setEnabled = useCallback(
    async (enabled: boolean): Promise<boolean> => {
      // Prevent auth during toggle
      if (isAuthenticating.current) {
        return false;
      }

      if (enabled) {
        // Verify biometrics before enabling
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

            // Reset justUnlocked after a delay
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

  // Store a biometric-gated copy of the current session's refresh token
  const enableBiometricLogin = useCallback(async (): Promise<boolean> => {
    // Prevent auth during the gated write (Android shows the system prompt for it)
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

  // Delete the gated copy and remember the choice
  const disableBiometricLogin = useCallback(async (): Promise<void> => {
    try {
      await disableBiometricLoginStorage();
      setBiometricLogin(await getBiometricLoginState());
    } catch {
      // Silently handle storage errors
    }
  }, []);

  // Unlock the gated refresh token with the OS prompt
  const readBiometricRefreshToken = useCallback(async (): Promise<BiometricRefreshTokenResult> => {
    // Prevent multiple simultaneous auth attempts
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

      // No entry, or the OS invalidated it after the enrolled biometrics changed
      await deleteBiometricRefreshToken();
      setBiometricLogin(await getBiometricLoginState());
      return { token: null, missing: true };
    } catch {
      // The user cancelled or failed the OS prompt
      return { token: null, missing: false };
    } finally {
      isAuthenticating.current = false;
    }
  }, [biometricType, markJustUnlocked]);

  // Don't render children until initialized
  if (!isInitialized) {
    return null;
  }

  return (
    <AppLockContext.Provider
      value={{
        // App Lock
        isLocked,
        isEnabled,
        unlock,
        setEnabled,

        // Biometric Login
        biometricLoginEnabled: biometricLogin.enabled,
        hasBiometricLogin: biometricLogin.ready,
        enableBiometricLogin,
        disableBiometricLogin,
        readBiometricRefreshToken,
        reloadBiometricLogin,

        // Shared
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
