import type { ComponentProps } from "react";
import { DataTable } from "./Common";

/** Display-only: keep short summaries inline, retaining every detailed row. */
export function ResultDataTable({
  detailsLabel,
  primary,
  ...props
}: ComponentProps<typeof DataTable> & {
  detailsLabel?: string;
  primary?: boolean;
}) {
  const columns = props.columns ?? Object.keys(props.rows[0] ?? {});
  const rowCount =
    props.rows.length +
    (props.groups ?? []).reduce((count, group) => count + group.rows.length, 0);
  if (primary || (!detailsLabel && rowCount <= 12 && columns.length <= 8))
    return <DataTable {...props} />;
  return (
    <details className="result-table-disclosure">
      <summary>{detailsLabel ?? props.caption ?? "Full result table"}</summary>
      <DataTable {...props} />
    </details>
  );
}
