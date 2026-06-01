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

const DISPLAY_TZ = (() => {
  try {
    Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Shanghai' })
    return 'Asia/Shanghai'
  } catch {
    return undefined // browser local
  }
})()

function toDate(iso: string): Date | null {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d
}

/** Full date + time with short timezone label, e.g. "Jun 1, 2026, 10:30 AM CST" */
export function formatDateTime(iso: string): string {
  const d = toDate(iso)
  if (!d) return iso || '—'
  return d.toLocaleString('en-US', {
    timeZone: DISPLAY_TZ,
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZoneName: 'short',
  })
}

/** Time only with timezone label, e.g. "10:30:05 AM CST" */
export function formatTime(iso: string): string {
  const d = toDate(iso)
  if (!d) return iso || '—'
  return d.toLocaleString('en-US', {
    timeZone: DISPLAY_TZ,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZoneName: 'short',
  })
}

/** Date only (no time, no TZ label), e.g. "Jun 1, 2026" */
export function formatDate(iso: string): string {
  const d = toDate(iso)
  if (!d) return iso || '—'
  return d.toLocaleString('en-US', {
    timeZone: DISPLAY_TZ,
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}
