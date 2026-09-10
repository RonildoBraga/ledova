export function createCameraWindowAccess(required: boolean, sessionKey = '') {
  let owner: string | null = null;
  let generation = -1;
  let snapshot: Readonly<{ allowed: boolean; key: string }> = { allowed: !required, key: 'platform' };
  const listeners = new Set<() => void>();

  const publish = (allowed: boolean) => {
    snapshot = { allowed, key: `${owner}:${generation}` };
    for (const listener of [...listeners]) listener();
  };

  return {
    sessionKey,
    getSnapshot: () => snapshot,
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    attach(ownerId: string) {
      if (!required) return;
      owner = ownerId;
      generation = -1;
      publish(false);
    },
    detach(ownerId: string) {
      if (!required || owner !== ownerId) return;
      owner = null;
      publish(false);
    },
    update(ownerId: string, event: unknown) {
      if (!required || owner !== ownerId || !event || typeof event !== 'object') return;
      const value = event as Record<string, unknown>;
      if (
        value.ownerId !== ownerId ||
        typeof value.generation !== 'number' ||
        !Number.isSafeInteger(value.generation) ||
        value.generation < 0 ||
        value.generation <= generation ||
        typeof value.allowed !== 'boolean'
      )
        return;
      generation = value.generation;
      publish(value.allowed);
    },
  };
}

export type CameraWindowAccess = ReturnType<typeof createCameraWindowAccess>;
