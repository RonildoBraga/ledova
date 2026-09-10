import { createContext } from 'react';

export function createCameraAccess() {
  let snapshot: Readonly<{ allowed: boolean }> = { allowed: false };
  const listeners = new Set<() => void>();

  return {
    getSnapshot: () => snapshot,
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    setAllowed(allowed: boolean): void {
      if (snapshot.allowed === allowed) return;
      snapshot = { allowed };
      for (const listener of [...listeners]) {
        try {
          listener();
        } catch {
          console.warn('Camera pause notification did not complete.');
        }
      }
    },
  };
}

type CameraAccess = Pick<ReturnType<typeof createCameraAccess>, 'getSnapshot' | 'subscribe'>;

export const CameraAccessContext = createContext<CameraAccess>(createCameraAccess());
