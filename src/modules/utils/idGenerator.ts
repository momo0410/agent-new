export function generateId(prefix?: string): string {
  const base = Date.now().toString(36) + Math.random().toString(36).substring(2);
  return prefix ? `${prefix}_${base}` : base;
}
