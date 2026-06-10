interface FeatureComparisonTableProps {
  data: Record<string, string>
  emptyMessage: string
}

function parseFeatureString(value: string): Map<string, string[]> {
  const result = new Map<string, string[]>()
  for (const segment of value.split(' | ')) {
    const colonIdx = segment.indexOf(':')
    if (colonIdx === -1) {
      const text = segment.trim()
      if (text) result.set(text, [])
      continue
    }
    const category = segment.slice(0, colonIdx).trim()
    const features = segment
      .slice(colonIdx + 1)
      .split(',')
      .map((f) => f.trim())
      .filter(Boolean)
    if (category) result.set(category, features)
  }
  return result
}

export function FeatureComparisonTable({ data, emptyMessage }: FeatureComparisonTableProps) {
  const entries = Object.entries(data ?? {})

  if (entries.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-gray-300 bg-white px-4 py-6 text-center text-sm text-gray-500">
        {emptyMessage}
      </p>
    )
  }

  const parsed = entries.map(([competitor, value]) => ({
    competitor,
    categories: parseFeatureString(value),
  }))

  // Collect all categories, preserving first-seen order across all competitors
  const seen = new Set<string>()
  const allCategories: string[] = []
  for (const { categories } of parsed) {
    for (const cat of categories.keys()) {
      if (!seen.has(cat)) {
        seen.add(cat)
        allCategories.push(cat)
      }
    }
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 bg-gray-50">
            <th
              scope="col"
              className="w-36 px-4 py-3 text-left text-xs font-semibold tracking-wider text-gray-500 uppercase"
            >
              功能
            </th>
            {parsed.map(({ competitor }) => (
              <th
                key={competitor}
                scope="col"
                className="px-4 py-3 text-left text-xs font-semibold tracking-wider text-gray-900 uppercase"
              >
                {competitor}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {allCategories.map((cat) => (
            <tr key={cat} className="hover:bg-gray-50/60">
              <td className="w-36 bg-gray-50 px-4 py-3 align-top text-xs font-semibold tracking-wide text-gray-500 uppercase">
                {cat}
              </td>
              {parsed.map(({ competitor, categories }) => {
                const features = categories.get(cat)
                return (
                  <td key={competitor} className="px-4 py-3 align-top text-gray-700">
                    {features && features.length > 0 ? (
                      <ul className="space-y-1">
                        {features.map((f, index) => (
                          <li key={`${cat}-${competitor}-${index}-${f}`} className="flex items-start gap-1.5 leading-snug">
                            <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-blue-400" />
                            {f}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
