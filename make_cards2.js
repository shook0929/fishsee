// 由 JSON 生成卡片 HTML 并渲染成 PNG
// 用法: node make_cards2.js <cards.json> <outdir>
// 类型: bill / compare / quote / punch / cta / figure / pipeline / code / list
const fs = require('fs')
const path = require('path')
const { chromium } = require('playwright-core')

const TPL = path.join(__dirname, 'tpl_card.html')
const CHAR = 'file:///' + path.join(__dirname, '..', 'video', 'char_full.png').replace(/\\/g, '/')

function esc (s) {
  return String(s ?? '').replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]))
}

function body (type, d) {
  if (type === 'bill') {
    const rows = (d.rows || []).map(r =>
      `<div class="row${r.hot ? ' hot' : ''}"><span>${esc(r.label)}</span><span class="v">${esc(r.value)}</span></div>`).join('')
    return `<div class="stage"><div class="card">
      <div class="kicker">${esc(d.kicker || '账单')}</div>
      <h2>${d.title || ''}</h2><div class="rows">${rows}</div>
      ${d.sub ? `<div class="sub">${d.sub}</div>` : ''}</div></div>`
  }

  if (type === 'compare') {
    return `<div class="stage"><div class="card">
      <div class="kicker">${esc(d.kicker || '')}</div>
      <div class="vs">
        <div class="side"><div class="n" style="color:#7A8290">${esc(d.left)}</div><div class="l">${esc(d.leftLabel)}</div></div>
        <div class="mid">→</div>
        <div class="side"><div class="n" style="color:#E85D00">${esc(d.right)}</div><div class="l">${esc(d.rightLabel)}</div></div>
      </div>
      ${d.sub ? `<div class="sub" style="text-align:center">${d.sub}</div>` : ''}</div></div>`
  }

  if (type === 'quote') {
    return `<div class="stage"><div class="quote">
      <div class="who">${esc(d.who || '')}</div>
      <div class="txt">${d.txt || ''}</div>
      ${d.sub ? `<div class="sub" style="color:#8C93A3;margin-top:18px">${esc(d.sub)}</div>` : ''}</div></div>`
  }

  if (type === 'punch') {
    return `<div class="punch"><div class="big">${d.big || ''}</div>
      ${d.small ? `<div class="small">${esc(d.small)}</div>` : ''}</div>`
  }

  if (type === 'cta') {
    return `<div class="stage"><div class="card">
      <div class="kicker">${esc(d.kicker || '')}</div>
      <h2>${d.title || ''}</h2>
      ${d.sub ? `<div class="sub">${d.sub}</div>` : ''}
      <div class="cta">
        <div class="btn primary">${esc(d.b1 || '点赞')}</div>
        <div class="btn">${esc(d.b2 || '投币')}</div>
        <div class="btn">${esc(d.b3 || '收藏')}</div>
      </div></div></div>`
  }

  // 嵌入真实截图
  if (type === 'figure') {
    const img = 'file:///' + path.resolve(d.img).replace(/\\/g, '/')
    return `<div class="stage wide"><div class="card fig">
      <div class="kicker">${esc(d.kicker || '')}</div>
      <img src="${img}">
      <div class="cap">${esc(d.cap || '')}</div>
    </div></div>`
  }

  // 流程图
  if (type === 'pipeline') {
    const steps = (d.steps || []).map((s, i) =>
      `<div class="pstep"><div class="num">${i + 1}</div><div class="ptxt"><b>${esc(s.name)}</b><span>${esc(s.desc)}</span></div></div>`).join('')
    return `<div class="stage"><div class="card pipe">
      <div class="kicker">${esc(d.kicker || '流水线')}</div>
      <h2 style="font-size:38px">${d.title || ''}</h2>
      <div class="psteps">${steps}</div></div></div>`
  }

  // 命令行
  if (type === 'code') {
    const lines = (d.lines || []).map(l => `<div class="cline">${l}</div>`).join('')
    return `<div class="stage"><div class="card">
      <div class="kicker">${esc(d.kicker || '')}</div>
      <h2 style="font-size:36px">${d.title || ''}</h2>
      <div class="codebox">${lines}</div>
      ${d.sub ? `<div class="sub">${esc(d.sub)}</div>` : ''}</div></div>`
  }

  // 列表
  if (type === 'list') {
    const items = (d.items || []).map(it =>
      `<li><b>${esc(it.k)}</b><span>${esc(it.v)}</span></li>`).join('')
    return `<div class="stage"><div class="card">
      <div class="kicker">${esc(d.kicker || '')}</div>
      <h2 style="font-size:40px">${d.title || ''}</h2>
      <ul class="plist">${items}</ul></div></div>`
  }

  return `<div class="stage"><div class="card"><h2>${d.title || ''}</h2></div></div>`
}

async function main () {
  const [jsonPath, outdir] = process.argv.slice(2)
  if (!jsonPath || !outdir) { console.error('用法: node make_cards2.js <cards.json> <outdir>'); process.exit(1) }
  const cards = JSON.parse(fs.readFileSync(jsonPath, 'utf8'))
  const tpl = fs.readFileSync(TPL, 'utf8')
  fs.mkdirSync(outdir, { recursive: true })

  const browser = await chromium.launch({ channel: 'msedge' })
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 })
  await page.addStyleTag({ content: EXTRA_CSS }) // 由下方注入

  for (const c of cards) {
    let html = tpl.split('../video/char_full.png').join(CHAR)
      .replace('{{DAY}}', esc(c.day || ''))
      .replace('{{BADGE}}', c.badge ? `<div class="badge">${esc(c.badge)}</div>` : '')
      .replace('{{BODY}}', body(c.type, c.data || {}))
      .replace('{{FOOT}}', c.foot === undefined ? '' : esc(c.foot))
    const tmp = path.join(outdir, `_${c.name}.html`)
    fs.writeFileSync(tmp, html, 'utf8')
    await page.goto('file:///' + tmp.replace(/\\/g, '/'), { waitUntil: 'load' })
    await page.addStyleTag({ content: EXTRA_CSS })
    await page.evaluate(() => document.fonts.ready)
    await page.waitForTimeout(120)
    await page.screenshot({ path: path.join(outdir, `${c.name}.png`), type: 'png' })
    fs.unlinkSync(tmp)
    console.log('  ', c.name)
  }
  await browser.close()
  console.log('done ->', outdir)
}

const EXTRA_CSS = `
  .stage.wide{width:840px}
  .card.fig{padding:20px 22px 14px;max-height:none}
  .card.fig img{display:block;margin:0 auto;max-width:100%;max-height:400px;width:auto;
    border-radius:10px;border:1px solid #D8DEE8;background:#fff}
  .card.fig .cap{margin-top:12px;font-size:20px;color:#5E6675;line-height:1.45}
  .card.pipe{padding:26px 30px}
  .psteps{margin-top:14px;display:flex;flex-direction:column;gap:9px}
  .pstep{display:flex;gap:12px;align-items:flex-start}
  .pstep .num{flex:0 0 30px;height:30px;border-radius:50%;background:#FF7500;color:#fff;
    font-size:17px;font-weight:800;display:flex;align-items:center;justify-content:center;margin-top:2px}
  .pstep .ptxt{display:flex;flex-direction:column;line-height:1.3}
  .pstep .ptxt b{font-size:23px;color:#0E1117}
  .pstep .ptxt span{font-size:18px;color:#5E6675}
  .codebox{margin-top:14px;background:#12151D;border-radius:14px;padding:18px 20px}
  .codebox .cline{font-family:Consolas,"Courier New",monospace;font-size:19px;color:#7EE7C7;line-height:1.7;white-space:pre-wrap}
  .plist{list-style:none;margin-top:14px}
  .plist li{display:flex;gap:14px;padding:11px 2px;border-bottom:1px dashed #D3D9E3;align-items:baseline}
  .plist li:last-child{border-bottom:0}
  .plist li b{flex:0 0 170px;font-size:22px;color:#0E1117}
  .plist li span{font-size:21px;color:#4A5262;line-height:1.4}
`

main().catch(e => { console.error('失败:', e.message); process.exit(1) })
