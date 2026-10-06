// Theme: <html data-theme="dark|light">, set before first paint by index.html.
// Components style themselves through CSS variables. Charts (Recharts, SVG
// sparklines) need concrete colors, so useTheme() reads the resolved tokens and
// re-renders whenever the theme attribute changes.

import { useEffect, useState } from 'react'

export type ThemeName = 'dark' | 'light'
const STORAGE_KEY = 'redline.theme'

const TOKEN_NAMES = [
  'bg', 'surface', 'surface-sunk', 'border', 'grid', 'text', 'text-2', 'muted', 'faint',
  'red', 'red-text', 'critical', 'warning', 'advisory', 'recovering', 'critical-tint',
] as const
type TokenName = (typeof TOKEN_NAMES)[number]
export type Tokens = Record<TokenName, string>

function currentTheme(): ThemeName {
  return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark'
}

function readTokens(): Tokens {
  const style = getComputedStyle(document.documentElement)
  return Object.fromEntries(TOKEN_NAMES.map((n) => [n, style.getPropertyValue(`--${n}`).trim()])) as Tokens
}

export function setTheme(theme: ThemeName) {
  document.documentElement.setAttribute('data-theme', theme)
  try { localStorage.setItem(STORAGE_KEY, theme) } catch { /* storage unavailable: theme lasts for this page only */ }
}

export function toggleTheme(): ThemeName {
  const next = currentTheme() === 'dark' ? 'light' : 'dark'
  setTheme(next)
  return next
}

/** The active theme and its resolved color tokens; updates instantly on switch. */
export function useTheme(): { theme: ThemeName; t: Tokens } {
  const [state, setState] = useState(() => ({ theme: currentTheme(), t: readTokens() }))
  useEffect(() => {
    const update = () => setState({ theme: currentTheme(), t: readTokens() })
    const observer = new MutationObserver(update)
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    // Follow the OS setting only while the user hasn't chosen a theme.
    const media = window.matchMedia('(prefers-color-scheme: light)')
    const onSystem = () => {
      let stored: string | null = null
      try { stored = localStorage.getItem(STORAGE_KEY) } catch { /* ignore */ }
      if (stored !== 'dark' && stored !== 'light') {
        document.documentElement.setAttribute('data-theme', media.matches ? 'light' : 'dark')
      }
    }
    media.addEventListener('change', onSystem)
    return () => { observer.disconnect(); media.removeEventListener('change', onSystem) }
  }, [])
  return state
}

/** Chart tooltip style from the active tokens. */
export function tooltipStyle(t: Tokens) {
  return {
    background: t.surface, border: `1px solid ${t.border}`, borderRadius: 8, color: t.text, fontSize: 12,
    boxShadow: 'var(--shadow)',
  }
}
