import { useEffect, useRef } from 'react';
import { AppState } from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import * as SecureStore from 'expo-secure-store';
import EventSource from 'react-native-sse';
import { TRADING_ENDPOINTS, TRADING_CONFIG, TRADING_EVENT_INVALIDATION_MAP } from '@ledova/shared';
import type { TradingEventType } from '@ledova/shared';

type SSEEventTypes = TradingEventType | 'connected';

export function useTradingEvents(tokenUuid: string | null | undefined) {
  const queryClient = useQueryClient();
  const esRef = useRef<EventSource<SSEEventTypes> | null>(null);
  const reconnectDelayRef = useRef<number>(TRADING_CONFIG.SSE_RECONNECT_DELAY);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    async function connect() {
      if (!tokenUuid) return;

      // Close previous connection
      esRef.current?.close();

      const accessToken = await SecureStore.getItemAsync('accessToken');
      if (!accessToken) return;

      const baseUrl = (process.env.EXPO_PUBLIC_API_URL || '').replace(/\/$/, '');
      const url = `${baseUrl}${TRADING_ENDPOINTS.EVENTS.STREAM}?token=${tokenUuid}`;

      const es = new EventSource<SSEEventTypes>(url, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });

      es.addEventListener('open', () => {
        reconnectDelayRef.current = TRADING_CONFIG.SSE_RECONNECT_DELAY;
      });

      // Listen for each trading event type and invalidate the corresponding queries
      for (const [eventType, queryKeys] of Object.entries(TRADING_EVENT_INVALIDATION_MAP)) {
        es.addEventListener(eventType as TradingEventType, () => {
          for (const queryKey of queryKeys) {
            queryClient.invalidateQueries({ queryKey });
          }
        });
      }

      es.addEventListener('error', () => {
        es.close();
        reconnectTimeoutRef.current = setTimeout(() => {
          reconnectDelayRef.current = Math.min(reconnectDelayRef.current * 2, TRADING_CONFIG.SSE_MAX_RECONNECT_DELAY);
          connect();
        }, reconnectDelayRef.current);
      });

      esRef.current = es;
    }

    connect();

    // Reconnect when app comes to foreground
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') {
        esRef.current?.close();
        connect();
      }
    });

    return () => {
      esRef.current?.close();
      esRef.current = null;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      sub.remove();
    };
  }, [tokenUuid, queryClient]);
}
