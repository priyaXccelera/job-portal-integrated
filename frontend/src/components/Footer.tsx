import { Link } from 'react-router-dom'
import { Facebook, Linkedin, Twitter, Youtube } from './SocialIcons'

const COLUMNS = [
  {
    title: 'Company',
    links: [
      { label: 'About us', to: '/about' },
      { label: 'Contact us', to: '/contact' },
      { label: 'Help center', to: '/help' },
    ],
  },
  {
    title: 'Legal',
    links: [
      { label: 'Terms & conditions', to: '/terms' },
      { label: 'Privacy policy', to: '/privacy' },
    ],
  },
  {
    title: 'Explore',
    links: [
      { label: 'Browse jobs', to: '/jobs' },
      { label: 'Top companies', to: '/companies' },
      { label: 'Post a job', to: '/recruiter/post-job' },
    ],
  },
]

const SOCIALS = [
  { label: 'Facebook', href: 'https://facebook.com', icon: Facebook },
  { label: 'Twitter', href: 'https://twitter.com', icon: Twitter },
  { label: 'LinkedIn', href: 'https://linkedin.com', icon: Linkedin },
  { label: 'YouTube', href: 'https://youtube.com', icon: Youtube },
]

export function Footer() {
  return (
    <footer className="mt-12 border-t border-line bg-surface">
      <div className="mx-auto grid max-w-7xl gap-8 px-4 py-10 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <p className="text-xl font-extrabold text-primary">JobHub</p>
          <p className="mt-2 text-sm text-muted">India's trusted platform connecting talent with great employers.</p>
          <div className="mt-4 flex gap-3">
            {SOCIALS.map((social) => (
              <a
                key={social.label}
                href={social.href}
                target="_blank"
                rel="noreferrer"
                aria-label={social.label}
                className="rounded-full bg-soft p-2 text-primary hover:bg-primary hover:text-white"
              >
                <social.icon className="h-4 w-4" />
              </a>
            ))}
          </div>
        </div>
        {COLUMNS.map((column) => (
          <div key={column.title}>
            <h3 className="mb-3 text-sm font-bold">{column.title}</h3>
            <ul className="space-y-2 text-sm text-muted">
              {column.links.map((link) => (
                <li key={link.label}>
                  <Link to={link.to} className="hover:text-primary hover:underline">
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <p className="border-t border-line py-4 text-center text-xs text-muted">© 2026 JobHub. All rights reserved.</p>
    </footer>
  )
}
