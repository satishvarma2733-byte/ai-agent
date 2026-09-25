// CSV cells that are safe to open in Excel/Sheets: quoted, quotes doubled, and values that a
// spreadsheet would run as a formula (= + - @, tab, carriage return) prefixed with an apostrophe.
const FORMULA_START = /^[=+\-@\t\r]/

export function csvCell(value: unknown): string {
  let text = value === null || value === undefined ? '' : String(value)
  if (FORMULA_START.test(text)) text = `'${text}`
  return `"${text.replace(/"/g, '""')}"`
}

export function csvRow(values: unknown[]): string {
  return values.map(csvCell).join(',')
}

export function downloadCsv(filename: string, rows: unknown[][]): void {
  const blob = new Blob([rows.map(csvRow).join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
