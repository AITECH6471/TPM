// 정기점검 관리: 점검 달력 · 계획 수립 · 점검표 · 기록 대장
// 데이터: pm_plans(월별 P=예정, D=확정, m{n}_date=점검일), pm_master(점검 항목), pm_result(항목별 O/X)
// 확정 = 그 달을 D로 바꾸는 것. 판정은 확정된 달의 결과에서 계산한다(X가 있으면 부적합).
import { state, $, pick, num, escapeHtml as esc, getRows, api, showToast } from './core.js';

const NOW = new Date();
const CUR_Y = NOW.getFullYear(), CUR_M = NOW.getMonth() + 1, TODAY = NOW.getDate();
const MS = Array.from({ length: 12 }, (_, i) => i + 1);
const LBL = { P: '예정', G: '적합', N: '부적합', L: '지연', D: '완료' };
const SYM = { P: '예정', G: '○', N: '✕', L: '지연', D: '완료' };
// 중요도 등급별 점검 달 (A 매월 · B 분기 · C 반기 · D 연 1회)
const CYCLE = { A: MS, B: [2, 5, 8, 11], C: [4, 10], D: [6] };
const CYCLE_LBL = { A: '매월', B: '분기', C: '반기', D: '연 1회' };

const S = {
  year: CUR_Y, tab: 'cal', sel: { c: '', m: CUR_M }, calM: CUR_M, led: { c: '', m: 0 },
  plans: {}, results: {}, items: {}, memo: {}, prevPlans: {},
  pending: null, msg: '', delAsk: null, unlockAsk: false, picked: null, busy: false, q: '', line: '',
};

// ---------- 데이터 ----------
const codeOf = (e) => String(pick(e.equip_code, e.code));
const targets = () => state.equipment.filter((e) => num(e.pm_yn) === 1);
const eqOf = (c) => state.equipment.find((e) => codeOf(e) === c) || { equip_code: c };
const gradeOf = (e) => String(pick(e.eval_grade, '')).toUpperCase();
const itemsOf = (c) => (S.items[c] || []).slice().sort((a, b) => num(a.sort_order) - num(b.sort_order) || num(a.id) - num(b.id));
const mv = (c, m) => { const v = S.plans[c]?.[`m${m}`]; return v === 'P' || v === 'D' ? v : ''; };
const dayOf = (c, m) => { const d = String(S.plans[c]?.[`m${m}_date`] || ''); return /^\d{4}-\d{2}-\d{2}$/.test(d) ? num(d.slice(8)) : 0; };
const past = (m) => S.year < CUR_Y || (S.year === CUR_Y && m < CUR_M);
const res = (c, m) => S.results[c]?.[m] || {};
const hasWork = (c, m) => Object.keys(res(c, m)).length > 0;
const pad = (n) => String(n).padStart(2, '0');
const cm = (m) => `${S.year}-${pad(m)}`;
const ymd = (m, d) => `${S.year}-${pad(m)}-${pad(d)}`;
const todayStr = () => `${CUR_Y}-${pad(CUR_M)}-${pad(TODAY)}`;

function status(c, m) {
  const v = mv(c, m);
  if (!v) return '';
  if (v === 'D') { const r = Object.values(res(c, m)); return !r.length ? 'D' : r.some((x) => x.pass_fail === 'X') ? 'N' : 'G'; }
  return past(m) ? 'L' : 'P';
}
const editable = (c, m) => mv(c, m) === 'P' && (S.year < CUR_Y || (S.year === CUR_Y && m <= CUR_M));

export async function loadPM() {
  const y = S.year;
  const [eq, pl, ms, rs] = await Promise.allSettled([
    state.equipment.length ? Promise.resolve(null) : api('equipment/list'),
    api(`pm/list?year=${y}`), api('pm/master/list'), api(`pm/result/year?year=${y}`),
  ]);
  if (eq.status === 'fulfilled' && eq.value) state.equipment = getRows(eq.value);
  if ([pl, ms, rs].some((p) => p.status === 'rejected')) showToast('정기점검 데이터 일부를 불러오지 못했습니다', 'error');
  if (pl.status === 'fulfilled') { S.plans = {}; state.pmPlans = getRows(pl.value); state.pmPlans.forEach((r) => { S.plans[r.equip_code] = r; }); }
  if (ms.status === 'fulfilled') setItems(getRows(ms.value));
  if (rs.status === 'fulfilled') setResults(getRows(rs.value));
  if (!S.sel.c || num(eqOf(S.sel.c).pm_yn) !== 1) S.sel.c = codeOf(targets()[0] || { equip_code: '' });
  // 60초 자동 새로고침 때 입력 중인 칸을 날리지 않는다
  const ae = document.activeElement;
  if (y === S.year && ae && $('pm-body')?.contains(ae) && /INPUT|TEXTAREA|SELECT/.test(ae.tagName)) return;
  render();
}
function setItems(rows) { state.pmMasters = rows; S.items = {}; rows.forEach((r) => { (S.items[r.equip_code] ||= []).push(r); }); }
function setResults(rows) {
  S.results = {};
  rows.forEach((r) => { const m = num(String(r.check_month).slice(5, 7)); ((S.results[r.equip_code] ||= {})[m] ||= {})[r.pm_master_id] = r; });
}
const reloadItems = async () => setItems(getRows(await api('pm/master/list')));
const reloadResults = async () => setResults(getRows(await api(`pm/result/year?year=${S.year}`)));

// ---------- 저장 ----------
function setMonth(c, m, v, date) {
  const p = (S.plans[c] ||= { equip_code: c, plan_year: S.year });
  p[`m${m}`] = v || '0';
  if (date !== undefined) p[`m${m}_date`] = date;
}
async function savePlan(c) {
  const p = S.plans[c] || {}, body = { equip_code: c, plan_year: S.year };
  MS.forEach((m) => { body[`m${m}`] = mv(c, m) || '0'; body[`m${m}_date`] = p[`m${m}_date`] || ''; });
  await api('pm/upsert-plan', { method: 'POST', body: JSON.stringify(body) });
}
async function submitResult(c, m, it, pf, memo = '') {
  const inspector = inspectorName();
  const body = { pm_master_id: it.id, equip_code: c, item_name: it.item_name, input_type: it.input_type || 'PASS_FAIL', pass_fail: pf, memo, check_month: cm(m), inspector, inspect_date: todayStr() };
  await api('pm/checklist/submit', { method: 'POST', body: JSON.stringify(body) });
  ((S.results[c] ||= {})[m] ||= {})[it.id] = { ...(res(c, m)[it.id] || {}), ...body };
}
async function clearResult(c, m, it) {
  if (!res(c, m)[it.id]?.id) await reloadResults();
  const id = res(c, m)[it.id]?.id;
  if (id) await api('pm/result/delete', { method: 'POST', body: JSON.stringify({ id }) });
  delete S.results[c]?.[m]?.[it.id];
}
async function run(fn) {
  if (S.busy) return;
  S.busy = true;
  try { await fn(); } catch (e) { showToast(`저장 실패: ${e.message}`, 'error'); await loadPM().catch(() => {}); } finally { S.busy = false; render(); }
}
function inspectorName() { try { return $('pm-inspector')?.value.trim() || localStorage.getItem('pm_inspector') || ''; } catch { return $('pm-inspector')?.value.trim() || ''; } }
// 대상에서 빼기: 지나지 않았고 손대지 않은 예정만 지우고, 지난 기록은 남긴다
async function setTarget(c, on) {
  const row = state.equipment.find((e) => codeOf(e) === c);
  if (!row) return 0;
  await api('equipment/upsert', { method: 'POST', body: JSON.stringify({ ...row, equip_code: c, pm_yn: on ? 1 : 0 }) });
  row.pm_yn = on ? 1 : 0;
  if (on) return 0;
  let n = 0;
  MS.forEach((m) => { if (mv(c, m) === 'P' && !past(m) && !hasWork(c, m)) { setMonth(c, m, '0', ''); n++; } });
  if (n) await savePlan(c);
  return n;
}

// ---------- 화면 공통 ----------
export function render() {
  const body = $('pm-body');
  if (!body) return;
  document.querySelectorAll('#page-pm-plan [data-pmtab]').forEach((b) => b.setAttribute('aria-selected', b.dataset.pmtab === S.tab));
  const ys = [...new Set([CUR_Y - 1, CUR_Y, CUR_Y + 1, S.year])].sort();
  $('pm-year-sel').innerHTML = ys.map((y) => `<option value="${y}"${y === S.year ? ' selected' : ''}>${y}년</option>`).join('');
  const late = targets().reduce((n, e) => n + MS.filter((m) => status(codeOf(e), m) === 'L').length, 0);
  $('pm-late-cnt').textContent = late ? `지연 ${late}` : '';
  body.innerHTML = { cal: calHTML, plan: planHTML, sheet: sheetHTML, led: ledHTML }[S.tab]();
  if (S.tab === 'sheet') renderSheetList();
}
const pill = (s) => s ? `<span class="pm-pill ${s}">${LBL[s]}</span>` : '';
const lineOptions = () => `<option value="">전체 라인</option>${[...new Set(targets().map((e) => pick(e.location, '')).filter(Boolean))].sort().map((l) => `<option${l === S.line ? ' selected' : ''}>${esc(l)}</option>`).join('')}`;
const inLine = (e) => !S.line || pick(e.location, '') === S.line;

// ---------- 점검 달력 ----------
function calHTML() {
  const m = S.calM, first = new Date(S.year, m - 1, 1).getDay(), days = new Date(S.year, m, 0).getDate();
  const list = targets().filter((e) => inLine(e) && mv(codeOf(e), m));
  const byDay = {};
  list.forEach((e) => { const d = dayOf(codeOf(e), m); if (d) (byDay[d] ||= []).push(e); });
  let cells = ['일', '월', '화', '수', '목', '금', '토'].map((d, i) => `<div class="pm-dn${i === 0 ? ' sun' : ''}">${d}</div>`).join('');
  const n = Math.ceil((first + days) / 7) * 7;
  for (let i = 0; i < n; i++) {
    const d = i - first + 1;
    if (d < 1 || d > days) { cells += '<div class="pm-d off"></div>'; continue; }
    const evs = byDay[d] || [];
    cells += `<div class="pm-d${S.year === CUR_Y && m === CUR_M && d === TODAY ? ' today' : ''}${S.picked ? ' pick' : ''}" data-day="${d}"><span class="n">${d}</span>${
      evs.slice(0, 4).map((e) => { const c = codeOf(e), s = status(c, m), fixed = ['G', 'N', 'D'].includes(s); return `<button class="pm-ev ${s}" data-open="${esc(c)}" ${fixed ? '' : 'draggable="true"'} data-drag="${esc(c)}" title="${esc(c)} ${esc(pick(e.equip_name, ''))} · ${LBL[s]}">${esc(c.replace(/^AIT-/, ''))}</button>`; }).join('')
    }${evs.length > 4 ? `<span class="pm-more">+${evs.length - 4}건</span>` : ''}</div>`;
  }
  const un = list.filter((e) => !dayOf(codeOf(e), m) && !['G', 'N', 'D'].includes(status(codeOf(e), m)));
  return `<div class="pm-tool">
      <button class="btn btn-secondary btn-sm" data-act="cal-prev" aria-label="이전 달">‹</button><b class="pm-ctitle">${S.year}년 ${m}월</b><button class="btn btn-secondary btn-sm" data-act="cal-next" aria-label="다음 달">›</button>
      <button class="btn btn-secondary btn-sm" data-act="cal-today">이번 달</button>
      <select class="form-control pm-sm" data-act="line" aria-label="라인">${lineOptions()}</select>
      <span class="pm-legend"><span><i class="P"></i>예정</span><span><i class="G"></i>적합</span><span><i class="N"></i>부적합</span><span><i class="L"></i>지연</span><span><i class="D"></i>완료(기록 없음)</span></span>
    </div>
    <div class="pm-calwrap"><div class="pm-cal">${cells}</div>
      <aside class="pm-unsch"><b>날짜 미정 ${un.length ? `<span class="pm-mu">${un.length}대</span>` : ''}</b>
        <p class="pm-mu pm-small">이 달에 계획은 있지만 날짜가 없는 설비입니다. 달력으로 끌어다 놓거나, 눌러서 고른 뒤 날짜를 누르세요.</p>
        ${un.map((e) => { const c = codeOf(e); return `<div class="pm-ev ${status(c, m)}${S.picked === c ? ' picked' : ''}" draggable="true" data-drag="${esc(c)}" data-pick="${esc(c)}" role="button" tabindex="0"><b>${esc(c)}</b><br>${esc(pick(e.equip_name, ''))}</div>`; }).join('') || '<p class="pm-mu pm-small">모두 날짜가 정해졌습니다.</p>'}
        <p class="pm-mu pm-small">달력 안의 예정 설비도 끌어서 옮길 수 있습니다. 확정된 점검은 옮길 수 없습니다. 설비를 누르면 점검표가 열립니다.</p>
      </aside></div>`;
}
async function placeDay(c, d) {
  const m = S.calM;
  if (['G', 'N', 'D'].includes(status(c, m))) return;
  S.picked = null;
  await run(async () => { setMonth(c, m, mv(c, m) || 'P', ymd(m, d)); await savePlan(c); });
}

// ---------- 계획 수립 ----------
const P = (c) => S.plans[c] || {};
const lockedForPlan = (c, m) => past(m) || hasWork(c, m) || mv(c, m) === 'D';
function workdays(m) {
  const n = new Date(S.year, m, 0).getDate(), out = [];
  for (let d = 1; d <= n; d++) { const w = new Date(S.year, m - 1, d).getDay(); if (w > 0 && w < 6 && !(S.year === CUR_Y && m === CUR_M && d <= TODAY)) out.push(d); }
  return out;
}
async function makePending(kind) {
  const pv = { kind, add: [], rm: [], dt: [], skipped: 0 };
  if (kind === 'fill') {
    const reset = $('pm-pmode')?.value === 'reset';
    targets().forEach((e) => {
      const c = codeOf(e), want = CYCLE[gradeOf(e)];
      if (!want) { pv.skipped++; return; }
      const have = MS.filter((m) => mv(c, m));
      if (!reset && have.length) return;
      want.forEach((m) => { if (!have.includes(m) && !lockedForPlan(c, m)) pv.add.push([c, m]); });
      if (reset) have.forEach((m) => { if (!want.includes(m) && !lockedForPlan(c, m)) pv.rm.push([c, m]); });
    });
  } else if (kind === 'copy') {
    const py = S.year - 1;
    if (!S.prevPlans[py]) { const rows = getRows(await api(`pm/list?year=${py}`)); S.prevPlans[py] = {}; rows.forEach((r) => { S.prevPlans[py][r.equip_code] = r; }); }
    const src = S.prevPlans[py];
    if (!Object.keys(src).length) { S.msg = `${py}년 계획이 없어 복사할 수 없습니다.`; return render(); }
    targets().forEach((e) => { const c = codeOf(e); MS.forEach((m) => { if (['P', 'D'].includes(src[c]?.[`m${m}`]) && !mv(c, m) && !lockedForPlan(c, m)) pv.add.push([c, m]); }); });
  } else if (kind === 'dist') {
    MS.forEach((m) => {
      const todo = targets().filter((e) => { const c = codeOf(e); return mv(c, m) === 'P' && !dayOf(c, m) && !lockedForPlan(c, m); });
      const wd = workdays(m);
      todo.forEach((e, i) => { if (wd.length) pv.dt.push([codeOf(e), m, wd[Math.floor(i * wd.length / todo.length)]]); });
    });
  }
  S.pending = pv; S.msg = ''; render();
}
async function applyPending() {
  const pv = S.pending, touched = new Set();
  pv.add.forEach(([c, m]) => { setMonth(c, m, 'P', ''); touched.add(c); });
  pv.rm.forEach(([c, m]) => { setMonth(c, m, '0', ''); touched.add(c); });
  pv.dt.forEach(([c, m, d]) => { setMonth(c, m, 'P', ymd(m, d)); touched.add(c); });
  const list = [...touched];
  for (let i = 0; i < list.length; i += 4) {
    S.msg = `저장 중… ${i}/${list.length}대`; render();
    await Promise.all(list.slice(i, i + 4).map(savePlan));
  }
  S.msg = `적용했습니다: 추가 ${pv.add.length} · 삭제 ${pv.rm.length} · 날짜 ${pv.dt.length}건 (설비 ${list.length}대 저장)`;
  S.pending = null;
}
function planHTML() {
  const tg = targets(), all = state.equipment.slice().sort((a, b) => num(b.pm_yn) - num(a.pm_yn) || String(pick(a.location, '')).localeCompare(String(pick(b.location, ''))) || codeOf(a).localeCompare(codeOf(b)));
  const total = tg.reduce((n, e) => n + MS.filter((m) => mv(codeOf(e), m)).length, 0);
  const undated = tg.reduce((n, e) => n + MS.filter((m) => mv(codeOf(e), m) === 'P' && !dayOf(codeOf(e), m) && !past(m)).length, 0);
  const empty = tg.filter((e) => !MS.some((m) => mv(codeOf(e), m))).length;
  const key = (c, m) => `${c}|${m}`, pv = S.pending;
  const A = new Set((pv?.add || []).map(([c, m]) => key(c, m))), R = new Set((pv?.rm || []).map(([c, m]) => key(c, m))), D = new Map((pv?.dt || []).map(([c, m, d]) => [key(c, m), d]));
  let preview = '';
  if (pv) {
    const title = { fill: '등급대로 채우기', copy: `${S.year - 1}년 계획 복사`, dist: '날짜 고르게 나누기' }[pv.kind];
    const none = !pv.add.length && !pv.rm.length && !pv.dt.length;
    preview = `<div class="pm-pv"><b>미리보기 · ${title}</b>${none ? `<span>바뀌는 칸이 없습니다.${S.year === CUR_Y && pv.kind !== 'dist' ? ` 올해는 지난달을 건드리지 않으므로 남은 달(${CUR_M}~12월)에 해당하는 점검만 넣습니다. 내년 계획은 "새 연도 만들기"로 만드세요.` : ''}</span>` : `<span>추가 <b class="add">${pv.add.length}</b></span><span>삭제 <b class="rm">${pv.rm.length}</b></span><span>날짜 지정 <b class="dt">${pv.dt.length}</b></span>`}${pv.skipped ? `<span class="pm-mu">중요도 등급이 없는 설비 ${pv.skipped}대는 건너뜀</span>` : ''}
      <span class="pm-mu pm-small">지난달, 결과를 넣었거나 확정한 달은 바꾸지 않습니다.</span>
      <span class="pm-right"><button class="btn btn-secondary btn-sm" data-act="pv-cancel">취소</button><button class="btn btn-primary btn-sm" data-act="pv-apply" ${none ? 'disabled' : ''}>적용</button></span></div>`;
  }
  const rows = all.map((e) => {
    const c = codeOf(e), on = num(e.pm_yn) === 1, g = gradeOf(e);
    return `<tr class="${on ? '' : 'off'}"><td><input type="checkbox" data-tg="${esc(c)}" ${on ? 'checked' : ''} aria-label="${esc(c)} 정기점검 대상"></td>
      <td><b>${esc(c)}</b> <span class="pm-small">${esc(pick(e.equip_name, ''))}</span></td><td>${esc(pick(e.location, ''))}</td><td>${esc(g || '-')}</td><td class="pm-mu">${CYCLE_LBL[g] || '-'}</td>
      ${MS.map((m) => {
        const k = key(c, m); let cell = '';
        if (A.has(k)) cell = '<span class="pm-pc add">+</span>';
        else if (R.has(k)) cell = '<span class="pm-pc rm">빼기</span>';
        else if (mv(c, m)) { const s = status(c, m), d = D.has(k) ? D.get(k) : dayOf(c, m); cell = `<span class="pm-pc ${s}${D.has(k) ? ' dt' : ''}">${['G', 'N', 'L', 'D'].includes(s) ? LBL[s] : d ? `${m}/${d}` : '미정'}</span>`; }
        return `<td class="m${S.year === CUR_Y && m === CUR_M ? ' now' : ''}">${cell}</td>`;
      }).join('')}<td class="pm-mu">${MS.filter((m) => mv(c, m)).length || ''}</td></tr>`;
  }).join('');
  return `<div class="pm-tool">
      <button class="btn btn-secondary btn-sm" data-act="new-year">새 연도 만들기 (${Math.max(S.year, CUR_Y) + 1}년)</button>
      <span class="pm-sep"></span>
      <select class="form-control pm-sm" id="pm-pmode" aria-label="채우는 방식"><option value="empty">계획 없는 설비만</option><option value="reset">등급대로 다시 맞추기</option></select>
      <button class="btn btn-secondary btn-sm" data-act="pv-fill">등급대로 채우기</button>
      <button class="btn btn-secondary btn-sm" data-act="pv-copy">작년 계획 복사</button>
      <button class="btn btn-secondary btn-sm" data-act="pv-dist">날짜 고르게 나누기</button>
    </div>
    <div class="pm-sum"><span>정기점검 대상 <b>${tg.length}</b> / 전체 ${state.equipment.length}대</span><span>${S.year}년 계획 <b>${total}</b>회</span><span>계획 없는 대상 <b class="${empty ? 'rm' : ''}">${empty}</b>대</span><span>날짜 미정 <b>${undated}</b>건</span>${S.msg ? `<span class="pm-msg">${esc(S.msg)}</span>` : ''}</div>
    ${preview}
    <div class="pm-scroll"><table class="pm-mx pm-plan-t"><thead><tr><th>대상</th><th>설비</th><th>라인</th><th>등급</th><th>주기</th>${MS.map((m) => `<th class="m${S.year === CUR_Y && m === CUR_M ? ' now' : ''}">${m}월</th>`).join('')}<th>횟수</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

// ---------- 점검표 ----------
function renderSheetList() {
  const box = $('pm-elist');
  if (!box) return;
  const q = S.q.toLowerCase();
  box.innerHTML = targets().filter((e) => inLine(e) && (!q || `${codeOf(e)} ${pick(e.equip_name, '')}`.toLowerCase().includes(q))).map((e) => {
    const c = codeOf(e), late = MS.some((m) => status(c, m) === 'L'), s = S.year === CUR_Y ? status(c, CUR_M) : '';
    const chip = late ? pill('L') : s === 'P' ? '<span class="pm-pill P">이달</span>' : pill(s);
    return `<button class="pm-e${c === S.sel.c ? ' on' : ''}" data-sel="${esc(c)}"><span><b>${esc(c)}</b><small>${esc(pick(e.equip_name, ''))}</small></span>${chip}</button>`;
  }).join('') || '<p class="pm-mu" style="padding:10px">정기점검 대상 설비가 없습니다. 계획 수립 탭에서 대상을 켜세요.</p>';
}
function sheetHTML() {
  const c = S.sel.c, e = eqOf(c), its = itemsOf(c), m0 = S.sel.m;
  const left = `<aside class="pm-elist"><div class="pm-f"><input class="form-control pm-sm" id="pm-q" placeholder="설비코드·설비명 검색" value="${esc(S.q)}" aria-label="설비 검색"><select class="form-control pm-sm" data-act="line" aria-label="라인">${lineOptions()}</select></div><div id="pm-elist" class="pm-items"></div></aside>`;
  if (!c) return `<div class="pm-sheetwrap">${left}<div class="pm-empty">정기점검 대상 설비가 없습니다.</div></div>`;
  const cls = (m) => `m${S.year === CUR_Y && m === CUR_M ? ' now' : ''}${m === m0 ? ' selc' : ''}`;
  let t = `<thead><tr><th>부위</th><th>점검 항목</th><th>기준</th>${MS.map((m) => `<th class="${cls(m)}"><button data-selm="${m}" class="${m === m0 ? 'cur' : ''}">${m}월</button></th>`).join('')}<th></th></tr></thead><tbody>`;
  t += `<tr class="pm-planrow"><td colspan="3"><b>계획</b> <span class="pm-mu pm-small">날짜는 달력에서</span></td>${MS.map((m) => {
    if (!mv(c, m)) return `<td class="${cls(m)}"><button data-plan="${m}" aria-label="${m}월 계획 추가">+</button></td>`;
    const s = status(c, m), d = dayOf(c, m);
    const txt = ['G', 'N', 'L', 'D'].includes(s) ? LBL[s] : d ? `${m}/${d}` : '미정';
    return `<td class="${cls(m)}"><button class="on ${s === 'P' ? '' : s}" data-plan="${m}" aria-label="${m}월 ${txt}">${txt}</button></td>`;
  }).join('')}<td></td></tr>`;
  its.forEach((it) => {
    const id = num(it.id), nres = MS.filter((m) => res(c, m)[id]).length;
    t += `<tr><td class="pm-mu">${esc(pick(it.part_name, '-'))}</td><td>${esc(pick(it.item_name, ''))}${it.criteria_photo ? ` <a href="${esc(it.criteria_photo)}" target="_blank" rel="noopener" title="기준 사진">사진</a>` : ''}</td><td class="pm-mu pm-small">${esc(pick(it.criteria, ''))}</td>`;
    MS.forEach((m) => {
      if (!mv(c, m)) { t += `<td class="${cls(m)}"></td>`; return; }
      const v = res(c, m)[id]?.pass_fail || '';
      t += editable(c, m)
        ? `<td class="${cls(m)}"><button class="pm-ox ${v}" data-ox="${id}" data-m="${m}" aria-label="${esc(it.item_name)} ${m}월 ${v || '미입력'}">${v || '·'}</button></td>`
        : `<td class="${cls(m)}"><span class="pm-r ${v}">${v}</span></td>`;
    });
    const ask = S.delAsk === id;
    t += `<td><button class="pm-del${ask ? ' ask' : ''}" data-del="${id}">${ask ? (nres ? `실적 ${nres}건도 지워집니다. 삭제?` : '삭제할까요?') : '삭제'}</button></td></tr>`;
  });
  t += `<tr class="pm-addrow"><td><input class="form-control pm-sm" id="pm-n-part" placeholder="부위" style="width:80px"></td><td><input class="form-control pm-sm" id="pm-n-name" placeholder="새 점검 항목" style="min-width:150px"></td><td colspan="13"><span class="pm-inline"><input class="form-control pm-sm" id="pm-n-crit" placeholder="점검 기준" style="width:180px"><button class="btn btn-secondary btn-sm" data-act="item-add">+ 항목 추가</button>
    <select class="form-control pm-sm" id="pm-copyfrom" aria-label="항목을 가져올 설비"><option value="">다른 설비 항목 가져오기</option>${Object.keys(S.items).filter((k) => k !== c).sort().map((k) => `<option value="${esc(k)}">${esc(k)} (${S.items[k].length})</option>`).join('')}</select><button class="btn btn-secondary btn-sm" data-act="item-copy">가져오기</button></span></td><td></td></tr>`;
  t += `<tr class="pm-verdict"><td colspan="3">판정</td>${MS.map((m) => `<td class="${cls(m)}">${pill(status(c, m))}</td>`).join('')}<td></td></tr></tbody>`;
  const g = gradeOf(e);
  return `<div class="pm-sheetwrap">${left}<div class="pm-sheetmain">
    <div class="pm-shead"><h3>${esc(c)} · ${esc(pick(e.equip_name, ''))}</h3><span class="pm-mu">${esc(pick(e.location, '-'))} · 중요도 ${esc(g || '-')}등급${CYCLE_LBL[g] ? `(권장 ${CYCLE_LBL[g]})` : ''} · ${S.year}년 점검 ${MS.filter((m) => mv(c, m)).length}회</span><span class="pm-pill mute">항목 ${its.length}개</span>
      <label class="pm-sw"><input type="checkbox" data-tg="${esc(c)}" checked> 정기점검 대상</label></div>
    ${S.msg ? `<div class="pm-sum"><span class="pm-msg">${esc(S.msg)}</span></div>` : ''}
    <div class="pm-scroll"><table class="pm-mx">${t}</table></div>
    <div class="pm-foot">${footHTML(c, m0, its)}</div></div></div>`;
}
function footHTML(c, m, its) {
  const r = res(c, m), s = status(c, m);
  if (!mv(c, m)) return `<div class="pm-row"><span class="pm-big">${m}월</span><span class="pm-mu">이 달은 점검 계획이 없습니다. 위 계획 줄의 + 를 누르면 추가됩니다.</span></div>`;
  if (mv(c, m) === 'D') {
    const any = Object.values(r)[0], memo = Object.values(r).find((x) => x.pass_fail === 'X')?.memo;
    return `<div class="pm-row"><span class="pm-big">${m}월 <span class="pm-v ${s}">${s === 'D' ? '완료(점검 기록 없음)' : LBL[s]}</span></span>${any ? `<span class="pm-mu">확정 · ${esc(pick(any.inspector, '-'))} · ${esc(pick(any.inspect_date, '-'))}</span>` : ''}${memo ? `<span>사유: ${esc(memo)}</span>` : ''}
      <span class="pm-right"><button class="btn btn-secondary btn-sm" data-act="go-led">기록지 보기</button><button class="btn btn-danger btn-sm" data-act="unlock">${S.unlockAsk ? '확정을 취소할까요? 한 번 더 누르세요' : '확정 취소'}</button></span></div>`;
  }
  if (!editable(c, m)) return `<div class="pm-row"><span class="pm-big">${m}월</span><span class="pm-mu">예정 ${dayOf(c, m) ? `${m}/${dayOf(c, m)}` : '(날짜 미정)'} · 그 달이 되면 입력할 수 있습니다.</span></div>`;
  const done = its.filter((it) => r[num(it.id)]).length, hasX = its.some((it) => r[num(it.id)]?.pass_fail === 'X');
  const memo = S.memo[`${c}|${m}`] ?? (Object.values(r).find((x) => x.pass_fail === 'X')?.memo || '');
  const ready = its.length > 0 && done === its.length && (!hasX || memo.trim());
  let insp = '';
  try { insp = localStorage.getItem('pm_inspector') || ''; } catch { /* 저장소 없음 */ }
  return `<div class="pm-row"><span class="pm-big">${m}월${s === 'L' ? ' <span class="pm-v N">지연</span>' : ''}</span>
      <span class="pm-prog" aria-hidden="true"><i style="width:${its.length ? done / its.length * 100 : 0}%"></i></span><span class="pm-mu">${done}/${its.length} 입력</span>
      ${its.length && done === its.length ? pill(hasX ? 'N' : 'G').replace('</span>', ' 예상</span>') : ''}
      <span class="pm-right"><label class="pm-mu" for="pm-inspector">점검자</label><input class="form-control pm-sm" id="pm-inspector" value="${esc(insp)}" style="width:90px">
      <button class="btn btn-secondary btn-sm" data-act="all-ok">빈 칸 모두 O</button>
      <button class="btn btn-primary btn-sm" id="pm-confirm" data-act="confirm" ${ready ? '' : 'disabled'}>${m}월 결과 확정</button></span></div>
    ${its.length ? '' : '<p class="pm-mu">점검 항목이 없습니다. 아래에서 항목을 추가하거나 다른 설비 항목을 가져오세요.</p>'}
    ${hasX ? `<div><label class="pm-mu pm-small" for="pm-memo">부적합 사유·조치 (필수, 200자)</label><textarea class="form-control" id="pm-memo" maxlength="200" placeholder="예: 압입 시 이상음 → 가이드 부시 교체, 재점검 정상">${esc(memo)}</textarea></div>` : ''}`;
}

// ---------- 기록 대장 ----------
function ledHTML() {
  const list = state.equipment.filter((e) => inLine(e) && (num(e.pm_yn) === 1 || MS.some((m) => mv(codeOf(e), m))));
  let plan = 0, done = 0, ng = 0, late = 0;
  list.forEach((e) => MS.forEach((m) => { const s = status(codeOf(e), m); if (!s || !(past(m) || (S.year === CUR_Y && m === CUR_M))) return; plan++; if (['G', 'N', 'D'].includes(s)) done++; if (s === 'N') ng++; if (s === 'L') late++; }));
  const upto = S.year === CUR_Y ? `${CUR_M}월까지` : S.year < CUR_Y ? '연간' : '-';
  const kpi = [[`계획 (${upto})`, plan], ['실시(확정)', done], ['실시율', plan ? `${Math.round(done / plan * 100)}%` : '-'], ['부적합', ng, 1], ['지연', late, 1]]
    .map(([l, v, b]) => `<div class="pm-kpi${b && v ? ' bad' : ''}"><div class="l">${l}</div><div class="v">${v}</div></div>`).join('');
  const rows = list.map((e) => {
    const c = codeOf(e), p = MS.filter((m) => status(c, m) && (past(m) || (S.year === CUR_Y && m === CUR_M))).length, d = MS.filter((m) => ['G', 'N', 'D'].includes(status(c, m))).length;
    return `<tr><td><b>${esc(c)}</b> <span class="pm-mu pm-small">${esc(pick(e.equip_name, ''))}</span></td><td class="pm-mu">${esc(pick(e.location, ''))}</td>${MS.map((m) => { const s = status(c, m); return `<td class="m${S.year === CUR_Y && m === CUR_M ? ' now' : ''}">${s ? `<button class="pm-lc ${s}${S.led.c === c && S.led.m === m ? ' sel' : ''}" data-lc="${esc(c)}" data-lm="${m}" aria-label="${esc(c)} ${m}월 ${LBL[s]}">${SYM[s]}</button>` : ''}</td>`; }).join('')}<td class="pm-mu">${d}/${p}</td></tr>`;
  }).join('');
  return `<div class="pm-tool"><select class="form-control pm-sm" data-act="line" aria-label="라인">${lineOptions()}</select><button class="btn btn-secondary btn-sm" data-act="csv">엑셀(CSV) 저장</button><span class="pm-mu pm-small">○ 적합 · ✕ 부적합 · 지연 · 예정 · 완료(예전 방식으로 완료 처리되어 점검 기록 없음) · 칸을 누르면 기록지가 열립니다</span></div>
    <div class="pm-kpis">${kpi}</div>
    <div class="pm-scroll"><table class="pm-mx pm-ledger"><thead><tr><th>설비</th><th>라인</th>${MS.map((m) => `<th class="m${S.year === CUR_Y && m === CUR_M ? ' now' : ''}">${m}월</th>`).join('')}<th>실시</th></tr></thead><tbody>${rows || `<tr><td colspan="15" class="pm-mu">${S.year}년 계획이 없습니다.</td></tr>`}</tbody></table></div>
    ${S.led.c && status(S.led.c, S.led.m) ? `<div class="modal-overlay open" data-docov><div class="modal" role="dialog" aria-modal="true" aria-label="정기점검 기록지"><div class="modal-header"><h2>${esc(S.led.c)} · ${S.year}년 ${S.led.m}월</h2><button type="button" class="modal-close" data-act="doc-close" aria-label="닫기">&times;</button></div><div class="modal-body"><div class="pm-doc">${docHTML()}</div></div></div></div>` : ''}`;
}
function docHTML() {
  const { c, m } = S.led, s = c ? status(c, m) : '';
  const e = eqOf(c), r = res(c, m);
  if (mv(c, m) !== 'D') return `<h4>정기점검 기록지</h4><p>${esc(c)} ${esc(pick(e.equip_name, ''))} · ${S.year}년 ${m}월은 <b class="pm-v ${s}">${LBL[s]}</b> 상태라 아직 확정된 기록이 없습니다.</p><button class="btn btn-primary btn-sm" data-act="open-sheet">점검표에서 입력하기</button>`;
  const items = itemsOf(c), rows = Object.values(r), first = rows[0] || {}, memo = rows.find((x) => x.pass_fail === 'X')?.memo;
  const name = (id) => items.find((it) => num(it.id) === num(id)) || {};
  return `<h4>정기점검 기록지</h4>
    <div class="pm-dochd"><div><b>설비코드</b>${esc(c)}</div><div><b>설비명</b>${esc(pick(e.equip_name, ''))}</div><div><b>라인 / 등급</b>${esc(pick(e.location, '-'))} / ${esc(gradeOf(e) || '-')}</div><div><b>점검월</b>${cm(m)}</div>
      <div><b>점검일</b>${esc(pick(first.inspect_date, '-'))}</div><div><b>점검자</b>${esc(pick(first.inspector, '-'))}</div><div><b>판정</b><span class="pm-v ${s}">${s === 'D' ? '완료(기록 없음)' : LBL[s]}</span></div><div><b>항목 수</b>${rows.length}</div></div>
    ${rows.length ? `<table><thead><tr><th>No.</th><th>부위</th><th>점검 항목</th><th>기준</th><th>결과</th><th>판정</th></tr></thead><tbody>${rows.map((x, i) => { const it = name(x.pm_master_id); return `<tr><td>${i + 1}</td><td>${esc(pick(it.part_name, '-'))}</td><td>${esc(pick(it.item_name, x.item_name, ''))}</td><td>${esc(pick(it.criteria, ''))}</td><td>${esc(x.pass_fail || '')}</td><td class="pm-v ${x.pass_fail === 'X' ? 'N' : 'G'}">${x.pass_fail === 'X' ? '불합격' : '합격'}</td></tr>`; }).join('')}</tbody></table>` : '<p class="pm-mu">예전 방식으로 완료 처리되어 항목별 결과가 없습니다.</p>'}
    ${memo ? `<p class="pm-small"><b>부적합 사유·조치:</b> ${esc(memo)}</p>` : ''}
    <div class="pm-docfoot"><button class="btn btn-secondary btn-sm" data-act="open-sheet">점검표에서 열기</button><div class="pm-sign"><div>점검자<span>${esc(pick(first.inspector, ''))}</span></div><div>확인<span></span></div><div>승인<span></span></div></div></div>`;
}
function downloadCSV() {
  const list = state.equipment.filter((e) => num(e.pm_yn) === 1 || MS.some((m) => mv(codeOf(e), m)));
  const lines = [['설비코드', '설비명', '라인', '등급', ...MS.map((m) => `${m}월`)].join(',')];
  list.forEach((e) => { const c = codeOf(e); lines.push([c, pick(e.equip_name, ''), pick(e.location, ''), gradeOf(e), ...MS.map((m) => LBL[status(c, m)] || '')].map((v) => `"${String(v).replace(/"/g, '""')}"`).join(',')); });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' }));
  a.download = `정기점검_기록대장_${S.year}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// ---------- 이벤트 ----------
function openSheet(c, m) { S.sel = { c, m }; S.delAsk = null; S.unlockAsk = false; S.msg = ''; S.tab = 'sheet'; render(); }
async function onClick(e) {
  if (e.target.hasAttribute?.('data-docov')) { S.led = { c: '', m: 0 }; return render(); } // 기록지 모달 바깥 클릭
  const b = e.target.closest('button, [data-pick], [data-day]');
  if (!b) return;
  const d = b.dataset, c = S.sel.c, m = S.sel.m;
  // 달력
  if (d.act === 'cal-prev') { S.calM = Math.max(1, S.calM - 1); S.picked = null; return render(); }
  if (d.act === 'cal-next') { S.calM = Math.min(12, S.calM + 1); S.picked = null; return render(); }
  if (d.act === 'cal-today') { S.calM = S.year === CUR_Y ? CUR_M : 1; return render(); }
  if (d.pick) { S.picked = S.picked === d.pick ? null : d.pick; return render(); }
  const dayEl = e.target.closest('[data-day]');
  if (S.picked && dayEl) return placeDay(S.picked, num(dayEl.dataset.day));
  if (d.open) return openSheet(d.open, S.calM);
  // 계획 수립
  if (d.act === 'pv-fill') return makePending('fill').catch((err) => showToast(err.message, 'error'));
  if (d.act === 'pv-copy') return makePending('copy').catch((err) => showToast(err.message, 'error'));
  if (d.act === 'pv-dist') return makePending('dist');
  if (d.act === 'pv-cancel') { S.pending = null; return render(); }
  if (d.act === 'pv-apply') return run(applyPending);
  if (d.act === 'new-year') { S.year = Math.max(S.year, CUR_Y) + 1; S.pending = null; S.msg = `${S.year}년 계획입니다. "작년 계획 복사"나 "등급대로 채우기"로 채우세요.`; return loadPM(); }
  // 점검표
  if (d.sel) { S.sel = { c: d.sel, m }; S.delAsk = null; S.unlockAsk = false; S.msg = ''; return render(); }
  if (d.selm) { S.sel.m = num(d.selm); S.unlockAsk = false; return render(); }
  if (d.plan) {
    const pm = num(d.plan);
    S.sel.m = pm;
    if (mv(c, pm) && (mv(c, pm) === 'D' || hasWork(c, pm))) return render();
    return run(async () => { setMonth(c, pm, mv(c, pm) ? '0' : 'P', ''); await savePlan(c); });
  }
  if (d.ox) {
    const it = itemsOf(c).find((x) => num(x.id) === num(d.ox)), om = num(d.m), cur = res(c, om)[it.id]?.pass_fail;
    S.sel.m = om;
    return run(async () => { if (cur === 'X') await clearResult(c, om, it); else await submitResult(c, om, it, cur === 'O' ? 'X' : 'O'); });
  }
  if (d.del) {
    const id = num(d.del);
    if (S.delAsk !== id) { S.delAsk = id; return render(); }
    S.delAsk = null;
    return run(async () => { await api('pm/master/delete', { method: 'POST', body: JSON.stringify({ id }) }); await Promise.all([reloadItems(), reloadResults()]); });
  }
  if (d.act === 'item-add') {
    const name = $('pm-n-name').value.trim();
    if (!name) { $('pm-n-name').focus(); return; }
    const order = Math.max(0, ...itemsOf(c).map((x) => num(x.sort_order))) + 1;
    return run(async () => { await api('pm/master/create', { method: 'POST', body: JSON.stringify({ equip_code: c, part_name: $('pm-n-part').value.trim(), item_name: name, criteria: $('pm-n-crit').value.trim(), input_type: 'PASS_FAIL', sort_order: order }) }); await reloadItems(); });
  }
  if (d.act === 'item-copy') {
    const from = $('pm-copyfrom').value;
    if (!from) return;
    const have = new Set(itemsOf(c).map((x) => x.item_name));
    const add = itemsOf(from).filter((x) => !have.has(x.item_name));
    let order = Math.max(0, ...itemsOf(c).map((x) => num(x.sort_order)));
    return run(async () => {
      for (const x of add) await api('pm/master/create', { method: 'POST', body: JSON.stringify({ equip_code: c, part_name: x.part_name, item_name: x.item_name, criteria: x.criteria, input_type: x.input_type || 'PASS_FAIL', sort_order: ++order, criteria_photo: x.criteria_photo || '' }) });
      await reloadItems(); S.msg = `${from}에서 항목 ${add.length}개를 가져왔습니다.`;
    });
  }
  if (d.act === 'all-ok') return run(async () => { for (const it of itemsOf(c)) if (!res(c, m)[num(it.id)]) await submitResult(c, m, it, 'O'); });
  if (d.act === 'confirm') {
    const insp = $('pm-inspector').value.trim();
    if (!insp) { showToast('점검자를 입력하세요.', 'warn'); $('pm-inspector').focus(); return; }
    try { localStorage.setItem('pm_inspector', insp); } catch { /* 저장소 없음 */ }
    const memo = (S.memo[`${c}|${m}`] ?? $('pm-memo')?.value ?? '').trim();
    return run(async () => {
      await Promise.all(itemsOf(c).map((it) => { const pf = res(c, m)[num(it.id)].pass_fail; return submitResult(c, m, it, pf, pf === 'X' ? memo : ''); }));
      setMonth(c, m, 'D', S.plans[c]?.[`m${m}_date`] || todayStr());
      await savePlan(c);
      delete S.memo[`${c}|${m}`]; S.led = { c, m };
      showToast(`${c} ${m}월 확정: ${LBL[status(c, m)]}`);
    });
  }
  if (d.act === 'unlock') {
    if (!S.unlockAsk) { S.unlockAsk = true; return render(); }
    S.unlockAsk = false;
    return run(async () => { setMonth(c, m, 'P'); await savePlan(c); });
  }
  if (d.act === 'go-led') { S.led = { c, m }; S.tab = 'led'; return render(); }
  // 기록 대장
  if (d.lc) { S.led = { c: d.lc, m: num(d.lm) }; return render(); }
  if (d.act === 'doc-close') { S.led = { c: '', m: 0 }; return render(); }
  if (d.act === 'open-sheet') { const { c: lc, m: lm } = S.led; S.led = { c: '', m: 0 }; return openSheet(lc, lm); }
  if (d.act === 'csv') return downloadCSV();
}
async function onChange(e) {
  const t = e.target;
  if (t.dataset.act === 'line') { S.line = t.value; return render(); }
  if (t.dataset.tg) {
    const c = t.dataset.tg, on = t.checked;
    return run(async () => {
      const n = await setTarget(c, on);
      S.msg = on ? `${c}를 정기점검 대상으로 지정했습니다. "등급대로 채우기"로 계획을 만드세요.` : `${c}를 대상에서 뺐습니다. 남은 예정 ${n}건을 지웠고, 지난 기록은 그대로 둡니다.`;
      S.pending = null;
    });
  }
  if (t.id === 'pm-inspector') { try { localStorage.setItem('pm_inspector', t.value.trim()); } catch { /* 저장소 없음 */ } }
}
function onInput(e) {
  const t = e.target;
  if (t.id === 'pm-q') { S.q = t.value; return renderSheetList(); }
  if (t.id === 'pm-memo') {
    const c = S.sel.c, m = S.sel.m, its = itemsOf(c), r = res(c, m);
    S.memo[`${c}|${m}`] = t.value;
    const btn = $('pm-confirm');
    if (btn) btn.disabled = !(its.length && its.every((it) => r[num(it.id)]) && t.value.trim());
  }
}
let bound = false;
export function initPM() {
  if (bound) return;
  bound = true;
  const page = $('page-pm-plan');
  page.querySelectorAll('[data-pmtab]').forEach((b) => b.addEventListener('click', () => { S.tab = b.dataset.pmtab; S.msg = ''; S.pending = null; S.led = { c: '', m: 0 }; render(); }));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && $('pm-body').querySelector('[data-docov]')) { S.led = { c: '', m: 0 }; render(); } });
  $('pm-year-sel').addEventListener('change', (e) => { S.year = num(e.target.value); S.calM = S.year === CUR_Y ? CUR_M : 1; S.pending = null; S.msg = ''; S.led = { c: '', m: 0 }; loadPM(); });
  const body = $('pm-body');
  body.addEventListener('click', onClick);
  body.addEventListener('change', onChange);
  body.addEventListener('input', onInput);
  body.addEventListener('keydown', (e) => { if ((e.key === 'Enter' || e.key === ' ') && e.target.dataset?.pick) { e.preventDefault(); e.target.click(); } });
  body.addEventListener('dragstart', (e) => { const t = e.target.closest('[data-drag]'); if (t) { e.dataTransfer.setData('text/plain', t.dataset.drag); e.dataTransfer.effectAllowed = 'move'; } });
  body.addEventListener('dragover', (e) => { const d = e.target.closest('[data-day]'); if (d) { e.preventDefault(); d.classList.add('drop'); } });
  body.addEventListener('dragleave', (e) => { e.target.closest('[data-day]')?.classList.remove('drop'); });
  body.addEventListener('drop', (e) => { const d = e.target.closest('[data-day]'); if (!d) return; e.preventDefault(); placeDay(e.dataTransfer.getData('text/plain'), num(d.dataset.day)); });
}
