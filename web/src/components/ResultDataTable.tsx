import type { ComponentProps } from "react";
import { DataTable } from "./Common";
import { resultTableColumns, resultColumnLabels } from "../resultPresentation";

/** Display-only: keep short summaries inline, retaining every detailed row. */
export function ResultDataTable({
  detailsLabel,
  primary,
  ...props
}: ComponentProps<typeof DataTable> & {
  detailsLabel?: string;
  primary?: boolean;
}) {
  const columns = resultTableColumns(props.rows, props.columns);
  const displayProps = {
    ...props,
    columns: props.groups?.length ? props.columns : columns,
    columnLabels: { ...resultColumnLabels(columns), ...props.columnLabels },
    mobileRecords:
      props.mobileRecords ??
      (columns.includes("term") &&
        columns.includes("estimate") &&
        props.rows.length <= 4 &&
        !props.groups?.length),
  };
  const rowCount =
    props.rows.length +
    (props.groups ?? []).reduce((count, group) => count + group.rows.length, 0);
  if (primary || (!detailsLabel && rowCount <= 12 && columns.length <= 8))
    return <DataTable {...displayProps} />;
  return (
    <details className="result-table-disclosure">
      <summary>{detailsLabel ?? props.caption ?? "Full result table"}</summary>
      <DataTable {...displayProps} />
    </details>
  );
}
