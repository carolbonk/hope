import type { HTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from "react";
import { cx } from "@/lib/cx";

export function Table({ className, caption, children, ...rest }: HTMLAttributes<HTMLTableElement> & { caption: string }) {
  return (
    <div className="glass-inset relative overflow-x-auto rounded-2xl p-2">
      <table className={cx("w-full min-w-[56rem] border-separate border-spacing-y-2 text-left text-sm", className)} {...rest}>
        <caption className="sr-only">{caption}</caption>
        {children}
      </table>
    </div>
  );
}

export function Th({ className, ...rest }: ThHTMLAttributes<HTMLTableCellElement>) {
  return <th scope="col" className={cx("px-3 py-2 text-xs font-semibold uppercase tracking-wide text-ink-muted", className)} {...rest} />;
}

export function Td({ className, ...rest }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cx("px-3 py-3 align-middle first:rounded-l-xl last:rounded-r-xl", className)} {...rest} />;
}

export function Tr({ className, ...rest }: HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cx("glass-control", className)} {...rest} />;
}
