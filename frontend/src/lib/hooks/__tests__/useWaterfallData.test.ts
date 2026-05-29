import { renderHook, waitFor, act } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../../tests/mocks/server'
import { mockWaterfallData, mockWaterfallFreezeData } from '../../../tests/mocks/handlers'
import { useWaterfallData } from '../useWaterfallData'

const API_BASE = 'http://localhost:8000/api'

describe('useWaterfallData', () => {
  it('fetches data on mount and resolves loading', async () => {
    const { result } = renderHook(() => useWaterfallData())

    expect(result.current.loading).toBe(true)
    expect(result.current.mode).toBe('standard')

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.data).toEqual(mockWaterfallData)
    expect(result.current.error).toBeNull()
  })

  it('handles API error', async () => {
    server.use(
      http.get(`${API_BASE}/waterfall`, () => {
        return HttpResponse.error()
      })
    )

    const { result } = renderHook(() => useWaterfallData())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.error).toBeTruthy()
    expect(result.current.data).toBeNull()
  })

  it('refetches when mode changes to freeze', async () => {
    const { result } = renderHook(() => useWaterfallData())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.data).toEqual(mockWaterfallData)

    act(() => {
      result.current.setMode('freeze')
    })

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.mode).toBe('freeze')
    expect(result.current.data).toEqual(mockWaterfallFreezeData)
  })

  it('accepts initial mode parameter', async () => {
    const { result } = renderHook(() => useWaterfallData('freeze'))

    expect(result.current.mode).toBe('freeze')

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.data).toEqual(mockWaterfallFreezeData)
  })
})
