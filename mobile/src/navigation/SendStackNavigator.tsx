import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { SendScreen } from '../screens/send';
import { useAppTheme } from '../contexts';
import { MainHeader, getMainHeaderStyle } from './headers';

export type SendStackParamList = {
  SendMain: undefined;
};

const Stack = createNativeStackNavigator<SendStackParamList>();

export function SendStackNavigator() {
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
        name="SendMain"
        component={SendScreen}
        options={() => ({
          title: 'Send',
        })}
      />
    </Stack.Navigator>
  );
}
