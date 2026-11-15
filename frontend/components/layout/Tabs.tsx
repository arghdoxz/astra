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
        className="flex gap-1 overflow-x-auto border-b border-line pb-px [scrollbar-width:thin]"
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
              className={`relative shrink-0 px-3.5 py-2.5 text-sm transition-colors duration-150 cursor-pointer ${
                active ? "text-fg" : "text-muted hover:text-fg"
              }`}
            >
              <span className="inline-flex items-center gap-1.5">
                {t.label}
                {t.badge}
              </span>
              <span
                aria-hidden
                className={`absolute left-2 right-2 -bottom-px h-[2px] rounded transition-opacity duration-150 ${
                  active ? "bg-accent opacity-100" : "opacity-0"
                }`}
              />
            </button>
          );
        })}
      </div>
      <div role="tabpanel" id={`${idPrefix}-panel-${value}`} aria-labelledby={`${idPrefix}-${value}`} className="pt-4 fade-in" key={value}>
        {children}
      </div>
    </div>
  );
}
