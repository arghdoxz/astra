// Recent investigations kept in this browser only (localStorage). Every access is guarded:
// storage can be unavailable (private windows, blocked cookies, SSR).

export interface RecentInvestigation {
  id: string;
  name?: string;
  ra: number;
  dec: number;
  fov_arcmin: number;
  at: string; // ISO time the investigation was opened
  href: string; // shareable URL (path + query)
}

const KEY = "astra.recent.v1";
const MAX = 20;

export function loadRecent(): RecentInvestigation[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? (arr as RecentInvestigation[]) : [];
  } catch {
    return [];
  }
}

export function addRecent(entry: Omit<RecentInvestigation, "at"> & { at?: string }): void {
  try {
    const cur = loadRecent().filter((e) => e.href !== entry.href && e.id !== entry.id);
    cur.unshift({ ...entry, at: entry.at ?? new Date().toISOString() });
    window.localStorage.setItem(KEY, JSON.stringify(cur.slice(0, MAX)));
  } catch {
    /* ignore */
  }
}

export function clearRecent(): void {
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

// Aliases
export const getRecent = loadRecent;
export const getHistory = loadRecent;
export const pushHistory = addRecent;
export const clearHistory = clearRecent;
