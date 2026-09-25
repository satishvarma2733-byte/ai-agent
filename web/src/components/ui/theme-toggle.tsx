import { useState } from "react"
import { Moon, Sun } from "lucide-react"
import { cn } from "@/lib/utils"

interface ThemeToggleProps {
  /** Extra Tailwind classes */
  className?: string
  /** Controlled dark-mode value (from parent) */
  isDark?: boolean
  /** Called when user clicks the toggle */
  onToggle?: (nextDark: boolean) => void
}

/**
 * ThemeToggle — animated pill-style dark/light mode switcher.
 *
 * Usage (uncontrolled, self-contained):
 *   <ThemeToggle />
 *
 * Usage (controlled, wired to Layout's darkMode state):
 *   <ThemeToggle isDark={darkMode} onToggle={setDarkMode} />
 */
export function ThemeToggle({ className, isDark: isDarkProp, onToggle }: ThemeToggleProps) {
  // Support both controlled and uncontrolled usage
  const [internalDark, setInternalDark] = useState(isDarkProp ?? true)
  const isDark = isDarkProp !== undefined ? isDarkProp : internalDark

  const handleClick = () => {
    const next = !isDark
    setInternalDark(next)
    onToggle?.(next)
  }

  return (
    <div
      className={cn(
        "flex w-16 h-8 p-1 rounded-full cursor-pointer transition-all duration-300",
        isDark
          ? "bg-zinc-950 border border-zinc-800"
          : "bg-white border border-zinc-200",
        className
      )}
      onClick={handleClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" || e.key === " " ? handleClick() : undefined}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      aria-pressed={isDark}
    >
      <div className="flex justify-between items-center w-full">
        {/* Left icon — moon (dark) / translates right when light */}
        <div
          className={cn(
            "flex justify-center items-center w-6 h-6 rounded-full transition-transform duration-300",
            isDark
              ? "transform translate-x-0 bg-zinc-800"
              : "transform translate-x-8 bg-gray-200"
          )}
        >
          {isDark ? (
            <Moon className="w-4 h-4 text-white" strokeWidth={1.5} />
          ) : (
            <Sun className="w-4 h-4 text-gray-700" strokeWidth={1.5} />
          )}
        </div>

        {/* Right icon — sun (dark) / moon translates left when light */}
        <div
          className={cn(
            "flex justify-center items-center w-6 h-6 rounded-full transition-transform duration-300",
            isDark
              ? "bg-transparent"
              : "transform -translate-x-8"
          )}
        >
          {isDark ? (
            <Sun className="w-4 h-4 text-gray-500" strokeWidth={1.5} />
          ) : (
            <Moon className="w-4 h-4 text-black" strokeWidth={1.5} />
          )}
        </div>
      </div>
    </div>
  )
}
