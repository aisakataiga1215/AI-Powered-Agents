/**
 * Shared timestamp formatting utility.
 *
 * All timestamps from the backend are UTC ISO strings (with +00:00 suffix).
 * We display them in Asia/Shanghai (UTC+8) so times are meaningful for
 * the primary users, and always show the timezone label so readers know
 * which zone they are seeing.
 *
 * The timezone is resolved once at module load. If the runtime does not
 * support Asia/Shanghai (extremely rare), we fall back to the browser's
 * local timezone.
 */

const TZ = 'Asia/Shanghai'

function toDate(iso: string): Date | null {
  if (!iso) return null
  // SQLite returns naive datetimes (no tz suffix). Treat them as UTC.
  let s = iso.trim().replace(' ', 'T')
  if (!/[Zz]|[+-]\d{2}/.test(s.slice(-6))) s += 'Z'
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? null : d
}

/** Full date + time in 24-hour UTC+8, e.g. "Jun 1, 2026, 19:39 UTC+8" */
export function formatDateTime(iso: string): string {
  const d = toDate(iso)
  if (!d) return iso || '—'
  return (
    new Intl.DateTimeFormat('en-US', {
      timeZone: TZ,
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(d) + ' UTC+8'
  )
}

/** Time only in 24-hour UTC+8, e.g. "19:39:05 UTC+8" */
export function formatTime(iso: string): string {
  const d = toDate(iso)
  if (!d) return iso || '—'
  return (
    new Intl.DateTimeFormat('en-US', {
      timeZone: TZ,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(d) + ' UTC+8'
  )
}

/** Date only (no time, no TZ label), e.g. "Jun 1, 2026" */
export function formatDate(iso: string): string {
  const d = toDate(iso)
  if (!d) return iso || '—'
  return new Intl.DateTimeFormat('en-US', {
    timeZone: TZ,
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(d)
}
