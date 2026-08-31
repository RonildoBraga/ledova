import React, { createContext, useContext, useState, useCallback, useMemo } from 'react';
import { Animated, View, StyleSheet, Pressable } from 'react-native';
import { overlayColors } from '../contexts';

interface DrawerContextValue {
  openDrawer: () => void;
  closeDrawer: () => void;
  isOpen: boolean;
}

const DrawerContext = createContext<DrawerContextValue | null>(null);

export function useDrawer() {
  const ctx = useContext(DrawerContext);
  if (!ctx) throw new Error('useDrawer must be used within DrawerProvider');
  return ctx;
}

const DRAWER_WIDTH = 280;

export function DrawerProvider({
  children,
  renderMenu,
}: {
  children: React.ReactNode;
  renderMenu: () => React.ReactNode;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [slideAnim] = useState(() => new Animated.Value(-DRAWER_WIDTH));
  const [overlayAnim] = useState(() => new Animated.Value(0));

  const openDrawer = useCallback(() => {
    setIsOpen(true);
    Animated.parallel([
      Animated.timing(slideAnim, {
        toValue: 0,
        duration: 250,
        useNativeDriver: true,
      }),
      Animated.timing(overlayAnim, {
        toValue: 1,
        duration: 250,
        useNativeDriver: true,
      }),
    ]).start();
  }, [slideAnim, overlayAnim]);

  const closeDrawer = useCallback(() => {
    Animated.parallel([
      Animated.timing(slideAnim, {
        toValue: -DRAWER_WIDTH,
        duration: 200,
        useNativeDriver: true,
      }),
      Animated.timing(overlayAnim, {
        toValue: 0,
        duration: 200,
        useNativeDriver: true,
      }),
    ]).start(() => setIsOpen(false));
  }, [slideAnim, overlayAnim]);

  const value = useMemo(() => ({ openDrawer, closeDrawer, isOpen }), [openDrawer, closeDrawer, isOpen]);

  return (
    <DrawerContext.Provider value={value}>
      {children}
      {isOpen && (
        <View style={StyleSheet.absoluteFill} pointerEvents="box-none">
          <Pressable style={StyleSheet.absoluteFill} onPress={closeDrawer}>
            <Animated.View style={[styles.overlay, { opacity: overlayAnim }]} />
          </Pressable>
          <Animated.View style={[styles.drawerPanel, { transform: [{ translateX: slideAnim }] }]}>
            {renderMenu()}
          </Animated.View>
        </View>
      )}
    </DrawerContext.Provider>
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: overlayColors.modal,
  },
  drawerPanel: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: DRAWER_WIDTH,
  },
});
