import React from 'react';
import { View, ActivityIndicator, Text } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateHomeDashboard } from '../../../utils/queryInvalidation';
import WebView from 'react-native-webview';
import type { WebViewMessageEvent } from 'react-native-webview';
import { GradientBackground } from '../../../components/GradientBackground';
import { useAppTheme, useThemedStyles } from '../../../contexts';

export interface OnRampWebViewParams {
  url: string;
}

/**
 * JS injected into the Transak WebView to listen for order events.
 * Transak dispatches events via window.postMessage internally.
 * We intercept them and forward to React Native via window.ReactNativeWebView.postMessage().
 */
const INJECTED_JS = `
  (function() {
    window.addEventListener('message', function(event) {
      try {
        var data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
        var eventId = data && data.event_id;
        if (eventId === 'TRANSAK_ORDER_SUCCESSFUL' || eventId === 'TRANSAK_WIDGET_CLOSE') {
          window.ReactNativeWebView.postMessage(JSON.stringify({ event_id: eventId }));
        }
      } catch(e) {}
    });
    true;
  })();
`;

export function OnRampWebViewScreen() {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      flex: 1,
    },
    webview: {
      flex: 1,
    },
    loading: {
      position: 'absolute',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      justifyContent: 'center',
      alignItems: 'center',
      gap: theme.spacing.md,
      backgroundColor: theme.colors.surface.base,
    },
    loadingText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
  }));
  const navigation = useNavigation();
  const route = useRoute<RouteProp<{ OnRampWebView: OnRampWebViewParams }, 'OnRampWebView'>>();
  const queryClient = useQueryClient();
  const { url } = route.params;

  const handleComplete = () => {
    queryClient.invalidateQueries({ queryKey: ['wallets'] });
    invalidateHomeDashboard(queryClient);
    if (navigation.canGoBack()) {
      navigation.goBack();
    }
  };

  const handleMessage = (event: WebViewMessageEvent) => {
    try {
      const data = JSON.parse(event.nativeEvent.data);
      if (data.event_id === 'TRANSAK_ORDER_SUCCESSFUL') {
        handleComplete();
      } else if (data.event_id === 'TRANSAK_WIDGET_CLOSE') {
        if (navigation.canGoBack()) {
          navigation.goBack();
        }
      }
    } catch {
      // Ignore non-JSON messages
    }
  };

  return (
    <GradientBackground>
      <View style={styles.container}>
        <WebView
          source={{ uri: url }}
          style={styles.webview}
          injectedJavaScript={INJECTED_JS}
          onMessage={handleMessage}
          startInLoadingState
          renderLoading={() => (
            <View style={styles.loading}>
              <ActivityIndicator size="large" color={theme.colors.interactive.active} />
              <Text style={styles.loadingText}>Loading...</Text>
            </View>
          )}
        />
      </View>
    </GradientBackground>
  );
}
