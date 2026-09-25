import { type ReactNode } from 'react'

interface Column<T> {
  key: string
  header: string
  width?: number | string
  render?: (row: T) => ReactNode
}

interface TableProps<T extends Record<string, unknown>> {
  columns: Column<T>[]
  data: T[]
  keyField?: string
  onRowClick?: (row: T) => void
  emptyMessage?: string
}

export default function Table<T extends Record<string, unknown>>({
  columns,
  data,
  keyField = 'id',
  onRowClick,
  emptyMessage = 'No data',
}: TableProps<T>) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: 13.5,
          color: 'var(--color-text-primary)',
        }}
      >
        <thead>
          <tr
            style={{
              borderBottom: '1px solid #1e2236',
            }}
          >
            {columns.map(col => (
              <th
                key={col.key}
                style={{
                  textAlign: 'left',
                  padding: '10px 16px',
                  fontSize: 11.5,
                  fontWeight: 600,
                  color: 'var(--color-text-muted)',
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  whiteSpace: 'nowrap',
                  width: col.width,
                  background: 'var(--color-bg-card)',
                }}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                style={{ textAlign: 'center', padding: '40px 16px', color: 'var(--color-text-muted)', fontSize: 13 }}
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            data.map((row, i) => (
              <tr
                key={String(row[keyField] ?? i)}
                onClick={() => onRowClick?.(row)}
                style={{
                  borderBottom: '1px solid #1a1e30',
                  cursor: onRowClick ? 'pointer' : undefined,
                  transition: 'background 0.1s',
                }}
                onMouseOver={e => {
                  if (onRowClick) (e.currentTarget as HTMLTableRowElement).style.background = '#181c2e'
                }}
                onMouseOut={e => {
                  (e.currentTarget as HTMLTableRowElement).style.background = ''
                }}
              >
                {columns.map(col => (
                  <td
                    key={col.key}
                    style={{
                      padding: '12px 16px',
                      verticalAlign: 'middle',
                    }}
                  >
                    {col.render ? col.render(row) : String(row[col.key] ?? '—')}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
