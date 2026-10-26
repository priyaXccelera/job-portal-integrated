import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowLeft, Send } from 'lucide-react'
import { EmptyState, ErrorState, PageHeader, Skeleton } from '../components/ui'
import { getThreads, markThreadRead, sendMessage } from '../data/store'
import { useAsync, useSeo } from '../hooks'
import { timeAgo } from '../utils/format'

export function MessagesInbox() {
  const { data, loading, error, reload, setData } = useAsync(() => getThreads(), [])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)
  useSeo('Messages', 'Your conversations with recruiters and candidates.')

  const threads = data ?? []
  const selected = threads.find((thread) => thread.id === selectedId)

  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: 'end' })
  }, [selected?.messages.length, selectedId])

  const open = async (id: string) => {
    setSelectedId(id)
    await markThreadRead(id)
    reload()
  }

  const send = async (event: FormEvent) => {
    event.preventDefault()
    if (!selected || !text.trim() || sending) return
    setSending(true)
    try {
      setData(await sendMessage(selected.id, text.trim()))
      setText('')
    } catch {
      // API client shows the error toast
    } finally {
      setSending(false)
    }
  }

  if (error) return <ErrorState message={error} onRetry={reload} />

  return (
    <div>
      <PageHeader title="Messages" />
      <div className="card grid h-[70vh] overflow-hidden md:grid-cols-3">
        <ul className={`overflow-y-auto border-r border-line ${selected ? 'hidden md:block' : ''}`} aria-label="Conversations">
          {loading && <li className="p-4"><Skeleton className="h-12 w-full" /></li>}
          {threads.map((thread) => {
            const last = thread.messages[thread.messages.length - 1]
            return (
              <li key={thread.id}>
                <button type="button" className={`flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-soft ${thread.id === selectedId ? 'bg-soft' : ''}`} onClick={() => open(thread.id)}>
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary font-bold text-white">{thread.participant.slice(0, 1)}</span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center justify-between">
                      <span className="truncate text-sm font-semibold">{thread.participant}</span>
                      {thread.unread > 0 && <span className="rounded-full bg-accent px-2 text-xs font-bold text-white">{thread.unread}</span>}
                    </span>
                    <span className="block truncate text-xs text-muted">{thread.subtitle}</span>
                    <span className="block truncate text-xs text-muted">{last?.text}</span>
                  </span>
                </button>
              </li>
            )
          })}
          {!loading && threads.length === 0 && <li className="p-6 text-center text-sm text-muted">No conversations yet</li>}
        </ul>

        <div className={`flex min-h-0 flex-col md:col-span-2 ${selected ? '' : 'hidden md:flex'}`}>
          {selected ? (
            <>
              <div className="flex items-center gap-3 border-b border-line px-4 py-3">
                <button type="button" aria-label="Back to conversations" className="md:hidden" onClick={() => setSelectedId(null)}>
                  <ArrowLeft className="h-5 w-5" />
                </button>
                <div>
                  <p className="font-semibold">{selected.participant}</p>
                  <p className="text-xs text-muted">{selected.subtitle}</p>
                </div>
              </div>
              <div className="flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite">
                {selected.messages.map((message) => (
                  <div key={message.id} className={`flex ${message.from === 'me' ? 'justify-end' : ''}`}>
                    <div className={`max-w-[75%] rounded-2xl px-3 py-2 text-sm ${message.from === 'me' ? 'bg-primary text-white' : 'bg-soft'}`}>
                      <p>{message.text}</p>
                      <p className={`mt-1 text-[10px] ${message.from === 'me' ? 'text-white/70' : 'text-muted'}`}>{timeAgo(message.at)}</p>
                    </div>
                  </div>
                ))}
                <div ref={bottom} />
              </div>
              <form onSubmit={send} className="flex gap-2 border-t border-line p-3">
                <input className="input" aria-label="Type a message" placeholder="Type a message" value={text} onChange={(event) => setText(event.target.value)} />
                <button type="submit" className="btn-primary" disabled={!text.trim() || sending} aria-label="Send message">
                  <Send className="h-4 w-4" />
                </button>
              </form>
            </>
          ) : (
            <div className="m-auto p-6">
              <EmptyState title="Select a conversation" message="Pick a thread on the left to start chatting." />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
