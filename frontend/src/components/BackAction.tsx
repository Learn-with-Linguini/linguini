import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

interface BackAction {
  onBack?: () => void;
  backLabel?: string;
}

const BackActionContext = createContext<{
  value: BackAction;
  set: (action: BackAction) => void;
}>({ value: {}, set: () => {} });

export function BackActionProvider({ children }: { children: ReactNode }) {
  const [value, setValue] = useState<BackAction>({});
  return <BackActionContext.Provider value={{ value, set: setValue }}>{children}</BackActionContext.Provider>;
}

export function useRegisteredBackAction(): BackAction {
  return useContext(BackActionContext).value;
}

export function useBackAction(handler: () => void, label?: string) {
  const { set } = useContext(BackActionContext);
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    set({ onBack: () => ref.current(), backLabel: label });
    return () => set({});
  }, [set, label]);
}
