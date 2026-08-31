import React from 'react';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { SendStackParamList } from '../../navigation/SendStackNavigator';
import { SendFormScreen } from './components/SendFormScreen';

export function SendScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<SendStackParamList>>();

  const handleDone = () => {
    if (navigation.canGoBack()) {
      navigation.goBack();
    }
  };

  return <SendFormScreen onDone={handleDone} />;
}
