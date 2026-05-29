import { useState, useCallback, useRef } from 'react'
import { predictPD, PredictData } from '@/lib/api'

export function usePredictData() {
  const [standardResult, setStandardResult] = useState<PredictData | null>(null)
  const [freezeResult, setFreezeResult] = useState<PredictData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const callIdRef = useRef(0)

  // Uses Promise.all (not Promise.allSettled) intentionally: the comparison UI
  // requires *both* standard and freeze results to render meaningfully. Showing
  // only one side would be misleading, so we treat a partial failure as a full
  // error — matching the original predict/page.tsx behaviour.
  const runPrediction = useCallback(async (priorityDate: string) => {
    const id = ++callIdRef.current
    setLoading(true)
    setError(null)
    try {
      const [std, frz] = await Promise.all([
        predictPD(priorityDate, false),
        predictPD(priorityDate, true),
      ])
      if (id !== callIdRef.current) return
      setStandardResult(std)
      setFreezeResult(frz)
    } catch (err: unknown) {
      if (id !== callIdRef.current) return
      const e = err as { response?: { data?: { detail?: string } } }
      const message = e?.response?.data?.detail || 'Prediction request failed'
      setError(message)
    } finally {
      if (id === callIdRef.current) setLoading(false)
    }
  }, [])

  return { standardResult, freezeResult, loading, error, runPrediction }
}
