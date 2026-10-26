import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { Bell, ChevronDown, LogOut, Menu, Moon, Sun, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { homeFor, logout, useAuth } from '../auth/auth'
import { getNotifications, markAllNotificationsRead } from '../data/store'
import { useAsync } from '../hooks'
import { timeAgo } from '../utils/format'
import { navFor } from './navItems'
import { ConfirmDialog } from './ui'

function useTheme(): [boolean, () => void] {
  const [dark, setDark] = useState(() => localStorage.getItem('theme') === 'dark')
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])
  return [dark, () => setDark((current) => !current)]
}

function useOutsideClick(onOutside: () => void) {
  const reference = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const handler = (event: MouseEvent) => {
      if (reference.current && !reference.current.contains(event.target as Node)) onOutside()
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [onOutside])
  return reference
}

function NotificationBell() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const reference = useOutsideClick(() => setOpen(false))
  const { data, reload } = useAsync(() => getNotifications(), [])
  const items = data ?? []
  const unread = items.filter((item) => !item.read).length

  return (
    <div ref={reference} className="relative">
      <button
        type="button"
        aria-label={`Notifications, ${unread} unread`}
        className="relative rounded-full p-2 hover:bg-soft"
        onClick={() => {
          setOpen((current) => !current)
          reload()
        }}
      >
        <Bell className="h-5 w-5" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[10px] font-bold text-white">
            {unread}
          </span>
        )}
      </button>
      {open && (
        <div className="card absolute right-0 z-40 mt-2 w-80 max-w-[90vw] overflow-hidden">
          <div className="flex items-center justify-between border-b border-line px-4 py-2">
            <span className="text-sm font-bold">Notifications</span>
            <button
              type="button"
              className="text-xs font-semibold text-primary"
              onClick={async () => {
                await markAllNotificationsRead()
                reload()
              }}
            >
              Mark all read
            </button>
          </div>
          <ul className="max-h-72 overflow-y-auto">
            {items.slice(0, 5).map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={`block w-full px-4 py-3 text-left hover:bg-soft ${item.read ? '' : 'bg-soft/60'}`}
                  onClick={() => {
                    setOpen(false)
                    navigate(item.link ?? '/notifications')
                  }}
                >
                  <p className="text-sm font-semibold">{item.title}</p>
                  <p className="text-xs text-muted">{item.body}</p>
                  <p className="mt-1 text-[11px] text-muted">{timeAgo(item.createdAt)}</p>
                </button>
              </li>
            ))}
            {items.length === 0 && <li className="px-4 py-6 text-center text-sm text-muted">You're all caught up</li>}
          </ul>
          <Link to="/notifications" onClick={() => setOpen(false)} className="block border-t border-line px-4 py-2 text-center text-sm font-semibold text-primary">
            View all
          </Link>
        </div>
      )}
    </div>
  )
}

function ProfileMenu() {
  const navigate = useNavigate()
  const { user, role } = useAuth()
  const [open, setOpen] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const reference = useOutsideClick(() => setOpen(false))

  return (
    <div ref={reference} className="relative">
      <button
        type="button"
        className="flex items-center gap-2 rounded-full py-1 pl-1 pr-2 hover:bg-soft"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-sm font-bold text-white">
          {user?.name.slice(0, 1)}
        </span>
        <span className="hidden max-w-28 truncate text-sm font-semibold md:inline">{user?.name}</span>
        <ChevronDown className="h-4 w-4" />
      </button>
      {open && (
        <div role="menu" className="card absolute right-0 z-40 mt-2 w-60 py-2">
          <div className="border-b border-line px-4 pb-2">
            <p className="truncate text-sm font-bold">{user?.name}</p>
            <p className="truncate text-xs text-muted">{user?.email}</p>
          </div>
          {navFor(role).slice(0, 7).map((item) => (
            <Link key={item.to} role="menuitem" to={item.to} onClick={() => setOpen(false)} className="flex items-center gap-2 px-4 py-2 text-sm hover:bg-soft">
              <item.icon className="h-4 w-4 text-muted" />
              {item.label}
            </Link>
          ))}
          <button type="button" role="menuitem" className="flex w-full items-center gap-2 px-4 py-2 text-sm text-danger hover:bg-soft" onClick={() => setConfirming(true)}>
            <LogOut className="h-4 w-4" />
            Logout
          </button>
        </div>
      )}
      <ConfirmDialog
        open={confirming}
        title="Log out?"
        message="You will need to log in again to access your account."
        confirmLabel="Logout"
        onCancel={() => setConfirming(false)}
        onConfirm={async () => {
          await logout()
          setConfirming(false)
          setOpen(false)
          toast.success('Logged out')
          navigate('/login')
        }}
      />
    </div>
  )
}

export function Header() {
  const { isLoggedIn, role } = useAuth()
  const [dark, toggleTheme] = useTheme()
  const [mobileOpen, setMobileOpen] = useState(false)

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-lg px-3 py-2 text-sm font-semibold ${isActive ? 'bg-soft text-primary' : 'text-ink hover:bg-soft'}`

  const employerTarget = role === 'RECRUITER' ? '/recruiter/post-job' : '/register?role=RECRUITER'

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-surface/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4">
        <Link to="/" className="text-2xl font-extrabold text-primary" aria-label="JobHub home">
          Job<span className="text-accent">Hub</span>
        </Link>
        <nav className="hidden items-center gap-1 md:flex" aria-label="Main">
          <NavLink to="/jobs" className={linkClass}>
            Jobs
          </NavLink>
          <NavLink to="/companies" className={linkClass}>
            Companies
          </NavLink>
          {isLoggedIn && role && (
            <NavLink to={homeFor(role)} className={linkClass}>
              Dashboard
            </NavLink>
          )}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <button type="button" aria-label="Toggle dark mode" className="rounded-full p-2 hover:bg-soft" onClick={toggleTheme}>
            {dark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
          </button>
          {isLoggedIn ? (
            <>
              <NotificationBell />
              <ProfileMenu />
            </>
          ) : (
            <div className="hidden items-center gap-2 sm:flex">
              <Link to="/login" className="btn-outline">
                Login
              </Link>
              <Link to="/register" className="btn-primary">
                Register
              </Link>
            </div>
          )}
          {role !== 'ADMIN' && role !== 'JOB_SEEKER' && (
            <Link to={employerTarget} className="btn-accent hidden lg:inline-flex">
              For Employers / Post a Job
            </Link>
          )}
          <button type="button" aria-label="Open menu" className="rounded p-2 hover:bg-soft md:hidden" onClick={() => setMobileOpen((current) => !current)}>
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>
      {mobileOpen && (
        <nav className="space-y-1 border-t border-line px-4 py-3 md:hidden" aria-label="Mobile">
          <NavLink to="/jobs" className={linkClass} onClick={() => setMobileOpen(false)}>
            Jobs
          </NavLink>
          <NavLink to="/companies" className={linkClass} onClick={() => setMobileOpen(false)}>
            Companies
          </NavLink>
          {!isLoggedIn && (
            <>
              <NavLink to="/login" className={linkClass} onClick={() => setMobileOpen(false)}>
                Login
              </NavLink>
              <NavLink to="/register" className={linkClass} onClick={() => setMobileOpen(false)}>
                Register
              </NavLink>
            </>
          )}
          {role !== 'ADMIN' && role !== 'JOB_SEEKER' && (
            <NavLink to={employerTarget} className={linkClass} onClick={() => setMobileOpen(false)}>
              For Employers / Post a Job
            </NavLink>
          )}
        </nav>
      )}
    </header>
  )
}
