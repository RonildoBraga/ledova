import React, { useState, useCallback } from 'react';
import { useFocusEffect, useNavigation, useRoute } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { NavigationProp } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import { GradientBackground } from '../../components/GradientBackground';
import { useUserPreferences } from '../../hooks/useUserPreferences';
import { BuyCryptoModal } from './components/BuyCryptoModal';
import type { BuyStackParamList } from '../../navigation/BuyStackNavigator';
import type { RootStackParamList } from '../../navigation/AppNavigator';

export function BuyScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<BuyStackParamList>>();
  const rootNavigation = useNavigation<NavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<BuyStackParamList, 'BuySelect'>>();
  const { selectedAccount } = useUserPreferences();
  const [showModal, setShowModal] = useState(false);

  const initialAsset = route.params?.asset;

  useFocusEffect(
    useCallback(() => {
      setShowModal(true);
    }, []),
  );

  const handleClose = () => {
    setShowModal(false);
    if (navigation.canGoBack()) {
      navigation.goBack();
    }
  };

  const handleNavigateToWebView = (url: string) => {
    setShowModal(false);
    navigation.navigate('OnRampWebView', { url });
  };

  const handleNavigateToProfile = () => {
    rootNavigation.navigate('MainApp', { screen: 'Main', params: { screen: 'Profile' } } as never);
  };

  return (
    <GradientBackground>
      <BuyCryptoModal
        visible={showModal}
        onClose={handleClose}
        onNavigateToWebView={handleNavigateToWebView}
        onNavigateToProfile={handleNavigateToProfile}
        userAccountUuid={selectedAccount?.uuid}
        initialAsset={initialAsset}
      />
    </GradientBackground>
  );
}
