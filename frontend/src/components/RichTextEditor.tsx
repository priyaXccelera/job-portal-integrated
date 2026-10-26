import { useEffect, useRef } from 'react'
import { Bold, Italic, List, ListOrdered, Underline } from 'lucide-react'

const TOOLS = [
  { command: 'bold', label: 'Bold', icon: Bold },
  { command: 'italic', label: 'Italic', icon: Italic },
  { command: 'underline', label: 'Underline', icon: Underline },
  { command: 'insertUnorderedList', label: 'Bulleted list', icon: List },
  { command: 'insertOrderedList', label: 'Numbered list', icon: ListOrdered },
]

/** Minimal contentEditable rich text editor with a formatting toolbar. */
export function RichTextEditor({
  value,
  onChange,
  error,
}: {
  value: string
  onChange: (html: string) => void
  error?: string
}) {
  const editor = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (editor.current && editor.current.innerHTML !== value) editor.current.innerHTML = value
    // only sync from props when the value changes externally
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="space-y-1">
      <span className="block text-sm font-medium" id="rte-label">
        Job description <span className="text-danger">*</span>
      </span>
      <div className={`rounded-lg border bg-surface ${error ? 'border-danger' : 'border-line'}`}>
        <div className="flex gap-1 border-b border-line p-1" role="toolbar" aria-label="Formatting">
          {TOOLS.map((tool) => (
            <button
              key={tool.command}
              type="button"
              aria-label={tool.label}
              className="rounded p-2 hover:bg-soft"
              onMouseDown={(event) => {
                event.preventDefault()
                document.execCommand(tool.command)
                onChange(editor.current?.innerHTML ?? '')
              }}
            >
              <tool.icon className="h-4 w-4" />
            </button>
          ))}
        </div>
        <div
          ref={editor}
          role="textbox"
          aria-multiline="true"
          aria-labelledby="rte-label"
          contentEditable
          suppressContentEditableWarning
          className="min-h-48 p-3 text-sm focus:outline-none [&_ol]:list-decimal [&_ol]:pl-5 [&_ul]:list-disc [&_ul]:pl-5"
          onInput={(event) => onChange((event.target as HTMLDivElement).innerHTML)}
        />
      </div>
      {error && <p className="text-xs text-danger" role="alert">{error}</p>}
    </div>
  )
}
