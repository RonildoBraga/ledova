import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { AppState, AppStateStatus } from 'react-native';
import * as LocalAuthentication from 'expo-local-authentication';
import * as SecureStore from 'expo-secure-store';

const STORAGE_KEY = 'settings.biometricsEnabled';
const BIOMETRIC_LOGIN_KEY = 'settings.biometricLoginEnabled';
const SAVED_EMAIL_KEY = 'credentials.email';
const SAVED_PASSWORD_KEY = 'credentials.password';
const AUTH_TOKEN_KEY = 'accessToken';
const LOCK_DELAY_MS = 3000; // Lock after 3 seconds in background

interface SavedCredentials {
  email: string;
  password: string;
}

interface AppLockContextType {
  // App Lock (session protection)
  isLocked: boolean;
  isEnabled: boolean;
  unlock: () => Promise<boolean>;
  setEnabled: (enabled: boolean) => Promise<boolean>;

  // Biometric Login (credential storage)
  biometricLoginEnabled: boolean;
  hasSavedCredentials: boolean;
  setBiometricLoginEnabled: (enabled: boolean) => Promise<boolean>;
  saveCredentials: (email: string, password: string) => Promise<void>;
  clearCredentials: () => Promise<void>;
  getBiometricCredentials: () => Promise<SavedCredentials | null>;

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
  const [biometricLoginEnabled, setBiometricLoginEnabledState] = useState(false);
  const [hasSavedCredentials, setHasSavedCredentials] = useState(false);

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

      // Load biometric login preference
      const biometricLoginSaved = await SecureStore.getItemAsync(BIOMETRIC_LOGIN_KEY);
      const biometricLoginEnabledValue = biometricLoginSaved === 'true';
      setBiometricLoginEnabledState(biometricLoginEnabledValue);

      // Check for saved credentials
      const savedEmail = await SecureStore.getItemAsync(SAVED_EMAIL_KEY);
      const savedPassword = await SecureStore.getItemAsync(SAVED_PASSWORD_KEY);
      const hasCredentials = !!(savedEmail && savedPassword);
      setHasSavedCredentials(hasCredentials);
    } catch {
      // Silently handle preference loading errors
    }
  }, []);

  // Check if user is logged in
  const isUserLoggedIn = useCallback(async (): Promise<boolean> => {
    try {
      const token = await SecureStore.getItemAsync(AUTH_TOKEN_KEY);
      return !!token;
    } catch {
      return false;
    }
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

  // Save credentials for biometric login
  const saveCredentials = useCallback(async (email: string, password: string): Promise<void> => {
    await SecureStore.setItemAsync(SAVED_EMAIL_KEY, email);
    await SecureStore.setItemAsync(SAVED_PASSWORD_KEY, password);
    await SecureStore.setItemAsync(BIOMETRIC_LOGIN_KEY, 'true');
    setBiometricLoginEnabledState(true);
    setHasSavedCredentials(true);
  }, []);

  // Clear saved credentials
  const clearCredentials = useCallback(async (): Promise<void> => {
    try {
      await SecureStore.deleteItemAsync(SAVED_EMAIL_KEY);
      await SecureStore.deleteItemAsync(SAVED_PASSWORD_KEY);
      await SecureStore.setItemAsync(BIOMETRIC_LOGIN_KEY, 'false');
      setBiometricLoginEnabledState(false);
      setHasSavedCredentials(false);
    } catch {
      // Silently handle credential clearing errors
    }
  }, []);

  // Get credentials after biometric authentication
  const getBiometricCredentials = useCallback(async (): Promise<SavedCredentials | null> => {
    // Prevent multiple simultaneous auth attempts
    if (isAuthenticating.current) {
      return null;
    }

    isAuthenticating.current = true;

    try {
      // First, verify with biometrics
      const result = await LocalAuthentication.authenticateAsync({
        promptMessage: `Sign in with ${biometricType}`,
        fallbackLabel: 'Use passcode',
        disableDeviceFallback: false,
      });

      if (!result.success) {
        return null;
      }

      // If successful, retrieve credentials
      const email = await SecureStore.getItemAsync(SAVED_EMAIL_KEY);
      const password = await SecureStore.getItemAsync(SAVED_PASSWORD_KEY);

      if (email && password) {
        justUnlocked.current = true;
        setTimeout(() => {
          justUnlocked.current = false;
        }, 2000);

        return { email, password };
      }

      return null;
    } catch {
      return null;
    } finally {
      isAuthenticating.current = false;
    }
  }, [biometricType]);

  // Enable/disable biometric login
  const setBiometricLoginEnabled = useCallback(
    async (enabled: boolean): Promise<boolean> => {
      if (enabled) {
        // To enable, we need to verify biometrics first (credentials should be saved separately)
        if (isAuthenticating.current) {
          return false;
        }

        isAuthenticating.current = true;

        try {
          const result = await LocalAuthentication.authenticateAsync({
            promptMessage: `Enable ${biometricType} sign in`,
            fallbackLabel: 'Use passcode',
            disableDeviceFallback: false,
          });

          if (result.success) {
            await SecureStore.setItemAsync(BIOMETRIC_LOGIN_KEY, 'true');
            setBiometricLoginEnabledState(true);
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
        // Disable and clear credentials
        await clearCredentials();
        return true;
      }
    },
    [biometricType, clearCredentials],
  );

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
        biometricLoginEnabled,
        hasSavedCredentials,
        setBiometricLoginEnabled,
        saveCredentials,
        clearCredentials,
        getBiometricCredentials,

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
