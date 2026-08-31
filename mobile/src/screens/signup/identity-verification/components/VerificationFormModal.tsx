import React, { useRef, useCallback } from 'react';
import { View, Modal, ActivityIndicator, Text, TouchableOpacity, Pressable } from 'react-native';
import WebView from 'react-native-webview';
import type { WebViewMessageEvent, WebViewNavigation } from 'react-native-webview';
import { XIcon } from 'phosphor-react-native';
import { overlayColors } from '../../../../contexts';
import { useAppTheme, useThemedStyles } from '../../../../contexts';
import { MARKETING_URL } from '../../../../config/publicLinks';

interface VerificationFormModalProps {
  visible: boolean;
  accessToken: string | null;
  formUrl: string | null;
  onComplete: () => void;
  onClose: () => void;
}

/** Redirect URL configured in the KYCAID form. When the form redirects here, verification is done. */
const REDIRECT_HOST = new URL(MARKETING_URL).hostname;

/**
 * Build HTML page that loads the Sumsub WebSDK via CDN and initialises it with the access token.
 * Uses dynamic script loading with onload/onerror to handle WebView constraints.
 * On `idCheck.onApplicantSubmitted` it posts `{ event: 'FORM_COMPLETED' }` to ReactNativeWebView.
 */
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

    function showError(msg) {
      document.getElementById('loading').style.display = 'none';
      var el = document.getElementById('error');
      el.style.display = 'flex';
      el.textContent = msg;
      if (window.ReactNativeWebView) {
        window.ReactNativeWebView.postMessage(JSON.stringify({ event: 'SDK_ERROR', message: msg }));
      }
    }

    function initSdk() {
      try {
        document.getElementById('loading').style.display = 'none';
        if (typeof snsWebSdk === 'undefined') {
          showError('SDK failed to initialize');
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
          .on('idCheck.onError', function(error) {
            showError('Verification error: ' + (error && error.message ? error.message : 'Unknown error'));
          })
          .build();
        snsWebSdkInstance.launch('#sumsub-websdk-container');
      } catch(e) {
        showError('Failed to start: ' + e.message);
      }
    }

    // Dynamically load the SDK script to get proper onload/onerror callbacks
    var script = document.createElement('script');
    script.src = 'https://static.sumsub.com/idensic/static/sns-websdk-builder.js';
    script.onload = initSdk;
    script.onerror = function() { showError('Failed to load verification SDK. Check your internet connection.'); };
    document.head.appendChild(script);
  </script>
</body>
</html>`;
}

/**
 * JS injected into the KYCAID WebView to listen for form completion events.
 */
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
  const completedRef = useRef(false);

  const triggerComplete = useCallback(() => {
    if (completedRef.current) return;
    completedRef.current = true;
    onComplete();
  }, [onComplete]);

  // Reset completion flag when modal opens
  React.useEffect(() => {
    if (visible && (accessToken || formUrl)) {
      completedRef.current = false;
    }
  }, [visible, accessToken, formUrl]);

  const handleMessage = (event: WebViewMessageEvent) => {
    try {
      const data = JSON.parse(event.nativeEvent.data);
      if (data.event === 'FORM_COMPLETED') {
        triggerComplete();
      } else if (data.event === 'SDK_ERROR') {
        // Error is displayed inside the WebView HTML — don't auto-close
        console.warn('[VerificationFormModal] SDK error:', data.message);
      }
    } catch {
      // Ignore non-JSON messages
    }
  };

  const handleNavigationStateChange = (navState: WebViewNavigation) => {
    // KYCAID redirect detection
    if (!formUrl) return;
    try {
      const url = new URL(navState.url);
      if (url.hostname === REDIRECT_HOST || url.hostname === `www.${REDIRECT_HOST}`) {
        triggerComplete();
      }
    } catch {
      // Ignore invalid URLs
    }
  };

  return (
    <Modal visible={visible} animationType="fade" transparent onRequestClose={onClose}>
      {/* Overlay — only direct taps on the backdrop close the modal */}
      <Pressable style={styles.overlay} onPress={onClose}>
        <Pressable style={styles.modalContainer} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modal}>
            {/* Header */}
            <View style={styles.header}>
              <Text style={styles.headerTitle}>Identity Verification</Text>
              <TouchableOpacity onPress={onClose} style={styles.closeButton} hitSlop={16}>
                <XIcon size={20} color={theme.colors.text.primary} weight="bold" />
              </TouchableOpacity>
            </View>

            {/* WebView */}
            <View style={styles.webviewContainer}>
              {accessToken ? (
                <WebView
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
                  javaScriptEnabled
                  domStorageEnabled
                  mediaPlaybackRequiresUserAction={false}
                  mediaCapturePermissionGrantType="grant"
                  allowsInlineMediaPlayback
                  originWhitelist={['*']}
                  mixedContentMode="compatibility"
                />
              ) : formUrl ? (
                <WebView
                  source={{ uri: formUrl }}
                  style={styles.webview}
                  injectedJavaScript={KYCAID_INJECTED_JS}
                  onMessage={handleMessage}
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
