// 用模板 + JSON 数据出封面
// 用法: node make_cover.js <data.json> <out.png> [scale]
// data.json 字段: kicker, n1, n2, punch, foot, date, char (true/false)
const fs = require('fs')
const path = require('path')
const { execFileSync } = require('child_process')
const { chromium } = require('playwright-core')

const TPL = path.join(__dirname, 'tpl_cover.html')
const CHAR_HTML = '<div class="charGlow"></div><img class="char" src="../video/char_full.png">'

function esc (s) {
  return String(s ?? '').replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]))
}

async function main () {
  const [dataFile, outPng, scale = '1.5'] = process.argv.slice(2)
  if (!dataFile || !outPng) {
    console.error('用法: node make_cover.js <data.json> <out.png> [scale]')
    process.exit(1)
  }
  const d = JSON.parse(fs.readFileSync(dataFile, 'utf8'))
  let html = fs.readFileSync(TPL, 'utf8')
  const map = {
    '{{KICKER}}': esc(d.kicker || 'AI 运营日记'),
    '{{N1}}': esc(d.n1 || ''),
    '{{N2}}': esc(d.n2 || ''),
    '{{PUNCH}}': d.punch || '',
    '{{FOOT}}': esc(d.foot || ''),
    '{{DATE}}': esc(d.date || 'BILIBILI · 2026.10'),
    '{{CHAR}}': d.char === false ? '' : CHAR_HTML,
  }
  for (const [k, v] of Object.entries(map)) html = html.split(k).join(v)

  const tmp = path.join(__dirname, '.tmp_cover.html')
  fs.writeFileSync(tmp, html, 'utf8')

  const browser = await chromium.launch({ channel: 'msedge' })
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: Number(scale) })
  await page.goto('file:///' + tmp.replace(/\\/g, '/'), { waitUntil: 'load' })
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(250)
  await page.screenshot({ path: path.resolve(outPng), type: 'jpeg', quality: 92 })
  await browser.close()
  fs.unlinkSync(tmp)
  const kb = Math.round(fs.statSync(outPng).size / 1024)
  console.log(`ok -> ${outPng}  ${kb} KB`)
}

main().catch(e => { console.error('失败:', e.message); process.exit(1) })
