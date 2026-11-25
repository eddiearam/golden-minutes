// Screenshots for the design review loop (DESIGN.md). Uses the system Chrome.
// Usage: node scripts/screens.mjs <baseUrl> <outDir> [zip]
import { chromium } from '@playwright/test'
import { mkdirSync } from 'node:fs'

const [, , base = 'http://localhost:4173/', out = '../docs/screenshots', zip = '10456'] = process.argv
mkdirSync(out, { recursive: true })

const browser = await chromium.launch({ channel: 'chrome' })
const shots = [
  { name: '01-citywide-default', w: 1440, h: 900, q: '' },
  { name: '02-zip-selected-island', w: 1440, h: 900, q: `?zip=${zip}` },
  { name: '03-optimised-view', w: 1440, h: 900, q: '?view=opt' },
  { name: '04-heatmap-drawer', w: 1440, h: 900, q: '?drawer=1' },
  { name: '05-width-1280', w: 1280, h: 800, q: `?view=opt&zip=${zip}` },
]
const errors = []
for (const s of shots) {
  const page = await browser.newPage({ viewport: { width: s.w, height: s.h }, deviceScaleFactor: 2 })
  page.on('pageerror', (e) => errors.push(`${s.name}: ${e.message}`))
  page.on('console', (m) => m.type() === 'error' && errors.push(`${s.name}: ${m.text()}`))
  await page.goto(base + s.q, { waitUntil: 'networkidle' })
  await page.waitForSelector('.maplibregl-canvas')
  await page.waitForTimeout(1800)
  await page.screenshot({ path: `${out}/${s.name}.png` })
  console.log('saved', s.name)
  await page.close()
}

// Island motion: hover a zip and capture frames through the morph, then toggle views for the digit roll.
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 })
await page.goto(base, { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
const island = page.getByTestId('island')
const map = await page.locator('.map-canvas').boundingBox()
const clip = { x: map.x + map.width / 2 - 260, y: map.y, width: 520, height: 210 }
await page.mouse.move(map.x + map.width * 0.6, map.y + map.height * 0.55)
for (let i = 0; i < 8; i++) {
  await page.screenshot({ path: `${out}/island-morph-${i}.png`, clip })
  await page.waitForTimeout(25)
}
await page.mouse.move(map.x + 4, map.y + map.height - 4)
await page.mouse.move(map.x - 40, map.y - 40)
await page.waitForTimeout(600)
await page.getByRole('radio', { name: 'Optimised staging' }).click()
for (let i = 0; i < 6; i++) {
  await page.screenshot({ path: `${out}/island-roll-${i}.png`, clip })
  await page.waitForTimeout(80)
}
console.log('island state after toggle:', await island.getAttribute('data-state'))
await page.getByRole('button', { name: 'About the data' }).click()
await page.waitForTimeout(500)
await page.screenshot({ path: `${out}/06-about-sheet.png` })
await Promise.race([browser.close(), new Promise((r) => setTimeout(r, 5000))])
if (errors.length) {
  console.error('page errors:\n' + errors.join('\n'))
  process.exit(1)
}
console.log('no page errors')
process.exit(0)
