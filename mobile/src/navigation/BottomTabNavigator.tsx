import React from 'react';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import type { NavigatorScreenParams } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import {
  HouseIcon,
  WalletIcon,
  CurrencyCircleDollarIcon,
  CertificateIcon,
  PaperPlaneTiltIcon,
  BuildingsIcon,
} from 'phosphor-react-native';
import { HomeStackNavigator } from './HomeStackNavigator';
import type { HomeStackParamList } from './HomeStackNavigator';
import { WalletsStackNavigator } from './WalletsStackNavigator';
import { BuyStackNavigator } from './BuyStackNavigator';
import { SendStackNavigator } from './SendStackNavigator';
import { TradingStackNavigator } from './TradingStackNavigator';
import { TransactionsScreen } from '../screens/transactions';
import { AssetPricesScreen } from '../screens/asset-prices';
import { UserProfileScreen } from '../screens/user-profile';
import { CompanyStackNavigator } from './CompanyStackNavigator';
import type { CompanyStackParamList } from './CompanyStackNavigator';
import { ListingScreen } from '../screens/listing';
import { InvestorEligibilityScreen } from '../screens/investor-eligibility';
import { getMainHeaderStyle, MainHeader } from './headers';
import type { WalletsStackParamList } from './WalletsStackNavigator';
import type { BuyStackParamList } from './BuyStackNavigator';
import type { SendStackParamList } from './SendStackNavigator';
import type { TradingStackParamList } from './TradingStackNavigator';
import { useFeatureFlags } from '../hooks/useFeatureFlags';
import { useRole } from '../hooks/useRole';
import { useAppTheme } from '../contexts';

export type BottomTabParamList = {
  Home: NavigatorScreenParams<HomeStackParamList>;
  Market: undefined;
  Buy: NavigatorScreenParams<BuyStackParamList>;
  Send: NavigatorScreenParams<SendStackParamList>;
  Trading: NavigatorScreenParams<TradingStackParamList>;
  Transactions: undefined;
  Wallets: NavigatorScreenParams<WalletsStackParamList>;
  Profile: undefined;
  Company: NavigatorScreenParams<CompanyStackParamList>;
  Listing: undefined;
  InvestorEligibility: undefined;
};

const Tab = createBottomTabNavigator<BottomTabParamList>();

interface BottomTabNavigatorProps {
  onNotifications: () => void;
  unreadCount: number;
}

export function BottomTabNavigator({ onNotifications, unreadCount }: BottomTabNavigatorProps) {
  const theme = useAppTheme();
  const insets = useSafeAreaInsets();
  const { isEnabled } = useFeatureFlags();
  const { isCompany, isLoading: isLoadingRole } = useRole();
  const showTrading = isEnabled('trading_enabled');

  if (isLoadingRole) {
    return null;
  }

  return (
    <Tab.Navigator
      initialRouteName={isCompany ? 'Company' : 'Home'}
      screenOptions={() => ({
        ...getMainHeaderStyle(theme),
        ...MainHeader({ theme, onNotifications, unreadCount }),
        tabBarStyle: {
          backgroundColor: theme.colors.surface.raised,
          borderTopColor: theme.colors.border.subtle,
          borderTopWidth: 1,
          height: 46 + insets.bottom,
          paddingBottom: insets.bottom,
          paddingTop: 8,
        },
        tabBarActiveTintColor: theme.colors.interactive.active,
        tabBarInactiveTintColor: theme.colors.text.muted,
        tabBarShowLabel: true,
        tabBarLabelStyle: {
          fontSize: 10,
          marginTop: 1,
        },
      })}
    >
      <Tab.Screen
        name="Home"
        options={{
          headerShown: false,
          tabBarLabel: 'Home',
          tabBarIcon: ({ color, size }) => <HouseIcon size={size} color={color} weight="regular" />,
          tabBarItemStyle: isCompany ? { display: 'none' } : undefined,
        }}
        listeners={({ navigation }) => ({
          tabPress: (e) => {
            e.preventDefault();
            navigation.navigate('Home', { screen: 'HomeMain' });
          },
        })}
      >
        {() => <HomeStackNavigator onNotifications={onNotifications} unreadCount={unreadCount} />}
      </Tab.Screen>

      <Tab.Screen
        name="Company"
        component={CompanyStackNavigator}
        options={{
          headerShown: false,
          tabBarLabel: 'Company',
          tabBarIcon: ({ color, size }) => <BuildingsIcon size={size} color={color} weight="regular" />,
          tabBarItemStyle: isCompany ? undefined : { display: 'none' },
        }}
        listeners={({ navigation }) => ({
          tabPress: (e) => {
            e.preventDefault();
            navigation.navigate('Company', { screen: 'CompanyMain' });
          },
        })}
      />

      <Tab.Screen
        name="Wallets"
        component={WalletsStackNavigator}
        options={{
          headerShown: false,
          tabBarLabel: 'Wallets',
          tabBarIcon: ({ color, size }) => <WalletIcon size={size} color={color} weight="regular" />,
        }}
        listeners={({ navigation }) => ({
          tabPress: (e) => {
            e.preventDefault();
            navigation.navigate('Wallets', { screen: 'WalletsList' });
          },
        })}
      />

      <Tab.Screen
        name="Buy"
        component={BuyStackNavigator}
        options={{
          headerShown: false,
          tabBarLabel: 'Buy',
          tabBarIcon: ({ color, size }) => <CurrencyCircleDollarIcon size={size} color={color} weight="regular" />,
          tabBarItemStyle: isCompany ? { display: 'none' } : undefined,
        }}
        listeners={({ navigation }) => ({
          tabPress: (e) => {
            e.preventDefault();
            navigation.navigate('Buy', { screen: 'BuySelect' });
          },
        })}
      />

      <Tab.Screen
        name="Send"
        component={SendStackNavigator}
        options={{
          headerShown: false,
          tabBarLabel: 'Send',
          tabBarIcon: ({ color, size }) => <PaperPlaneTiltIcon size={size} color={color} weight="regular" />,
          tabBarItemStyle: isCompany ? { display: 'none' } : undefined,
        }}
        listeners={({ navigation }) => ({
          tabPress: (e) => {
            e.preventDefault();
            navigation.navigate('Send', { screen: 'SendMain' });
          },
        })}
      />

      {showTrading && (
        <Tab.Screen
          name="Trading"
          component={TradingStackNavigator}
          options={{
            headerShown: false,
            tabBarLabel: 'Trading',
            tabBarIcon: ({ color, size }) => <CertificateIcon size={size} color={color} weight="regular" />,
          }}
          listeners={({ navigation }) => ({
            tabPress: (e) => {
              e.preventDefault();
              navigation.navigate('Trading', { screen: 'TradingMain' });
            },
          })}
        />
      )}

      <Tab.Screen
        name="Transactions"
        component={TransactionsScreen}
        options={{
          title: 'Transactions',
          tabBarItemStyle: { display: 'none' },
        }}
      />

      <Tab.Screen
        name="Market"
        component={AssetPricesScreen}
        options={{
          title: 'Market',
          tabBarItemStyle: { display: 'none' },
        }}
      />

      <Tab.Screen
        name="Profile"
        component={UserProfileScreen}
        options={{
          title: 'Profile',
          tabBarItemStyle: { display: 'none' },
        }}
      />

      <Tab.Screen
        name="Listing"
        component={ListingScreen}
        options={{
          title: 'Listing',
          tabBarItemStyle: { display: 'none' },
        }}
      />

      <Tab.Screen
        name="InvestorEligibility"
        component={InvestorEligibilityScreen}
        options={{
          title: 'Eligibility',
          tabBarItemStyle: { display: 'none' },
        }}
      />
    </Tab.Navigator>
  );
}
