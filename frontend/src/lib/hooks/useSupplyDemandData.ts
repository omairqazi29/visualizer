import { useState, useEffect } from 'react'
import { getSupplyDemandData, SupplyDemandData } from '@/lib/api'

export function useSupplyDemandData() {
  const [standardData, setStandardData] = useState<SupplyDemandData | null>(null)
  const [realData, setRealData] = useState<SupplyDemandData | null>(null)
  const [freezeData, setFreezeData] = useState<SupplyDemandData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.allSettled([
      getSupplyDemandData(false, false),
      getSupplyDemandData(false, true),
      getSupplyDemandData(true, false),
    ]).then(([stdRes, realRes, frzRes]) => {
      if (stdRes.status === 'fulfilled') setStandardData(stdRes.value)
      if (realRes.status === 'fulfilled') setRealData(realRes.value)
      if (frzRes.status === 'fulfilled') setFreezeData(frzRes.value)
      if (
        stdRes.status === 'rejected' ||
        realRes.status === 'rejected' ||
        frzRes.status === 'rejected'
      ) {
        setError('One or more supply/demand scenarios failed to load')
      }
      setLoading(false)
    })
  }, [])

  return { standardData, realData, freezeData, loading, error }
}
