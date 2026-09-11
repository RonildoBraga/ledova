import { useContext, useLayoutEffect, useMemo, useReducer, useRef, useState, useSyncExternalStore } from 'react';
import { AppState } from 'react-native';
import { CameraAccessContext } from '../contexts/cameraAccess';
import { getSessionEpoch, subscribeSession } from '../services/sessionScope';

function subscribeAppState(listener: () => void) {
  const subscription = AppState.addEventListener('change', listener);
  return () => subscription.remove();
}

const getAppState = () => AppState.currentState;

export function createProviderLifetime() {
  let retired = false;
  let disposed = false;
  return {
    isActive: () => !retired && !disposed,
    mount: () => {
      disposed = false;
    },
    unmount: () => {
      disposed = true;
    },
    retire: () => {
      retired = true;
    },
  };
}

export function useProviderViewLifecycle(
  visible: boolean,
  accessToken: string | null,
  formUrl: string | null,
  sessionEpoch: number | null,
  onComplete: () => void,
  onClose: () => void,
) {
  const access = useContext(CameraAccessContext);
  const admission = useSyncExternalStore(access.subscribe, access.getSnapshot, access.getSnapshot);
  const appState = useSyncExternalStore(subscribeAppState, getAppState, getAppState);
  useSyncExternalStore(subscribeSession, getSessionEpoch, getSessionEpoch);
  const [, render] = useReducer((value: number) => value + 1, 0);
  const form = useMemo(
    () => ({ visible, sessionEpoch, lifetime: createProviderLifetime() }),
    [visible, accessToken, formUrl, sessionEpoch],
  );
  const [view, setView] = useState({ form, admission, appState, key: 0 });
  if (view.form !== form || view.admission !== admission || view.appState !== appState) {
    setView({ form, admission, appState, key: view.key + 1 });
  }
  const current = useRef(view);
  const handlers = useRef({ onComplete, onClose });

  useLayoutEffect(() => {
    current.current = view;
    handlers.current = { onComplete, onClose };
  }, [view, onComplete, onClose]);

  useLayoutEffect(() => {
    form.lifetime.mount();
    return form.lifetime.unmount;
  }, [form]);

  const isAdmitted = () =>
    form.visible &&
    form.lifetime.isActive() &&
    form.sessionEpoch === getSessionEpoch() &&
    view.admission.allowed &&
    access.getSnapshot() === view.admission &&
    view.appState === 'active' &&
    AppState.currentState === 'active';

  const isCurrent = () => current.current === view && isAdmitted();

  const retire = (handler: 'onComplete' | 'onClose') => {
    if (!isCurrent()) return;
    form.lifetime.retire();
    render();
    handlers.current[handler]();
  };

  return {
    admitted: isAdmitted(),
    key: view.key,
    isCurrent,
    complete: () => retire('onComplete'),
    close: () => retire('onClose'),
  };
}
