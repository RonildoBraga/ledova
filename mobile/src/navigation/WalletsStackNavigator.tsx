import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { WalletsScreen } from '../screens/wallets';
import { WalletActionScreen } from '../screens/wallets/components/WalletActionScreen';
import { WalletVerificationScreen } from '../screens/wallets/components/WalletVerificationScreen';
import { SeedPhraseBackupScreen } from '../screens/wallets/components/SeedPhraseBackupScreen';
import { TransferFormScreen } from '../screens/transfers/components/TransferFormScreen';
import { OnRampWebViewScreen } from '../screens/wallets/components/OnRampWebViewScreen';
import type { OnRampWebViewParams } from '../screens/wallets/components/OnRampWebViewScreen';
import { useAppTheme } from '../contexts';
import { MainHeader } from './headers';
import type { Wallet } from '@ledova/shared';
import { getMainHeaderStyle } from './headers/MainHeader';

export type WalletsStackParamList = {
  WalletsList: undefined;
  WalletAction: {
    wallet: Wallet;
  };
  TransferDetails: {
    wallet: Wallet;
  };
  WalletVerification: {
    wallet: Wallet;
  };
  SeedPhraseBackup: {
    seedIdentifier: string;
  };
  OnRampWebView: OnRampWebViewParams;
};

const Stack = createNativeStackNavigator<WalletsStackParamList>();

export function WalletsStackNavigator() {
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
        name="WalletsList"
        component={WalletsScreen}
        options={() => ({
          title: 'Wallets',
        })}
      />
      <Stack.Screen
        name="WalletAction"
        component={WalletActionScreen}
        options={({ route }) => ({
          title: route.params.wallet.name || 'Wallet',
          headerLeft: undefined,
          headerBackVisible: true,
          headerRight: () => null,
        })}
      />
      <Stack.Screen
        name="TransferDetails"
        component={TransferFormScreen}
        options={() => ({
          title: 'Send',
          headerLeft: undefined,
          headerBackVisible: true,
          headerRight: () => null,
        })}
      />
      <Stack.Screen
        name="WalletVerification"
        component={WalletVerificationScreen}
        options={() => ({
          title: 'Verify Wallet',
          headerLeft: undefined,
          headerBackVisible: true,
          headerRight: () => null,
        })}
      />
      <Stack.Screen
        name="SeedPhraseBackup"
        component={SeedPhraseBackupScreen}
        options={() => ({
          title: 'Recovery Phrase',
          headerLeft: undefined,
          headerBackVisible: true,
          headerRight: () => null,
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
