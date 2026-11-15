"use client";

import { useRef, type KeyboardEvent, type ReactNode } from "react";

export interface TabDef<T extends string> {
  id: T;
  label: string;
  badge?: ReactNode;
}

export default function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  children,
  idPrefix = "tab",
}: {
  tabs: TabDef<T>[];
  value: T;
  onChange: (id: T) => void;
  children: ReactNode;
  idPrefix?: string;
}) {
  const listRef = useRef<HTMLDivElement>(null);

  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    const i = tabs.findIndex((t) => t.id === value);
    let n = -1;
    if (e.key === "ArrowRight") n = (i + 1) % tabs.length;
    else if (e.key === "ArrowLeft") n = (i - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") n = 0;
    else if (e.key === "End") n = tabs.length - 1;
    if (n >= 0) {
      e.preventDefault();
      onChange(tabs[n].id);
      const btn = listRef.current?.querySelectorAll<HTMLButtonElement>("[role=tab]")[n];
      btn?.focus();
    }
  }

  return (
    <div>
      <div
        ref={listRef}
        role="tablist"
        aria-label="Analysis"
        onKeyDown={onKey}
        className="relative z-10 -mb-px flex items-end gap-1 overflow-x-auto [scrollbar-width:thin]"
      >
        {tabs.map((t) => {
          const active = t.id === value;
          return (
            <button
              key={t.id}
              role="tab"
              id={`${idPrefix}-${t.id}`}
              aria-selected={active}
              aria-controls={`${idPrefix}-panel-${t.id}`}
              tabIndex={active ? 0 : -1}
              onClick={() => onChange(t.id)}
              className={`shrink-0 cursor-pointer border px-4 text-[0.95rem] ${
                active
                  ? "border-fg border-b-panel bg-panel py-2.5 font-semibold text-fg"
                  : "border-line border-b-fg bg-panel2 py-2 text-muted hover:text-fg"
              }`}
            >
              <span className="inline-flex items-center gap-1.5">
                {t.label}
                {t.badge}
              </span>
            </button>
          );
        })}
      </div>
      <div role="tabpanel" id={`${idPrefix}-panel-${value}`} aria-labelledby={`${idPrefix}-${value}`} className="card border-fg card-pad sm:p-6" key={value}>
        {children}
      </div>
    </div>
  );
}
