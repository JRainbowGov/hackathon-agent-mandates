/*
 * The UI can be served under a path prefix (e.g. behind a shared web server at /frontend). The prefix is fixed at
 * build time from PUBLIC_BASE_PATH (astro.config.mjs `base`), so every root-relative path the UI builds goes through
 * here. With no prefix, both functions leave paths unchanged.
 */
const BASE = (import.meta.env.BASE_URL ?? '/').replace(/\/+$/, ''); // '' or '/frontend'

/** `/approve/x` -> `/frontend/approve/x` */
export function withBase(path: string): string {
  return `${BASE}${path.startsWith('/') ? path : `/${path}`}`;
}

/** `/frontend/approve/x` -> `/approve/x`, for matching routes the same way with or without a prefix */
export function stripBase(pathname: string): string {
  if (!BASE) return pathname;
  if (pathname === BASE) return '/';
  return pathname.startsWith(`${BASE}/`) ? pathname.slice(BASE.length) : pathname;
}
