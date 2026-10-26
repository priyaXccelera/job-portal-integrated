import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/auth'
import { Footer } from './Footer'
import { Header } from './Header'
import { navFor } from './navItems'

export function PublicLayout() {
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-primary focus:px-3 focus:py-2 focus:text-white">
        Skip to content
      </a>
      <Header />
      <main id="main" className="flex-1">
        <Outlet />
      </main>
      <Footer />
    </div>
  )
}

export function AreaLayout() {
  const { role } = useAuth()
  const items = navFor(role)

  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-4 py-6 lg:flex-row">
        <aside className="lg:w-60 lg:shrink-0">
          <nav aria-label="Account" className="flex gap-1 overflow-x-auto lg:sticky lg:top-20 lg:flex-col lg:overflow-visible lg:rounded-card lg:border lg:border-line lg:bg-surface lg:p-2">
            {items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `flex shrink-0 items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium ${
                    isActive ? 'bg-primary text-white' : 'text-muted hover:bg-soft hover:text-ink'
                  }`
                }
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </NavLink>
            ))}
          </nav>
        </aside>
        <main id="main" className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>
      <Footer />
    </div>
  )
}
