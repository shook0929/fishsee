const path = require('path')
const fs = require('fs')
const { chromium } = require('playwright-core')

const OUT = process.argv[2] || 'D:\\dsh-working area\\video\\cover_day4_v2.jpg'
const CHAR = 'file:///' + path.join(__dirname, '..', 'video', 'char_full.png').replace(/\\/g, '/')
const SPEC = 'file:///' + path.join(__dirname, '..', 'video', 'spectrum_clean.png').replace(/\\/g, '/')

const HTML = `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1280px;height:720px;overflow:hidden;font-family:"Microsoft YaHei UI","Microsoft YaHei",sans-serif}
body{background:#0B0D12;color:#fff;position:relative}
.bg{position:absolute;inset:0;background:
  radial-gradient(900px 520px at 6% -14%, rgba(255,117,0,.20), transparent 60%),
  radial-gradient(700px 500px at 104% 110%, rgba(60,140,255,.16), transparent 62%),
  linear-gradient(160deg,#11141B,#0B0D12 52%,#08090C)}
.top{position:absolute;left:0;top:0;height:6px;width:100%;background:linear-gradient(90deg,#FF7500,#FFA24A 34%,rgba(255,117,0,0) 72%)}
.bar{position:absolute;left:56px;top:38px;font-size:17px;letter-spacing:.18em;color:#98A0AF;display:flex;gap:12px;align-items:center}
.bar b{color:#FF7500;letter-spacing:.06em}
.dot{width:8px;height:8px;border-radius:50%;background:#FF7500;box-shadow:0 0 12px 2px rgba(255,117,0,.7)}
.specWrap{position:absolute;left:0;right:0;bottom:0;height:330px;overflow:hidden;opacity:.55;
  -webkit-mask-image:linear-gradient(to top,#000 12%,rgba(0,0,0,.4) 64%,transparent 100%)}
.spec{position:absolute;right:0;bottom:0;width:112%;display:block}
.char{position:absolute;right:-16px;bottom:-18px;height:520px;filter:drop-shadow(0 20px 44px rgba(0,0,0,.7))}
.txt{position:absolute;left:56px;top:150px;width:760px}
.k{font-size:30px;color:#FF9D4D;letter-spacing:.1em;margin-bottom:14px;font-weight:700}
h1{font-size:96px;line-height:1.06;font-weight:900;letter-spacing:-.01em}
h1 em{font-style:normal;color:#FF7500;text-shadow:0 0 40px rgba(255,117,0,.45)}
.sub{margin-top:22px;font-size:30px;color:#C9CFDB;letter-spacing:.02em}
.tag{display:inline-block;margin-top:26px;background:rgba(255,117,0,.13);border:1px solid rgba(255,117,0,.38);
  color:#FFC08A;border-radius:999px;padding:10px 22px;font-size:22px;letter-spacing:.04em}
</style></head><body>
<div class="bg"></div><div class="top"></div>
<div class="bar"><span class="dot"></span><span><b>DAY 4</b> · 大肥鱼替 AI 看视频</span></div>
<div class="specWrap"><img class="spec" src="${SPEC}"></div>
<img class="char" src="${CHAR}">
<div class="txt">
  <div class="k">六层流水线，一台没显卡的电脑</div>
  <h1>AI 真的能<em>「看」</em>视频吗</h1>
  <div class="sub">同一支片子，以前只能猜，现在能说到秒</div>
  <div class="tag">3 分 36 秒，他按下了开关</div>
</div>
</body></html>`

;(async () => {
  const browser = await chromium.launch({ channel: 'msedge' })
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 })
  const tmp = path.join(__dirname, '_cover4.html')
  fs.writeFileSync(tmp, HTML, 'utf8')
  await page.goto('file:///' + tmp.replace(/\\/g, '/'), { waitUntil: 'load' })
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(400)
  await page.screenshot({ path: OUT, type: 'jpeg', quality: 92 })
  await browser.close()
  fs.unlinkSync(tmp)
  console.log('ok ->', OUT)
})().catch(e => { console.error('失败:', e.message); process.exit(1) })
