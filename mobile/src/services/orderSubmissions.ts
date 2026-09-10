import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Crypto from 'expo-crypto';
import { createOrderSubmissionStore, type OrderSubmissionSession } from '@ledova/shared';
import { getSessionEpoch, subscribeSession } from './sessionScope';

export const orderSubmissionStore = createOrderSubmissionStore(AsyncStorage, () => Crypto.randomUUID());
export const orderSubmissionSession: OrderSubmissionSession = {
  getEpoch: getSessionEpoch,
  subscribe: subscribeSession,
  requestConfig: () => ({ ledovaSessionEpoch: getSessionEpoch() }),
};
