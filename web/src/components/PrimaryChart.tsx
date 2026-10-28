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
  insightTarget: HTMLDivElement | null;
  selected: string | undefined;
  selectedInsight: string | undefined;
  register: (id: string, priority: number, insight: boolean) => () => void;
  setTarget: (node: HTMLDivElement | null) => void;
  setInsightTarget: (node: HTMLDivElement | null) => void;
} | null>(null);
export function PrimaryChartProvider({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<HTMLDivElement | null>(null);
  const [insightTarget, setInsightTarget] = useState<HTMLDivElement | null>(
    null,
  );
  const [ids, setIds] = useState<
    { id: string; priority: number; insight: boolean }[]
  >([]);
  const register = useCallback(
    (id: string, priority: number, insight: boolean) => {
      setIds((old) =>
        old.some((item) => item.id === id)
          ? old
          : [...old, { id, priority, insight }],
      );
      return () => setIds((old) => old.filter((value) => value.id !== id));
    },
    [],
  );
  return (
    <PrimaryChartContext.Provider
      value={{
        target,
        insightTarget,
        selected: [...ids]
          .filter((item) => !item.insight)
          .sort((a, b) => b.priority - a.priority)[0]?.id,
        selectedInsight: ids.find((item) => item.insight)?.id,
        register,
        setTarget,
        setInsightTarget,
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
export function CoefficientChartSlot() {
  const context = useContext(PrimaryChartContext);
  return (
    <div
      ref={context?.setInsightTarget}
      className="coefficient-chart-slot"
      data-testid="coefficient-insight-chart"
    />
  );
}
// eslint-disable-next-line react-refresh/only-export-components
export function usePrimaryChart(
  primary: boolean | number = false,
  insight = false,
) {
  const context = useContext(PrimaryChartContext);
  const id = useId();
  const register = context?.register;
  const priority = typeof primary === "number" ? primary : primary ? 5 : 0;
  useEffect(
    () => register?.(id, priority, insight),
    [register, id, priority, insight],
  );
  if (context?.selectedInsight === id) return context.insightTarget;
  return context?.selected === id ? context.target : null;
}
