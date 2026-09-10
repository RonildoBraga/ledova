export function createScannerWindow(required: boolean) {
  let snapshot = { allowed: !required, generation: 0 };
  const listeners = new Set<() => void>();
  return {
    getSnapshot: () => snapshot,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    update(allowed: boolean, generation: number) {
      if (snapshot.allowed === allowed && snapshot.generation === generation) return;
      snapshot = { allowed, generation };
      for (const listener of listeners) listener();
    },
  };
}

export type ScannerWindow = ReturnType<typeof createScannerWindow>;
