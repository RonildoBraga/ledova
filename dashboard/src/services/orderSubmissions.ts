import { createOrderSubmissionStore } from '@ledova/shared';

export const orderSubmissionStore = createOrderSubmissionStore(
  {
    getAllKeys: () => Object.keys(localStorage),
    getItem: (key) => localStorage.getItem(key),
    setItem: (key, value) => localStorage.setItem(key, value),
    removeItem: (key) => localStorage.removeItem(key),
  },
  () => crypto.randomUUID(),
);
