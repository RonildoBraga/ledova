import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Crypto from 'expo-crypto';
import { createOrderActionStore } from '@ledova/shared';

export const orderActionStore = createOrderActionStore(AsyncStorage, () => Crypto.randomUUID());
