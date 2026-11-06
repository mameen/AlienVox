"""Create a standalone interactive HTML view of a CPU benchmark JSON report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

PREFS = {
    ("kokoro", "af_heart"): ("Favorite", "Fantastic; overall quality favorite, former runtime default"),
    ("kokoro", "af_bella"): ("Favorite", "Fantastic in latest listening note"),
    ("kokoro", "bf_emma"): ("5/5", "Historical subjective rating; fantastic"),
    ("kokoro", "am_adam"): ("Not too bad", "Latest note; historical export 5/5"),
    ("kokoro", "bm_george"): ("Not too bad", "Latest note; historical export 4/5"),
    ("supertonic3", "F1"): ("5/5", "Historical subjective rating"),
    ("supertonic3", "F4"): ("5/5", "Historical subjective rating"),
    ("piper", "en_US-ryan-high"): ("Really good · 5/5", "Latest developer endorsement; historical rating 5/5"),
    ("piper", "en_US-lessac-medium"): ("Really good · 4/5", "Developer's latest qualitative endorsement; historical rating 4/5"),
    ("piper", "en_US-amy-medium"): ("Really good · 4/5", "Developer's latest qualitative endorsement; historical rating 4/5"),
    ("piper", "en_US-kathleen-low"): ("Really good · 4/5", "Latest developer endorsement; historical rating 4/5"),
    ("piper", "en_GB-southern_english_female-low"): ("Really good · 4/5", "Latest developer endorsement; historical rating 4/5"),
    ("piper", "en_GB-jenny_dioco-medium"): ("Really good · 4/5", "Developer's latest qualitative endorsement; historical rating 4/5"),
    ("sapi5", "MSTTS_V110_enGB_HazelM"): ("Unscored", "Audition shortlist; no star score"),
    ("sapi5", "MSTTS_V110_enGB_SusanM"): ("Unscored", "Audition shortlist; no star score"),
    ("sapi5", "TTS_MS_EN-US_ZIRA_11.0"): ("Unscored", "Audition shortlist; no star score"),
}


def render(source: Path, target: Path) -> None:
    report = json.loads(source.read_text(encoding="utf-8-sig"))
    rows = []
    for result in report["results"]:
        if result.get("status") != "ok":
            continue
        warm = result["runs"][1:]
        middle = len(warm) // 2
        pref, note = PREFS.get((result["engine"], result["voice_requested"]), ("Unrated", "No rating"))
        rows.append({
            "engine": result["engine"], "voice": result["voice_requested"],
            "cold": result["runs"][0]["synthesis_seconds"],
            "cold_cpu": result["runs"][0]["process_cpu_seconds"],
            "latency": result["warm_median_seconds"],
            "cpu": sorted(r["process_cpu_seconds"] for r in warm)[middle],
            "cpu_pct": sorted(r["cpu_percent_one_core"] for r in warm)[middle],
            "rtf": sorted(r["real_time_factor"] for r in warm)[middle],
            "rss": result["runs"][-1]["rss_mb_after"], "pref": pref, "note": note,
            "audio": f"{result['engine']}-{result['voice_requested']}.wav",
        })
    data = json.dumps({"rows": rows, "phrase": report["phrase"], "created": report["created_utc"],
                       "notes": report["measurement_notes"]}, ensure_ascii=False).replace("</", "<\\/")
    page = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AlienVox CPU voice cost</title>
<style>
:root{color-scheme:dark;--bg:#0b1222;--panel:#131f35;--line:#283956;--text:#e8efff;--muted:#9bacc8;--gold:#ffd166}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 Segoe UI,system-ui,sans-serif}main{max-width:1450px;margin:auto;padding:28px}h1{margin:0;font-size:30px}h2{font-size:20px;margin:0 0 14px}.muted{color:var(--muted)}.panel,.card{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:16px;margin:15px 0}.banner{border-left:4px solid var(--gold);color:#f5e8ba}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.card{margin:0}.card small{display:block;color:var(--muted);text-transform:uppercase}.card b{display:block;font-size:22px;margin-top:6px}.ctrl{display:flex;gap:18px;align-items:center;flex-wrap:wrap;color:var(--muted);margin-bottom:10px}select{padding:7px;background:#0d1729;color:var(--text)}canvas{width:100%;height:380px;display:block}.legend{display:flex;gap:16px;color:var(--muted)}.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px}.wrap{overflow:auto}table{width:100%;min-width:1080px;border-collapse:collapse}th,td{text-align:left;padding:9px;border-bottom:1px solid var(--line)}th{color:#9eeaf2;font-size:12px;text-transform:uppercase}td.num{white-space:nowrap;font-variant-numeric:tabular-nums}.pref{color:var(--gold)}.audio{width:175px;height:30px}.phrase{font-family:Consolas,monospace;background:#0d1729;padding:12px;border-radius:5px}.rating-cell{white-space:nowrap}.error-flag{width:29px;height:29px;border:2px solid #ff4545;border-radius:50%;background:transparent;color:#ff4545;cursor:pointer;font-size:18px;font-weight:900;line-height:1;padding:0;margin-right:6px;vertical-align:middle}.error-flag.selected{background:#e32636;color:#fff;box-shadow:0 0 8px #ff303088}.rating-star{border:0;background:transparent;color:#68748c;cursor:pointer;font-size:18px;padding:1px}.rating-star.selected{color:#ffd34e}.rating-star:disabled{cursor:not-allowed;opacity:.3}button.export{padding:8px 12px;background:#176b9c;border:0;border-radius:5px;color:white;cursor:pointer}button.export:hover{background:#2189c4}@media(max-width:750px){main{padding:15px}.cards{grid-template-columns:repeat(2,1fr)}canvas{height:310px}}
</style></head><body><main><h1>CPU cost of your preferred voices</h1><p class="muted">Offline benchmark · <span id="date"></span> · same canonical phrase for every voice</p>
<section class="panel banner"><b>GPU comparison:</b> every run shown here used CPU to keep the GPU free for ML work. There is no GPU run in this report, so it does not claim a CPU-versus-GPU speedup.</section><div class="cards" id="cards"></div>
<section class="panel"><h2>CPU time vs synthesis latency</h2><div class="ctrl"><label>Pass <select id="mode"><option value="warm">Warm median (3 runs)</option><option value="cold">First run (cold)</option></select></label><span>X: CPU seconds per sample · Y: synthesis wall time</span></div><canvas id="plot"></canvas><div class="legend" id="legend"></div></section>
<section class="panel"><h2>Voice comparison</h2><div class="ctrl" id="filters"></div><p><button class="export" id="export">Download metrics + ratings JSON</button></p><div class="wrap"><table><thead><tr><th>Technology</th><th>Voice</th><th title="Elapsed time of the first synthesis call, including model/runtime initialization when it occurs.">Cold latency</th><th title="Median elapsed time for the three warm synthesis runs. Model loading is excluded.">Warm latency</th><th title="Median process CPU time consumed for one warm synthesis. This can exceed wall time when multiple cores are active.">Warm CPU time</th><th title="Process CPU time divided by wall-clock time. 100% means one fully busy CPU core; over 100% means multiple cores were used.">CPU / one core</th><th title="Real-time factor: synthesis time divided by generated audio duration. Below 1.0 means faster than playback speed.">RTF</th><th title="Whole-process resident memory after this voice's run. Previous models remain loaded, so this is not isolated per-voice memory.">Process RSS*</th><th title="Developer's subjective listening preference; labels and historical star scores are personal feedback, not objective quality measurements.">Preference</th><th title="Play the offline WAV generated with the same canonical phrase used in the benchmark.">Audio sample</th><th>Your feedback · error / stars</th></tr></thead><tbody id="body"></tbody></table></div></section>
<section class="panel"><h2>Canonical test phrase</h2><div id="phrase" class="phrase"></div></section><section class="panel muted"><h2>Measurement notes</h2><p id="notes"></p><p>CPU percent is process CPU time divided by wall time; over 100% means multiple cores were used. RSS is whole-process memory after each voice, retaining earlier models; it is not isolated model memory. Ratings are subjective; SAPI voices are unscored.</p></section></main>
<script>
const D=__DATA__,C={kokoro:'#32c7f4',supertonic3:'#a78bfa',piper:'#65d68b',sapi5:'#ffad61'},R=D.rows,G=[...new Set(R.map(r=>r.engine))],STORE='alienvox-cpu-voice-feedback-v1';let feedback={};try{feedback=JSON.parse(localStorage.getItem(STORE)||'{}')}catch{}
document.getElementById('date').textContent=new Date(D.created).toLocaleString();document.getElementById('phrase').textContent=D.phrase;document.getElementById('notes').textContent=D.notes;
let fastest=R.reduce((a,b)=>a.latency<b.latency?a:b),least=R.reduce((a,b)=>a.cpu<b.cpu?a:b);document.getElementById('cards').innerHTML=[['Voices tested',R.length],['Fastest warm voice',fastest.voice],['Lowest warm CPU',least.voice],['GPU workload','None (CPU run)']].map(a=>`<div class="card"><small>${a[0]}</small><b>${a[1]}</b></div>`).join('');
document.getElementById('filters').innerHTML=G.map(g=>`<label><input type="checkbox" checked data-g="${g}"> ${g}</label>`).join('');document.getElementById('legend').innerHTML=G.map(g=>`<span><i style="background:${C[g]}"></i>${g}</span>`).join('');
function visible(){return R.filter(r=>document.querySelector(`[data-g="${r.engine}"]`).checked)}
function key(r){return r.engine+'/'+r.voice}function persist(){try{localStorage.setItem(STORE,JSON.stringify(feedback))}catch{alert('Browser storage is unavailable. Download the JSON to keep your feedback.')}}
function table(){document.getElementById('body').innerHTML=visible().map(r=>{let k=key(r),f=feedback[k]||{},err=f.error===true,stars=Number(f.stars)||0;return `<tr><td style="color:${C[r.engine]}">${r.engine}</td><td>${r.voice}</td><td class="num">${r.cold.toFixed(3)} s</td><td class="num">${r.latency.toFixed(3)} s</td><td class="num">${r.cpu.toFixed(2)} s</td><td class="num">${r.cpu_pct.toFixed(0)}%</td><td class="num">${r.rtf.toFixed(3)}</td><td class="num">${r.rss.toFixed(0)} MB*</td><td class="pref" title="${r.note}">${r.pref}</td><td><audio class="audio" controls preload="none" src="${r.audio}"></audio></td><td class="rating-cell"><button type="button" class="error-flag ${err?'selected':''}" data-error="${k}" title="${err?'Error reported; clear before rating':'Report an error; this blocks star rating'}" aria-label="${err?'Error reported':'Report an error'}" aria-pressed="${err}">!</button>${[1,2,3,4,5].map(n=>`<button type="button" class="rating-star ${!err&&stars>=n?'selected':''}" data-key="${k}" data-star="${n}" ${err?'disabled':''} title="Rate ${n} out of 5" aria-label="Rate ${n} out of 5">★</button>`).join('')}</td></tr>`}).join('');document.querySelectorAll('[data-error]').forEach(b=>b.onclick=()=>{let k=b.dataset.error,was=feedback[k]?.error===true;feedback[k]={...(feedback[k]||{}),error:!was};if(!was)delete feedback[k].stars;persist();table()});document.querySelectorAll('[data-star]').forEach(b=>b.onclick=()=>{let k=b.dataset.key;feedback[k]={...(feedback[k]||{}),stars:Number(b.dataset.star),error:false};persist();table()})}
function draw(){let a=visible(),cold=document.getElementById('mode').value==='cold',cv=document.getElementById('plot'),ctx=cv.getContext('2d'),d=window.devicePixelRatio||1,w=cv.clientWidth,h=cv.clientHeight;cv.width=w*d;cv.height=h*d;ctx.scale(d,d);let L=70,T=18,B=45,Q=18,pw=w-L-Q,ph=h-T-B,xs=a.map(r=>cold?r.cold_cpu:r.cpu),ys=a.map(r=>cold?r.cold:r.latency),xm=Math.max(...xs)*1.12||1,ym=Math.max(...ys)*1.12||1;ctx.font='12px Segoe UI';ctx.fillStyle='#aab8d0';ctx.strokeStyle='#31415d';for(let i=0;i<=5;i++){let xx=L+pw*i/5,yy=T+ph*(1-i/5);ctx.beginPath();ctx.moveTo(xx,T);ctx.lineTo(xx,T+ph);ctx.moveTo(L,yy);ctx.lineTo(L+pw,yy);ctx.stroke();ctx.fillText((xm*i/5).toFixed(1),xx-9,T+ph+18);ctx.fillText((ym*i/5).toFixed(1),8,yy+4)}ctx.fillStyle='#d7e4fb';ctx.fillText('CPU seconds / sample',L+pw/2-50,h-4);ctx.save();ctx.translate(14,T+ph/2+40);ctx.rotate(-Math.PI/2);ctx.fillText('Elapsed synthesis seconds',0,0);ctx.restore();a.forEach((r,i)=>{let x=L+pw*xs[i]/xm,y=T+ph-ph*ys[i]/ym;ctx.fillStyle=C[r.engine];ctx.beginPath();ctx.arc(x,y,6,0,Math.PI*2);ctx.fill();ctx.strokeStyle='#fff';ctx.stroke();ctx.fillStyle='#e6edfa';ctx.fillText(r.voice,x+8,y-7)})}
document.querySelectorAll('#filters input').forEach(e=>e.addEventListener('change',()=>{draw();table()}));document.getElementById('mode').addEventListener('change',draw);document.getElementById('export').addEventListener('click',()=>{let payload={schema_version:1,source_report:'report.json',benchmark_created:D.created,phrase:D.phrase,voice_feedback:feedback,results:R.map(r=>({...r,user_rating_1_to_5:feedback[r.engine+'/'+r.voice]?.stars??null,error_reported:feedback[r.engine+'/'+r.voice]?.error===true}))};let blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='alienvox-cpu-voice-feedback.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});window.addEventListener('resize',draw);draw();table();
</script></body></html>'''.replace("__DATA__", data)
    target.write_text(page, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    target = args.output or args.report.with_name("cpu-voice-cost.html")
    render(args.report, target)
    print(target.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
