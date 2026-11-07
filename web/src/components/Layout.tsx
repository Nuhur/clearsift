import { Link, NavLink, Outlet, useLocation } from 'react-router'
import { screenerLink } from '../lib/screener'
import { SieveMark } from './SieveMark'
import { StockSearch } from './StockSearch'
import { ThemeSwitch } from './ThemeSwitch'

const PAGE = 'mx-auto w-full max-w-[1180px] px-4 sm:px-10'

function navClass({ isActive }: { isActive: boolean }): string {
  // a see-through border when not active, so the text doesn't jump when it's picked
  const state = isActive
    ? 'border-lapis font-bold text-ink'
    : 'border-transparent font-medium text-body hover:text-ink'
  return `flex min-h-11 items-center border-b-3 ${state}`
}

/** The header and page frame shared by every route. */
export function Layout() {
  const { pathname, search } = useLocation()
  return (
    <>
      <a
        href="#main"
        className="sr-only rounded-md bg-surface px-4 py-3 text-ink focus:not-sr-only focus:absolute focus:top-2 focus:left-2"
      >
        Skip to content
      </a>
      <header className="border-b border-line bg-surface">
        <div className={`${PAGE} flex flex-wrap items-center gap-x-8 gap-y-1 py-2`}>
          <Link to="/" className="flex min-h-11 items-center gap-2 text-xl font-extrabold text-ink">
            <SieveMark />
            clearsift
          </Link>
          <nav aria-label="Main">
            <ul className="flex gap-6">
              <li>
                {/* end, or every page would count as being under / */}
                <NavLink to="/" end className={navClass}>
                  Portfolio
                </NavLink>
              </li>
              <li>
                <NavLink to={screenerLink(pathname, search)} className={navClass}>
                  Screener
                </NavLink>
              </li>
            </ul>
          </nav>
          <div className="flex w-full flex-wrap items-center gap-x-6 gap-y-1 sm:ml-auto sm:w-auto">
            <ThemeSwitch />
            <StockSearch />
          </div>
        </div>
      </header>
      <main id="main" className={`${PAGE} py-8`}>
        <Outlet />
      </main>
    </>
  )
}
