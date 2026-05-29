import { useState, useCallback } from 'react'
import { predictPD, PredictData } from '@/lib/api'

export function usePredictData() {
  const [standardResult, setStandardResult] = useState<PredictData | null>(null)
  const [freezeResult, setFreezeResult] = useState<PredictData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const runPrediction = useCallback(async (priorityDate: string) => {
    setLoading(true)
    setError(null)
    try {
      const [std, frz] = await Promise.all([
        predictPD(priorityDate, false),
        predictPD(priorityDate, true),
      ])
      setStandardResult(std)
      setFreezeResult(frz)
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      const message = e?.response?.data?.detail || 'Prediction request failed'
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [])

  return { standardResult, freezeResult, loading, error, runPrediction }
}
