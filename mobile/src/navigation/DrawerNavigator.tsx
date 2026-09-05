import React, { useState } from 'react';
import { View, Text, TouchableOpacity, Image } from 'react-native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useNavigation, NavigationProp } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import {
  HouseIcon,
  WalletIcon,
  UserIcon,
  GearIcon,
  QuestionIcon,
  SignOutIcon,
  LinkIcon,
  ChartBarIcon,
  CurrencyCircleDollarIcon,
  CertificateIcon,
  PaperPlaneTiltIcon,
  BuildingsIcon,
  FileTextIcon,
} from 'phosphor-react-native';
import { signout } from '@ledova/shared-services';
import { apiClient } from '../services/apiClient';
import { notificationsService } from '../services/notificationsService';
import { clearTokens } from '../services/tokenStorage';
import { useAppTheme, useThemedStyles } from '../contexts';
import { NotificationsModal } from '../components/notifications';
import { useNotifications } from '../hooks/useNotifications';
import type { RootStackParamList } from './AppNavigator';
import { BottomTabNavigator } from './BottomTabNavigator';
import { MainHeader, getMainHeaderStyle } from './headers';
import { SignOutModal } from '../components/auth';
import { HelpScreen } from '../screens/help';
import { SettingsScreen } from '../screens/settings';
import { DrawerProvider, useDrawer } from './DrawerContext';
import { useFeatureFlags } from '../hooks/useFeatureFlags';
import { useRole } from '../hooks/useRole';
import type { ComponentType } from 'react';

export type DrawerParamList = {
  Main: undefined;
  Settings: undefined;
  Help: undefined;
};

const Stack = createNativeStackNavigator<DrawerParamList>();

interface MenuItem {
  label: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  icon: ComponentType<any>;
  action: 'tab' | 'screen' | 'logout';
  target?: string;
}

const INVESTOR_MENU_ITEMS: MenuItem[] = [
  { label: 'Home', icon: HouseIcon, action: 'tab', target: 'Home' },
  { label: 'Wallets', icon: WalletIcon, action: 'tab', target: 'Wallets' },
  { label: 'Buy', icon: CurrencyCircleDollarIcon, action: 'tab', target: 'Buy' },
  { label: 'Send', icon: PaperPlaneTiltIcon, action: 'tab', target: 'Send' },
  { label: 'Transactions', icon: LinkIcon, action: 'tab', target: 'Transactions' },
  { label: 'Market', icon: ChartBarIcon, action: 'tab', target: 'Market' },
];

const COMPANY_MENU_ITEMS: MenuItem[] = [
  { label: 'Company', icon: BuildingsIcon, action: 'tab', target: 'Company' },
  { label: 'Listing', icon: FileTextIcon, action: 'tab', target: 'Listing' },
  { label: 'Wallets', icon: WalletIcon, action: 'tab', target: 'Wallets' },
];

const SECONDARY_ITEMS: MenuItem[] = [
  { label: 'Profile', icon: UserIcon, action: 'tab', target: 'Profile' },
  { label: 'Settings', icon: GearIcon, action: 'screen', target: 'Settings' },
  { label: 'Help & Support', icon: QuestionIcon, action: 'screen', target: 'Help' },
  { label: 'Logout', icon: SignOutIcon, action: 'logout' },
];

function DrawerMenuContent({ onSignOut }: { onSignOut: () => void }) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    drawerContent: {
      flex: 1,
      paddingTop: 50,
      backgroundColor: theme.colors.surface.raised,
    },
    drawerHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      padding: 20,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.default,
    },
    logo: {
      width: 40,
      height: 32,
    },
    drawerTitle: {
      fontSize: theme.fontSize.xl,
      fontWeight: 'bold',
      color: theme.colors.text.primary,
      marginLeft: 12,
    },
    menuItem: {
      flexDirection: 'row',
      alignItems: 'center',
      padding: 16,
      marginHorizontal: 12,
      borderRadius: theme.borderRadius.md,
    },
    menuText: {
      marginLeft: 16,
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    divider: {
      height: 1,
      backgroundColor: theme.colors.border.default,
      marginVertical: 16,
      marginHorizontal: 20,
    },
  }));

  const ICON_PROPS = {
    size: theme.icon.sizes.lg,
    color: theme.colors.text.muted,
    weight: theme.icon.weights.regular,
  } as const;

  const { closeDrawer } = useDrawer();
  const navigation = useNavigation<NavigationProp<RootStackParamList>>();
  const { isEnabled } = useFeatureFlags();
  const { isCompany } = useRole();

  const handleAction = (item: MenuItem) => {
    closeDrawer();
    if (item.action === 'logout') {
      onSignOut();
    } else if (item.action === 'tab') {
      let params;
      if (item.target === 'Company') {
        params = { screen: 'Company', params: { screen: 'CompanyMain' } };
      } else if (item.target === 'Wallets') {
        params = { screen: 'Wallets', params: { screen: 'WalletsList' } };
      } else if (item.target === 'Buy') {
        params = { screen: 'Buy', params: { screen: 'BuySelect' } };
      } else if (item.target === 'Send') {
        params = { screen: 'Send', params: { screen: 'SendMain' } };
      } else {
        params = { screen: item.target as string };
      }
      navigation.navigate('MainApp', { screen: 'Main', params } as never);
    } else {
      navigation.navigate('MainApp', { screen: item.target } as never);
    }
  };

  const renderItem = (item: MenuItem) => (
    <TouchableOpacity key={item.label} style={styles.menuItem} onPress={() => handleAction(item)}>
      <item.icon {...ICON_PROPS} />
      <Text style={styles.menuText}>{item.label}</Text>
    </TouchableOpacity>
  );

  const showTrading = isEnabled('trading_enabled');
  const menuItems = isCompany ? COMPANY_MENU_ITEMS : INVESTOR_MENU_ITEMS;

  return (
    <View style={styles.drawerContent}>
      <View style={styles.drawerHeader}>
        {/* eslint-disable-next-line @typescript-eslint/no-require-imports */}
        <Image source={require('../../assets/logo.png')} style={styles.logo} resizeMode="contain" />
        <Text style={styles.drawerTitle}>Ledova</Text>
      </View>

      {menuItems.map(renderItem)}
      {showTrading && (
        <TouchableOpacity
          style={styles.menuItem}
          onPress={() => {
            closeDrawer();
            navigation.navigate('MainApp', {
              screen: 'Main',
              params: { screen: 'Trading', params: { screen: 'TradingMain' } },
            } as never);
          }}
        >
          <CertificateIcon {...ICON_PROPS} />
          <Text style={styles.menuText}>Trading</Text>
        </TouchableOpacity>
      )}
      <View style={styles.divider} />
      {SECONDARY_ITEMS.map(renderItem)}
    </View>
  );
}

export function DrawerNavigator() {
  const theme = useAppTheme();
  const navigation = useNavigation<NavigationProp<RootStackParamList>>();
  const queryClient = useQueryClient();
  const [showSignOutModal, setShowSignOutModal] = useState(false);
  const [showNotificationsModal, setShowNotificationsModal] = useState(false);
  const [isSigningOut, setIsSigningOut] = useState(false);
  const { unreadCount } = useNotifications();

  const handleSignOutConfirm = async () => {
    setIsSigningOut(true);
    try {
      await notificationsService.unregisterToken();
      await signout(apiClient);
    } catch (error) {
      console.error('Sign-out API call failed:', error);
    } finally {
      // The backend revoked the session; drop the pair and the biometric-gated copy with it
      await clearTokens();

      queryClient.clear();
      queryClient.removeQueries();
      queryClient.resetQueries();

      navigation.reset({ index: 0, routes: [{ name: 'SignIn' }] });
      setIsSigningOut(false);
      setShowSignOutModal(false);
    }
  };

  return (
    <DrawerProvider renderMenu={() => <DrawerMenuContent onSignOut={() => setShowSignOutModal(true)} />}>
      <View style={{ flex: 1 }}>
        <Stack.Navigator
          initialRouteName="Main"
          screenOptions={() => ({
            contentStyle: { backgroundColor: theme.colors.surface.base },
            ...getMainHeaderStyle(theme),
            ...MainHeader({ theme, onNotifications: () => setShowNotificationsModal(true), unreadCount }),
          })}
        >
          <Stack.Screen name="Main" options={{ headerShown: false }}>
            {() => (
              <BottomTabNavigator onNotifications={() => setShowNotificationsModal(true)} unreadCount={unreadCount} />
            )}
          </Stack.Screen>
          <Stack.Screen name="Settings" component={SettingsScreen} options={{ title: 'Settings' }} />
          <Stack.Screen name="Help" component={HelpScreen} options={{ title: 'Help & Support' }} />
        </Stack.Navigator>
      </View>

      <SignOutModal
        visible={showSignOutModal}
        onClose={() => setShowSignOutModal(false)}
        onConfirm={handleSignOutConfirm}
        isLoading={isSigningOut}
      />

      <NotificationsModal visible={showNotificationsModal} onClose={() => setShowNotificationsModal(false)} />
    </DrawerProvider>
  );
}
