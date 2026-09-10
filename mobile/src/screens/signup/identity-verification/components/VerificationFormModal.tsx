import React from 'react';
import { View, Modal, ActivityIndicator, Text, TouchableOpacity, Pressable } from 'react-native';
import WebView from 'react-native-webview';
import type { WebViewMessageEvent, WebViewNavigation } from 'react-native-webview';
import { XIcon } from 'phosphor-react-native';
import { overlayColors } from '../../../../contexts';
import { useAppTheme, useThemedStyles } from '../../../../contexts';
import { MARKETING_URL } from '../../../../config/publicLinks';
import { allowWebNavigation } from '../../../../config/networkPolicy';
import { useVerificationFormLifecycle } from './useVerificationFormLifecycle';

interface VerificationFormModalProps {
  visible: boolean;
  accessToken: string | null;
  formUrl: string | null;
  sessionEpoch: number | null;
  onComplete: () => void;
  onClose: () => void;
}

const REDIRECT_HOST = new URL(MARKETING_URL).hostname;

function buildSumsubHtml(token: string, themeColors: { bg: string; muted: string; error: string }): string {
  return `<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body { height: 100%; background: ${themeColors.bg}; overflow: hidden; }
    #sumsub-websdk-container { height: 100%; width: 100%; }
    .status-msg {
      display: flex; height: 100%; justify-content: center; align-items: center;
      font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 14px;
      text-align: center; padding: 20px; flex-direction: column; gap: 12px;
    }
    #loading { color: ${themeColors.muted}; }
    #error { display: none; color: ${themeColors.error}; }
  </style>
</head>
<body>
  <div id="loading" class="status-msg">Loading verification...</div>
  <div id="error" class="status-msg"></div>
  <div id="sumsub-websdk-container"></div>
  <script>
    var ACCESS_TOKEN = ${JSON.stringify(token)};

    function showError() {
      document.getElementById('loading').style.display = 'none';
      var el = document.getElementById('error');
      el.style.display = 'flex';
      el.textContent = 'Verification could not continue. Close this form and try again.';
      if (window.ReactNativeWebView) {
        window.ReactNativeWebView.postMessage(JSON.stringify({ event: 'SDK_ERROR' }));
      }
    }

    function initSdk() {
      try {
        document.getElementById('loading').style.display = 'none';
        if (typeof snsWebSdk === 'undefined') {
          showError();
          return;
        }
        var snsWebSdkInstance = snsWebSdk
          .init(ACCESS_TOKEN, function() {
            return Promise.resolve('');
          })
          .withConf({ lang: 'en', theme: 'dark' })
          .on('idCheck.onApplicantSubmitted', function() {
            window.ReactNativeWebView.postMessage(JSON.stringify({ event: 'FORM_COMPLETED' }));
          })
          .on('idCheck.onError', function() {
            showError();
          })
          .build();
        snsWebSdkInstance.launch('#sumsub-websdk-container');
      } catch(e) {
        showError();
      }
    }

    var script = document.createElement('script');
    script.src = 'https://static.sumsub.com/idensic/static/sns-websdk-builder.js';
    script.onload = initSdk;
    script.onerror = function() { showError(); };
    document.head.appendChild(script);
  </script>
</body>
</html>`;
}

const KYCAID_INJECTED_JS = `
  (function() {
    window.addEventListener('message', function(event) {
      try {
        var data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
        if (data.event === 'FORM_COMPLETED') {
          window.ReactNativeWebView.postMessage(JSON.stringify({ event: 'FORM_COMPLETED' }));
        }
      } catch(e) {}
    });

    var _notified = false;
    function checkForResult() {
      if (_notified) return;
      var text = document.body ? document.body.innerText : '';
      if (text.indexOf('Verification Approved') !== -1 || text.indexOf('Verification Declined') !== -1) {
        _notified = true;
        setTimeout(function() {
          window.ReactNativeWebView.postMessage(JSON.stringify({ event: 'FORM_COMPLETED' }));
        }, 2000);
      }
    }
    if (typeof MutationObserver !== 'undefined') {
      var obs = new MutationObserver(checkForResult);
      obs.observe(document.documentElement, { childList: true, subtree: true });
    }
    setInterval(checkForResult, 1500);
    true;
  })();
`;

export function VerificationFormModal({
  visible,
  accessToken,
  formUrl,
  sessionEpoch,
  onComplete,
  onClose,
}: VerificationFormModalProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    overlay: {
      flex: 1,
      backgroundColor: overlayColors.modal,
      justifyContent: 'center',
      alignItems: 'center',
    },
    modalContainer: {
      width: '95%',
      height: '85%',
      borderRadius: theme.borderRadius.lg,
      shadowColor: theme.colors.utility.black,
      shadowOffset: { width: 0, height: 8 },
      shadowOpacity: 0.5,
      shadowRadius: 12,
      elevation: 10,
    },
    modal: {
      flex: 1,
      backgroundColor: theme.colors.surface.raised,
      borderRadius: theme.borderRadius.lg,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      overflow: 'hidden',
    },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      paddingHorizontal: theme.spacing.md,
      paddingVertical: theme.spacing.md,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.default,
    },
    headerTitle: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    closeButton: {
      position: 'absolute',
      right: theme.spacing.md,
      padding: theme.spacing.xs,
    },
    webviewContainer: {
      flex: 1,
      borderBottomLeftRadius: theme.borderRadius.lg,
      borderBottomRightRadius: theme.borderRadius.lg,
      overflow: 'hidden',
    },
    webview: {
      flex: 1,
      backgroundColor: theme.colors.surface.base,
    },
    loading: {
      flex: 1,
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
  const lifecycle = useVerificationFormLifecycle(visible, accessToken, formUrl, sessionEpoch, onComplete, onClose);

  const handleMessage = (event: WebViewMessageEvent) => {
    if (!lifecycle.isCurrent()) return;
    try {
      const data = JSON.parse(event.nativeEvent.data);
      if (data.event === 'FORM_COMPLETED') {
        lifecycle.complete();
      } else if (data.event === 'SDK_ERROR') {
        console.warn('Identity verification form reported an error.');
      }
    } catch {}
  };

  const handleNavigationStateChange = (navState: WebViewNavigation) => {
    if (!formUrl || !lifecycle.isCurrent()) return;
    try {
      const url = new URL(navState.url);
      if (url.hostname === REDIRECT_HOST || url.hostname === `www.${REDIRECT_HOST}`) {
        lifecycle.complete();
      }
    } catch {}
  };

  const handleLoadError = () => {
    if (lifecycle.isCurrent()) console.warn('Identity verification form could not load.');
  };

  const renderLoadError = () => (
    <View style={styles.loading}>
      <Text style={styles.loadingText}>Could not load verification. Close this form and try again.</Text>
    </View>
  );

  return (
    <Modal visible={lifecycle.admitted} animationType="fade" transparent onRequestClose={lifecycle.close}>
      <Pressable style={styles.overlay} onPress={lifecycle.close}>
        <Pressable style={styles.modalContainer} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modal}>
            <View style={styles.header}>
              <Text style={styles.headerTitle}>Identity Verification</Text>
              <TouchableOpacity onPress={lifecycle.close} style={styles.closeButton} hitSlop={16}>
                <XIcon size={20} color={theme.colors.text.primary} weight="bold" />
              </TouchableOpacity>
            </View>

            <View style={styles.webviewContainer}>
              {lifecycle.admitted && accessToken && allowWebNavigation(MARKETING_URL) ? (
                <WebView
                  key={lifecycle.key}
                  source={{
                    html: buildSumsubHtml(accessToken, {
                      bg: theme.colors.surface.base,
                      muted: theme.colors.text.muted,
                      error: theme.colors.error.light,
                    }),
                    baseUrl: MARKETING_URL,
                  }}
                  style={styles.webview}
                  onMessage={handleMessage}
                  onError={handleLoadError}
                  renderError={renderLoadError}
                  javaScriptEnabled
                  domStorageEnabled
                  mediaPlaybackRequiresUserAction={false}
                  mediaCapturePermissionGrantType="grant"
                  allowsInlineMediaPlayback
                  originWhitelist={['*']}
                  onShouldStartLoadWithRequest={({ url }) => lifecycle.isCurrent() && allowWebNavigation(url)}
                  mixedContentMode="never"
                />
              ) : lifecycle.admitted && formUrl && allowWebNavigation(formUrl) ? (
                <WebView
                  key={lifecycle.key}
                  source={{ uri: formUrl }}
                  originWhitelist={['*']}
                  onShouldStartLoadWithRequest={({ url }) => lifecycle.isCurrent() && allowWebNavigation(url)}
                  mixedContentMode="never"
                  style={styles.webview}
                  injectedJavaScript={KYCAID_INJECTED_JS}
                  onMessage={handleMessage}
                  onError={handleLoadError}
                  renderError={renderLoadError}
                  onNavigationStateChange={handleNavigationStateChange}
                  mediaPlaybackRequiresUserAction={false}
                  mediaCapturePermissionGrantType="grant"
                  allowsInlineMediaPlayback
                  startInLoadingState
                  renderLoading={() => (
                    <View style={styles.loading}>
                      <ActivityIndicator size="large" color={theme.colors.interactive.active} />
                      <Text style={styles.loadingText}>Loading verification...</Text>
                    </View>
                  )}
                />
              ) : (
                <View style={styles.loading}>
                  <ActivityIndicator size="large" color={theme.colors.interactive.active} />
                  <Text style={styles.loadingText}>Loading verification...</Text>
                </View>
              )}
            </View>
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}
