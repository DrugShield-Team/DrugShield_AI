(() => {
  'use strict';
  const $ = (s) => document.querySelector(s);
  const state = { user:null, cases:[], selected:null, dispatches:[], hits:[], seen:new Set(), timer:null };
  const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const when = v => { const d=new Date(v); return v && !Number.isNaN(d.valueOf()) ? d.toLocaleString() : '—'; };
  const channel = v => ({instagram:'Instagram',telegram:'Telegram',whatsapp:'WhatsApp'}[v] || v || 'Unknown');
  const statusName = v => ({pending_review:'Pending review',further_review:'Further review',accepted:'Accepted',dismissed:'Dismissed'}[v] || v || 'Unknown');
  const toast = msg => { const e=$('#toast');e.textContent=msg;e.classList.remove('hidden');setTimeout(()=>e.classList.add('hidden'),2800); };
  async function api(path,options={}) {
    const r=await fetch(path,{credentials:'include',...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});
    if(r.status===401){lock();throw Error('Your session expired. Sign in again.');}
    const data=await r.json().catch(()=>({}));
    if(!r.ok)throw Error(data.detail||'Request failed.');return data;
  }
  function lock(){clearInterval(state.timer);state.timer=null;state.user=null;$('#app-view').classList.add('hidden');$('#login-view').classList.remove('hidden');}
  async function enter(user){
    if(!user.roles?.some(x=>['reviewer','admin'].includes(x))){$('#login-error').textContent='This account does not have reviewer access.';await fetch('/api/v1/auth/logout',{method:'POST',credentials:'include'});return;}
    state.user=user;$('#user-name').textContent=user.username;$('#user-initials').textContent=(user.username[0]||'R').toUpperCase();
    $('#login-view').classList.add('hidden');$('#app-view').classList.remove('hidden');await refresh();clearInterval(state.timer);state.timer=setInterval(refresh,7000);
  }
  $('#login-form').addEventListener('submit',async e=>{
    e.preventDefault();const button=e.currentTarget.querySelector('button');button.disabled=true;$('#login-error').textContent='';
    try{await api('/api/v1/auth/token',{method:'POST',body:JSON.stringify({username:$('#username').value.trim(),password:$('#password').value})});$('#password').value='';await enter(await api('/api/v1/auth/me'));}
    catch(err){$('#login-error').textContent=err.message;}finally{button.disabled=false;}
  });
  $('#logout-button').addEventListener('click',async()=>{await fetch('/api/v1/auth/logout',{method:'POST',credentials:'include'}).catch(()=>{});$('#password').value='';lock();});
  $('#refresh-button').addEventListener('click',refresh);
  $('#status-filter').addEventListener('change',renderCases);$('#case-search').addEventListener('input',renderCases);
  $('#case-table-body').addEventListener('click',e=>{const row=e.target.closest('[data-case]');if(row)selectCase(row.dataset.case);});
  document.addEventListener('click',e=>{
    const review=e.target.closest('[data-action]');if(review)submitReview(review.dataset.action);
    const attachment=e.target.closest('[data-attachment]');if(attachment)downloadAttachment(attachment.dataset.case,attachment.dataset.attachment,attachment.dataset.name);
    if(e.target.closest('[data-print]'))printReport();
  });
  async function refresh(){
    if(!state.user)return;
    const results=await Promise.allSettled([
      api('/api/v1/cases?limit=500'),api('/api/v1/graph?limit=500'),
      api('/api/v1/dispatch/alerts?limit=30'),api('/api/v1/honeypot/logs?limit=30')
    ]);
    let failed=false;
    if(results[0].status==='fulfilled'){state.cases=results[0].value.cases||[];renderCases();renderMetrics();}
    else{failed=true;$('#case-table-body').innerHTML='<tr><td colspan="5" class="empty">Case data unavailable.</td></tr>';}
    if(results[1].status==='fulfilled')renderGraph(results[1].value);else{failed=true;$('#graph-container').innerHTML='<p class="empty">Graph data unavailable.</p>';}
    if(results[2].status==='fulfilled'){state.dispatches=results[2].value.alerts||[];renderActivity();notify();}
    else{failed=true;$('#dispatch-list').innerHTML='<p class="empty">Scenario routing data unavailable.</p>';}
    if(results[3].status==='fulfilled'){state.hits=results[3].value.hits||[];renderActivity();}
    else{failed=true;$('#hit-list').innerHTML='<p class="empty">Scenario access data unavailable.</p>';}
    $('#global-alert').textContent=failed?'Some dashboard data could not be refreshed. Check the API connection and your account access.':'';
    $('#global-alert').classList.toggle('hidden',!failed);$('#last-updated').textContent='Updated '+new Date().toLocaleTimeString();
    if(state.selected && !state.cases.some(c=>c.case_id===state.selected)){state.selected=null;$('#case-detail').innerHTML='<div class="empty">Select a case to inspect its report and evidence.</div>';}
  }
  function renderMetrics(){
    const c={pending_review:0,further_review:0,accepted:0,dismissed:0};state.cases.forEach(x=>{if(x.status in c)c[x.status]++;});
    $('#metric-open').textContent=c.pending_review;$('#metric-escalated').textContent=c.further_review;$('#metric-accepted').textContent=c.accepted;$('#metric-dismissed').textContent=c.dismissed;
  }
  function renderCases(){
    const filter=$('#status-filter').value,q=$('#case-search').value.trim().toLowerCase();
    const items=state.cases.filter(x=>{const s=x.summary||{};const all=[x.case_id,x.status,s.channel,s.sender_display_name,s.recipient_display_name,s.message_text].join(' ').toLowerCase();return(!filter||x.status===filter)&&(!q||all.includes(q));});
    $('#case-count').textContent=items.length;
    $('#case-table-body').innerHTML=items.length?items.map(x=>{const s=x.summary||{};return '<tr data-case="'+esc(x.case_id)+'" class="'+(state.selected===x.case_id?'selected':'')+'"><td class="case-id">'+esc(String(x.case_id).slice(0,8))+'</td><td>'+esc(channel(s.channel))+'</td><td>'+esc(s.sender_display_name||s.sender_id||'—')+'</td><td>'+esc(when(x.created_at))+'</td><td><span class="status status-'+esc(x.status)+'">'+esc(statusName(x.status))+'</span></td></tr>';}).join(''):'<tr><td colspan="5" class="empty">No cases match this view.</td></tr>';
  }
  async function selectCase(id){
    state.selected=id;renderCases();$('#case-detail').innerHTML='<div class="empty">Loading report…</div>';
    try{renderDetail(await api('/api/v1/cases/'+encodeURIComponent(id)));}catch(e){$('#case-detail').innerHTML='<div class="empty">'+esc(e.message)+'</div>';}
  }
  function renderDetail(c){
    const r=c.report||{},s=r.summary||{},a=r.analysis||{},p=r.review_policy||{},reasons=p.reasons||[],attachments=r.attachments||[],history=c.review_history||[];
    const text=a.text_analysis||{},vpas=a.vpa_candidates||[],qr=a.qr_analysis||a.qr_codes||[];
    const list=(arr,empty)=>arr.length?arr.map(x=>'<li>'+esc(typeof x==='string'?x:(x.signal||x.description||x.value||x.filename||JSON.stringify(x)))+'</li>').join(''):'<li>'+empty+'</li>';
    const attach=attachments.length?attachments.map(x=>'<li><button data-case="'+esc(c.case_id)+'" data-attachment="'+esc(x.attachment_id)+'" data-name="'+esc(x.filename||'evidence')+'">'+esc(x.filename||x.attachment_id)+'</button> · '+esc(x.content_type||'file')+'</li>').join(''):'<li>No attachments recorded.</li>';
    const reviews=history.length?history.map(x=>'<li>'+esc(x.action)+' by '+esc(x.reviewer_id||'reviewer')+' · '+esc(when(x.occurred_at))+(x.note?'<br>'+esc(x.note):'')+'</li>').join(''):'<li>No review actions recorded.</li>';
    const open=['pending_review','further_review'].includes(c.status);
    const qrLabel=Array.isArray(qr)?(qr.length?qr.map(x=>typeof x==='string'?x:(x.payload||x.text||x.status||'QR detected')).join('; '):'No findings'):JSON.stringify(qr||'No findings');
    $('#case-detail').dataset.case=c.case_id;$('#case-detail').dataset.report=JSON.stringify(c);
    $('#case-detail').innerHTML='<div class="detail-head"><div><h3>Case '+esc(String(c.case_id).slice(0,12))+'</h3><p>'+esc(channel(s.channel))+' · '+esc(when(c.created_at))+'</p></div><span class="status status-'+esc(c.status)+'">'+esc(statusName(c.status))+'</span></div>'+
    '<div class="detail-block"><h4>Conversation context</h4><div class="facts"><div class="fact"><span>Sender</span><strong>'+esc(s.sender_display_name||s.sender_id||'—')+'</strong></div><div class="fact"><span>Recipient</span><strong>'+esc(s.recipient_display_name||s.recipient_id||'—')+'</strong></div><div class="fact"><span>Conversation</span><strong>'+esc(s.conversation_id||'—')+'</strong></div><div class="fact"><span>Message time</span><strong>'+esc(when(s.timestamp))+'</strong></div></div><div class="detail-copy">'+esc(s.message_text||'(No text content)')+'</div></div>'+
    '<div class="detail-block"><h4>Analysis evidence</h4><div class="facts"><div class="fact"><span>Text risk score</span><strong>'+esc(text.risk_score??'Not provided')+'</strong></div><div class="fact"><span>Text category</span><strong>'+esc(text.prediction||text.label||text.status||'Not provided')+'</strong></div><div class="fact"><span>Candidate VPA / UPI</span><strong>'+esc(vpas.length?vpas.map(x=>typeof x==='string'?x:(x.value||x.candidate||JSON.stringify(x))).join(', '):'None identified')+'</strong></div><div class="fact"><span>QR analysis</span><strong>'+esc(qrLabel)+'</strong></div></div><ul class="detail-list">'+list(reasons,'No review reason supplied.')+'</ul></div>'+
    '<div class="detail-block"><h4>Attachments</h4><ul class="detail-list">'+attach+'</ul></div><div class="detail-block"><h4>Review history</h4><ul class="detail-list">'+reviews+'</ul></div>'+
    '<div class="review-form">'+(open?'<textarea id="review-note" maxlength="4000" placeholder="Add a concise review note (optional)"></textarea><div class="review-actions"><button class="accept" data-action="accept">Accept</button><button class="escalate" data-action="further_review">Further review</button><button class="dismiss" data-action="dismiss">Dismiss</button><button class="print" data-print>Print report</button></div>':'<div class="review-actions"><button class="print" data-print>Print report</button></div>')+'</div>';
  }
  async function submitReview(action){
    const id=$('#case-detail').dataset.case;if(!id)return;
    try{await api('/api/v1/cases/'+encodeURIComponent(id)+'/review',{method:'POST',body:JSON.stringify({action,note:$('#review-note')?.value||''})});toast('Review decision saved.');await refresh();await selectCase(id);}
    catch(e){toast(e.message);}
  }
  async function downloadAttachment(caseId,attachmentId,name){
    try{const r=await fetch('/api/v1/cases/'+encodeURIComponent(caseId)+'/attachments/'+encodeURIComponent(attachmentId),{credentials:'include'});if(r.status===401){lock();throw Error('Session expired.');}if(!r.ok)throw Error('Attachment unavailable.');const url=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=url;a.download=name||'evidence';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
    catch(e){toast(e.message);}
  }
  function printReport(){
    const raw=$('#case-detail').dataset.report;if(!raw)return;const c=JSON.parse(raw),r=c.report||{},s=r.summary||{};
    const w=window.open('','_blank');if(!w){toast('Allow pop-ups to print the report.');return;}
    w.document.write('<!doctype html><meta charset="utf-8"><title>DrugShield-AI Evidence Report</title><style>body{font:14px Arial;color:#192b3f;max-width:850px;margin:40px auto;padding:0 24px}h1{font-size:22px}h2{font-size:15px;margin-top:24px;border-bottom:1px solid #ddd;padding-bottom:6px}.meta{color:#54677b;font-size:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f7f8;padding:14px;border:1px solid #ddd}.notice{margin-top:25px;padding:12px;background:#eef5f4;font-size:12px}</style><p class="meta">DRUGSHIELD-AI / SIMULATION EVIDENCE REVIEW</p><h1>Case '+esc(c.case_id)+'</h1><p class="meta">'+esc(channel(s.channel))+' · '+esc(statusName(c.status))+' · '+esc(when(c.created_at))+'</p><h2>Participants</h2><p>'+esc(s.sender_display_name||s.sender_id||'—')+' → '+esc(s.recipient_display_name||s.recipient_id||'—')+'</p><h2>Message evidence</h2><pre>'+esc(s.message_text||'No text content')+'</pre><h2>Analysis</h2><pre>'+esc(JSON.stringify(r.analysis||{},null,2))+'</pre><h2>Review policy</h2><pre>'+esc(JSON.stringify(r.review_policy||{},null,2))+'</pre><div class="notice">Decision-support prototype output for fictional simulation data. Not a determination of wrongdoing.</div><script>window.onload=()=>window.print()<\/script>');w.document.close();
  }
  function renderGraph(g){
    const nodes=g.nodes||[],edges=g.edges||[];$('#graph-meta').textContent=(g.case_count||0)+' cases · '+nodes.length+' entities · '+edges.length+' links';
    const box=$('#graph-container');if(!nodes.length){box.innerHTML='<p class="empty">No entity relationships available.</p>';return;}
    const width=Math.max(box.clientWidth||650,520),height=220,cx=width/2,cy=85,rx=Math.min(width*.38,300),ry=63;
    const pos=new Map(nodes.map((n,i)=>{const a=2*Math.PI*i/nodes.length-Math.PI/2;return[n.id,{x:cx+rx*Math.cos(a),y:cy+ry*Math.sin(a)}];}));
    const lines=edges.map(e=>{const a=pos.get(e.source),b=pos.get(e.target);return a&&b?'<line x1="'+a.x+'" y1="'+a.y+'" x2="'+b.x+'" y2="'+b.y+'"/>':'';}).join('');
    const circles=nodes.map(n=>{const p=pos.get(n.id),label=String(n.label||n.name||n.id),short=label.length>24?label.slice(0,21)+'…':label;return '<g><circle cx="'+p.x+'" cy="'+p.y+'" r="19"/><text x="'+p.x+'" y="'+(p.y+34)+'" text-anchor="middle">'+esc(short)+'</text></g>';}).join('');
    box.innerHTML='<svg role="img" aria-label="Evidence relationship graph" viewBox="0 0 '+width+' '+height+'">'+lines+circles+'</svg>';
  }
  function renderActivity(){
    $('#dispatch-list').innerHTML=state.dispatches.length?state.dispatches.map(x=>{const d=x.details||{},node=d.assigned_precinct||{};return '<article class="activity-item"><strong><span>Scenario '+esc(x.tracking_token||d.tracking_token||x.id||'event')+'</span><time>'+esc(when(x.created_at||d.timestamp))+'</time></strong><p>Nearest simulation node: '+esc(x.precinct_name||node.name||'Not assigned')+' · route '+esc(x.distance_km??node.distance_km??'—')+' km / '+esc(x.eta_minutes??node.estimated_eta_minutes??'—')+' min. Synthetic scenario only.</p></article>';}).join(''):'<p class="empty">No scenario routing events.</p>';
    $('#hit-list').innerHTML=state.hits.length?state.hits.map(x=>'<article class="activity-item"><strong><span>Scenario '+esc(x.tracking_token||x.id||'event')+'</span><time>'+esc(when(x.created_at))+'</time></strong><p>Fictional scenario location: '+esc([x.city,x.region].filter(Boolean).join(', ')||'not specified')+'. No visitor IP, device fingerprint, or GPS data is collected.</p></article>').join(''):'<p class="empty">No scenario access events.</p>';
  }
  function notify(){state.dispatches.forEach(x=>{const id=x.id||x.tracking_token;if(!id||state.seen.has(id))return;state.seen.add(id);if(state.seen.size>1)toast('New simulated scenario routing event.');});}
  async function session(){try{await enter(await api('/api/v1/auth/me'));}catch{}}
  session();
})();
