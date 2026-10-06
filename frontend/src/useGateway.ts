import { useEffect, useReducer, useState } from 'react'
import type { Alert, RunState, ServerMessage, Tick } from './types'

const MAX_TICKS = 600      // a full shift, for the shift overview
const MAX_ALERTS = 1000

interface Store {
  state: RunState | null
  ticks: Tick[]
  alerts: Alert[]
}

function reducer(store: Store, msg: ServerMessage): Store {
  switch (msg.type) {
    case 'init':
      return { state: msg.state, ticks: msg.ticks, alerts: msg.alerts }
    case 'state':
      return { ...store, state: msg.state }
    case 'tick':
      return {
        ...store,
        ticks: [...store.ticks.slice(-(MAX_TICKS - 1)), msg.tick],
        alerts: msg.tick.alerts.length
          ? [...store.alerts, ...msg.tick.alerts].slice(-MAX_ALERTS)
          : store.alerts,
      }
  }
}

/** Live connection to the gateway: an initial snapshot, then one tick per simulated minute. */
export function useGateway() {
  const [store, dispatch] = useReducer(reducer, { state: null, ticks: [], alerts: [] })
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let ws: WebSocket | null = null
    let retry: number | undefined
    let closed = false

    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws`)
      ws.onopen = () => setConnected(true)
      ws.onmessage = (e) => dispatch(JSON.parse(e.data) as ServerMessage)
      ws.onclose = () => {
        setConnected(false)
        if (!closed) retry = window.setTimeout(connect, 1000)
      }
    }
    connect()
    return () => {
      closed = true
      window.clearTimeout(retry)
      ws?.close()
    }
  }, [])

  return { ...store, connected }
}

export async function control(body: Record<string, unknown>): Promise<void> {
  await fetch('/api/control', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
