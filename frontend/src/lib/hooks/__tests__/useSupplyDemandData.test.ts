import { renderHook, waitFor } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../../tests/mocks/server'
import {
  mockSupplyDemandStandardData,
  mockSupplyDemandRealData,
  mockSupplyDemandFreezeData,
} from '../../../tests/mocks/handlers'
import { useSupplyDemandData } from '../useSupplyDemandData'

const API_BASE = 'http://localhost:8000/api'

describe('useSupplyDemandData', () => {
  it('fetches all three scenarios with correct params', async () => {
    const { result } = renderHook(() => useSupplyDemandData())

    expect(result.current.loading).toBe(true)

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.standardData).toEqual(mockSupplyDemandStandardData)
    expect(result.current.realData).toEqual(mockSupplyDemandRealData)
    expect(result.current.freezeData).toEqual(mockSupplyDemandFreezeData)
    // Verify each slot got distinct data
    expect(result.current.standardData).not.toEqual(result.current.realData)
    expect(result.current.standardData).not.toEqual(result.current.freezeData)
    expect(result.current.error).toBeNull()
  })

  it('sets error when one scenario fails (partial success)', async () => {
    server.use(
      http.get(`${API_BASE}/supply-demand`, ({ request }) => {
        const url = new URL(request.url)
        // Fail only the real-policy call (apply_real_restrictions=true)
        if (url.searchParams.get('apply_real_restrictions') === 'true') {
          return HttpResponse.error()
        }
        const applyFreeze = url.searchParams.get('apply_freeze') === 'true'
        return HttpResponse.json(
          applyFreeze ? mockSupplyDemandFreezeData : mockSupplyDemandStandardData
        )
      })
    )

    const { result } = renderHook(() => useSupplyDemandData())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.error).toBe('One or more supply/demand scenarios failed to load')
    // Successful calls still populate their data
    expect(result.current.standardData).toEqual(mockSupplyDemandStandardData)
    expect(result.current.realData).toBeNull()
    expect(result.current.freezeData).toEqual(mockSupplyDemandFreezeData)
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
