import { createOrderActionStore } from '@ledova/shared';

export const orderActionStore = createOrderActionStore(
  {
    getAllKeys: () => Object.keys(localStorage),
    getItem: (key) => localStorage.getItem(key),
    setItem: (key, value) => localStorage.setItem(key, value),
    removeItem: (key) => localStorage.removeItem(key),
  },
  () => crypto.randomUUID(),
);
