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
