'use strict';
let takeoverSignature='',takeoverSchedule='',takeoverReady=null;
function updateTakeoverButtons(){
 const blocked=!online||pending||!!state?.busy||state?.role==='viewer';
 for(const id of ['takeover-slot','takeover-date','takeover-inspect'])$(id).disabled=blocked;
 $('takeover-confirm').disabled=blocked||!takeoverReady;
}
function renderTakeover(){
 const signature=JSON.stringify(state.schedule.map(s=>[s.id,s.name,s.enabled]));
 if(signature!==takeoverSchedule){
  const selected=$('takeover-slot').value;takeoverSchedule=signature;
  $('takeover-slot').replaceChildren(...state.schedule.filter(s=>s.enabled).map(s=>{const o=el('option','',s.name);o.value=s.id;return o;}));
  if(state.schedule.some(s=>s.id===selected&&s.enabled))$('takeover-slot').value=selected;
 }
 if(!$('takeover-date').value)$('takeover-date').value=state.now.slice(0,10);
 const info=state.takeover||{status:'idle'},key=JSON.stringify(info);
 if(key!==takeoverSignature){
  takeoverSignature=key;takeoverReady=info.status==='ready'?info:null;
  const root=$('takeover-preview');root.replaceChildren();
  if(info.name)root.append(el('h3','',info.name));
  if(info.youtube_title)root.append(el('p','','YouTube: '+info.youtube_title),el('p','','Facebook: '+info.facebook_title));
  if(info.both_live_at)root.append(el('p','hint','Both live since: '+formatRunTime(info.both_live_at)+' · End: '+(info.end_at?formatRunTime(info.end_at):'Manual end')));
  for(const a of info.camera||[])root.append(el('p','hint',a.label+' · '+formatRunTime(a.due)+' · '+(a.state==='pending'?'Remaining':a.state==='skipped_before_takeover'?'Skipped · before control began':a.state.replaceAll('_',' '))));
  for(const [name,url] of [['YouTube',info.youtube_url],['Facebook',info.facebook_url]])if(url){const link=el('a','secondary','Inspect '+name);link.href=url;link.target='_blank';link.rel='noopener noreferrer';root.append(link);}
  $('takeover-status').textContent=info.message||({idle:'Inspect first, then confirm the exact running live.',ready:'Review these events and remaining actions. Preview expires after 90 seconds; confirmation checks the live again.',active:'Controlling this live only. Keep the PC awake and Live Desk running.',ended:'Controlled live ended.',paused:'Control paused.'}[info.status]||info.status);
  $('takeover-confirm').hidden=info.status!=='ready';
 }
 updateTakeoverButtons();
}
for(const id of ['takeover-slot','takeover-date'])$(id).onchange=()=>{takeoverReady=null;$('takeover-confirm').hidden=true;$('takeover-preview').replaceChildren();$('takeover-status').textContent='Selection changed. Inspect this program again.';updateTakeoverButtons();};
async function takeoverRequest(data){
 if(!online||pending)return;pending=true;updateButtons();
 try{await api('/api/takeover',data);await refresh();}
 catch(e){toast(e.message);}
 finally{pending=false;updateButtons();}
}
$('takeover-inspect').onclick=()=>takeoverRequest({action:'inspect',slot:$('takeover-slot').value,date:$('takeover-date').value});
$('takeover-confirm').onclick=async()=>{
 const p=takeoverReady;if(!p)return;
 const message=p.name+' · '+p.date+'\nYouTube: '+p.youtube_title+'\nFacebook: '+p.facebook_title+'\n\nEnd: '+(p.end_at?formatRunTime(p.end_at):'Manual end')+'\n'+p.camera.map(a=>a.label+' · '+formatRunTime(a.due)+' · '+a.state).join('\n')+'\n\nTake control of these two existing live events and their associated OBS outputs. Remaining camera steps and the saved end time become active. Steps which have already elapsed are skipped. This session controls this live only; it does not start other programs. Pause automation stops future camera/end actions.';
 if(await confirmAction('Control this running live?',message))takeoverRequest({action:'confirm',slot:$('takeover-slot').value,date:$('takeover-date').value,token:p.token,confirmed:true});
};
