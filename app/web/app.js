'use strict';
const $=id=>document.getElementById(id);
let state=null, csrf='', online=false, pending=false, formLoaded=false, scheduleLoaded=false, toastTimer;
const labels={disabled:'Disabled',ended:'Ended',waiting:'Waiting',new:'Waiting',preparing:'Preparing',prepared:'Prepared',starting:'Starting',live:'Start confirmed',done:'Start confirmed',missed:'Skipped',needs_review:'Needs review',patrol_sending:'Patrol starting'};
const fields=[['workspace_name','Workspace name'],['youtube_channel_id','YouTube channel ID (UC…)'],['youtube_stream_title','Existing YouTube stream key name (not the secret key)'],['facebook_page_id','Facebook Page ID'],['camera_channel','ISAPI camera channel'],['obs_exe','OBS executable'],['obs_port','OBS WebSocket port'],['obs_password','OBS WebSocket password','password'],['obs_profile','OBS profile'],['obs_collection','Scene collection'],['obs_scene','Program scene'],['fb_target','Facebook output target'],['google_client_file','Google Desktop OAuth JSON path'],['facebook_page_token','Facebook Page access token','password'],['graph_version','Meta Graph API version'],['camera_url','Camera base address'],['camera_user','Camera username'],['camera_password','Camera password','password']];
function el(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;}
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,6500);}
async function api(path,data){const options={cache:'no-store',signal:AbortSignal.timeout(15000)};if(data!==undefined){options.method='POST';options.headers={'Content-Type':'application/json','X-CSRF-Token':csrf};options.body=JSON.stringify(data);}const res=await fetch(path,options);const out=await res.json();if(!res.ok){if(res.status===401&&path!='/api/login')showLogin();throw new Error(out.error||'Request failed.');}return out;}
function showLogin(){$('app').hidden=true;$('login').hidden=false;online=false;state=null;csrf='';formLoaded=false;scheduleLoaded=false;}
async function pair(code){await api('/api/login',{code});$('pair-code').value='';$('pair-error').textContent='';await refresh();}
$('pair-form').addEventListener('submit',async event=>{event.preventDefault();const b=event.submitter;b.disabled=true;try{await pair($('pair-code').value.trim());}catch(e){$('pair-error').textContent=e.message;}finally{b.disabled=false;}});
const recoveryNav=el('button','nav','Run history & backups');recoveryNav.dataset.view='recovery';document.querySelector('nav').append(recoveryNav);
function navigate(view){if(!['overview','schedule','connections','activity','mobile','updates','visible','recovery','pc'].includes(view))view='overview';document.querySelectorAll('.view').forEach(n=>n.hidden=n.id!=='view-'+view);document.querySelectorAll('[data-view]').forEach(n=>{n.classList.toggle('active',n.dataset.view===view);if(n.dataset.view===view)n.setAttribute('aria-current','page');else n.removeAttribute('aria-current');});$('page-title').textContent={overview:'Live overview',schedule:'Schedule',connections:'Connections',activity:'Activity',mobile:'Mobile access',updates:'App updates',visible:'Visible automation',recovery:'Run history & backups',pc:'PC controls'}[view];history.replaceState(null,'','#'+view);}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>navigate(b.dataset.view));document.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>navigate(b.dataset.go));
function makeSlots(target,full){const parent=$(target);parent.replaceChildren();for(const s of state.slots){const row=el('div','slot'+(s.name===state.next.name?' next':''));const time=el('div','slot-time',s.at);time.append(el('small','','IST'));const name=el('div');name.append(el('div','slot-name',s.name),el('div','slot-dest',full&&s.last_error?s.last_error:(s.end_at?'End '+s.end_at+(s.end_next_day?' +1 day':'')+' · YouTube + Facebook':'Manual end · YouTube + Facebook')));const status=el('span','slot-state'+(s.phase==='needs_review'||s.end_state==='needs_review'?' attention':['live','done'].includes(s.phase)?' confirmed':''),s.end_state==='needs_review'?'End needs review':labels[s.phase]||s.phase);row.append(time,name,status);parent.append(row);}}
function render(){
 $('workspace-name').textContent=state.workspace_name||'Live Desk';
 $('setup-steps').replaceChildren(...(state.setup_steps||[]).map(step=>el('li',step.done?'setup-done':'', (step.done?'✓ ':'○ ')+step.label)));
 $('destinations').textContent='YouTube: '+(state.destinations.youtube_channel_id||'Set channel ID, or retain verified legacy references')+' · Facebook Page: '+(state.destinations.facebook_page_id||'Not configured')+' · Stream key name: '+(state.destinations.youtube_stream_title||'Not configured');
 $('app-version').textContent=state.app_version||'—';$('open-updates').hidden=!state.local;$('updates-help').textContent=state.local?'Pause automation and finish any active live or recording before installing.':'Manage updates from the Windows PC. Your phone will reconnect after the app restarts and may need pairing again.';
 $('login').hidden=true;$('app').hidden=false;$('offline').hidden=true;$('today').textContent=state.date;$('status-message').textContent=state.message;$('status-message').classList.toggle('error',state.error);
 $('link-state').textContent='● PC connected';$('link-state').className='badge good';$('next-name').textContent=state.next.name;$('next-time').textContent=state.next.at;$('arm-badge').textContent=state.armed?'Automation enabled':state.arm_requested&&state.busy?'Waiting for connections':'Automation paused';
 const sameDay=state.next.due?.slice(0,10)===state.now.slice(0,10);$('next-day').textContent=state.next.due?(sameDay?'Today':state.next.due.slice(0,10)):'No date';
 const cards=$('connection-cards');cards.replaceChildren();for(const [key,title,detail,icon] of [['obs','OBS Studio','Program scene on the PC','◉'],['youtube','YouTube',state.destinations.youtube_channel_id||'Check channel in Connections','▶'],['facebook','Facebook',state.destinations.facebook_page_id||'Choose your Page in Connections','f'],['camera','PTZ camera','Channel '+state.destinations.camera_channel+' · Scheduled actions','◈']]){const card=el('article','connection-card'),top=el('div','service-top');top.append(el('span','service-icon '+key,icon),el('span','service-state '+state.connections[key],state.connections[key]==='verified'?'● Verified':state.connections[key]==='skipped'?'○ Not requested':'○ Not checked'));card.append(top,el('div','service-name',title),el('div','service-detail',detail));cards.append(card);}
 $('checked-at').textContent=state.checked?'Last full check: '+new Date(state.checked).toLocaleTimeString('en-GB',{timeZone:'Asia/Kolkata'})+' IST · This is a connection check, not current live status.':'Connection status reflects checks in this app session.';
 makeSlots('schedule-preview',false);makeSlots('schedule-full',true);if(!scheduleLoaded)buildSchedule();$('program-count').textContent=state.schedule.filter(s=>s.enabled).length+' enabled';$('export-diagnostics').hidden=!state.local;
 const logs=$('log-list');const atBottom=logs.scrollHeight-logs.scrollTop-logs.clientHeight<60;logs.replaceChildren();for(const item of state.logs){const row=el('div','log-entry'+(/failed|attention|review|error/i.test(item.message)?' log-error':''));row.append(el('span','log-time',item.time),el('span','',item.message));logs.append(row);}if(atBottom)logs.scrollTop=logs.scrollHeight;
 $('remote-settings').hidden=state.local;$('settings-form').hidden=!state.local;
 if(state.local&&!formLoaded){const grid=$('settings-fields');grid.replaceChildren();for(const [key,label,type] of fields){const wrap=el('div','field'),l=el('label','',label),input=el('input');input.id='field-'+key;input.name=key;input.type=type||'text';input.autocomplete='off';input.value=type==='password'?'':state.settings[key]||'';if(type==='password')input.placeholder='Saved value retained when blank';l.htmlFor=input.id;wrap.append(l,input);grid.append(wrap);}formLoaded=true;}
 const addresses=$('phone-addresses');addresses.replaceChildren();if(!state.local)addresses.textContent='This phone is paired. Controls are available in Overview.';else if(!state.mobile_enabled)addresses.textContent='Wi-Fi mobile access is off. Enable it below on this PC. Internet remote access is separate.';else{addresses.append(el('b','','Phone address'));state.mobile_urls.forEach(url=>{const p=el('p'),a=el('a','',url);a.href=url;p.append(a);addresses.append(p);});if(!state.mobile_urls.length)addresses.append(el('p','','Choose a local network address below.'));}
 renderRemote();renderOperations();renderVisible();renderPC();updateButtons();updateClock();
}
function updateButtons(){updatePCButtons();updateVisibleButtons();const busy=!online||pending;for(const id of ['arm','check','check-settings','retry','save-settings','connect-youtube','save-schedule','reload-schedule'])$(id).disabled=busy||!!state?.busy;$('pause').disabled=busy||!(state?.armed||state?.busy);document.querySelectorAll('#schedule-form input,#schedule-form select,#schedule-form button').forEach(i=>i.disabled=busy||!!state?.busy);document.querySelectorAll('#settings-form input').forEach(i=>i.disabled=busy||!!state?.busy);updateOperationsButtons();}
function updateClock(){if(!state)return;const now=new Date(Date.parse(state.now)+(Date.now()-state.received));$('clock').replaceChildren(document.createTextNode(now.toLocaleTimeString('en-GB',{timeZone:'Asia/Kolkata'})+' '),el('small','','IST'));const diff=Math.max(0,Date.parse(state.next.due)-now.getTime()),mins=Math.floor(diff/60000),h=Math.floor(mins/60),m=mins%60;$('countdown').textContent=!state.next.due?'Add and enable a program with a future date in Schedule.':(state.armed?'Starts in ':'Next program in ')+(h?h+'h ':'')+m+'m'+(state.armed?'':' · enable automation to run this schedule');}
async function refresh(){try{const out=await api('/api/state');state={...out,received:Date.now()};csrf=out.csrf;online=true;render();}catch(e){if(state){online=false;$('offline').hidden=false;$('link-state').textContent='○ PC disconnected';$('link-state').className='badge';updateButtons();}else if(!$('login').hidden){}else showLogin();}}
function confirmAction(title,message){return new Promise(resolve=>{const d=$('confirm-dialog');$('confirm-title').textContent=title;$('confirm-text').textContent=message;const finish=value=>{d.oncancel=null;$('confirm-ok').onclick=null;$('confirm-cancel').onclick=null;d.close();resolve(value);};$('confirm-ok').onclick=()=>finish(true);$('confirm-cancel').onclick=()=>finish(false);d.oncancel=e=>{e.preventDefault();finish(false);};d.showModal();$('confirm-cancel').focus();});}
async function action(name,extra={}){if(!online||pending)return;pending=true;updateButtons();try{await api('/api/action',{action:name,...extra});await refresh();}catch(e){toast(e.message);}finally{pending=false;updateButtons();}}
$('arm').onclick=async()=>{if(await confirmAction('Enable your saved automation plan?','The PC will create broadcasts and start live at your saved times. Any end times will end this app’s YouTube/Facebook broadcasts and associated OBS outputs. Camera actions will run as configured. Check the Schedule tab and OBS scene before confirming.'))action('arm',{confirmed:true});};
$('pause').onclick=()=>action('pause');$('check').onclick=()=>action('check');$('check-settings').onclick=()=>action('check');$('connect-youtube').onclick=()=>action('youtube');
$('retry').onclick=async()=>{if(await confirmAction('Have you checked both platforms?','Only continue after inspecting OBS, YouTube and Facebook for a partial live or duplicate event. This resets the selected program for its scheduled window. It does not immediately start a live.'))action('retry',{slot:$('retry-slot').value,confirmed:true});};
$('settings-form').onsubmit=async e=>{e.preventDefault();if(pending||!online)return;pending=true;updateButtons();try{const data={};for(const [key] of fields)data[key]=$('field-'+key).value;await api('/api/settings',data);fields.filter(f=>f[2]==='password').forEach(([key])=>$('field-'+key).value='');toast('Settings saved.');await refresh();}catch(err){toast(err.message);}finally{pending=false;updateButtons();}};
$('mobile-logout').onclick=$('logout').onclick=async()=>{try{await api('/api/logout',{});showLogin();}catch(e){toast(e.message);}};
$('copy-log').onclick=async()=>{try{const text=state.logs.map(r=>r.time+'  '+r.message).join('\n');if(navigator.clipboard)await navigator.clipboard.writeText(text);else{const t=el('textarea');t.value=text;document.body.append(t);t.select();if(!document.execCommand('copy'))throw new Error();t.remove();}toast('Activity copied.');}catch(e){toast('Select and copy the activity text manually.');}};
function inputField(parent,label,name,type,value){const wrap=el('label','editor-field'),input=el('input');wrap.append(el('span','',label));input.dataset.field=name;input.type=type;if(type==='checkbox')input.checked=!!value;else input.value=value??'';wrap.append(input);parent.append(wrap);return input;}
function selectField(parent,label,name,value,choices){const wrap=el('label','editor-field'),select=el('select');wrap.append(el('span','',label));select.dataset.field=name;for(const [v,t] of choices){const o=el('option','',t);o.value=v;select.append(o);}select.value=value;wrap.append(select);parent.append(wrap);return select;}
function addCameraRow(container,a={kind:'patrol_start',number:8,timing:'after_live',delay_seconds:120,at:'',next_day:false,only_if_live:true}){
 const row=el('div','camera-editor-row');
 const kind=selectField(row,'Camera action','kind',a.kind,[['patrol_start','Start patrol'],['patrol_stop','Stop patrol'],['preset','Go to preset']]);
 const number=inputField(row,'Number','number','number',a.number);number.min=1;number.max=a.kind==='preset'?32:8;
 kind.onchange=()=>{number.max=kind.value==='preset'?32:8;};
 const timing=selectField(row,'When','timing',a.timing,[['after_live','After BOTH go live'],['clock','At a clock time']]);
 const delay=inputField(row,'Delay (seconds)','delay_seconds','number',a.delay_seconds);delay.min=0;delay.max=43200;
 const at=inputField(row,'Clock time (IST)','at','time',a.at);const nd=inputField(row,'Next day','next_day','checkbox',a.next_day);const only=inputField(row,'Only while BOTH live','only_if_live','checkbox',a.only_if_live);
 function timingChanged(){const clock=timing.value==='clock';delay.parentElement.hidden=clock;at.parentElement.hidden=!clock;nd.parentElement.hidden=!clock;only.parentElement.hidden=!clock;}
 timing.onchange=timingChanged;timingChanged();
 const remove=el('button','text-button remove-action','Remove');remove.type='button';remove.onclick=()=>row.remove();row.append(remove);container.append(row);
}
function addProgram(s){
 const editor=$('schedule-editor'),panel=el('article','panel schedule-program');panel.dataset.slot=s.id;
 const title=el('div','section-head');title.append(el('h3','','Program'));inputField(title,'Enabled','enabled','checkbox',s.enabled);panel.append(title);
 const details=el('div','settings-grid');inputField(details,'Program name','name','text',s.name).maxLength=60;
 inputField(details,'Reference YouTube livestream ID (11 characters)','reference','text',s.reference).maxLength=11;
 inputField(details,'Title template ({date} and {program}); blank keeps legacy title','title_template','text',s.title_template||'').maxLength=100;
 panel.append(details,el('p','hint','Reference must be a previous livestream on your selected channel. Its description and thumbnail are reused. All broadcasts are public.'));
 const calendar=el('div','settings-grid');const repeat=selectField(calendar,'Repeat','repeat',s.repeat||'daily',[['daily','Every day'],['weekdays','Selected weekdays'],['once','One date']]);
 const onDate=inputField(calendar,'One date (IST)','on_date','date',s.on_date||'');
 const weekdays=inputField(calendar,'Weekdays (Mon=1 … Sun=7, comma separated)','weekdays','text',(s.weekdays||[0,1,2,3,4,5,6]).map(d=>d+1).join(','));
 const lead=inputField(calendar,'Prepare before start (minutes)','prepare_minutes','number',s.prepare_minutes||5);lead.min=5;lead.max=60;
 inputField(calendar,'Skip dates (YYYY-MM-DD, comma separated)','skip_dates','text',(s.skip_dates||[]).join(', '));
 function showRepeat(){onDate.parentElement.hidden=repeat.value!=='once';weekdays.parentElement.hidden=repeat.value!=='weekdays';}repeat.onchange=showRepeat;showRepeat();panel.append(calendar);
 const times=el('div','schedule-times');inputField(times,'Live start (IST)','at','time',s.at);inputField(times,'Live end (optional)','end_at','time',s.end_at);inputField(times,'End on next day','end_next_day','checkbox',s.end_next_day);panel.append(times,el('h4','','Camera steps'));
 const actions=el('div','camera-editor');s.camera_actions.forEach(a=>addCameraRow(actions,a));panel.append(actions);
 const add=el('button','secondary add-action','+ Add camera step');add.type='button';add.onclick=()=>{if(actions.children.length>=8)return toast('Maximum 8 camera steps per program.');addCameraRow(actions);};
 const remove=el('button','text-button','Remove program');remove.type='button';remove.onclick=async()=>{if(await confirmAction('Remove this program?','Removal takes effect when you save. Programs with recent unfinished runs cannot be removed.'))panel.remove();};
 panel.append(add,remove,el('p','hint','Patrol 1–8 · ordinary position presets 1–32. Clock-based moves require deliberate live-only choices.'));editor.append(panel);
}
function buildSchedule(){if(!state?.schedule)return;$('grace-minutes').value=state.grace_minutes;$('schedule-editor').replaceChildren();$('retry-slot').replaceChildren();for(const s of state.schedule){addProgram(s);const option=el('option','',s.at+' — '+s.name);option.value=s.id;$('retry-slot').append(option);}scheduleLoaded=true;}
$('add-program').onclick=()=>{if(document.querySelectorAll('.schedule-program').length>=24)return toast('Maximum 24 programs.');const bytes=crypto.getRandomValues(new Uint8Array(12));addProgram({id:'program_'+Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join(''),name:'',reference:'',title_template:'{date} | {program}',enabled:false,at:'',end_at:'',end_next_day:false,camera_actions:[]});updateButtons();};
function readEditor(){const read=(row,key)=>{const i=row.querySelector('[data-field="'+key+'"]');return i.type==='checkbox'?i.checked:i.type==='number'?Number(i.value):i.value;};return [...document.querySelectorAll('.schedule-program')].map(panel=>({id:panel.dataset.slot,name:read(panel,'name'),reference:read(panel,'reference'),title_template:read(panel,'title_template'),at:read(panel,'at'),end_at:read(panel,'end_at'),end_next_day:read(panel,'end_next_day'),enabled:read(panel,'enabled'),repeat:read(panel,'repeat'),on_date:read(panel,'on_date'),weekdays:read(panel,'weekdays').split(',').map(d=>Number(d.trim())-1),prepare_minutes:read(panel,'prepare_minutes'),skip_dates:read(panel,'skip_dates').split(',').map(d=>d.trim()).filter(Boolean),camera_actions:[...panel.querySelectorAll('.camera-editor-row')].map(row=>Object.fromEntries(['kind','number','timing','delay_seconds','at','next_day','only_if_live'].map(k=>[k,read(row,k)])))}));}
$('reload-schedule').onclick=async()=>{if(await confirmAction('Discard unsaved edits?','The editor will reload your currently saved schedule.')){scheduleLoaded=false;buildSchedule();updateButtons();}};
$('schedule-form').onsubmit=async event=>{event.preventDefault();if(!online||pending)return;const schedule=readEditor();const summary=schedule.filter(s=>s.enabled).map(s=>s.at+' '+s.name+' → '+(s.end_at?'end '+s.end_at+(s.end_next_day?' next day':''):'manual end')+'; '+s.camera_actions.length+' camera step(s)').join('\n');if(!await confirmAction('Save these timings?',summary+'\n\nClock camera steps without the live-only option can move the camera even before a live starts.'))return;pending=true;updateButtons();try{await api('/api/schedule',{schedule,grace_minutes:Number($('grace-minutes').value),confirmed:true});scheduleLoaded=false;await refresh();toast('Schedule saved. Enable automation when ready.');}catch(e){toast(e.message);}finally{pending=false;updateButtons();}};
$('export-diagnostics').onclick=async()=>{try{const data=await api('/api/diagnostics');const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download='Live-Desk-diagnostics.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('Diagnostics downloaded. Send this file to investigate the missed start.');}catch(e){toast(e.message);}};
(async()=>{const fragment=location.hash.slice(1);if(fragment.startsWith('pair=')){history.replaceState(null,'','/');try{await pair(decodeURIComponent(fragment.slice(5)));}catch(e){showLogin();$('pair-error').textContent=e.message;}}else{navigate(fragment||'overview');await refresh();}setInterval(refresh,3000);setInterval(updateClock,1000);})();

$('open-updates').onclick=async()=>{try{await api('/api/updates/open',{});toast('Update controls opened on this PC.');}catch(e){toast(e.message);}};

const visibleFlows=[['youtube_prepare','YouTube — create schedule'],['facebook_prepare','Facebook — create live event'],['youtube_go','YouTube — Go live'],['facebook_go','Facebook — Go live'],['youtube_end','YouTube — End live'],['facebook_end','Facebook — End live'],['camera_patrol_start','Camera — Start patrol'],['camera_patrol_stop','Camera — Stop patrol'],['camera_preset','Camera — Go to preset']];
let visibleLoaded=false,visibleDraftSignature='',visibleSteps=[],visibleIdentity=null;
for(const [value,label] of visibleFlows){const option=el('option','',label);option.value=value;$('visible-flow').append(option);}
function visibleLabel(loc){return loc.css?(loc.label?loc.label+' · ':'')+loc.css:loc.tag+' · '+loc.text;}
function buildVisibleSteps(steps,identity=null){
 visibleSteps=steps.map(s=>({...s,locator:{...s.locator}}));visibleIdentity=identity;
 const targets=$('visible-identity-target');targets.replaceChildren();
 const unique=[];for(const step of visibleSteps){if(!unique.some(loc=>JSON.stringify(loc)===JSON.stringify(step.locator)))unique.push(step.locator);}
 if(identity&&!unique.some(loc=>JSON.stringify(loc)===JSON.stringify(identity.locator)))unique.unshift(identity.locator);
 unique.forEach(loc=>{const option=el('option','',visibleLabel(loc));option.value=JSON.stringify(loc);targets.append(option);});
 if(identity){targets.value=JSON.stringify(identity.locator);$('visible-identity-text').value=identity.text;}else $('visible-identity-text').value='';
 const root=$('visible-steps');root.replaceChildren();
 visibleSteps.forEach((step,index)=>{
  const row=el('div','visible-step');row.append(el('p','',`${index+1}. ${visibleLabel(step.locator)}`));
  const kind=selectField(row,'Action','kind',step.kind,[['click','Click'],['fill','Type run data'],['assert','Check result']]);
  const variable=selectField(row,'Text field value','variable',step.variable||'',[['','Choose variable'],['title','Program title'],['description','Reference description'],['date','Date — YYYY-MM-DD'],['time','Time — HH:MM'],['number','Camera number']]);
  const text=inputField(row,'Expected visible result','text','text',step.text||'');
  const update=()=>{step.kind=kind.value;step.variable=variable.value;step.text=text.value;variable.parentElement.hidden=kind.value!=='fill';text.parentElement.hidden=kind.value!=='assert';};
  kind.onchange=variable.onchange=text.oninput=update;update();
  const remove=el('button','text-button','Remove step');remove.type='button';remove.onclick=()=>{const saved=targets.value?{locator:JSON.parse(targets.value),text:$('visible-identity-text').value}:null;buildVisibleSteps(visibleSteps.filter((_,i)=>i!==index),saved);updateVisibleButtons();};row.append(remove);root.append(row);
 });
}
function renderVisible(){
 const v=state.visible;if(!v)return;
 $('visible-status').textContent=(v.mode==='visible'?'VISIBLE BROWSER MODE · ':'API MODE · ')+(v.status?.message||'Idle');
 $('visible-configured').textContent='Configured: '+(v.configured.length?v.configured.map(k=>visibleFlows.find(([id])=>id===k)?.[1]||k).join(', '):'No workflows yet');
 $('visible-local').hidden=!state.local;$('visible-remote').hidden=state.local;
 if(!visibleLoaded&&state.local){$('visible-mode').value=v.mode;$('visible-browser-source').value=v.browser_source||'dedicated';buildVisibleSteps(v.recipes?.[$('visible-flow').value]?.steps||[],v.recipes?.[$('visible-flow').value]?.identity||null);visibleLoaded=true;}
 $('visible-chrome-status').textContent=state.local&&$('visible-browser-source').value!==(v.browser_source||'dedicated')?'Browser choice has not been saved. Use Save browser only; then connect on this PC.':v.browser_source==='running_chrome'?(v.chrome_connected?'Your running Chrome is connected.':'Your running Chrome is selected; connect on this PC before opening or recording.'):'Separate Live Desk browser is selected.';
 if(state.local&&v.draft){const signature=JSON.stringify(v.draft);if(signature!==visibleDraftSignature){visibleDraftSignature=signature;buildVisibleSteps(v.draft);}}
}
function updateVisibleButtons(){
 const blocked=!online||pending||!!state?.busy||!state?.local;
 for(const id of ['visible-save-mode','visible-save-browser','visible-open','visible-record','visible-save-recipe','visible-mode','visible-browser-source','visible-flow','visible-reference','visible-facebook-event','visible-identity-target','visible-identity-text'])$(id).disabled=blocked||!!state?.visible?.recording;
 $('visible-connect-chrome').disabled=blocked||!!state?.visible?.recording||state?.visible?.browser_source!=='running_chrome'||!!state?.visible?.chrome_connected;
 $('visible-disconnect-chrome').disabled=blocked||!!state?.visible?.recording||!state?.visible?.chrome_connected;
 $('visible-finish').disabled=blocked||!state?.visible?.recording;
 $('visible-save-recipe').disabled=blocked||!!state?.visible?.recording||visibleSteps.length===0;
 document.querySelectorAll('#visible-steps input,#visible-steps select,#visible-steps button').forEach(n=>n.disabled=blocked||!!state?.visible?.recording);
}
$('visible-flow').onchange=()=>{visibleDraftSignature=JSON.stringify(state.visible.draft);const r=state.visible.recipes?.[$('visible-flow').value];buildVisibleSteps(r?.steps||[],r?.identity||null);};
$('visible-browser-source').onchange=()=>{renderVisible();updateVisibleButtons();};
async function visibleRequest(path,data){if(!online||pending)return;pending=true;updateButtons();try{await api(path,data);await refresh();}catch(e){toast(e.message);}finally{pending=false;updateButtons();}}
$('visible-open').onclick=()=>visibleRequest('/api/visible/browser',{action:'open',flow:$('visible-flow').value,reference:$('visible-reference').value.trim(),facebook_event:$('visible-facebook-event').value.trim()});
$('visible-record').onclick=async()=>{if(await confirmAction('Record this real workflow?','You will perform real actions in the opened browser. These can create public broadcasts, start/end live or move the camera. Sign in first. Record only an intentional supervised workflow. Passwords and text values are not recorded.')){buildVisibleSteps([]);visibleDraftSignature='';visibleRequest('/api/visible/browser',{action:'record',flow:$('visible-flow').value,reference:$('visible-reference').value.trim(),facebook_event:$('visible-facebook-event').value.trim(),confirmed:true});}};
$('visible-finish').onclick=()=>visibleRequest('/api/visible/browser',{action:'finish'});
$('visible-save-mode').onclick=async()=>{if(await confirmAction('Save execution mode and browser?','Visible mode needs reviewed workflows and an unlocked PC. My running Chrome requires you to connect locally and approve Chrome browser control. Saving does not start automation or connect to Chrome.'))visibleRequest('/api/visible/save',{mode:$('visible-mode').value,browser_source:$('visible-browser-source').value,confirmed:true});};
$('visible-save-browser').onclick=()=>visibleRequest('/api/visible/save',{browser_source:$('visible-browser-source').value,confirmed:true});
$('visible-connect-chrome').onclick=()=>visibleRequest('/api/visible/browser',{action:'connect'});
$('visible-disconnect-chrome').onclick=()=>visibleRequest('/api/visible/browser',{action:'disconnect'});
$('visible-save-recipe').onclick=async()=>{if(!$('visible-identity-target').value)return toast('Record an identity target first.');if(await confirmAction('Approve this recorded workflow?','Review targets, remove unwanted actions, and map every input field. Live automation will replay these actual clicks when you enable it. Test under supervision.'))visibleRequest('/api/visible/save',{confirmed:true,flow:$('visible-flow').value,recipe:{identity:{locator:JSON.parse($('visible-identity-target').value),text:$('visible-identity-text').value},steps:visibleSteps}});};

function downloadJSON(data,name){const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})),a=el('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function formatRunTime(value){return value?new Date(value).toLocaleString('en-GB',{timeZone:'Asia/Kolkata',dateStyle:'medium',timeStyle:'short'})+' IST':'Manual end';}
function renderOperations(){
 const calendar=$('upcoming-runs');calendar.replaceChildren();
 for(const run of (state.upcoming||[]).slice(0,12)){const row=el('div','panel');row.append(el('b','',run.name),el('p','',formatRunTime(run.due)),el('p','hint','Preparation: '+formatRunTime(run.prepare_at)+' · End: '+formatRunTime(run.end_at)));calendar.append(row);}
 if(!calendar.children.length)calendar.append(el('p','muted','No upcoming saved runs. Add a future date or recurring program below.'));
 const history=$('run-history');history.replaceChildren();
 for(const run of state.runs||[]){const row=el('article','panel');row.append(el('h3','',run.name+' · '+run.key.slice(0,10)),el('p','',labels[run.phase]||run.phase),el('p','hint',run.last_error||run.stage));
  for(const [key,label] of [['youtube_url','Open recorded YouTube event'],['facebook_url','Open recorded Facebook event']])if(run[key]){const link=el('a','secondary',label);link.href=run[key];link.target='_blank';link.rel='noopener noreferrer';row.append(link);}
  if(run.inspection)row.append(el('p','notice','Checked '+formatRunTime(run.inspection.checked_at)+' · YouTube: '+run.inspection.youtube+' · Facebook: '+run.inspection.facebook+' · OBS: '+(run.inspection.obs_active?'Output active':'Outputs inactive')));
  if(!run.reviewed){const inspect=el('button','secondary','Inspect recorded run'),review=el('button','secondary','Mark reviewed');for(const b of [inspect,review])b.dataset.operation='run';inspect.onclick=()=>visibleRequest('/api/runs',{key:run.key,action:'inspect'});review.onclick=async()=>{if(await confirmAction('Finish review of '+run.name+'?','Confirm that you have checked both platforms and the camera. A fresh read must confirm inactive outputs. Remaining actions for this recorded run will be cancelled. Draft broadcasts and history remain; this does not end a live or stop a patrol.'))visibleRequest('/api/runs',{key:run.key,action:'review',confirmed:true});};row.append(inspect,review);}
  if(!run.reviewed&&run.confirmed_at&&run.phase!=='ended'){const end=el('button','primary','End this recorded live');end.dataset.operation='run';end.onclick=async()=>{if(await confirmAction('End '+run.name+' now?','This ends the recorded YouTube and Facebook broadcasts and their verified OBS outputs. Pause automation first. A changed or unverified output will be refused. Camera patrols are not stopped by this action.'))visibleRequest('/api/runs',{key:run.key,action:'end',confirmed:true});};row.append(end);}
  history.append(row);
 }
 if(!history.children.length)history.append(el('p','muted','No recorded runs yet.'));
 $('backup-tools').hidden=!state.local;$('device-tools').hidden=!state.local;
}
function updateOperationsButtons(){
 const blocked=!online||pending||!!state?.busy||state?.role==='viewer';
 document.querySelectorAll('[data-operation="run"],#backup-restore,#backup-file').forEach(n=>n.disabled=blocked);
 $('backup-export').disabled=!online||pending;
 for(const id of ['devices-refresh','pair-rotate'])$(id).disabled=!online||pending;
 if(state?.role==='viewer')document.querySelectorAll('#arm,#pause,#check,#check-settings,#retry,#schedule-form input,#schedule-form select,#schedule-form button').forEach(n=>n.disabled=true);
}
$('backup-export').onclick=async()=>{try{downloadJSON(await api('/api/backup'),'Live-Desk-settings.json');}catch(e){toast(e.message);}};
$('backup-restore').onclick=async()=>{try{const file=$('backup-file').files[0];if(!file||file.size>60000)throw new Error('Choose a settings JSON backup under 60 KB.');const backup=JSON.parse(await file.text());const names=(backup.schedule||[]).map(s=>s.name+' · '+s.at).join('\n');if(await confirmAction('Restore settings for '+(backup.settings?.workspace_name||'this workspace')+'?',names+'\n\nCurrent settings are backed up first. Automation will remain paused. Credentials, network addresses and run history stay on this PC.')){await visibleRequest('/api/restore',{backup,confirmed:true});formLoaded=false;scheduleLoaded=false;await refresh();}}catch(e){toast(e.message);}};
const devicePanel=el('article','panel');devicePanel.id='device-tools';devicePanel.append(el('h2','','Paired devices'),el('p','','Phone sessions last 12 hours. New phone pairing codes last 30 minutes. Existing sessions stay valid when you replace the code. Revoke a device to disconnect it.'));
const deviceRefresh=el('button','secondary','Refresh device list');deviceRefresh.id='devices-refresh';
const roleSelect=el('select');roleSelect.id='pair-role';roleSelect.setAttribute('aria-label','New pairing role');for(const [v,t] of [['operator','Operator — can control schedules'],['viewer','Viewer — status only']]){const option=el('option','',t);option.value=v;roleSelect.append(option);}
const pairRotate=el('button','secondary','Generate 30-minute pairing code');pairRotate.id='pair-rotate';const pairOutput=el('p','notice');pairOutput.id='pair-output';const deviceList=el('div');deviceList.id='device-list';devicePanel.append(deviceRefresh,deviceList,roleSelect,pairRotate,pairOutput);$('view-mobile').append(devicePanel);
deviceRefresh.onclick=async()=>{try{const data=await api('/api/devices');deviceList.replaceChildren();for(const item of data.devices){const row=el('p','',item.label+' · '+item.role+' · '+formatRunTime(item.created_at)),revoke=el('button','text-button','Revoke');revoke.onclick=async()=>{if(await confirmAction('Disconnect this device?','It will need a current pairing code to reconnect.')){await api('/api/devices/revoke',{id:item.id});await refresh();if(online)deviceRefresh.click();}};row.append(revoke);deviceList.append(row);}}catch(e){toast(e.message);}};
pairRotate.onclick=async()=>{try{const result=await api('/api/devices/rotate',{role:roleSelect.value});pairOutput.textContent=result.role+' code · valid 30 minutes: '+result.code;}catch(e){toast(e.message);}};

const remotePanel=el('article','panel');remotePanel.id='remote-tools';remotePanel.append(el('h2','','Internet remote access (optional)'),el('p','','Requires your own deployed Live Desk HTTPS relay. Keep the PC ports private. Agent enrollment tokens are saved only in Windows Credential Manager. Local scheduling continues if the relay disconnects.'));
const remoteStatus=el('p','notice');remoteStatus.id='remote-status';remotePanel.append(remoteStatus);
const remoteURL=inputField(remotePanel,'HTTPS remote service address','remote-url','url','');remoteURL.id='remote-url';
const remoteToken=inputField(remotePanel,'PC agent enrollment token (blank keeps saved value)','remote-token','password','');remoteToken.id='remote-token';remoteToken.autocomplete='off';
const remoteEnabled=inputField(remotePanel,'Enable internet remote control','remote-enabled','checkbox',false);remoteEnabled.id='remote-enabled';
const remoteSave=el('button','primary','Save remote access');remoteSave.id='remote-save';remotePanel.append(remoteSave);$('view-mobile').append(remotePanel);
let remoteLoaded=false;
function renderRemote(){remotePanel.hidden=!state?.local;if(!state)return;remoteStatus.textContent=state.remote?.status||'Not connected';if(!remoteLoaded){remoteURL.value=state.remote?.url||'';remoteEnabled.checked=!!state.remote?.enabled;remoteLoaded=true;}remoteSave.disabled=!online||pending;}
remoteSave.onclick=async()=>{if(await confirmAction('Save internet access settings?',remoteEnabled.checked?'Workspace owners and operators on this server will be able to check, enable and pause this PC. Use only a relay you trust.':'Remote commands will be disabled; local automation continues.')){await visibleRequest('/api/remote/settings',{url:remoteURL.value.trim(),token:remoteToken.value.trim(),enabled:remoteEnabled.checked,confirmed:true});remoteToken.value='';}};


// Desktop-only controls use a bounded queue consumed by the Windows UI thread.
const lanPanel=el('article','panel');lanPanel.id='pc-lan-tools';
lanPanel.append(el('h2','','Wi-Fi mobile access'),el('p','','Use this for phones on the same trusted Wi-Fi. Internet access above works separately with your saved relay pairing.'));
const lanIP=selectField(lanPanel,'PC network address','pc-ip','',[]);lanIP.id='pc-ip';
const lanButton=el('button','primary','Enable Wi-Fi mobile access');lanButton.id='pc-mobile-toggle';lanPanel.append(lanButton);
$('view-mobile').prepend(lanPanel);
function renderPC(){
 const host=state?.desktop_host,available=!!state?.local&&!!host?.available;
 $('pc-nav').hidden=!state?.local;lanPanel.hidden=!available;
 $('pc-action-status').textContent=state?.local&&host?host.message:'PC controls are available in the Windows app on this PC.';
 $('pc-startup-status').textContent=host?.startup?'Live Desk opens after Windows login.':'Start with Windows is off.';
 $('pc-local-help').hidden=available;
 if(!state?.local&&!$('view-pc').hidden)navigate('overview');
 if(available){
  const addresses=host.addresses||[],old=lanIP.value;
  if(JSON.stringify([...lanIP.options].map(o=>o.value))!==JSON.stringify(addresses)){
   lanIP.replaceChildren(...addresses.map(ip=>{const o=el('option','',ip);o.value=ip;return o;}));
   if(addresses.includes(old))lanIP.value=old;
  }
  lanButton.textContent=state.mobile_enabled?'Disable Wi-Fi mobile access':'Enable Wi-Fi mobile access';
 }
 updatePCButtons();
}
function updatePCButtons(){
 const blocked=!online||pending||!state?.local||!state?.desktop_host?.available||state.desktop_host.busy||state.role==='viewer';
 document.querySelectorAll('[data-pc]').forEach(b=>b.disabled=blocked);
 lanIP.disabled=blocked||!!state?.mobile_enabled;
 lanButton.disabled=blocked||(!state?.mobile_enabled&&!lanIP.value);
}
async function pcRequest(action,extra={}){
 if(!online||pending)return;
 pending=true;updateButtons();
 try{const result=await api('/api/desktop/action',{action,...extra});$('pc-action-status').textContent=result.message;await refresh();}
 catch(e){$('pc-action-status').textContent=e.message;toast(e.message);}
 finally{pending=false;updateButtons();}
}
for(const b of document.querySelectorAll('[data-pc]'))b.onclick=async()=>{
 if(b.dataset.pc==='quit'){
  if(!await confirmAction('Quit Live Desk on this PC?','Future starts, scheduled endings, camera actions and phone control will stop. Existing live broadcasts continue. Closing the browser alone keeps automation running.'))return;
  return pcRequest('quit',{confirmed:true});
 }
 pcRequest(b.dataset.pc);
};
lanButton.onclick=async()=>{
 if(state.mobile_enabled){
  if(!await confirmAction('Disable Wi-Fi mobile access?','Phones connected through the local Wi-Fi address will disconnect. Internet remote access and automation continue.'))return;
  await pcRequest('mobile-off',{confirmed:true});
 }else await pcRequest('mobile-on',{ip:lanIP.value});
};
