import { useEffect, useRef, useState } from 'react'
import { Modal } from './ui'

const SIZE = 240

/** Square crop with zoom + pan sliders, rendered to a canvas. Returns a PNG data URL. */
export function PhotoCropper({
  file,
  onCancel,
  onSave,
}: {
  file: File | null
  onCancel: () => void
  onSave: (dataUrl: string) => void
}) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const [image, setImage] = useState<HTMLImageElement | null>(null)
  const [zoom, setZoom] = useState(1)
  const [offsetX, setOffsetX] = useState(0)
  const [offsetY, setOffsetY] = useState(0)

  useEffect(() => {
    if (!file) return undefined
    const url = URL.createObjectURL(file)
    const loaded = new Image()
    loaded.onload = () => {
      setImage(loaded)
      setZoom(1)
      setOffsetX(0)
      setOffsetY(0)
    }
    loaded.src = url
    return () => URL.revokeObjectURL(url)
  }, [file])

  useEffect(() => {
    const context = canvas.current?.getContext?.('2d')
    if (!context || !image) return
    const base = SIZE / Math.min(image.width, image.height)
    const width = image.width * base * zoom
    const height = image.height * base * zoom
    context.clearRect(0, 0, SIZE, SIZE)
    context.drawImage(image, (SIZE - width) / 2 + offsetX, (SIZE - height) / 2 + offsetY, width, height)
  }, [image, zoom, offsetX, offsetY])

  return (
    <Modal open={Boolean(file)} title="Crop profile photo" onClose={onCancel}>
      <div className="flex flex-col items-center gap-4">
        <canvas ref={canvas} width={SIZE} height={SIZE} className="h-60 w-60 rounded-full border border-line bg-canvas" aria-label="Photo preview" />
        <label className="flex w-full items-center gap-3 text-sm">
          Zoom
          <input type="range" min={1} max={3} step={0.05} value={zoom} onChange={(event) => setZoom(Number(event.target.value))} className="flex-1 accent-primary" />
        </label>
        <label className="flex w-full items-center gap-3 text-sm">
          Left / right
          <input type="range" min={-100} max={100} value={offsetX} onChange={(event) => setOffsetX(Number(event.target.value))} className="flex-1 accent-primary" />
        </label>
        <label className="flex w-full items-center gap-3 text-sm">
          Up / down
          <input type="range" min={-100} max={100} value={offsetY} onChange={(event) => setOffsetY(Number(event.target.value))} className="flex-1 accent-primary" />
        </label>
        <div className="flex w-full justify-end gap-3">
          <button type="button" className="btn-outline" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="btn-primary" disabled={!image} onClick={() => canvas.current && onSave(canvas.current.toDataURL('image/png'))}>
            Save photo
          </button>
        </div>
      </div>
    </Modal>
  )
}
