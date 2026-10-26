import {
  BarChart3,
  Bell,
  Bookmark,
  BriefcaseBusiness,
  Building2,
  CheckSquare,
  Database,
  FolderSearch,
  KeyRound,
  LayoutDashboard,
  Lock,
  MessageSquare,
  PlusCircle,
  Settings,
  ShieldAlert,
  Sparkles,
  UserCircle,
  Users,
  UsersRound,
  Heart,
  BellRing,
  FileText,
  Search,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { Role } from '../types'

export interface NavItem {
  label: string
  to: string
  icon: LucideIcon
  roles: Role[]
}

const SEEKER: Role[] = ['JOB_SEEKER']
const RECRUITER: Role[] = ['RECRUITER']
const ADMIN: Role[] = ['ADMIN']
const ALL: Role[] = ['JOB_SEEKER', 'RECRUITER', 'ADMIN']

export const NAV_ITEMS: NavItem[] = [
  { label: 'Dashboard', to: '/seeker/dashboard', icon: LayoutDashboard, roles: SEEKER },
  { label: 'My profile', to: '/seeker/profile', icon: UserCircle, roles: SEEKER },
  { label: 'Recommended jobs', to: '/seeker/recommended', icon: Sparkles, roles: SEEKER },
  { label: 'Saved jobs', to: '/seeker/saved', icon: Bookmark, roles: SEEKER },
  { label: 'Applied jobs', to: '/seeker/applied', icon: CheckSquare, roles: SEEKER },
  { label: 'Job alerts', to: '/seeker/alerts', icon: BellRing, roles: SEEKER },
  { label: 'Following', to: '/seeker/following', icon: Heart, roles: SEEKER },
  { label: 'Privacy', to: '/seeker/privacy', icon: Lock, roles: SEEKER },
  { label: 'Notification settings', to: '/seeker/notification-preferences', icon: Settings, roles: SEEKER },
  { label: 'Account settings', to: '/seeker/account', icon: FileText, roles: SEEKER },

  { label: 'Dashboard', to: '/recruiter/dashboard', icon: LayoutDashboard, roles: RECRUITER },
  { label: 'Post a job', to: '/recruiter/post-job', icon: PlusCircle, roles: RECRUITER },
  { label: 'Manage jobs', to: '/recruiter/jobs', icon: BriefcaseBusiness, roles: RECRUITER },
  { label: 'Candidate search', to: '/recruiter/candidates', icon: Search, roles: RECRUITER },
  { label: 'Searches & folders', to: '/recruiter/saved', icon: FolderSearch, roles: RECRUITER },
  { label: 'Company profile', to: '/recruiter/company', icon: Building2, roles: RECRUITER },
  { label: 'Team', to: '/recruiter/team', icon: UsersRound, roles: RECRUITER },

  { label: 'Dashboard', to: '/admin/dashboard', icon: LayoutDashboard, roles: ADMIN },
  { label: 'Company approvals', to: '/admin/companies', icon: Building2, roles: ADMIN },
  { label: 'Moderation', to: '/admin/moderation', icon: ShieldAlert, roles: ADMIN },
  { label: 'Master data', to: '/admin/master', icon: Database, roles: ADMIN },
  { label: 'Users & credits', to: '/admin/users', icon: Users, roles: ADMIN },
  { label: 'Analytics', to: '/admin/analytics', icon: BarChart3, roles: ADMIN },

  { label: 'Messages', to: '/messages', icon: MessageSquare, roles: ['JOB_SEEKER', 'RECRUITER'] },
  { label: 'Notifications', to: '/notifications', icon: Bell, roles: ALL },
  { label: 'Change password', to: '/change-password', icon: KeyRound, roles: ALL },
]

export function navFor(role: Role | null): NavItem[] {
  if (!role) return []
  return NAV_ITEMS.filter((item) => item.roles.includes(role))
}
