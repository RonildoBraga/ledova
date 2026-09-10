import { useCallback, useEffect, useMemo, useReducer, useRef, useSyncExternalStore } from 'react';
import { DocumentCopy, pickDocumentCopy, UploadFile } from '../services/documentCopies';
import { getAccessToken } from '../services/tokenStorage';
import { getSessionEpoch, subscribeSession } from '../services/sessionScope';

export interface DocumentSubmission {
  file: UploadFile;
  owner: string;
  sessionEpoch: number;
}

export function useDocumentUpload(owner?: string | null) {
  const epoch = useSyncExternalStore(subscribeSession, getSessionEpoch, getSessionEpoch);
  const [, render] = useReducer((value: number) => value + 1, 0);
  const scope = useMemo(
    () => ({
      owner,
      epoch,
      generation: 0,
      copy: null as DocumentCopy | null,
      disposed: false,
      picking: false,
      submitting: false,
    }),
    [owner, epoch],
  );
  const active = useRef(scope);
  active.current = scope;

  const isCurrent = useCallback(
    () => !scope.disposed && active.current === scope && scope.epoch === getSessionEpoch(),
    [scope],
  );

  useEffect(() => {
    scope.disposed = false;
    const retire = () => {
      scope.disposed = true;
      scope.generation++;
      scope.copy?.retire();
      scope.copy = null;
    };
    const unsubscribe = subscribeSession(retire);
    return () => {
      unsubscribe();
      retire();
    };
  }, [scope]);

  const clear = useCallback(() => {
    scope.generation++;
    scope.copy?.retire();
    scope.copy = null;
    if (isCurrent()) render();
  }, [scope, isCurrent]);

  const pick = async (): Promise<boolean> => {
    if (!owner || !isCurrent() || scope.picking) return false;
    scope.picking = true;
    const generation = ++scope.generation;
    const currentPick = () => isCurrent() && scope.generation === generation;
    render();
    try {
      const access = await getAccessToken();
      if (!currentPick()) return false;
      if (!access) throw new Error('Please sign in again before choosing a document.');
      const copy = await pickDocumentCopy(currentPick);
      if (!copy) return false;
      if (!currentPick()) {
        copy.retire();
        return false;
      }
      const previous = scope.copy;
      scope.copy = copy;
      previous?.retire();
      return true;
    } catch (error) {
      if (currentPick()) throw error;
      return false;
    } finally {
      scope.picking = false;
      if (isCurrent()) render();
    }
  };

  const submit = async (consume: (submission: DocumentSubmission) => Promise<unknown>): Promise<boolean> => {
    const copy = scope.copy;
    if (!owner || !copy || !isCurrent() || scope.submitting) return false;
    const generation = scope.generation;
    const release = copy.acquire();
    scope.submitting = true;
    render();
    try {
      await consume({ file: copy.file, owner, sessionEpoch: scope.epoch });
      const current = isCurrent() && scope.copy === copy && scope.generation === generation;
      if (scope.copy === copy) scope.copy = null;
      copy.retire();
      return current;
    } catch (error) {
      if (isCurrent() && scope.copy === copy && scope.generation === generation) throw error;
      return false;
    } finally {
      release();
      scope.submitting = false;
      if (isCurrent()) render();
    }
  };

  return {
    file: scope.copy?.file ?? null,
    isPicking: scope.picking,
    isSubmitting: scope.submitting,
    pick,
    submit,
    clear,
  };
}
