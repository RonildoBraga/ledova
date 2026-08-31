import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { BuyScreen } from '../screens/buy';
import { OnRampWebViewScreen } from '../screens/wallets/components/OnRampWebViewScreen';
import type { OnRampWebViewParams } from '../screens/wallets/components/OnRampWebViewScreen';
import { useAppTheme } from '../contexts';
import { MainHeader, getMainHeaderStyle } from './headers';

export type BuyStackParamList = {
  BuySelect: { asset?: string } | undefined;
  OnRampWebView: OnRampWebViewParams;
};

const Stack = createNativeStackNavigator<BuyStackParamList>();

export function BuyStackNavigator() {
  const theme = useAppTheme();
  return (
    <Stack.Navigator
      screenOptions={() => ({
        animation: 'default',
        contentStyle: {
          backgroundColor: theme.colors.surface.base,
        },
        ...getMainHeaderStyle(theme),
        ...MainHeader({ theme, onNotifications: () => {} }),
      })}
    >
      <Stack.Screen
        name="BuySelect"
        component={BuyScreen}
        options={() => ({
          title: 'Buy Crypto',
        })}
      />
      <Stack.Screen
        name="OnRampWebView"
        component={OnRampWebViewScreen}
        options={() => ({
          title: 'Buy Crypto',
          headerLeft: undefined,
          headerBackVisible: true,
          headerRight: () => null,
        })}
      />
    </Stack.Navigator>
  );
}
