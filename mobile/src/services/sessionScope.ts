let epoch = 0;
const listeners = new Set<() => void>();

export const getSessionEpoch = () => epoch;

export function subscribeSession(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function invalidateSessionScope(): void {
  epoch++;
  for (const listener of [...listeners]) {
    try {
      listener();
    } catch {
      console.warn('Session cleanup did not complete.');
    }
  }
}

export function assertSessionEpoch(expected: number): void {
  if (expected !== epoch) throw new Error('The saved session changed.');
}
