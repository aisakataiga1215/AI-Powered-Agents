interface PricingComparisonTableProps {
  data: Record<string, string>
  emptyMessage: string
}

function parsePricingString(value: string): Map<string, string> {
  const result = new Map<string, string>()
  for (const segment of value.split(' | ')) {
    const colonIdx = segment.indexOf(':')
    if (colonIdx === -1) {
      const text = segment.trim()
      if (text) result.set(text, '')
      continue
    }
    const plan = segment.slice(0, colonIdx).trim()
    const price = segment.slice(colonIdx + 1).trim()
    if (plan) result.set(plan, price)
  }
  return result
}

export function PricingComparisonTable({ data, emptyMessage }: PricingComparisonTableProps) {
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
    plans: parsePricingString(value),
  }))

  // Collect all plan names, preserving first-seen order
  const seen = new Set<string>()
  const allPlans: string[] = []
  for (const { plans } of parsed) {
    for (const plan of plans.keys()) {
      if (!seen.has(plan)) {
        seen.add(plan)
        allPlans.push(plan)
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
              套餐
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
          {allPlans.map((plan) => (
            <tr key={plan} className="hover:bg-gray-50/60">
              <td className="w-36 bg-gray-50 px-4 py-3 align-middle text-xs font-semibold tracking-wide text-gray-500 uppercase">
                {plan}
              </td>
              {parsed.map(({ competitor, plans }) => {
                const price = plans.get(plan)
                const isFree = price?.toLowerCase() === 'free'
                return (
                  <td key={competitor} className="px-4 py-3 align-middle">
                    {price !== undefined ? (
                      <span
                        className={
                          isFree ? 'font-medium text-green-700' : 'font-medium text-gray-900'
                        }
                      >
                        {price || '—'}
                      </span>
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
