// 실시간 데이터(배차간격·도착정보·혼잡도) 로더.
//
// 서버 cron 이 10분마다 realtime.json 을 만들어 OCI Object Storage 에 덮어쓴다.
// 화면은 그 URL 하나만 읽는다. 서버에 직접 붙지 않으므로 SSH 키도 API 키도 필요 없다.
//
// 원칙: 실시간은 '있으면 얹는' 부가정보다. 로드에 실패해도 예보 화면은 그대로 동작해야 한다.
//       그래서 모든 접근자는 데이터가 없으면 조용히 null/'' 을 돌려준다.
//
// URL 설정: index.html 에서 로드 전에
//     <script>window.REALTIME_URL = 'https://objectstorage.../realtime.json'</script>
// 미설정 시엔 로컬 동기화본(../../data/realtime.json)을 본다 — 개발용.

const RT_URL = window.REALTIME_URL || '../../data/realtime.json';
const RT_REFRESH_MS = 60_000;      // 1분마다 갱신 (원본은 10분마다 바뀐다)
const RT_STALE_MIN = 30;           // 이보다 오래되면 '지연'으로 표시

let RT = null;

// citydata 는 '건대입구역', 지하철 API 는 '건대입구' — 같은 키로 맞춘다(서버 가공과 동일 규칙).
const rtNorm = s => {
  s = (s || '').trim();
  return s.length > 1 && s.endsWith('역') ? s.slice(0, -1) : s;
};

async function rtLoad() {
  try {
    // 캐시 우회 — 10분마다 덮어써지므로 브라우저 캐시를 타면 낡은 값을 본다.
    const res = await fetch(`${RT_URL}?t=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    RT = await res.json();
  } catch (e) {
    RT = null;                     // 조용히 포기 — 예보 화면은 계속 돈다
    console.warn('[realtime] 로드 실패 (예보만 표시):', e.message);
  }
  return RT;
}

/** 데이터가 몇 분 전 것인지. 없으면 null. */
function rtAgeMin() {
  if (!RT?.generated_at) return null;
  const t = new Date(RT.generated_at).getTime();
  return Number.isNaN(t) ? null : Math.max(0, Math.round((Date.now() - t) / 60000));
}

function rtStale() {
  const age = rtAgeMin();
  return age === null || age > RT_STALE_MIN;
}

/** 지점 실시간 혼잡도 — {level, ppltn_min, ppltn_max, base_time, forecast} 또는 null. */
function rtCongestion(station) {
  return RT?.congestion?.[rtNorm(station)] || null;
}

/** (호선, 역) 실측 배차간격 — {headway_sec, n_samples} 또는 null. */
function rtHeadway(line, station) {
  return RT?.headway?.[`${+line}|${rtNorm(station)}`] || null;
}

/** 역 도착정보 — {updated_at, trains[]} 또는 null. */
function rtArrivals(station) {
  return RT?.arrivals?.[rtNorm(station)] || null;
}

/** 해당 역의 다음 열차(해당 호선) — {eta_sec, msg, dest} 또는 null. */
function rtNextTrain(line, station) {
  const a = rtArrivals(station);
  if (!a) return null;
  return a.trains.find(t => +t.line === +line && t.eta_sec != null) || null;
}

/**
 * 경로 정류장에 붙일 실시간 태그 HTML. 없으면 빈 문자열.
 * 혼잡도 → 배차 → 다음 열차 순으로, 있는 것만 붙인다.
 */
function rtTags(line, station) {
  if (!RT || rtStale()) return '';
  const out = [];

  const c = rtCongestion(station);
  if (c?.level) out.push(`<span class="tag rt" title="서울시 실시간 도시데이터 · 기준 ${c.base_time || '-'}">실시간 ${c.level}</span>`);

  const h = rtHeadway(line, station);
  if (h) out.push(`<span class="tag rt" title="최근 ${h.window_min}분 표본 ${h.n_samples}건의 중앙값">배차 ${(h.headway_sec / 60).toFixed(1)}분</span>`);

  const n = rtNextTrain(line, station);
  if (n) {
    const m = Math.round(n.eta_sec / 60);
    out.push(`<span class="tag rt" title="${n.dest || ''}행 · ${n.current || ''}">다음 ${m <= 0 ? '곧' : m + '분'}</span>`);
  }
  return out.join('');
}

/** 화면 하단에 붙일 실시간 상태 문구. */
function rtStatusText() {
  if (!RT) return '실시간 미연결 (예보만 표시)';
  const age = rtAgeMin();
  const n = Object.keys(RT.congestion || {}).length;
  const h = Object.keys(RT.headway || {}).length;
  return rtStale()
    ? `실시간 지연 — ${age}분 전 데이터`
    : `실시간 ${age}분 전 · 혼잡도 ${n}곳 · 배차 ${h}건`;
}

/** 주기 갱신 시작. 갱신될 때마다 onUpdate() 를 부른다. */
function rtStart(onUpdate) {
  const tick = () => rtLoad().then(() => onUpdate && onUpdate());
  tick();
  setInterval(tick, RT_REFRESH_MS);
}
