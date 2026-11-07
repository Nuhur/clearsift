import { useTheme } from '../theme'
import { Switch } from './Switch'

/** The dark mode switch in the header. */
export function ThemeSwitch() {
  const [theme, setTheme] = useTheme()
  return (
    <Switch
      label="Dark mode"
      checked={theme === 'dark'}
      onChange={(dark) => setTheme(dark ? 'dark' : 'light')}
    />
  )
}
