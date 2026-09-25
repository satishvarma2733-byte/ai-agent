import { type ReactNode, useState } from 'react'

interface AnimatedTableProps<T> {
  columns: {
    key: string
    label: string
    width?: string | number
    align?: 'left' | 'right' | 'center'
    render?: (row: T, index: number) => ReactNode
  }[]
  data: T[]
  keyExtractor: (row: T, index: number) => string | number
  onRowClick?: (row: T) => void
  emptyState?: ReactNode
  loading?: boolean
}

export default function AnimatedTable<T>({
  columns,
  data,
  keyExtractor,
  onRowClick,
  emptyState,
  loading,
}: AnimatedTableProps<T>) {
  const [hovered, setHovered] = useState<string | number | null>(null)

  if (loading) {
    return (
      <div style={{ overflow: 'hidden', borderRadius: 14 }}>
        <table className="avn-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col.key} style={{ width: col.width, textAlign: col.align ?? 'left' }}>
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: 5 }, (_, i) => (
              <tr key={i}>
                {columns.map((col) => (
                  <td key={col.key}>
                    <div
                      style={{
                        height: 14,
                        borderRadius: 7,
                        background: 'rgba(255,255,255,0.04)',
                        width: `${50 + Math.random() * 40}%`,
                      }}
                      className="animate-shimmer"
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (!data.length && emptyState) {
    return <>{emptyState}</>
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="avn-table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} style={{ width: col.width, textAlign: col.align ?? 'left' }}>
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, index) => {
            const key = keyExtractor(row, index)
            return (
              <tr
                key={key}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                onMouseEnter={() => setHovered(key)}
                onMouseLeave={() => setHovered(null)}
                style={{
                  cursor: onRowClick ? 'pointer' : 'default',
                  background: hovered === key ? 'rgba(123,97,255,0.05)' : 'transparent',
                  opacity: 1,
                  transform: 'translateY(0)',
                  animation: `fadeInUp 0.3s cubic-bezier(0.22,1,0.36,1) ${index * 40}ms both`,
                }}
              >
                {columns.map((col) => (
                  <td key={col.key} style={{ textAlign: col.align ?? 'left' }}>
                    {col.render
                      ? col.render(row, index)
                      : String((row as Record<string, unknown>)[col.key] ?? '—')}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
