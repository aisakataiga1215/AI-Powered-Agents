interface ComparisonCardsProps {
  data: Record<string, string>
  emptyMessage: string
}

/**
 * ComparisonCards — renders a row of cards keyed by competitor name.
 *
 * IMPORTANT: `feature_comparison` and `pricing_comparison` are
 * `Record<string, string>` on the backend — competitor_name → summary
 * string. Do NOT try to render this as a nested table.
 */
export function ComparisonCards({ data, emptyMessage }: ComparisonCardsProps) {
  const entries = Object.entries(data ?? {})
  if (entries.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-gray-300 bg-white px-4 py-6 text-center text-sm text-gray-500">
        {emptyMessage}
      </p>
    )
  }
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {entries.map(([competitor, summary]) => (
        <article
          key={competitor}
          className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
        >
          <h4 className="mb-2 text-sm font-semibold text-gray-900">
            {competitor}
          </h4>
          <p className="whitespace-pre-line text-sm leading-relaxed text-gray-700">
            {summary || '—'}
          </p>
        </article>
      ))}
    </div>
  )
}
