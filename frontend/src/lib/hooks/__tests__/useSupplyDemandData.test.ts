import { renderHook, waitFor } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../../tests/mocks/server'
import { mockSupplyDemandData } from '../../../tests/mocks/handlers'
import { useSupplyDemandData } from '../useSupplyDemandData'

const API_BASE = 'http://localhost:8000/api'

describe('useSupplyDemandData', () => {
  it('fetches all three scenarios on mount', async () => {
    const { result } = renderHook(() => useSupplyDemandData())

    expect(result.current.loading).toBe(true)

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.standardData).toEqual(mockSupplyDemandData)
    expect(result.current.realData).toEqual(mockSupplyDemandData)
    expect(result.current.freezeData).toEqual(mockSupplyDemandData)
    expect(result.current.error).toBeNull()
  })

  it('sets error when one scenario fails', async () => {
    let callCount = 0
    server.use(
      http.get(`${API_BASE}/supply-demand`, () => {
        callCount++
        // Fail the second call (real policy)
        if (callCount === 2) {
          return HttpResponse.error()
        }
        return HttpResponse.json(mockSupplyDemandData)
      })
    )

    const { result } = renderHook(() => useSupplyDemandData())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.error).toBe('One or more supply/demand scenarios failed to load')
    // Successful calls still populate their data
    expect(result.current.standardData).toEqual(mockSupplyDemandData)
  })

  it('handles all scenarios failing', async () => {
    server.use(
      http.get(`${API_BASE}/supply-demand`, () => {
        return HttpResponse.error()
      })
    )

    const { result } = renderHook(() => useSupplyDemandData())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.error).toBe('One or more supply/demand scenarios failed to load')
    expect(result.current.standardData).toBeNull()
    expect(result.current.realData).toBeNull()
    expect(result.current.freezeData).toBeNull()
  })

  it('returns trajectory data in the response', async () => {
    const { result } = renderHook(() => useSupplyDemandData())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.standardData?.trajectory).toHaveLength(2)
    expect(result.current.standardData?.trajectory[0]).toHaveProperty('date')
    expect(result.current.standardData?.trajectory[0]).toHaveProperty('backlog')
  })
})
