import { useEffect, useRef, type ReactNode } from "react";
export function MethodDrawer({
  open,
  close,
  children,
}: {
  open: boolean;
  close: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (open && !el?.open) el?.showModal();
    if (!open && el?.open) el.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      className="method-drawer"
      aria-labelledby="method-drawer-title"
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
    >
      <div className="row between">
        <h2 id="method-drawer-title">Browse methods</h2>
        <button onClick={close}>Close method browser</button>
      </div>
      <div id="browse-methods" tabIndex={-1}>
        {children}
      </div>
    </dialog>
  );
}
