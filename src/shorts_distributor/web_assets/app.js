"use strict";
const $ = (id) => document.getElementById(id);
const token = document.querySelector('meta[name="app-token"]').content;
const names = {instagram:"Instagram",threads:"Threads",tiktok:"TikTok",linkedin:"LinkedIn",facebook:"Facebook",naver:"Naver Clip"};
const symbols = {instagram:"◎",threads:"@",tiktok:"♪",linkedin:"in",facebook:"f",naver:"N"};
const fields = {
  instagram:[["INSTAGRAM_HANDLE","Instagram 핸들"]], threads:[["THREADS_HANDLE","Threads 핸들 (생략 시 Instagram 계정)"]],
  tiktok:[["TIKTOK_HANDLE","TikTok 핸들 (선택)"]], linkedin:[["LINKEDIN_RECENT_ACTIVITY_URL","최근 활동 검증 URL"]],
  facebook:[["FACEBOOK_VIDEOS_URL","영상 목록 검증 URL"],["FACEBOOK_PAGE_NAME","페이지 이름 (페이지 계정)"]],
  naver:[["NAVER_CHANNEL_SLUG","채널 슬러그"],["NAVER_CLIP_URL","Clip 목록 URL (선택)"],["NAVER_CATEGORY_1","카테고리 1"],["NAVER_CATEGORY_2","카테고리 2"]]
};
const actionNames = {doctor:"환경 점검",discover:"채널 영상 조회",preview:"미리보기 준비",login:"계정 로그인",publish:"영상 배포",verify:"게시 검증"};
const statusNames = {running:"진행 중",stopping:"중단 중",succeeded:"완료",attention:"확인 필요",failed:"실패",cancelled:"중단됨",interrupted:"실행 중단",planned:"준비됨",already:"기록 있음",verified:"검증 완료",published:"게시됨", "pending-verify":"검증 대기", "skipped-policy":"정책상 제외", "skipped-ad":"광고 제외",blocked:"연결 필요","agent-required":"수동 확인",missing:"누락",inconclusive:"확인 불충분"};
let config = {}, enabled = [], selectedPlatforms = [], selectedVideos = new Set(), candidates = [];
let allowPublish = false, currentJob = null, previewJob = null, renderedResult = "", working = false, pollBusy = false;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function notify(message, error = false) {
  $("notice").hidden = false;
  $("notice").textContent = message;
  $("notice").className = "notice" + (error ? " error" : "");
}
async function api(path, body) {
  const options = {headers:{"X-App-Token":token}};
  if (body !== undefined) {options.method = "POST"; options.headers["Content-Type"] = "application/json"; options.body = JSON.stringify(body);}
  const response = await fetch(path, options);
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || "요청에 실패했습니다.");
  return value;
}
function navigate(view) {
  for (const node of document.querySelectorAll(".view")) node.hidden = node.id !== "view-" + view;
  for (const node of document.querySelectorAll(".nav")) node.classList.toggle("active", node.dataset.view === view);
  $("page-label").textContent = {distribute:"배포 작업",settings:"계정 및 설정",history:"작업 기록",guide:"사용 가이드"}[view];
  if (view === "history") refreshHistory().catch(error => notify(error.message, true));
}
function counts() {
  $("selected-count").replaceChildren(document.createTextNode(selectedVideos.size),element("small","편"));
  $("target-count").replaceChildren(document.createTextNode(selectedPlatforms.length),element("small","곳"));
  $("cell-count").replaceChildren(document.createTextNode(selectedVideos.size * selectedPlatforms.length),element("small","개"));
  $("preview-button").disabled = working || !selectedVideos.size || !selectedPlatforms.length;
  $("discover").disabled = working || !config.YOUTUBE_HANDLE || !enabled.length;
  $("doctor").disabled = working;
  $("verify").disabled = working;
  $("publish-button").disabled = working || !allowPublish || !previewJob?.preview_ready;
  for (const btn of document.querySelectorAll("[data-login]")) btn.disabled = working;
  $("settings-form").querySelector('button[type="submit"]').disabled = working;
  $("apply-ids").disabled = working;
}
function clearPreview() {
  previewJob = null;
  $("preview-label").textContent = "다시 준비";
  $("preview").replaceChildren(element("div","선택이나 설정이 변경됐습니다. 미리보기를 다시 만드세요.","compact-empty"));
  counts();
}
function renderTargets() {
  $("targets").replaceChildren();
  if (!enabled.length) $("targets").append(element("p","계정 및 설정에서 플랫폼을 선택하세요.","subtle"));
  for (const id of enabled) {
    const label = element("label",undefined,"target" + (selectedPlatforms.includes(id) ? " selected" : ""));
    const text = element("span",names[id],"platform-name"); text.append(element("small","배포 대상"));
    const checkbox = element("input"); checkbox.type = "checkbox"; checkbox.checked = selectedPlatforms.includes(id);
    checkbox.disabled = working;
    checkbox.addEventListener("change",()=>{
      selectedPlatforms = checkbox.checked ? enabled.filter(p => p === id || selectedPlatforms.includes(p)) : selectedPlatforms.filter(p => p !== id);
      clearPreview(); renderTargets();
    });
    label.append(element("span",symbols[id],"platform-icon"),text,checkbox); $("targets").append(label);
  }
}
function renderSettings() {
  for (const [key,value] of Object.entries(config)) {
    const input = $("settings-form").elements.namedItem(key); if (input) input.value = value;
  }
  $("account-fields").replaceChildren();
  for (const [id,title] of Object.entries(names)) {
    const card = element("div",undefined,"account");
    const top = element("div",undefined,"account-top");
    const check = element("input");check.type="checkbox";check.name="target";check.value=id;check.checked=enabled.includes(id);
    const label = element("label");label.append(check,document.createTextNode(title));
    top.append(element("span",symbols[id],"platform-icon"),label);card.append(top);
    for (const [key,title] of fields[id]) {
      const label = element("label",title);const input = element("input");input.name=key;input.value=config[key] || "";label.append(input);card.append(label);
    }
    const button = element("button","로그인 연결 ↗","button secondary small");button.type="button";button.dataset.login=id;
    button.addEventListener("click",()=>startJob({action:"login",platform:id}));card.append(button);$("account-fields").append(card);
  }
  $("source-caption").textContent = config.YOUTUBE_HANDLE ? "소스 · " + config.YOUTUBE_HANDLE : "계정 및 설정에서 YouTube 채널을 먼저 저장하세요.";
}
function renderVideos() {
  if (!candidates.length) return;
  $("videos").replaceChildren();
  candidates.forEach((item,index)=>{
    const label = element("label",undefined,"video-row");const check=element("input");check.type="checkbox";check.checked=selectedVideos.has(item.youtube_id);check.disabled=working;
    check.addEventListener("change",()=>{if(check.checked)selectedVideos.add(item.youtube_id);else selectedVideos.delete(item.youtube_id);clearPreview();counts();});
    const info=element("div",undefined,"video-info"); info.append(element("strong",item.title||item.youtube_id),element("span",item.youtube_id+" · "+(item.missing_platforms||[]).map(p=>names[p]||p).join(", ")));
    label.append(check,element("div",String(index+1).padStart(2,"0"),"video-art"),info);$("videos").append(label);
  });
}
function renderPreview(job) {
  const report=job.result;$("preview").replaceChildren();previewJob=job;
  $("preview-label").textContent=job.preview_ready?"검토 가능":statusNames[job.status]||job.status;
  if (!report || !report.batch_oldest_first?.length) {
    $("preview").append(element("p",report?.error || "준비된 영상이 없습니다. 실행 로그와 셀 결과를 확인하세요.","subtle"));
  }
  for (const [index,item] of (report?.batch_oldest_first||[]).entries()) {
    const card=element("article",undefined,"preview-video");card.append(element("div",`${String(index+1).padStart(2,"0")} · ${item.upload_date||"날짜 없음"} · ${item.codec}`,"meta"),element("h3",item.title));
    card.append(element("div",item.post_text,"post-text"));
    if (item.policy_names?.length) card.append(element("p","콘텐츠 정책 · "+item.policy_names.join(", "),"subtle"));
    const cells=element("div",undefined,"cells");
    for(const cell of report.cells.filter(c=>c.youtube_id===item.youtube_id)){
      const chip=element("span",`${names[cell.platform]||cell.platform} · ${statusNames[cell.status]||cell.status}`,"cell"+(["failed","blocked"].includes(cell.status)?" error":""));chip.title=cell.hint||cell.error||"";cells.append(chip);
    }
    card.append(cells);$("preview").append(card);
  }
  for (const cell of (report?.cells||[]).filter(c=>c.status==="failed")) $("preview").append(element("p",`${names[cell.platform]} ${cell.youtube_id}: ${cell.error||cell.hint}`,"subtle"));
  if (report?.preview_note) $("preview").append(element("p",report.preview_note,"subtle"));
  counts();
}
function renderDoctor(report) {
  $("doctor-result").replaceChildren();if(!report?.tools)return;
  const tools=Object.entries(report.tools).map(([key,ok])=>`${key} ${ok?"✓":"미설치"}`).join(" · ");
  $("doctor-result").append(element("div",tools,"doctor-row"));
  if(report.env&&!report.env.YOUTUBE_HANDLE)$("doctor-result").append(element("div","YouTube 채널 설정이 필요합니다.","doctor-row"));
  for (const item of report.platforms) {
    const row=element("div",`${names[item.platform]||item.platform} · ${item.session==="ok"?"연결 확인":item.session==="profile-missing"?"로그인 필요":item.session}`,"doctor-row");
    if(item.missing_env.length)row.append(element("span"," / 설정 필요: "+item.missing_env.join(", ")));$("doctor-result").append(row);
  }
}
function renderJob(job) {
  currentJob=job;working=["running","stopping"].includes(job.status);
  $("job-status").textContent=statusNames[job.status]||job.status;
  $("job-message").textContent=(actionNames[job.action]||job.action)+" · "+(job.message||statusNames[job.status]||job.status);
  $("job-log").textContent=job.log||"작업을 준비하고 있습니다…";
  $("cancel-job").hidden=!working;$("cancel-job").disabled=job.status==="stopping";
  $("login-complete").hidden=!(working&&job.action==="login");
  const resultKey=job.id+":"+job.status;
  if(!working&&renderedResult!==resultKey){
    renderedResult=resultKey;
    if(job.action==="doctor")renderDoctor(job.result);
    if(job.action==="discover"&&job.result?.selected_newest_first){
      candidates=job.result.selected_newest_first;selectedVideos=new Set(candidates.slice(0,Number(config.SHORTS_UPLOAD_LIMIT)||2).map(v=>v.youtube_id));renderVideos();
      if(!candidates.length){$("videos").replaceChildren(element("div","조회 범위에 새로운 배포 후보가 없습니다. 광고 제외 설정이나 영상 ID를 확인하세요.","compact-empty"));}
      if(job.result.ad_skipped?.length)notify(`광고 의심 영상 ${job.result.ad_skipped.length}편을 목록에서 제외했습니다.`);
    }
    if(job.action==="preview")renderPreview(job);
    if(job.action==="publish"){
      previewJob=null;$("publish-button").disabled=true;renderPreview({...job,preview_ready:false});
    }
    if(job.status==="failed")notify(job.result?.error||job.message||"작업에 실패했습니다. 실행 로그를 확인하세요.",true);
    if(job.action==="verify"&&Array.isArray(job.result))notify(job.result.length?job.result.map(r=>`${names[r.platform]} ${r.youtube_id} · ${statusNames[r.verify_status]||r.verify_status}`).join("\n"):"검증 대기 항목이 없습니다.");
  }
  counts();renderTargets();renderVideos();
}
async function startJob(payload) {
  if(working){notify("진행 중인 작업을 먼저 완료하세요.",true);return;}
  try {
    working=true;counts();
    const job=await api("/api/jobs",payload);renderedResult="";renderJob(job);
    if(payload.action==="login")notify("Chrome에서 로그인한 다음, 이 화면의 ‘로그인 완료’를 누르세요.");
    else notify((actionNames[payload.action]||payload.action)+" 작업을 시작했습니다.");
    navigate("distribute");
  }catch(error){working=false;counts();notify(error.message,true);}
}
async function refreshHistory() {
  const [jobs,history]=await Promise.all([api("/api/jobs"),api("/api/history")]);
  $("job-history").replaceChildren();
  if(!jobs.length)$("job-history").append(element("div","아직 실행한 작업이 없습니다.","compact-empty"));
  for(const job of jobs){
    const row=element("div",undefined,"history-row");const info=element("div");info.append(element("strong",actionNames[job.action]||job.action),element("small",new Date(job.created_at).toLocaleString("ko-KR")));
    const button=element("button","결과 보기 ↗","button secondary small");button.addEventListener("click",async()=>{try{renderedResult="";renderJob(await api("/api/jobs/"+job.id));navigate("distribute");}catch(e){notify(e.message,true);}});
    row.append(info,element("span",statusNames[job.status]||job.status,"badge muted"),button);$("job-history").append(row);
  }
  $("upload-history").replaceChildren();
  if(!history.length){$("upload-history").append(element("div","게시 기록이 아직 없습니다.","compact-empty"));return;}
  const table=element("table"),thead=element("thead"),head=element("tr");["영상 ID","플랫폼","검증","게시 시각","게시물"].forEach(t=>head.append(element("th",t)));thead.append(head);table.append(thead);const tbody=element("tbody");
  for(const item of history){const row=element("tr");row.append(element("td",item.youtube_id),element("td",names[item.platform]||item.platform),element("td",item.verified_at?"검증 완료":"검증 대기"),element("td",new Date(item.uploaded_at).toLocaleString("ko-KR")));const linkCell=element("td");if(item.platform_url&&/^https:\/\//.test(item.platform_url)){const link=element("a","게시물 열기 ↗");link.href=item.platform_url;link.target="_blank";link.rel="noopener noreferrer";linkCell.append(link);}else linkCell.textContent="URL 대기";row.append(linkCell);tbody.append(row);}
  table.append(tbody);$("upload-history").append(table);
}
async function poll() {
  if(pollBusy)return;pollBusy=true;
  try{if(currentJob&&["running","stopping"].includes(currentJob.status))renderJob(await api("/api/jobs/"+currentJob.id));}
  catch(error){notify("진행 상태 연결 오류: "+error.message,true);}finally{pollBusy=false;}
}
async function initialize() {
  try{
    const settings=await api("/api/settings");config=settings.values;allowPublish=settings.allow_publish;enabled=config.TARGET_PLATFORMS.split(",").filter(p=>names[p]);selectedPlatforms=[...enabled];renderSettings();renderTargets();counts();
    $("mode").textContent=allowPublish?"게시 모드":"준비 모드";
    $("publish-help").textContent=allowPublish?"미리보기 검토 후 실제 배포를 시작합니다.":"준비 모드 · 미리보기까지 사용할 수 있습니다.";
    const jobs=await api("/api/jobs");const active=jobs.find(j=>["running","stopping"].includes(j.status));if(active)renderJob(await api("/api/jobs/"+active.id));
  }catch(error){notify(error.message,true);}
}
document.querySelectorAll("[data-view]").forEach(button=>button.addEventListener("click",()=>navigate(button.dataset.view)));
$("settings-form").addEventListener("submit",async(event)=>{
  event.preventDefault();try{const form=new FormData(event.currentTarget),payload={};for(const key of Object.keys(config))if(key!=="TARGET_PLATFORMS"&&form.has(key))payload[key]=String(form.get(key));payload.TARGET_PLATFORMS=form.getAll("target").join(",");const result=await api("/api/settings",payload);config=result.values;enabled=config.TARGET_PLATFORMS.split(",").filter(p=>names[p]);selectedPlatforms=[...enabled];selectedVideos.clear();candidates=[];$("videos").replaceChildren(element("div","설정을 저장했습니다. 채널 영상을 불러오세요.","compact-empty"));clearPreview();renderTargets();renderSettings();$("save-state").textContent="저장됨 · "+new Date().toLocaleTimeString("ko-KR");notify("설정을 저장했습니다.");}catch(error){notify(error.message,true);}
});
$("apply-ids").addEventListener("click",()=>{const ids=$("video-ids").value.split(/[\s,]+/).filter(Boolean);if(!ids.length||ids.length>20||ids.some(id=>!/^[A-Za-z0-9_-]{11}$/.test(id))){notify("11자리 영상 ID를 1~20개 입력하세요.",true);return;}selectedVideos=new Set(ids);candidates=[...selectedVideos].map(id=>({youtube_id:id,title:"직접 선택 · "+id,missing_platforms:selectedPlatforms}));clearPreview();renderVideos();counts();});
$("doctor").addEventListener("click",()=>startJob({action:"doctor"}));
$("discover").addEventListener("click",()=>{clearPreview();startJob({action:"discover"});});
$("preview-button").addEventListener("click",()=>{clearPreview();startJob({action:"preview",video_ids:[...selectedVideos],platforms:selectedPlatforms});});
$("verify").addEventListener("click",()=>startJob({action:"verify"}));
$("refresh-history").addEventListener("click",()=>refreshHistory().catch(e=>notify(e.message,true)));
$("login-complete").addEventListener("click",async()=>{try{await api("/api/login-complete",{job_id:currentJob.id});notify("로그인 상태를 확인하고 있습니다.");}catch(e){notify(e.message,true);}});
$("cancel-job").addEventListener("click",async()=>{if(!confirm("진행 중인 작업을 중단할까요? 게시 작업이면 플랫폼에서 완료 여부를 확인하세요."))return;try{await api("/api/cancel",{job_id:currentJob.id});await poll();}catch(e){notify(e.message,true);}});
$("publish-button").addEventListener("click",()=>{if(!previewJob?.preview_ready)return;$("publish-summary").textContent=`영상 ${previewJob.result.batch_oldest_first.length}편 · ${previewJob.result.target_platforms.map(p=>names[p]).join(", ")}`;$("review-confirm").checked=false;$("publish-confirm").value="";$("publish-dialog").showModal();});
$("confirm-publish").addEventListener("click",()=>{if(!$("review-confirm").checked||$("publish-confirm").value!=="게시"){notify("검토 체크와 확인 문구 ‘게시’를 입력하세요.",true);return;}const id=previewJob.id;$("publish-dialog").close();startJob({action:"publish",preview_id:id,confirm:"게시"});});
initialize();setInterval(poll,1200);
