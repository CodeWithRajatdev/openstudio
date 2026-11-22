import { useCallback, useEffect, useState } from 'react'
import { api } from './api'

/** Debounced live preview from the API. Returns {data, error, loading, refresh}. */
export function usePreview(body, enabled = true, delay = 350) {
  const [st, setSt] = useState({ data: null, error: null, loading: false })
  const [tick, setTick] = useState(0)
  const key = JSON.stringify(body)
  const refresh = useCallback(() => setTick((n) => n + 1), [])
  useEffect(() => {
    if (!enabled) { setSt({ data: null, error: null, loading: false }); return }
    const ctl = new AbortController()
    setSt((s) => ({ ...s, loading: true }))
    const wait = tick > 0 ? 0 : delay
    const t = setTimeout(async () => {
      try { setSt({ data: await api.post('/api/preview', body, ctl.signal), error: null, loading: false }) }
      catch (e) { if (e.name !== 'AbortError') setSt({ data: null, error: e, loading: false }) }
    }, wait)
    return () => { clearTimeout(t); ctl.abort() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled, tick])
  return { ...st, refresh }
}
