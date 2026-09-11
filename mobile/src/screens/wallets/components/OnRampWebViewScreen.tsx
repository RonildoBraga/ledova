import React, { useLayoutEffect, useMemo, useReducer, useRef } from 'react';
import { View, ActivityIndicator, Text } from 'react-native';
import { useIsFocused, useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import { invalidateHomeDashboard } from '../../../utils/queryInvalidation';
import WebView from 'react-native-webview';
import type { WebViewMessageEvent } from 'react-native-webview';
import { GradientBackground } from '../../../components/GradientBackground';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { allowWebNavigation } from '../../../config/networkPolicy';
import { createProviderLifetime, useProviderViewLifecycle } from '../../../hooks/useProviderViewLifecycle';

export interface OnRampWebViewParams {
  url: string;
  sessionEpoch: number;
}

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
  const { url, sessionEpoch } = route.params;
  const focused = useIsFocused();
  const blurRevision = useRef(0);
  const [navigationRevision, refreshNavigation] = useReducer((value: number) => value + 1, 0);
  const capturedRevision = blurRevision.current;
  const outcome = useMemo(() => ({ url, sessionEpoch, lifetime: createProviderLifetime() }), [url, sessionEpoch]);
  const safeUrl = allowWebNavigation(url) ? url : null;

  useLayoutEffect(
    () =>
      navigation.addListener('blur', () => {
        blurRevision.current += 1;
        refreshNavigation();
      }),
    [navigation],
  );

  const handleComplete = () => {
    outcome.lifetime.retire();
    queryClient.invalidateQueries({ queryKey: ['wallets'] });
    invalidateHomeDashboard(queryClient);
    handleClose();
  };

  const handleClose = () => {
    outcome.lifetime.retire();
    if (navigation.canGoBack()) {
      navigation.goBack();
    }
  };

  const lifecycle = useProviderViewLifecycle(focused, null, safeUrl, sessionEpoch, handleComplete, handleClose);
  const isCurrent = () =>
    outcome.lifetime.isActive() &&
    capturedRevision === blurRevision.current &&
    navigation.isFocused() &&
    lifecycle.isCurrent();

  const handleMessage = (event: WebViewMessageEvent) => {
    if (!isCurrent()) return;
    try {
      const data = JSON.parse(event.nativeEvent.data);
      if (data.event_id === 'TRANSAK_ORDER_SUCCESSFUL') {
        lifecycle.complete();
      } else if (data.event_id === 'TRANSAK_WIDGET_CLOSE') {
        lifecycle.close();
      }
    } catch {}
  };

  const handleLoadError = () => {
    if (isCurrent()) console.warn('The purchase provider could not load.');
  };

  return (
    <GradientBackground>
      <View style={styles.container}>
        {!safeUrl ? (
          <Text>Unable to open an insecure provider URL.</Text>
        ) : !lifecycle.admitted || !outcome.lifetime.isActive() ? (
          <Text>Provider view paused.</Text>
        ) : (
          <WebView
            key={`${lifecycle.key}:${navigationRevision}`}
            source={{ uri: safeUrl }}
            originWhitelist={['*']}
            onShouldStartLoadWithRequest={({ url }) => isCurrent() && allowWebNavigation(url)}
            mixedContentMode="never"
            style={styles.webview}
            injectedJavaScript={INJECTED_JS}
            onMessage={handleMessage}
            onError={handleLoadError}
            renderError={() => <Text>Could not load the purchase provider. Go back and try again.</Text>}
            startInLoadingState
            renderLoading={() => (
              <View style={styles.loading}>
                <ActivityIndicator size="large" color={theme.colors.interactive.active} />
                <Text style={styles.loadingText}>Loading...</Text>
              </View>
            )}
          />
        )}
      </View>
    </GradientBackground>
  );
}
