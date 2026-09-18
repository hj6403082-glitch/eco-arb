#!/usr/bin/env node
/**
 * End-to-end smoke test against a running stack.
 *
 *   ./start.sh            # in one terminal
 *   node scripts/smoke.mjs  # in another
 *
 * Exists because `vite build` happily compiles a reference to an undefined
 * variable: a build that passes is not a page that runs. This drives the real
 * browser and fails loudly on any console error.
 *
 * Requires playwright (`npm i -D playwright` in frontend/, or a global install).
 */
import { chromium } from 'playwright'

const API = process.env.SMOKE_API ?? 'http://127.0.0.1:8000'
const UI = process.env.SMOKE_UI ?? 'http://127.0.0.1:5173'
const EXE = process.env.PLAYWRIGHT_CHROMIUM // set to reuse a preinstalled binary

let failures = 0
const check = (label, ok, detail = '') => {
  console.log(`${ok ? '  ok  ' : '  FAIL'} ${label}${detail ? ` — ${detail}` : ''}`)
  if (!ok) failures++
}

const api = async (path, init) => {
  const res = await fetch(`${API}${path}`, {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json()
}

console.log('\nAPI')
const health = await api('/api/health')
check('health responds', health.ok === true)

await api('/api/reset', { method: 'POST' })
const seeded = await api('/api/demo/seed', { method: 'POST' })
const decisions = seeded.seeded.map((s) => s.decision)
check('seed returns three jobs', seeded.seeded.length === 3)
check(
  'seed exercises both actions',
  new Set(decisions.map((d) => d.action)).size === 2,
  decisions.map((d) => d.action).join(','),
)

const deferred = decisions.find((d) => d.action === 'WAIT')
check('a deferral saves carbon', deferred?.carbon_saved_pct > 0, `${deferred?.carbon_saved_pct}%`)
check('a deferral explains itself', (deferred?.reason?.length ?? 0) > 40)
check(
  'deferred window ends before its deadline',
  Date.parse(deferred.window_end_iso) <=
    Date.parse(seeded.seeded.find((s) => s.job.id === deferred.job_id).job.deadline_iso),
)

const state = await api('/api/state')
check('forecast covers 24h in half-hour slots', state.grid.forecast.length === 48)
check('provenance is declared', Boolean(state.grid.provenance?.price))

const bad = await fetch(`${API}/api/speed`, {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ speed: 7 }),
})
check('an unsupported speed is rejected', bad.status === 400)

console.log('\nExecution (real workload, real wall-clock seconds)')
const { job } = await api('/api/jobs', {
  method: 'POST',
  body: JSON.stringify({
    name: 'smoke-job',
    energy_kwh: 1,
    duration_minutes: 30,
    deadline_hours: 0.5, // deadline-bound, so it dispatches immediately
    workload: 'hash_grind',
  }),
})
let finished = null
for (let i = 0; i < 60; i++) {
  const { job: j } = await api(`/api/jobs/${job.id}`)
  if (j.status === 'DONE' || j.status === 'FAILED') { finished = j; break }
  await new Promise((r) => setTimeout(r, 500))
}
check('job reaches DONE', finished?.status === 'DONE', finished?.status ?? 'timed out')
if (finished?.status === 'DONE') {
  const { independently_verified } = await api(`/api/jobs/${job.id}/artifact`)
  check('artifact digest verifies from its seed', independently_verified === true)
}

console.log('\nTerminal')
const browser = await chromium.launch(EXE ? { executablePath: EXE } : {})
const page = await browser.newPage({ viewport: { width: 1600, height: 950 } })
const errors = []
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
page.on('pageerror', (e) => errors.push(`PAGEERROR ${e.message}`))

const decisionHeading = () =>
  page
    .locator('section:has(h2:text("Decision")) .truncate.text-sm')
    .first()
    .innerText({ timeout: 5000 })

try {
  await page.goto(UI, { waitUntil: 'networkidle' })
  await page.waitForTimeout(2500)

  check('forecast chart renders', (await page.locator('svg[aria-label*="Carbon intensity"]').count()) === 1)
  check('compression badge is visible', await page.getByText(/time-compressed|real time/i).first().isVisible())

  const first = await decisionHeading()
  check('a decision is shown on load', first.length > 0, first)

  await page.locator('table tbody tr').nth(1).click()
  const picked = await decisionHeading()
  await page.waitForTimeout(3000) // outlast three poll cycles
  check('selection survives polling', (await decisionHeading()) === picked, picked)
} catch (err) {
  // A blank or half-rendered page throws here rather than failing a check.
  // Report it as the failure it is instead of an unhandled rejection.
  check('terminal renders and responds', false, err.message.split('\n')[0])
}

// Last, and never skipped: a page that threw is a broken page even if every
// locator above happened to resolve.
check('no console errors', errors.length === 0, errors.join(' | '))
await browser.close()

console.log(`\n${failures ? `✗ ${failures} check(s) failed` : '✓ all checks passed'}\n`)
process.exit(failures ? 1 : 0)
