import { useTheme } from '../theme'

/** The dark mode switch in the header. */
export function ThemeSwitch() {
  const [theme, setTheme] = useTheme()
  return (
    <label className="flex min-h-11 cursor-pointer items-center gap-3 font-medium text-body">
      Dark mode
      {/* a real checkbox underneath, so keyboards and screen readers get it for free */}
      <input
        type="checkbox"
        role="switch"
        checked={theme === 'dark'}
        onChange={(event) => setTheme(event.target.checked ? 'dark' : 'light')}
        className="peer sr-only"
      />
      <span
        aria-hidden="true"
        className="relative h-6 w-11 shrink-0 rounded-full bg-muted peer-checked:bg-action peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-lapis after:absolute after:top-0.5 after:left-0.5 after:size-5 after:rounded-full after:bg-white after:content-[''] peer-checked:after:translate-x-5 motion-safe:after:transition-transform"
      />
    </label>
  )
}
