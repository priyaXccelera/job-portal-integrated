import { useParams } from 'react-router-dom'
import { JobDetailView } from '../components/JobDetailView'
import { Breadcrumbs } from '../components/ui'
import { idFromSlug } from '../utils/format'

export function JobDetail() {
  const { slugId } = useParams()
  return (
    <div className="mx-auto max-w-4xl px-4 py-6">
      <Breadcrumbs items={[{ label: 'Home', to: '/' }, { label: 'Jobs', to: '/jobs' }, { label: 'Job details' }]} />
      <JobDetailView jobId={idFromSlug(slugId)} />
    </div>
  )
}
