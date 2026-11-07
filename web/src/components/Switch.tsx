/** An on/off switch, built on a real checkbox so keyboards and screen readers get it for free. */
export function Switch({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <label className="flex min-h-11 cursor-pointer items-center gap-3 font-medium text-body">
      {label}
      <input
        type="checkbox"
        role="switch"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="peer sr-only"
      />
      <span
        aria-hidden="true"
        className="relative h-6 w-11 shrink-0 rounded-full bg-muted peer-checked:bg-action peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-lapis after:absolute after:top-0.5 after:left-0.5 after:size-5 after:rounded-full after:bg-white after:content-[''] peer-checked:after:translate-x-5 motion-safe:after:transition-transform"
      />
    </label>
  )
}
