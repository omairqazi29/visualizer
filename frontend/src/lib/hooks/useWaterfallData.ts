import { useState, useEffect } from 'react'
import { getWaterfallData, WaterfallData } from '@/lib/api'

export type WaterfallMode = 'standard' | 'real' | 'freeze'

export function useWaterfallData(initialMode: WaterfallMode = 'standard') {
  const [data, setData] = useState<WaterfallData | null>(null)
  const [mode, setMode] = useState<WaterfallMode>(initialMode)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setData(null)
    setLoading(true)
    setError(null)
    const applyFreeze = mode === 'freeze'
    const applyReal = mode === 'real'
    getWaterfallData(applyFreeze, applyReal)
      .then((d) => {
        if (!cancelled) setData(d)
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          const err = e as { message?: string }
          setError(err?.message || 'Failed to load waterfall data')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [mode])

  return { data, loading, error, mode, setMode }
}
