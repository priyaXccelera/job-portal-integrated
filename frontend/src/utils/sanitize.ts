/** Strips scripts, iframes, inline event handlers and javascript: links from rich-text HTML. */
export function sanitizeHtml(html: string): string {
  const documentFragment = new DOMParser().parseFromString(html, 'text/html')
  documentFragment.querySelectorAll('script, style, iframe, object, embed, link, meta').forEach((node) => node.remove())
  documentFragment.body.querySelectorAll('*').forEach((element) => {
    Array.from(element.attributes).forEach((attribute) => {
      const name = attribute.name.toLowerCase()
      if (name.startsWith('on') || (['href', 'src'].includes(name) && attribute.value.trim().toLowerCase().startsWith('javascript:'))) {
        element.removeAttribute(attribute.name)
      }
    })
  })
  return documentFragment.body.innerHTML
}
