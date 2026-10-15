export const LIBRARY_PAGE_SIZE = 20;

export type LibraryFilters = { search?: string; category?: string };

export function libraryHref(filters: LibraryFilters = {}, page = 1): string {
  const query = new URLSearchParams();
  if (filters.search) query.set("search", filters.search);
  if (filters.category) query.set("category", filters.category);
  if (page > 1) query.set("page", String(page));
  return query.size ? `/library?${query}` : "/library";
}

export function libraryPage(value: string | string[] | undefined): number {
  if (typeof value !== "string" || !/^[1-9]\d*$/.test(value)) return 1;
  const page = Number(value);
  return Number.isSafeInteger(page) && Number.isSafeInteger((page - 1) * LIBRARY_PAGE_SIZE) ? page : 1;
}
