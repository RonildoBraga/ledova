import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { TradingScreen } from '../screens/trading';
import { useAppTheme } from '../contexts';
import { MainHeader, getMainHeaderStyle } from './headers';

export type TradingStackParamList = {
  TradingMain: undefined;
};

const Stack = createNativeStackNavigator<TradingStackParamList>();

export function TradingStackNavigator() {
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
        name="TradingMain"
        component={TradingScreen}
        options={() => ({
          title: 'Trading',
        })}
      />
    </Stack.Navigator>
  );
}
