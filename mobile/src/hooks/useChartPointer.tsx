import { useEffect, useRef, useMemo } from 'react';
import { View } from 'react-native';
import { useAppTheme } from '../contexts';

interface UseChartPointerOptions {
  onActivePointChange?: (index: number) => void;
  initialPointerIndex?: number;
  dataLength?: number;
}

export function useChartPointer({ onActivePointChange, initialPointerIndex, dataLength }: UseChartPointerOptions) {
  const theme = useAppTheme();
  const lastIndexRef = useRef(-1);
  const mountedRef = useRef(true);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const pointerConfig = useMemo(
    () => ({
      persistPointer: true,
      ...(initialPointerIndex != null ? { initialPointerIndex } : {}),
      pointerStripColor: theme.colors.chartUI.pointerStrip,
      pointerStripWidth: 1,
      stripOverPointer: false,
      radius: 4,
      pointerLabelWidth: 0,
      pointerLabelHeight: 0,
      pointerLabelComponent: (_items: unknown, _secondary: unknown, pointerIndex: number) => {
        const inBounds = dataLength == null || (pointerIndex >= 0 && pointerIndex < dataLength);
        if (inBounds && lastIndexRef.current !== pointerIndex) {
          lastIndexRef.current = pointerIndex;
          setTimeout(() => {
            if (mountedRef.current) onActivePointChange?.(pointerIndex);
          }, 0);
        }
        return <View />;
      },
    }),
    [initialPointerIndex, dataLength, onActivePointChange, theme.colors.chartUI.pointerStrip],
  );

  return pointerConfig;
}
