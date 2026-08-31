import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { AppNavigator } from './src/navigation/AppNavigator';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppLockProvider, ThemeProvider } from './src/contexts';
import { AppLockScreen } from './src/components/app-lock';
import { ErrorBoundary } from './src/components/ErrorBoundary';
// Import apiClient to ensure it's initialized and configures auth service
import './src/services/apiClient';
import { notificationsService } from './src/services/notificationsService';

// Configure notification handler early
notificationsService.configure();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export default function App() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <ErrorBoundary>
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <AppLockProvider>
              <AppNavigator />
              <AppLockScreen />
              <StatusBar style="auto" />
            </AppLockProvider>
          </ThemeProvider>
        </QueryClientProvider>
      </ErrorBoundary>
    </GestureHandlerRootView>
  );
}
