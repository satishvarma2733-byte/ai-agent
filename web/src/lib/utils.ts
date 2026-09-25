import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * cn() — shadcn-compatible class name utility.
 * Merges Tailwind classes intelligently via tailwind-merge,
 * and handles conditional classes via clsx.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
