// Apex 혼잡도 예보 화면 — 전체 호선 통합 검색 + 환승 경로 + 요일/공휴일 + 혼잡도 %.
// 로직 단일 출처는 src/service.py; 화면은 export된 밀도·백분위표로 조회·보간·경로계산.
let DB = null, NAME_LINES = {}, ZONE = 'p', PROFILE = '일반', SELECTED_ROUTE = 0, BASIS = 'rel';
// 정원 대비(첨두) 4단계 경계(%). 휠체어는 더 보수적.
const ABS_BANDS = { '일반': [40, 70, 100], '휠체어': [25, 50, 75] };
const $ = id => document.getElementById(id);
window.selectRoute = i => { SELECTED_ROUTE = i; render(); };
// 서울지하철 공식 노선색
const LINE_COLORS = { 1: '#0052A4', 2: '#00A84D', 3: '#EF7C1C', 4: '#00A5DE',
  5: '#996CAC', 6: '#CD7C2F', 7: '#747F00', 8: '#E6186C', 9: '#BB8336' };
const lineColor = l => LINE_COLORS[+l] || '#888';
const zoneTable = () => DB.pctTable[ZONE === 'p' ? 'platform' : 'concourse'];

// 프로필별 혼잡 등급 기준(백분위 밴드). 휠체어는 더 보수적(낮은 임계)·더 세분화(6단계).
// 근거: ADA 휠체어 정지 점유면적 0.93㎡ ≈ 일반 보행자 개인공간의 약 2배,
//       군중에 휠체어 혼입 시 병목 유량 ~15% 감소(휠체어는 혼잡에 더 취약).
//       → 같은 밀도라도 더 이른 단계에서 '혼잡'으로 판정, 상단을 심각/위험으로 세분.
// 향후: 밴드를 사용자 개인 설정으로 덮어쓸 수 있게 확장 예정.
const PROFILES = {
  '일반':   { labels: ['여유', '보통', '주의', '혼잡'], bands: [50, 80, 95] },
  '휠체어': { labels: ['여유', '보통', '주의', '혼잡', '심각', '위험'], bands: [30, 50, 70, 85, 95] },
};

async function boot() {
  try { DB = await (await fetch('../../output/forecast.json')).json(); }
  catch (e) { $('foot').textContent = 'forecast.json 로드 실패: ' + e; return; }

  // 역명 → 호선 맵(환승 그래프용)
  for (const [line, stns] of Object.entries(DB.lines))
    stns.forEach(s => (NAME_LINES[s] = NAME_LINES[s] || []).push(+line));

  DB.days.forEach(d => $('day').add(new Option(d + (d === '공휴일' ? '' : '요일'), d)));
  $('day').value = '월';
  $('stationList').innerHTML = DB.allStations.map(s => `<option value="${s}">`).join('');
  $('from').value = '왕십리'; $('to').value = '시청';

  ['day', 'from', 'to', 'depart'].forEach(id => $(id).addEventListener('input', () => {
    if (id !== 'depart') SELECTED_ROUTE = 0;
    render();
  }));
  $('zoneSeg').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    ZONE = b.dataset.z;
    [...$('zoneSeg').children].forEach(x => x.classList.toggle('on', x === b));
    buildLegend(); render();
  });
  $('modeSeg').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    PROFILE = b.dataset.m;
    [...$('modeSeg').children].forEach(x => x.classList.toggle('on', x === b));
    buildLegend(); render();
  });
  $('basisSeg').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    BASIS = b.dataset.b;
    [...$('basisSeg').children].forEach(x => x.classList.toggle('on', x === b));
    buildLegend(); render();
  });
  buildLegend();
  $('foot').innerHTML = '혼잡도 % = 그 밀도의 <b>백분위수</b>(평일 전 역·시간대 해당 구역 밀도 분포 기준). 4단계 = 50/80/95%.<br>' +
    '공휴일은 별도 카테고리(학습 결과 ≈ 일요일).<br>' +
    '승강장/대합실 = 밀도 백분위, <b>열차 = 재차/정원 %</b>(공식). ETA는 역간거리·환승소요 실측 반영 · 시간 사이 선형 보간.';
  render();
}

// ── 조회·보간·백분위 ──────────────────────────────────────────
const clampMin = m => Math.max(300, Math.min(1440, m));
const clampHour = h => Math.max(5, Math.min(24, h));
const fmt = m => { m = Math.round(m); return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}`; };

function cell(line, station, day, hour) {
  const s = DB.curve[line] && DB.curve[line][station];
  return (s && s[day] && s[day][String(clampHour(hour))]) || null;
}
function densityAt(line, station, day, totalMin) {
  const hf = clampMin(totalMin) / 60;
  const c0 = cell(line, station, day, Math.floor(hf)), c1 = cell(line, station, day, Math.ceil(hf));
  const d0 = c0 ? c0[ZONE] : null, d1 = c1 ? c1[ZONE] : null;
  if (d0 == null) return d1; if (d1 == null) return d0;
  return d0 + (d1 - d0) * (hf - Math.floor(hf));
}
function badgeAt(line, station, day, totalMin) {
  const c = cell(line, station, day, Math.round(clampMin(totalMin) / 60));
  return c ? !!c[ZONE === 'p' ? 'pb' : 'cb'] : false;
}
function percentOf(density) {
  if (density == null) return null;
  const t = zoneTable(); let c = 0;
  for (let i = 0; i < t.length; i++) { if (t[i] <= density) c++; else break; }
  return Math.max(0, Math.min(100, c));
}
function levelOf(pct) {
  if (pct == null) return '-';
  const p = PROFILES[PROFILE];
  for (let i = p.bands.length - 1; i >= 0; i--) if (pct >= p.bands[i]) return p.labels[i + 1];
  return p.labels[0];
}

// ── 환승 그래프 최단시간 경로(Dijkstra) ────────────────────────
const segMin = (line, st) => (DB.segMin?.[line]?.[st]) ?? DB.meta.min_per_station;
const xferMin = (st, a, b) => (DB.xferMin?.[st]?.[`${a}-${b}`]) ?? (DB.xferMin?.[st]?.[`${b}-${a}`]) ?? DB.meta.transfer_min;
function neighbors(line, st) {
  const seq = DB.lines[line], i = seq.indexOf(st), out = [];
  if (i > 0) out.push([line, seq[i - 1], segMin(line, st), false]);            // 두 역 시간 = 현재역 seg
  if (i < seq.length - 1) out.push([line, seq[i + 1], segMin(line, seq[i + 1]), false]);
  (NAME_LINES[st] || []).forEach(o => { if (o !== +line) out.push([o, st, xferMin(st, +line, o), true]); });
  return out;
}
// tPenalty: 환승 1회당 라우팅 가산(분). 0=최소시간, 크게=최소환승. 실제 소요는 페널티 없이 재계산.
function route(frm, to, tPenalty = 0) {
  if (!NAME_LINES[frm] || !NAME_LINES[to]) return [];
  const dist = {}, prev = {}, key = (l, s) => l + '|' + s;
  NAME_LINES[frm].forEach(l => dist[key(l, frm)] = 0);
  const visited = {}; let goal = null;
  while (true) {
    let u = null, ud = Infinity;
    for (const k in dist) if (!visited[k] && dist[k] < ud) { ud = dist[k]; u = k; }
    if (u == null) break;
    visited[u] = 1;
    const [ul, us] = u.split('|'); if (us === to) { goal = u; break; }
    neighbors(+ul, us).forEach(([nl, ns, w, tf]) => {
      const nk = key(nl, ns), nd = ud + w + (tf ? tPenalty : 0);
      if (nd < (dist[nk] ?? Infinity)) { dist[nk] = nd; prev[nk] = u; }
    });
  }
  if (!goal) return [];
  const nodes = []; let n = goal;
  while (n) { const [l, s] = n.split('|'); nodes.push({ line: +l, station: s }); n = prev[n]; }
  nodes.reverse();
  // 실제 소요시간(페널티 제외) 재계산
  nodes[0].cum = 0; nodes[0].transfer = false;
  for (let i = 1; i < nodes.length; i++) {
    const p = nodes[i - 1], c = nodes[i];
    const nb = neighbors(p.line, p.station).find(x => x[0] === c.line && x[1] === c.station);
    c.cum = (p.cum || 0) + (nb ? nb[2] : 0); c.transfer = nb ? nb[3] : false;
  }
  return nodes;
}
// 여러 경로 후보(최소시간·최소환승) — 서명 기준 중복 제거, (환승, 시간) 순 정렬
function routeOptions(frm, to) {
  const seen = new Set(), out = [];
  [0, 8, 30, 90].forEach(pen => {
    const r = route(frm, to, pen);
    if (!r.length) return;
    const sig = r.map(l => l.line + ':' + l.station).join('>');
    if (!seen.has(sig)) { seen.add(sig); out.push(r); }
  });
  out.sort((a, b) => {
    const ta = a.filter(l => l.transfer).length, tb = b.filter(l => l.transfer).length;
    return ta - tb || a[a.length - 1].cum - b[b.length - 1].cum;
  });
  return out.slice(0, 3);
}

// 열차 내 혼잡(OA-12928, 재차/정원 %) — 공식 기준. 요일유형 매핑 + 시간 보간.
const dayToTrain = d => d === '토' ? '토요일' : (d === '일' || d === '공휴일') ? '일요일' : '평일';
function trainCell(line, station, dt, slotmin) {
  const s = DB.trainPct && DB.trainPct[line] && DB.trainPct[line][station];
  return (s && s[dt] && s[dt][String(slotmin)]) ?? null;
}
function trainPctAt(line, station, dt, totalMin) {   // 30분 격자 보간
  const t = clampMin(totalMin), lo = Math.floor(t / 30) * 30, hi = lo + 30;
  const a = trainCell(line, station, dt, lo), b = trainCell(line, station, dt, hi);
  if (a == null) return b; if (b == null) return a;
  return a + (b - a) * ((t - lo) / 30);
}
// 서울교통공사 열차 혼잡도 등급(%). 휠체어는 더 보수적.
const TRAIN_BANDS = { '일반': [80, 130, 150], '휠체어': [60, 100, 130] };
function trainLevel(v) {
  if (v == null) return '-';
  const b = TRAIN_BANDS[PROFILE];
  return v > b[2] ? '혼잡' : v > b[1] ? '주의' : v > b[0] ? '보통' : '여유';
}
// 정원 대비(첨두) % — 셀의 pa/ca(30분 아님, 시간 보간)
function absAt(line, station, day, totalMin) {
  const hf = clampMin(totalMin) / 60, k = ZONE === 'p' ? 'pa' : 'ca';
  const c0 = cell(line, station, day, Math.floor(hf)), c1 = cell(line, station, day, Math.ceil(hf));
  const d0 = c0 ? c0[k] : null, d1 = c1 ? c1[k] : null;
  if (d0 == null) return d1; if (d1 == null) return d0;
  return d0 + (d1 - d0) * (hf - Math.floor(hf));
}
function absLevel(v) {
  if (v == null) return '-';
  const b = ABS_BANDS[PROFILE];
  return v >= b[2] ? '혼잡' : v >= b[1] ? '주의' : v >= b[0] ? '보통' : '여유';
}
// 구역별 통합 지표: 열차=공식%, 승강장/대합실=상대(백분위) 또는 정원대비(첨두)
function stopMetric(line, station, day, totalMin) {
  if (ZONE === 't') {
    const v = trainPctAt(line, station, dayToTrain(day), totalMin);
    return { pct: v == null ? null : Math.round(v), level: trainLevel(v), train: true };
  }
  if (BASIS === 'abs') {
    const v = absAt(line, station, day, totalMin);
    return { pct: v == null ? null : Math.round(v), level: absLevel(v) };
  }
  const pc = percentOf(densityAt(line, station, day, totalMin));
  return { pct: pc, level: levelOf(pc), train: false };
}

function legForecast(leg, departMin, day) {
  const arr = departMin + leg.cum, m = stopMetric(leg.line, leg.station, day, arr);
  return { ...leg, arr, pct: m.pct, level: m.level, train: m.train,
           badge: ZONE !== 't' && badgeAt(leg.line, leg.station, day, arr) };
}
// 판단 기준: '대표 혼잡' = 실제 승차하는 지점(출발역 + 환승 후 승차역)의 혼잡 최댓값.
// 탑승/환승 순간의 붐빔이 이동 난이도를 좌우하므로 도착역 단독이 아니라 승차지점 기준.
const boardingLegs = legs => legs.filter((l, i) => i === 0 || l.transfer);
function repMetric(legs, departMin, day) {
  let mx = { pct: -1, level: '-' };
  boardingLegs(legs).forEach(l => {
    const m = stopMetric(l.line, l.station, day, departMin + l.cum);
    if (m.pct != null && m.pct > mx.pct) mx = m;
  });
  return mx.pct < 0 ? { pct: null, level: '-' } : mx;
}
const routeScore = (legs, departMin, day) => {
  const r = repMetric(legs, departMin, day);
  return r.pct == null ? Infinity : r.pct;
};

// ── 렌더 ─────────────────────────────────────────────────────
const parseDepart = () => { const [h, m] = $('depart').value.split(':').map(Number); return clampMin(h * 60 + (m || 0)); };

function render() {
  const frm = $('from').value.trim(), to = $('to').value.trim(), day = $('day').value, departMin = parseDepart();
  if (!NAME_LINES[frm] || !NAME_LINES[to] || frm === to) {
    $('route').innerHTML = '<div class="leg">서로 다른 역을 입력하세요.</div>';
    $('reco').innerHTML = ''; $('routeOpts').innerHTML = ''; return;
  }
  const routes = routeOptions(frm, to);
  if (!routes.length) {
    $('route').innerHTML = '<div class="leg">경로를 찾지 못했습니다.</div>';
    $('reco').innerHTML = ''; $('routeOpts').innerHTML = ''; return;
  }
  if (SELECTED_ROUTE >= routes.length) SELECTED_ROUTE = 0;
  const legs = routes[SELECTED_ROUTE];
  const rlabel = ['최소환승', '대안 2', '대안 3'];
  $('routeOpts').innerHTML = routes.map((r, i) => {
    const t = Math.round(r[r.length - 1].cum), tr = r.filter(l => l.transfer).length;
    return `<button class="ropt ${i === SELECTED_ROUTE ? 'on' : ''}" onclick="selectRoute(${i})">` +
      `<div class="rl">${i === 0 ? '추천' : rlabel[i]}</div><div class="rt"><b>${t}분</b> · 환승 ${tr}회</div></button>`;
  }).join('');

  // 1-5 출발 시간 추천 (±60분 10분 간격)
  let best = { m: departMin, score: Infinity };
  for (let dm = departMin - 60; dm <= departMin + 60; dm += 10) {
    const s = routeScore(legs, clampMin(dm), day);
    if (s < best.score) best = { m: clampMin(dm), score: s };
  }
  const repAt = dm => repMetric(legs, dm, day);
  const destAt = dm => legForecast(legs[legs.length - 1], dm, day);
  const bR = repAt(best.m), cR = repAt(departMin), bD = destAt(best.m), same = Math.abs(best.m - departMin) < 5;
  const nTransfer = legs.filter(l => l.transfer).length;
  $('reco').innerHTML =
    `<div class="r-top">출발 시간 추천 · 총 ${Math.round(legs[legs.length - 1].cum)}분 · 환승 ${nTransfer}회 · 기준=승차 혼잡</div>` +
    `<div class="r-main">` +
    (same ? `지금(${fmt(departMin)}) 출발이 가장 쾌적 · 승차 ${bR.level} ${bR.pct}%`
          : `${fmt(best.m)} 출발 추천 · 승차 ${bR.level} ${bR.pct}% <span class="pct">(${fmt(departMin)}은 ${cR.level} ${cR.pct}%)</span>`) +
    ` <span class="pct">· 도착 ${bD.level} ${bD.pct}%</span></div><div class="r-opts">` +
    Array.from({ length: 13 }, (_, i) => -60 + i * 10).map(off => {
      const dm = clampMin(departMin + off), r = repAt(dm), isBest = Math.abs(dm - best.m) < 5;
      return `<div class="opt ${isBest ? 'best' : ''}"><div class="oh">${fmt(dm)}</div>` +
             `<div class="ol"><span class="pill p-${r.level}">${r.level}<span class="pv">${r.pct}%</span></span></div></div>`;
    }).join('') + `</div>`;

  // 1-1 도착 시점 예보 — 호선색 타임라인(같은 호선 연결) + 환승 + %/4단계 + 배지 + 원인
  $('route').innerHTML = legs.map(leg => {
    const f = legForecast(leg, departMin, day);
    const off = Math.round(leg.cum), c = lineColor(leg.line);
    const trans = leg.transfer
      ? `<div class="xfer" style="color:${c}"><i style="background:${c}"></i>${leg.line}호선으로 환승</div>` : '';
    const cs = (DB.causes || []).filter(x => x.station === leg.station && x.line === leg.line)
      .map(x => `<span class="tag cause">${x.type}: ${x.desc}</span>`).join('');
    const badge = f.badge ? '<span class="tag badge">평소보다 붐빔</span>' : '';
    const lineTag = `<span class="tag" style="background:${c};color:#fff">${leg.line}호선</span>`;
    return trans +
      `<div class="stop"><div class="rail" style="--lc:${c}"><span class="rdot"></span></div>` +
      `<div class="time">${fmt(f.arr)}<b>+${off}분</b></div>` +
      `<div class="mid"><div class="stn">${leg.station}</div><div class="tags">${lineTag}${badge}${cs}</div></div>` +
      `<span class="pill p-${f.level}">${f.level}<span class="pv">${f.pct}%</span></span></div>`;
  }).join('');
}

function buildLegend() {
  let labels, edges, suffix = '%';
  if (ZONE === 't') {
    labels = ['여유', '보통', '주의', '혼잡'];
    const b = TRAIN_BANDS[PROFILE]; edges = [0, ...b, '∞'];
  } else if (BASIS === 'abs') {
    labels = ['여유', '보통', '주의', '혼잡'];
    const b = ABS_BANDS[PROFILE]; edges = [0, ...b, '∞'];
  } else {
    const p = PROFILES[PROFILE]; labels = p.labels; edges = [0, ...p.bands, 100];
  }
  $('legend').innerHTML = labels.map((l, i) =>
    `<span class="lg"><span class="dot b-${l}"></span>${l} <span class="pct">${edges[i]}–${edges[i + 1]}${suffix}</span></span>`).join('');
}

boot();
