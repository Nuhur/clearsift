import { Link } from 'react-router'

/** Shown for any address that isn't a page. */
export function NotFoundPage() {
  return (
    <>
      <h1 className="mb-2 text-3xl font-extrabold">Page not found</h1>
      <Link
        to="/"
        className="inline-flex min-h-11 items-center font-medium text-lapis underline underline-offset-4"
      >
        Back to Portfolio
      </Link>
    </>
  )
}
