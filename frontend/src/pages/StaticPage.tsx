import { useState } from 'react'
import type { FormEvent } from 'react'
import { ChevronDown } from 'lucide-react'
import toast from 'react-hot-toast'
import { TextAreaField, TextField } from '../components/fields'
import { Breadcrumbs } from '../components/ui'
import { useSeo } from '../hooks'
import { validateEmail, validateMinLength } from '../validation'

export type StaticPageKey = 'about' | 'contact' | 'terms' | 'privacy' | 'help'

const CONTENT: Record<StaticPageKey, { title: string; paragraphs: string[] }> = {
  about: {
    title: 'About JobHub',
    paragraphs: [
      'JobHub connects millions of job seekers with leading employers across India. Our mission is to make hiring and job search faster, fairer and more transparent.',
      'Candidates can discover roles, track applications and build a profile; recruiters can post jobs, manage applicants on a pipeline and search our talent database.',
    ],
  },
  terms: {
    title: 'Terms & Conditions',
    paragraphs: [
      'By using JobHub you agree to provide accurate information and to use the platform only for lawful hiring and job-seeking purposes.',
      'Recruiters must not charge candidates any fee. Accounts that post misleading jobs may be blocked without notice.',
      'We may update these terms from time to time; continued use means you accept the updated terms.',
    ],
  },
  privacy: {
    title: 'Privacy Policy',
    paragraphs: [
      'We collect the profile details you provide to help you find jobs and to let recruiters find you. You control your profile visibility from Privacy settings.',
      'Recruiters see masked contact details until they unlock a profile. We never sell your personal data.',
      'You can delete your account at any time from Account settings.',
    ],
  },
  help: { title: 'Help center', paragraphs: [] },
  contact: { title: 'Contact us', paragraphs: ['Questions, feedback or partnership ideas? Send us a message and we will respond within two business days.'] },
}

const FAQS = [
  { question: 'How do I apply for a job?', answer: 'Log in as a job seeker, open a job and press Apply. You can choose a resume and answer any screening questions.' },
  { question: 'How do I reset my password?', answer: 'Use the "Forgot password" link on the login page and follow the instructions sent to your email or mobile.' },
  { question: 'Why is my company awaiting approval?', answer: 'New company profiles are reviewed by our team before jobs can be published. This usually takes one business day.' },
  { question: 'How do credits work for recruiters?', answer: 'Viewing a candidate contact in the database costs credits. Your balance is shown in the candidate search and dashboard.' },
]

function ContactForm() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState('')
  const [attempted, setAttempted] = useState(false)
  const [sent, setSent] = useState(false)
  const errors = {
    name: validateMinLength(name, 2, 'Name'),
    email: validateEmail(email),
    message: validateMinLength(message, 10, 'Message'),
  }
  const isValid = !errors.name && !errors.email && !errors.message

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setAttempted(true)
    if (!isValid) return
    // MOCK: no endpoint exists in the API contract for contact messages; nothing is sent.
    setSent(true)
    toast.success('Message sent. We will get back to you soon.')
  }

  if (sent) {
    return <p className="rounded-lg bg-success/10 p-4 text-sm font-semibold text-success">Thanks {name}! Your message has been received.</p>
  }
  return (
    <form onSubmit={submit} noValidate className="mt-6 space-y-4">
      <TextField label="Your name" required value={name} error={attempted ? errors.name : ''} onChange={(event) => setName(event.target.value)} />
      <TextField label="Email" type="email" required value={email} error={attempted ? errors.email : ''} onChange={(event) => setEmail(event.target.value)} />
      <TextAreaField label="Message" required value={message} help="At least 10 characters" error={attempted ? errors.message : ''} onChange={(event) => setMessage(event.target.value)} />
      <button type="submit" className="btn-primary" disabled={attempted && !isValid}>
        Send message
      </button>
    </form>
  )
}

export function StaticPage({ page = 'about' }: { page?: StaticPageKey }) {
  const content = CONTENT[page]
  const [openIndex, setOpenIndex] = useState<number | null>(0)
  useSeo(content.title, content.paragraphs[0] ?? 'Help and support for JobHub users.')

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <Breadcrumbs items={[{ label: 'Home', to: '/' }, { label: content.title }]} />
      <h1 className="mb-4 text-3xl font-bold">{content.title}</h1>
      <div className="space-y-3 text-muted">
        {content.paragraphs.map((paragraph) => (
          <p key={paragraph}>{paragraph}</p>
        ))}
      </div>
      {page === 'contact' && <ContactForm />}
      {page === 'help' && (
        <div className="space-y-2">
          {FAQS.map((faq, index) => (
            <div key={faq.question} className="card">
              <button
                type="button"
                aria-expanded={openIndex === index}
                className="flex w-full items-center justify-between px-4 py-3 text-left font-semibold"
                onClick={() => setOpenIndex(openIndex === index ? null : index)}
              >
                {faq.question}
                <ChevronDown className={`h-4 w-4 transition ${openIndex === index ? 'rotate-180' : ''}`} />
              </button>
              {openIndex === index && <p className="px-4 pb-4 text-sm text-muted">{faq.answer}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
