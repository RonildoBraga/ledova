import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { CompanyScreen } from '../screens/company';
import { TokenDetailScreen } from '../screens/company-tokens/TokenDetailScreen';
import { useAppTheme } from '../contexts';
import { getMainHeaderStyle } from './headers/MainHeader';
import { MainHeader } from './headers';

export type CompanyStackParamList = {
  CompanyMain: undefined;
  TokenDetail: { uuid: string; name?: string };
};

const Stack = createNativeStackNavigator<CompanyStackParamList>();

export function CompanyStackNavigator() {
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
      <Stack.Screen name="CompanyMain" component={CompanyScreen} options={{ title: 'Company' }} />
      <Stack.Screen
        name="TokenDetail"
        component={TokenDetailScreen}
        options={({ route }) => ({
          title: route.params.name || 'Token',
          headerLeft: undefined,
          headerBackVisible: true,
          headerRight: () => null,
        })}
      />
    </Stack.Navigator>
  );
}
