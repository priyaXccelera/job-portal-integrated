export function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(new Error('Could not read the file'))
    reader.readAsDataURL(file)
  })
}

export function isImageFile(file: File, maxBytes = 2 * 1024 * 1024): string {
  if (!file.type.startsWith('image/')) return 'Please choose an image file'
  if (file.size > maxBytes) return 'Image must be smaller than 2 MB'
  return ''
}
