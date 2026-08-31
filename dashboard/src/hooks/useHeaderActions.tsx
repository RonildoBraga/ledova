import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

interface HeaderActionsContextType {
  actions: ReactNode | null;
  setActions: (actions: ReactNode | null) => void;
}

const HeaderActionsContext = createContext<HeaderActionsContextType>({
  actions: null,
  setActions: () => {},
});

export function HeaderActionsProvider({ children }: { children: ReactNode }) {
  const [actions, setActionsState] = useState<ReactNode | null>(null);
  const setActions = useCallback((a: ReactNode | null) => setActionsState(a), []);

  return <HeaderActionsContext.Provider value={{ actions, setActions }}>{children}</HeaderActionsContext.Provider>;
}

export function useHeaderActions() {
  return useContext(HeaderActionsContext);
}
