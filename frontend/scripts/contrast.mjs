// Contrast check for the Redline themes. Reads the color tokens straight from
// src/index.css and checks every pair the UI actually uses, in both themes.
//   node scripts/contrast.mjs        (exit code 1 on any failure)

import { readFileSync } from 'node:fs'

const css = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')

function block(selector) {
  const i = css.indexOf(selector)
  if (i < 0) throw new Error(`no ${selector} block`)
  const body = css.slice(css.indexOf('{', i) + 1, css.indexOf('}', i))
  return Object.fromEntries([...body.matchAll(/--([\w-]+)\s*:\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]))
}

function rgb(value) {
  const hex = value.match(/^#([0-9a-f]{6})$/i)
  if (hex) return [0, 2, 4].map((i) => parseInt(hex[1].slice(i, i + 2), 16))
  const m = value.match(/^rgba?\(([^)]+)\)$/)
  if (m) return m[1].split(',').slice(0, 3).map(Number)
  throw new Error(`not a color: ${value}`)
}
const lin = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4 }
const lum = (v) => { const [r, g, b] = rgb(v).map(lin); return 0.2126 * r + 0.7152 * g + 0.0722 * b }
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05) }

const shared = block(':root {')
const themes = { dark: { ...shared, ...block(':root[data-theme="dark"]') }, light: { ...shared, ...block(':root[data-theme="light"]') } }

const SURFACES = ['bg', 'surface', 'surface-sunk']
const checks = [
  // text tokens on every surface they can sit on: 4.5:1
  // (--critical is only used as text at hero size, which needs 3:1 and is checked as a line below;
  //  small red text uses --red-text)
  ...['text', 'text-2', 'muted', 'faint', 'red-text', 'warning', 'advisory', 'recovering']
    .flatMap((fg) => SURFACES.map((bg) => [fg, bg, 4.5, 'text'])),
  // lines that carry meaning (limit, level borders, chart lines): 3:1
  ...['red', 'critical', 'warning', 'advisory', 'recovering', 'muted', 'text-2']
    .flatMap((fg) => SURFACES.map((bg) => [fg, bg, 3, 'line'])),
  // filled chips, statement strip, inverted toast / primary button: 4.5:1
  ...['critical', 'warning', 'advisory', 'recovering', 'muted'].map((bg) => ['on-level', bg, 4.5, 'chip']),
  ['statement-text', 'statement-bg', 4.5, 'statement'],
  ['bg', 'text', 4.5, 'inverted'],
]

let failures = 0
for (const [name, tok] of Object.entries(themes)) {
  console.log(`\n== ${name} theme`)
  for (const [fg, bg, min, kind] of checks) {
    const r = ratio(tok[fg], tok[bg])
    if (r < min) { failures++; console.log(`  FAIL ${kind.padEnd(9)} --${fg} on --${bg}: ${r.toFixed(2)} < ${min}`) }
  }
  // Levels must differ in lightness, not just hue (readable in grayscale).
  const levels = ['critical', 'warning', 'advisory'].map((l) => [l, lum(tok[l])])
  console.log('  level luminance: ' + levels.map(([l, v]) => `${l} ${v.toFixed(3)}`).join(' · '))
  for (let i = 0; i < levels.length; i++) for (let j = i + 1; j < levels.length; j++) {
    const r = ratio(tok[levels[i][0]], tok[levels[j][0]])
    if (r < 1.25) { failures++; console.log(`  FAIL grayscale ${levels[i][0]} vs ${levels[j][0]}: lightness ratio ${r.toFixed(2)} < 1.25`) }
  }
  // Decorative tokens (hairlines between panels, chart gridlines), reported but not required to hit 3:1.
  for (const fg of ['border', 'grid']) console.log(`  info decorative --${fg} on --bg: ${ratio(tok[fg].startsWith('rgba') ? tok.border : tok[fg], tok.bg).toFixed(2)}`)
}
console.log(failures ? `\n${failures} failure(s)` : '\nAll contrast checks passed.')
process.exit(failures ? 1 : 0)
