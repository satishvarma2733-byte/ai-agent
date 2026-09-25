// Types generated from the backend OpenAPI schema. Regenerate with `npm run gen:api`
// after changing backend schemas (repo root: `python -m scripts.export_openapi`).
import type { components } from './generated/schema'

export type Schema<Name extends keyof components['schemas']> = components['schemas'][Name]
