import { renderHook, waitFor, act } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../../tests/mocks/server'
import { mockPredictData, mockPredictFreezeData } from '../../../tests/mocks/handlers'
import { usePredictData } from '../usePredictData'

const API_BASE = 'http://localhost:8000/api'

describe('usePredictData', () => {
  it('starts idle with no data', () => {
    const { result } = renderHook(() => usePredictData())

    expect(result.current.loading).toBe(false)
    expect(result.current.standardResult).toBeNull()
    expect(result.current.freezeResult).toBeNull()
    expect(result.current.error).toBeNull()
  })

  it('fetches standard and freeze predictions', async () => {
    const { result } = renderHook(() => usePredictData())

    await act(async () => {
      await result.current.runPrediction('2025-01-16')
    })

    expect(result.current.loading).toBe(false)
    expect(result.current.standardResult).toEqual(mockPredictData)
    expect(result.current.freezeResult).toEqual(mockPredictFreezeData)
    expect(result.current.error).toBeNull()
  })

  it('passes priority_date param to the API', async () => {
    const receivedDates: string[] = []
    server.use(
      http.get(`${API_BASE}/predict`, ({ request }) => {
        const url = new URL(request.url)
        const pd = url.searchParams.get('priority_date')
        if (pd) receivedDates.push(pd)
        const applyFreeze = url.searchParams.get('apply_freeze') === 'true'
        return HttpResponse.json(applyFreeze ? mockPredictFreezeData : mockPredictData)
      })
    )

    const { result } = renderHook(() => usePredictData())

    await act(async () => {
      await result.current.runPrediction('2024-07-01')
    })

    // Both standard and freeze calls should include the priority_date
    expect(receivedDates).toEqual(['2024-07-01', '2024-07-01'])
  })

  it('handles prediction error', async () => {
    server.use(
      http.get(`${API_BASE}/predict`, () => {
        return HttpResponse.error()
      })
    )

    const { result } = renderHook(() => usePredictData())

    await act(async () => {
      await result.current.runPrediction('2025-01-16')
    })

    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBe('Prediction request failed')
    expect(result.current.standardResult).toBeNull()
  })

  it('clears previous error on new prediction', async () => {
    // First: fail
    server.use(
      http.get(`${API_BASE}/predict`, () => {
        return HttpResponse.error()
      })
    )

    const { result } = renderHook(() => usePredictData())

    await act(async () => {
      await result.current.runPrediction('2025-01-16')
    })
    expect(result.current.error).toBeTruthy()

    // Reset handlers so the default (success) handler is restored
    server.resetHandlers()

    await act(async () => {
      await result.current.runPrediction('2025-01-16')
    })

    expect(result.current.error).toBeNull()
    expect(result.current.standardResult).toEqual(mockPredictData)
  })
})
