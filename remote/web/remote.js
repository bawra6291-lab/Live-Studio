'use strict';
const $=id=>document.getElementById(id);let csrf='',state=null,pending=false,lastCommand=null;
const node=(tag,text)=>{const n=document.createElement(tag);n.textContent=text;return n;};
// HTML confirmation works inside Android WebView without a native WebChromeClient.
function confirmAction(title,detail){
 const dialog=$('confirm-dialog');if(dialog.open)return Promise.resolve(false);
 $('confirm-title').textContent=title;$('confirm-detail').textContent=detail;
 return new Promise(resolve=>{let settled=false;const finish=accepted=>{if(settled)return;settled=true;dialog.close();resolve(accepted);};
  $('confirm-submit').onclick=()=>finish(true);$('confirm-cancel').onclick=()=>finish(false);
  dialog.oncancel=e=>{e.preventDefault();finish(false);};dialog.onclose=()=>finish(false);
  dialog.showModal();$('confirm-cancel').focus();
 });
}
function notice(text,error=false){const n=$('command-message');n.hidden=false;n.textContent=text;n.classList.toggle('error',error);}
function commandFeedback(){if(!lastCommand)return;const item=state.commands.find(c=>c.id===lastCommand.id);if(!item)return;
 const label=lastCommand.label;
 if(item.status==='queued')notice(label+': waiting for the PC.');
 else if(item.status==='dispatched')notice(label+': sent to PC; waiting for acknowledgement.');
 else if(item.status==='accepted')notice(label+': '+item.result+'. Check the PC status below.');
 else if(item.status==='running')notice(label+': running on PC · '+item.result);
 else if(item.status==='completed')notice(label+': completed · '+item.result);
 else notice(label+': '+item.status+' · '+item.result,true);
}

async function api(path,data){const r=await fetch(path,{method:data===undefined?'GET':'POST',cache:'no-store',signal:AbortSignal.timeout(12000),headers:data===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:data===undefined?undefined:JSON.stringify(data)});const out=await r.json();if(!r.ok){if(r.status===401){$('login').hidden=false;$('desk').hidden=true;}throw Error(out.error||'Request failed');}return out;}
async function refresh(){try{state=await api('/api/state');csrf=state.csrf;$('login').hidden=true;$('desk').hidden=false;$('message').textContent='Connected · this phone stays paired';$('role').textContent='Access: '+state.role;render();commandFeedback();}catch(e){$('message').textContent=e.message;document.querySelectorAll('[data-command]').forEach(b=>b.disabled=true);}}
$('login').onsubmit=async e=>{e.preventDefault();try{await api('/api/login',{code:$('code').value.trim()});$('code').value='';await refresh();}catch(err){$('message').textContent=err.message;}};
$('logout').onclick=async()=>{lastCommand=null;$('command-message').hidden=true;await api('/api/logout',{});csrf='';state=null;$('desk').hidden=true;$('login').hidden=false;};
function render(){const devices=$('devices');devices.replaceChildren();for(const device of state.devices){const s=device.snapshot,card=node('article','');card.append(node('h2',device.name),node('p',(device.online?'● Online':'○ Offline')+' · '+(s.armed?'Automation enabled':'Automation paused')),node('p',s.message||'Waiting for the PC heartbeat'),node('p','Next: '+(s.next?.name||'Not configured')+' · '+(s.next?.due||'No upcoming date')));
 if(s.monitor){const m=s.monitor,stale=!device.online||!m.observed_at||Date.now()-Date.parse(m.observed_at)>45000;card.append(node('h3','Observed live status'),node('p',stale?'Status unavailable or stale':('OBS: '+(m.obs?.connected?(m.obs.active?'Streaming':'Idle'):'Unavailable')+' · YouTube: '+m.youtube+' · Facebook: '+m.facebook)),node('p','Platform read: '+(m.platform_at||'Not read')));if(m.frame&&!stale&&/^data:image\/(jpeg|jpg);base64,[A-Za-z0-9+/=]+$/.test(m.frame)&&m.frame.length<=22000){const img=document.createElement('img');img.src=m.frame;img.alt='Sample of OBS program scene';img.className='live-preview';card.append(img,node('small','OBS sample · '+m.frame_at+' · refreshed about every 15 seconds'));}}
 if(s.progress){card.append(node('h3',s.progress.name+' · '+s.progress.stage));for(const step of s.progress.steps||[])card.append(node('p',step.label+' · '+step.status));for(const a of s.progress.camera||[])card.append(node('p',a.label+' · '+a.state+' · '+(a.due||'Waits for both live')));}
 if(s.readiness){card.append(node('h3','Readiness'));for(const x of s.readiness.items||[])if(x.status!=='ready')card.append(node('p',x.label+' · '+x.status+' · '+x.detail));}
 if(s.connections)card.append(node('p','Connections: '+Object.entries(s.connections).map(([name,value])=>name.toUpperCase()+' '+value).join(' · ')));
 if(s.error)card.append(node('p',s.error===true?(s.message||'Inspect local PC activity'):String(s.error)));
 for(const [action,label] of [['check','Check connections'],['arm','Enable automation'],['pause','Pause automation']]){const b=node('button',label);b.dataset.command=action;b.disabled=!device.online||state.role==='viewer'||pending||(s.busy&&action!=='pause');b.onclick=()=>command(device,action,{},label);card.append(b);}
 if(s.progress?.started_by_app&&s.progress.phase!=='ended'){const end=node('button','End recorded live');end.dataset.command='end';end.disabled=!device.online||state.role==='viewer'||pending||s.busy;end.onclick=()=>command(device,'end',{key:s.progress.key},'End recorded live');card.append(end,node('small','Pause automation first. End stops only the verified broadcasts and outputs recorded by this app.'));}
 const plans=node('details','');plans.append(node('summary',"Today's recorded runs"));for(const slot of s.slots||[]){const line=node('p',slot.name+' · '+slot.at+' · '+slot.phase+(slot.last_error?' · '+slot.last_error:''));plans.append(line);}card.append(plans);
 if(state.role==='owner'){const revoke=node('button','Revoke this PC');revoke.onclick=async()=>{if(await confirmAction('Revoke this PC?','Local schedules continue. Remote control stops.')){await api('/api/revoke',{id:device.id,kind:'device'});await refresh();}};card.append(revoke);}devices.append(card);}
 const log=$('commands');log.replaceChildren();for(const item of state.commands)log.append(node('p',new Date(item.created*1000).toLocaleString()+' · '+item.action+' · '+item.status+' · '+item.result));
 const phones=$('phones');phones.replaceChildren();if(state.role==='owner'){phones.append(node('h2','Paired phones'));for(const item of state.phones||[]){const row=node('p',item.role+' · '+(item.current?'This phone':item.id.slice(0,8))),b=node('button','Forget phone');b.onclick=async()=>{try{if(await confirmAction('Forget this phone?','It will need its access code again. The PC schedule continues.')){await api('/api/revoke',{id:item.id,kind:'phone'});await refresh();}}catch(e){$('message').textContent=e.message;}};row.append(b);phones.append(row);}}
 const members=$('members');members.replaceChildren();if(state.role==='owner'){members.append(node('h2','Workspace access'));for(const item of state.members){if(!item.enabled)continue;const row=node('p',item.role+' · '+item.id.slice(0,8)),button=node('button','Revoke access');button.onclick=async()=>{try{if(await confirmAction('Revoke access?','This member and their pending commands will be revoked.')){await api('/api/revoke',{id:item.id,kind:'principal'});await refresh();}}catch(e){$('message').textContent=e.message;}};row.append(button);members.append(row);}}}
async function command(device,action,args,label){
 if(pending)return;pending=true;render();
 try{
  const detail=action==='arm'?'Saved plans can publish real broadcasts and move the camera. Inspect the PC schedule first. Automation follows the saved start times shown below.':action==='end'?'End the exact YouTube and Facebook events and associated OBS outputs recorded by Live Desk. Camera patrol remains unchanged.':action==='pause'?'Future scheduled endings and camera actions also pause. Existing lives keep running.':'Check the saved OBS, YouTube, Facebook and camera connections on this PC.';
  if(!await confirmAction(label+' on '+device.name+'?',detail)){lastCommand=null;notice(label+': cancelled.');return;}
  lastCommand=null;notice(label+': sending request…');
  const result=await api('/api/command',{device:device.id,boot:device.boot,action,args,confirmed:true,nonce:crypto.randomUUID()});
  lastCommand={id:result.id,label};notice(label+': request queued.');await refresh();
 }catch(e){lastCommand=null;notice(e.message,true);}
 finally{pending=false;await refresh();}
}
refresh();setInterval(refresh,4000);
