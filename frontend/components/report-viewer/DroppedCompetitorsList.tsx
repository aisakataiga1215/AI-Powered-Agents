interface DroppedCompetitor {
  name: string
  url: string
  reason: string
}

interface Props {
  dropped: DroppedCompetitor[]
  className?: string
}

export function DroppedCompetitorsList({ dropped, className }: Props) {
  return (
    <section
      className={`rounded-xl border border-orange-200 bg-orange-50 p-5${className ? ` ${className}` : ''}`}
    >
      <h3 className="mb-3 text-sm font-semibold text-orange-900">
        Dropped / Insufficient Competitors ({dropped.length})
      </h3>
      <ul className="space-y-2 text-sm">
        {dropped.map((c) => (
          <li
            key={c.name}
            className="flex items-start gap-3 rounded border border-orange-100 bg-white/70 px-3 py-2"
          >
            <div>
              <span className="font-medium text-gray-900">{c.name}</span>
              <span className="ml-2 text-xs text-gray-500">{c.url}</span>
              <p className="mt-0.5 text-xs text-orange-700">{c.reason}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

export type { DroppedCompetitor }
