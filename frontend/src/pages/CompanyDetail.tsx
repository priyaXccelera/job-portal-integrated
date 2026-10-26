import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Globe, MapPin, Users } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAuth } from '../auth/auth'
import { JobCard } from '../components/JobCard'
import { TextAreaField, TextField } from '../components/fields'
import { Breadcrumbs, CompanyLogo, EmptyState, ErrorState, ListSkeleton, Skeleton, Stars } from '../components/ui'
import { addCompanyReview, followCompany, getCompany, getCompanyJobs, getCompanyReviews, getFollowingIds, unfollowCompany } from '../data/store'
import { useAsync, useDebouncedValue, useSeo } from '../hooks'
import { formatDate, idFromSlug } from '../utils/format'
import { validateMinLength } from '../validation'

export function CompanyDetail() {
  const { slugId } = useParams()
  const id = idFromSlug(slugId)
  const navigate = useNavigate()
  const { role } = useAuth()
  const [search, setSearch] = useState('')
  const debounced = useDebouncedValue(search)
  const company = useAsync(() => getCompany(id), [id])
  const jobs = useAsync(() => getCompanyJobs(id, debounced), [id, debounced])
  const reviews = useAsync(() => getCompanyReviews(id), [id])
  const following = useAsync(() => (role === 'JOB_SEEKER' ? getFollowingIds() : Promise.resolve([] as string[])), [role])
  const [rating, setRating] = useState(0)
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [attempted, setAttempted] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  useSeo(company.data?.name ?? 'Company', company.data?.about ?? 'Company profile on JobHub')

  const isFollowing = Boolean(following.data?.includes(id))
  const errors = {
    rating: rating ? '' : 'Choose a star rating',
    title: validateMinLength(title, 3, 'Title'),
    body: validateMinLength(body, 10, 'Review'),
  }
  const isValid = !errors.rating && !errors.title && !errors.body

  const toggleFollow = async () => {
    if (!role) {
      navigate(`/login?returnTo=${encodeURIComponent(window.location.pathname)}`)
      return
    }
    if (role !== 'JOB_SEEKER') {
      toast.error('Only job seekers can follow companies')
      return
    }
    try {
      if (isFollowing) await unfollowCompany(id)
      else await followCompany(id)
      following.reload()
      toast.success(isFollowing ? 'Unfollowed' : 'Following company')
    } catch {
      // API client toasts errors
    }
  }

  const submitReview = async () => {
    setAttempted(true)
    if (!isValid) return
    setSubmitting(true)
    try {
      await addCompanyReview(id, { rating, title: title.trim(), body: body.trim() })
      toast.success('Review submitted')
      setRating(0)
      setTitle('')
      setBody('')
      setAttempted(false)
      reviews.reload()
    } catch {
      // API client toasts errors
    } finally {
      setSubmitting(false)
    }
  }

  if (company.loading) {
    return (
      <div className="mx-auto max-w-5xl space-y-4 px-4 py-6">
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    )
  }
  if (company.error) return <div className="mx-auto max-w-3xl px-4 py-10"><ErrorState message={company.error} onRetry={company.reload} /></div>
  const data = company.data
  if (!data) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <EmptyState title="Company not found" action={<Link to="/companies" className="btn-primary">Browse companies</Link>} />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      <Breadcrumbs items={[{ label: 'Home', to: '/' }, { label: 'Companies', to: '/companies' }, { label: data.name }]} />
      <div className="card overflow-hidden">
        <img src={data.bannerUrl} alt="" className="h-40 w-full object-cover" />
        <div className="flex flex-wrap items-end gap-4 p-5">
          <div className="-mt-14 rounded-xl border-4 border-surface">
            <CompanyLogo src={data.logoUrl} name={data.name} size="h-20 w-20" />
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="text-2xl font-bold">{data.name}</h1>
            <div className="flex flex-wrap items-center gap-3 text-sm text-muted">
              <Stars value={data.rating} />
              <span>
                {data.rating} · {data.reviewsCount} reviews
              </span>
              <span className="inline-flex items-center gap-1"><MapPin className="h-4 w-4" />{data.headquarters}</span>
              <span className="inline-flex items-center gap-1"><Users className="h-4 w-4" />{data.size} employees</span>
            </div>
          </div>
          <div className="flex gap-2">
            <a href={data.website} target="_blank" rel="noreferrer" className="btn-outline">
              <Globe className="h-4 w-4" />
              Website
            </a>
            <button type="button" className={isFollowing ? 'btn-outline' : 'btn-primary'} aria-pressed={isFollowing} onClick={toggleFollow}>
              {isFollowing ? 'Following' : 'Follow'}
            </button>
          </div>
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <section className="card p-5">
            <h2 className="mb-2 font-bold">About {data.name}</h2>
            <p className="text-sm text-muted">{data.about}</p>
            <p className="mt-3 text-sm">
              <span className="text-muted">Industry:</span> {data.industry} · <span className="text-muted">Type:</span> {data.companyType}
            </p>
          </section>

          <section className="card p-5">
            <h2 className="mb-3 font-bold">Benefits</h2>
            <div className="flex flex-wrap gap-2">
              {data.benefits.map((benefit) => (
                <span key={benefit} className="chip">{benefit}</span>
              ))}
              {data.benefits.length === 0 && <p className="text-sm text-muted">No benefits listed yet.</p>}
            </div>
          </section>

          {data.gallery.length > 0 && (
            <section className="card p-5">
              <h2 className="mb-3 font-bold">Gallery</h2>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {data.gallery.map((image, index) => (
                  <img key={index} src={image} alt={`${data.name} office ${index + 1}`} className="h-24 w-full rounded-lg object-cover" />
                ))}
              </div>
            </section>
          )}

          <section>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-bold">Active jobs</h2>
              <input className="input w-56" type="search" placeholder="Search jobs in company" aria-label="Search jobs in company" value={search} onChange={(event) => setSearch(event.target.value)} />
            </div>
            {jobs.loading ? (
              <ListSkeleton count={2} />
            ) : jobs.data && jobs.data.length > 0 ? (
              <div className="space-y-3">{jobs.data.map((job) => <JobCard key={job.id} job={job} />)}</div>
            ) : (
              <EmptyState title="No active jobs" message="This company has no openings matching your search." />
            )}
          </section>
        </div>

        <section className="space-y-4" aria-label="Reviews">
          <h2 className="font-bold">Reviews</h2>
          {role === 'JOB_SEEKER' && (
            <div className="card space-y-3 p-4">
              <h3 className="text-sm font-bold">Write a review</h3>
              <div>
                <Stars value={rating} onChange={setRating} size="h-6 w-6" />
                {attempted && errors.rating && <p className="text-xs text-danger" role="alert">{errors.rating}</p>}
              </div>
              <TextField label="Title" value={title} error={attempted ? errors.title : ''} onChange={(event) => setTitle(event.target.value)} />
              <TextAreaField label="Your review" value={body} help="At least 10 characters" error={attempted ? errors.body : ''} onChange={(event) => setBody(event.target.value)} />
              <button type="button" className="btn-primary w-full" disabled={submitting} onClick={submitReview}>
                {submitting ? 'Submitting…' : 'Submit review'}
              </button>
            </div>
          )}
          {!role && (
            <p className="text-sm text-muted">
              <Link to={`/login?returnTo=${encodeURIComponent(window.location.pathname)}`} className="font-semibold text-primary">Log in</Link> as a job seeker to write a review.
            </p>
          )}
          {reviews.loading && <Skeleton className="h-24 w-full" />}
          {reviews.data?.map((review) => (
            <article key={review.id} className="card p-4">
              <Stars value={review.rating} />
              <h3 className="mt-1 text-sm font-bold">{review.title}</h3>
              <p className="mt-1 text-sm text-muted">{review.body}</p>
              <p className="mt-2 text-xs text-muted">{review.author} · {formatDate(review.createdAt)}</p>
            </article>
          ))}
          {reviews.data?.length === 0 && <p className="text-sm text-muted">No reviews yet.</p>}
        </section>
      </div>
    </div>
  )
}
