/**
 * Evaluates a keyword query that supports AND / OR / NOT operators
 * (plain spaces behave like AND) against a haystack string.
 * Example: "react AND typescript NOT angular OR vue"
 */
export function matchesBoolean(haystack: string, query: string): boolean {
  const text = haystack.toLowerCase()
  const trimmed = query.trim()
  if (!trimmed) return true
  const clauses = trimmed.split(/\s+OR\s+/)
  return clauses.some((clause) => {
    const tokens = clause.split(/\s+/).filter((token) => token && token !== 'AND')
    let negate = false
    for (const token of tokens) {
      if (token === 'NOT') {
        negate = true
        continue
      }
      const found = text.includes(token.toLowerCase())
      if (negate ? found : !found) return false
      negate = false
    }
    return true
  })
}
