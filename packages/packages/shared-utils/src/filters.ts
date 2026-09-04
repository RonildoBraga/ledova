export function hasActiveFilters<T extends Record<string, unknown>>(
  filters: T,
  excludeFields: (keyof T)[] = ['searchQuery' as keyof T],
): boolean {
  return Object.entries(filters)
    .filter(([key]) => !excludeFields.includes(key as keyof T))
    .some(
      ([, value]) =>
        value !== undefined && value !== null && value !== '' && !(Array.isArray(value) && value.length === 0),
    );
}
