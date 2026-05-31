/**
 * cn — tiny class-name combiner.
 *
 * We intentionally avoid pulling in clsx/tailwind-merge as a dependency
 * for the MVP. This handles strings, undefined, false, and arrays.
 */

type ClassValue = string | undefined | null | false | ClassValue[]

export function cn(...values: ClassValue[]): string {
  const out: string[] = []
  for (const value of values) {
    if (!value) continue
    if (Array.isArray(value)) {
      out.push(cn(...value))
    } else if (typeof value === 'string') {
      out.push(value)
    }
  }
  return out.filter(Boolean).join(' ')
}
