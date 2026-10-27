import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useState,
  type ReactNode,
} from "react";

// Relocate the existing chart instance. Its points, export context and callbacks
// remain owned by the original method view; there is no second chart serializer.
const PrimaryChartContext = createContext<{
  target: HTMLDivElement | null;
  selected: string | undefined;
  register: (id: string, primary: boolean) => () => void;
  setTarget: (node: HTMLDivElement | null) => void;
} | null>(null);
export function PrimaryChartProvider({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<HTMLDivElement | null>(null);
  const [ids, setIds] = useState<{ id: string; primary: boolean }[]>([]);
  const register = useCallback((id: string, primary: boolean) => {
    setIds((old) =>
      old.some((item) => item.id === id) ? old : [...old, { id, primary }],
    );
    return () => setIds((old) => old.filter((value) => value.id !== id));
  }, []);
  return (
    <PrimaryChartContext.Provider
      value={{
        target,
        selected: (ids.find((item) => item.primary) ?? ids[0])?.id,
        register,
        setTarget,
      }}
    >
      {children}
    </PrimaryChartContext.Provider>
  );
}
export function PrimaryChartSlot() {
  const context = useContext(PrimaryChartContext);
  return (
    <div
      ref={context?.setTarget}
      className="primary-chart-slot"
      data-testid="primary-chart"
    />
  );
}
// eslint-disable-next-line react-refresh/only-export-components
export function usePrimaryChart(primary = false) {
  const context = useContext(PrimaryChartContext);
  const id = useId();
  const register = context?.register;
  useEffect(() => register?.(id, primary), [register, id, primary]);
  return context?.selected === id ? context.target : null;
}
