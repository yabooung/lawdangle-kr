# -*- coding: utf-8 -*-
"""lawdangle 로컬 웹 UI — 브라우저에서 인용 분석/조문 매핑을 테스트.

추가 의존성 없음(파이썬 표준 http.server). 법제처 OC 키 필요(--deep/실조회).

실행:
    LAW_OC=your_oc python examples/webapp.py        # 또는 .env 의 oc=
    → http://localhost:8000 접속
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from lawdangle.classifier import classify           # noqa: E402
from lawdangle.cli import run_law                    # noqa: E402
from lawdangle.mapper import (  # noqa: E402
    enrich_result, suggest_mapping, suggest_mapping_auto,
)
from lawdangle.parser import parse_citations         # noqa: E402
from lawdangle.resolver import LawGoKrResolver        # noqa: E402

PORT = int(os.environ.get("PORT", "8000"))


def _load_oc() -> str | None:
    oc = os.environ.get("LAW_OC")
    if oc:
        return oc
    env = Path(__file__).resolve().parents[1] / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().lower().startswith("oc="):
                return line.split("=", 1)[1].strip()
    return None


OC = _load_oc()
RESOLVER = LawGoKrResolver(OC) if OC else None

PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>lawdangle — 죽은 인용 검출기</title>
<style>
:root{--bg:#0f1115;--card:#181b22;--line:#2a2f3a;--fg:#e6e9ef;--mut:#9aa4b2;--acc:#5b9dff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,"Malgun Gothic",sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:28px 20px 80px}
h1{font-size:22px;margin:0 0 4px}.sub{color:var(--mut);margin:0 0 20px;font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:18px}
.card h2{font-size:15px;margin:0 0 12px;color:var(--acc)}
textarea,input{width:100%;background:#0c0e12;color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:10px;font:14px/1.5 ui-monospace,monospace}
textarea{min-height:120px;resize:vertical}
.row{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px;align-items:center}
.row input{flex:1;min-width:160px}
button{background:var(--acc);color:#04122e;border:0;border-radius:8px;padding:10px 18px;font-weight:700;cursor:pointer}
button:disabled{opacity:.5;cursor:wait}
label.ck{color:var(--mut);font-size:13px;display:flex;gap:6px;align-items:center;cursor:pointer}
table{width:100%;border-collapse:collapse;margin-top:14px;font-size:13px}
th,td{border-bottom:1px solid var(--line);padding:8px 6px;text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:600}
.cat{font-weight:800;padding:2px 8px;border-radius:6px;font-size:12px}
.A{background:#1f4d2e;color:#7ee2a8}.B{background:#4d4318;color:#f0d36b}
.C{background:#5a3417;color:#ffb27a}.D{background:#1f3a5a;color:#86c2ff}
.E{background:#5a1f23;color:#ff8a90}.none{background:#2a2f3a;color:#9aa4b2}
.mut{color:var(--mut)}.warn{color:#ffb27a}
.bar{display:flex;gap:14px;flex-wrap:wrap;margin:10px 0;font-size:13px}
.pill{background:#0c0e12;border:1px solid var(--line);border-radius:20px;padding:4px 12px}
code{background:#0c0e12;padding:1px 6px;border-radius:5px;font-size:12px}
.err{color:#ff8a90}
</style></head><body><div class="wrap">
<h1>lawdangle <span class="mut">— 현행 법령의 죽은 인용 검출기</span></h1>
<p class="sub">인용된 대상 법령의 폐지·개명·이관·사문화를 탐지해 5분류(A~E)로 태깅합니다. __OCNOTE__</p>

<div class="card">
  <h2>① 법령명으로 분석 <span class="mut">(권장 — 본문 자동 fetch, 조 단위)</span></h2>
  <div class="row">
    <input id="lawname" placeholder="법령명 — 예: 공유수면 관리 및 매립에 관한 법률" onkeydown="if(event.key==='Enter')analyzeLaw()">
    <label class="ck"><input type="checkbox" id="ldeep"> --deep</label>
    <button id="lrun" onclick="analyzeLaw()">분석</button>
  </div>
  <div id="lout"></div>
</div>

<div class="card">
  <h2>② 법령 본문(텍스트) 분석 <span class="mut">— 임시/부분 텍스트용</span></h2>
  <textarea id="text" placeholder="법령 본문을 붙여넣으세요. 예) 「국가균형발전 특별법」 제17조제2항에 따른 사업 …"></textarea>
  <div class="row">
    <label class="ck"><input type="checkbox" id="deep"> --deep (대응 조문까지 매핑 · 느림)</label>
    <button id="run" onclick="analyze()">분석</button>
  </div>
  <div id="out"></div>
</div>

<div class="card">
  <h2>③ 조문 대응 매핑 (--map)</h2>
  <div class="row">
    <input id="m_old" placeholder="옛(폐지) 법령명 — 예: 국가균형발전 특별법">
    <input id="m_art" placeholder="조문 — 예: 제17조제2항" style="max-width:180px">
  </div>
  <div class="row">
    <input id="m_succ" placeholder="후속법령명 (비우면 본문 기반 자동 발견 — 분할 이관도 OK)">
    <button id="mrun" onclick="domap()">매핑</button>
  </div>
  <div id="mout"></div>
</div>

<script>
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function catCell(c){const k=c||'none';const lbl=c||'정상/미확인';return `<span class="cat ${k}">${lbl}</span>`}

function renderResults(d, out, showCiting){
  const s=d.summary;
  let h=`<div class="bar">
    <span class="pill">총 ${s.total}건</span>
    <span class="pill A">A ${s.distribution.A}</span>
    <span class="pill B">B ${s.distribution.B}</span>
    <span class="pill C">C ${s.distribution.C}</span>
    <span class="pill D">D ${s.distribution.D}</span>
    <span class="pill E">E ${s.distribution.E}</span>
    <span class="pill warn">심각성 상위(E·C·D) ${s.high_severity_ECD}</span>
    <span class="pill">수동 ${s.flagged_manual}</span></div>`;
  // 분류된 것(A~E)을 위로, 정상/미확인은 접어서
  const flagged=d.results.filter(x=>x.category), normal=d.results.filter(x=>!x.category);
  h+='<table><tr>'+(showCiting?'<th>인용하는 조</th>':'')+
     '<th>인용 대상</th><th>조문</th><th>상태</th><th>분류</th><th>신뢰도</th><th>제안</th><th>근거</th></tr>';
  for(const x of flagged){
    h+='<tr>'+(showCiting?`<td class="mut">${esc(x.citing_article)}</td>`:'')+
    `<td>${esc(x.cited_law_name)}</td><td>${esc(x.cited_article)}</td>
    <td class="mut">${esc(x.cited_status)}</td><td>${catCell(x.category)}</td>
    <td class="mut">${esc(x.confidence)}</td><td>${esc(x.successor_suggestion)}</td>
    <td class="mut">${esc(x.note)}</td></tr>`;
  }
  h+='</table>';
  if(normal.length) h+=`<p class="mut">＋ 현행·정상/미확인 ${normal.length}건 (분류 대상 아님)</p>`;
  if(!flagged.length) h+='<p class="mut">죽은 인용 없음 — 모두 현행/정상.</p>';
  out.innerHTML=h;
}

async function analyzeLaw(){
  const btn=document.getElementById('lrun'), out=document.getElementById('lout');
  const law=document.getElementById('lawname').value.trim();
  if(!law){out.innerHTML='<p class="err">법령명을 입력하세요.</p>';return}
  btn.disabled=true; out.innerHTML='<p class="mut">본문 fetch + 분석 중… (큰 법령은 다소 걸립니다)</p>';
  try{
    const r=await fetch('/api/law',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({law, deep:document.getElementById('ldeep').checked})});
    const d=await r.json();
    if(d.error){out.innerHTML='<p class="err">'+esc(d.error)+'</p>';return}
    renderResults(d, out, true);
  }catch(e){out.innerHTML='<p class="err">'+esc(''+e)+'</p>'}
  finally{btn.disabled=false}
}

async function analyze(){
  const btn=document.getElementById('run'), out=document.getElementById('out');
  const text=document.getElementById('text').value;
  if(!text.trim()){out.innerHTML='<p class="err">본문을 입력하세요.</p>';return}
  btn.disabled=true; out.innerHTML='<p class="mut">분석 중… (라이브 API 조회)</p>';
  try{
    const r=await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text, deep:document.getElementById('deep').checked})});
    const d=await r.json();
    if(d.error){out.innerHTML='<p class="err">'+esc(d.error)+'</p>';return}
    renderResults(d, out, false);
  }catch(e){out.innerHTML='<p class="err">'+esc(''+e)+'</p>'}
  finally{btn.disabled=false}
}

async function domap(){
  const btn=document.getElementById('mrun'), out=document.getElementById('mout');
  const old=document.getElementById('m_old').value, art=document.getElementById('m_art').value, succ=document.getElementById('m_succ').value;
  if(!old||!art){out.innerHTML='<p class="err">옛 법령명과 조문은 필수입니다(후속법은 비우면 자동 발견).</p>';return}
  btn.disabled=true; out.innerHTML='<p class="mut">매핑 중… (연혁 walk + 유사도)</p>';
  try{
    const r=await fetch('/api/map',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({old_law:old, article:art, successor:succ})});
    const d=await r.json();
    if(d.error){out.innerHTML='<p class="err">'+esc(d.error)+'</p>';return}
    let h=`<p class="mut">옛 ${esc(d.old_article)} ${d.version?('(실본문 '+d.version+' 시행본)'):''}<br>${esc(d.old_snippet)}</p>`;
    h+=`<p>판정: <b>${d.confident?'유력':'수동확인'}</b> — ${esc(d.note)}</p>`;
    h+='<table><tr><th>#</th><th>후속 조문</th><th>유사도</th><th>발췌</th></tr>';
    d.candidates.forEach((c,i)=>{h+=`<tr><td>${i+1}</td><td><b>${esc(c.article)}</b></td><td>${c.score}</td><td class="mut">${esc(c.snippet)}</td></tr>`});
    h+='</table>';
    out.innerHTML=h;
  }catch(e){out.innerHTML='<p class="err">'+esc(''+e)+'</p>'}
  finally{btn.disabled=false}
}
</script>
</div></body></html>"""


def _row(r):
    return {
        "citing_article": r.citation.citing_article or "",
        "cited_law_name": r.citation.cited_law_name,
        "cited_article": r.citation.cited_article or "",
        "cited_status": r.history.status.value,
        "category": r.category.name if r.category else "",
        "confidence": r.confidence.value,
        "successor_suggestion": r.successor_suggestion or "",
        "note": r.note,
    }


def _summary(results):
    from collections import Counter
    dist = Counter(r.category.name for r in results if r.category)
    return {
        "total": len(results),
        "distribution": {k: dist.get(k, 0) for k in "ABCDE"},
        "high_severity_ECD": dist["E"] + dist["C"] + dist["D"],
        "flagged_manual": sum(1 for r in results if r.flag),
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):  # 콘솔 소음 줄이기
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            note = ("법제처 OC 키 로드됨 ✓" if OC
                    else "⚠ OC 키 없음 — LAW_OC 또는 .env(oc=) 설정 필요(실조회 불가)")
            self._send(200, PAGE.replace("__OCNOTE__", note), "text/html; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain; charset=utf-8")

    def _read_json(self):
        n = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(n) or "{}")

    def do_POST(self):
        if RESOLVER is None:
            self._send(200, json.dumps({"error": "OC 키 없음 — LAW_OC 또는 .env(oc=)를 설정하세요."}))
            return
        try:
            body = self._read_json()
            if self.path == "/api/analyze":
                results = [classify(c, RESOLVER.resolve(c.cited_law_name))
                           for c in parse_citations(body.get("text", ""))]
                if body.get("deep"):
                    results = [enrich_result(r, RESOLVER) for r in results]
                self._send(200, json.dumps(
                    {"results": [_row(r) for r in results], "summary": _summary(results)},
                    ensure_ascii=False))
            elif self.path == "/api/law":
                results = run_law(body["law"], RESOLVER, deep=bool(body.get("deep")))
                self._send(200, json.dumps(
                    {"results": [_row(r) for r in results], "summary": _summary(results)},
                    ensure_ascii=False))
            elif self.path == "/api/map":
                succ = (body.get("successor") or "").strip()
                if succ:
                    s = suggest_mapping(RESOLVER, body["old_law"], body["article"], succ)
                else:
                    s = suggest_mapping_auto(RESOLVER, body["old_law"], body["article"])
                if s is None:
                    self._send(200, json.dumps({"error": "후속법을 자동 발견하지 못했습니다(직접 입력해 보세요)."}, ensure_ascii=False))
                    return
                self._send(200, json.dumps({
                    "old_article": s.old_article, "version": s.old_article_version,
                    "old_snippet": s.old_snippet, "successor_law": s.successor_law,
                    "confident": s.confident, "note": s.note,
                    "candidates": [{"article": c.article, "score": c.score, "snippet": c.snippet}
                                   for c in s.candidates],
                }, ensure_ascii=False))
            else:
                self._send(404, json.dumps({"error": "unknown endpoint"}))
        except Exception as e:  # noqa: BLE001
            self._send(200, json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False))


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"lawdangle web UI → http://localhost:{PORT}  (OC: {'OK' if OC else '없음'})")
    print("종료: Ctrl+C")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
