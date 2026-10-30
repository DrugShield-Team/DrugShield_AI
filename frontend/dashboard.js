(() => {
  'use strict';
  const $ = (s) => document.querySelector(s);
  const state = { user:null, cases:[], selected:null, dispatches:[], hits:[], caseSeen:new Set(), hasLoadedCases:false, timer:null, prefs:loadPreferences(), setGraphMotion:null, view:'overview' };
  const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const when = v => { const d=new Date(v); return v && !Number.isNaN(d.valueOf()) ? d.toLocaleString() : '—'; };
  const channel = v => ({instagram:'Instagram',telegram:'Telegram',whatsapp:'WhatsApp'}[v] || v || 'Unknown');
  const statusName = v => ({pending_review:'Pending review',further_review:'Further review',accepted:'Accepted',dismissed:'Dismissed'}[v] || v || 'Unknown');
  const toast = msg => { const e=$('#toast');e.textContent=msg;e.classList.remove('hidden');setTimeout(()=>e.classList.add('hidden'),2800); };
  function initLoginCursorGlow(){
    const root=$('#login-view'),glow=$('#login-cursor-glow');if(!root||!glow)return;
    root.addEventListener('pointermove',event=>{
      const rect=root.getBoundingClientRect();
      glow.style.left=(event.clientX-rect.left)+'px';
      glow.style.top=(event.clientY-rect.top)+'px';
      glow.classList.add('visible');
    });
    root.addEventListener('pointerleave',()=>glow.classList.remove('visible'));
  }
  function loadPreferences(){
    const defaults={theme:'midnight',textSize:'standard',refreshSeconds:7,animateGraph:true,highContrast:false};
    try{
      const saved=JSON.parse(localStorage.getItem('drugshield-dashboard-preferences-v1')||'{}');
      return{...defaults,...saved,theme:['midnight','ocean'].includes(saved.theme)?saved.theme:'midnight',textSize:['standard','large','larger'].includes(saved.textSize)?saved.textSize:'standard',refreshSeconds:[0,7,15,30,60].includes(Number(saved.refreshSeconds))?Number(saved.refreshSeconds):7,animateGraph:saved.animateGraph!==false,highContrast:saved.highContrast===true};
    }catch{return defaults;}
  }
  function savePreferences(){try{localStorage.setItem('drugshield-dashboard-preferences-v1',JSON.stringify(state.prefs));}catch{}}
  function applyPreferences(){
    const app=$('#app-view');document.documentElement.dataset.theme=state.prefs.theme;
    app.classList.toggle('theme-ocean',state.prefs.theme==='ocean');
    app.classList.remove('text-standard','text-large','text-larger');app.classList.add('text-'+state.prefs.textSize);
    app.classList.toggle('high-contrast',state.prefs.highContrast);
    app.classList.toggle('reduce-motion',!state.prefs.animateGraph);
    $('#settings-theme').value=state.prefs.theme;$('#settings-text-size').value=state.prefs.textSize;
    $('#settings-refresh').value=String(state.prefs.refreshSeconds);$('#settings-animate').checked=state.prefs.animateGraph;$('#settings-contrast').checked=state.prefs.highContrast;
    state.setGraphMotion?.(state.prefs.animateGraph);
  }
  function scheduleRefresh(){
    clearInterval(state.timer);state.timer=null;
    if(state.user&&state.prefs.refreshSeconds>0)state.timer=setInterval(refresh,state.prefs.refreshSeconds*1000);
  }
  function updatePreference(key,value){state.prefs[key]=value;savePreferences();applyPreferences();if(key==='refreshSeconds')scheduleRefresh();}
  function signOut(){fetch('/api/v1/auth/logout',{method:'POST',credentials:'include'}).catch(()=>{});$('#password').value='';$('#settings-dialog').close();lock();}
  async function api(path,options={}) {
    const r=await fetch(path,{credentials:'include',...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});
    if(r.status===401){lock();throw Error('Your session expired. Sign in again.');}
    const data=await r.json().catch(()=>({}));
    if(!r.ok){
      const detail=data.detail;
      const message=typeof detail==='string'?detail:
        Array.isArray(detail)?detail.map(item=>{
          if(typeof item==='string')return item;
          const field=Array.isArray(item?.loc)?item.loc.filter(part=>part!=='body').join('.'):'';
          const reason=typeof item?.msg==='string'?item.msg:typeof item?.message==='string'?item.message:'';
          return field&&reason?field+': '+reason:reason||'Invalid request.';
        }).filter(Boolean).join(' '):
        detail&&typeof detail==='object'?(detail.message||detail.msg||'Request failed.'):'Request failed.';
      throw Error(message||'Request failed.');
    }
    return data;
  }
  function lock(){clearInterval(state.timer);state.timer=null;state.user=null;if($('#settings-dialog').open)$('#settings-dialog').close();$('#app-view').classList.add('hidden');$('#login-view').classList.remove('hidden');}
  async function enter(user){
    if(!user.roles?.some(x=>['reviewer','admin'].includes(x))){$('#login-error').textContent='This account does not have reviewer access.';await fetch('/api/v1/auth/logout',{method:'POST',credentials:'include'});return;}
    state.user=user;state.caseSeen=new Set();state.hasLoadedCases=false;$('#user-name').textContent=user.username;$('#user-initials').textContent=(user.username[0]||'R').toUpperCase();
    $('#user-role').textContent=user.roles.map(role=>role.charAt(0).toUpperCase()+role.slice(1)).join(' · ');
    $('#settings-username').textContent=user.username;$('#settings-roles').textContent=user.roles.join(', ');
    const stationLabel=$('#user-station');
    stationLabel.hidden=!user.station;
    stationLabel.textContent=user.station?'Station: '+user.station:'';
    $('#admin-users-link').classList.toggle('hidden',!user.roles.includes('admin'));
    $('#login-view').classList.add('hidden');$('#app-view').classList.remove('hidden');applyPreferences();await refresh();scheduleRefresh();
    if(user.roles.includes('admin'))loadAdminUsers();
  }
  $('#login-form').addEventListener('submit',async e=>{
    e.preventDefault();const button=e.currentTarget.querySelector('button');button.disabled=true;$('#login-error').textContent='';
    try{await api('/api/v1/auth/token',{method:'POST',body:JSON.stringify({username:$('#username').value.trim(),password:$('#password').value})});$('#password').value='';await enter(await api('/api/v1/auth/me'));}
    catch(err){$('#login-error').textContent=err.message;}finally{button.disabled=false;}
  });
  $('#settings-signout').addEventListener('click',signOut);
  document.querySelectorAll('[data-open-settings]').forEach(button=>button.addEventListener('click',()=>$('#settings-dialog').showModal()));
  $('#settings-dialog').addEventListener('click',event=>{if(event.target===$('#settings-dialog'))$('#settings-dialog').close();});
  $('#settings-theme').addEventListener('change',event=>updatePreference('theme',event.target.value));
  $('#settings-text-size').addEventListener('change',event=>updatePreference('textSize',event.target.value));
  $('#settings-refresh').addEventListener('change',event=>updatePreference('refreshSeconds',Number(event.target.value)));
  $('#settings-animate').addEventListener('change',event=>updatePreference('animateGraph',event.target.checked));
  $('#settings-contrast').addEventListener('change',event=>updatePreference('highContrast',event.target.checked));
  async function loadAdminUsers(){
    const body=$('#reviewer-table-body');if(!body)return;
    body.innerHTML='<tr><td colspan="4" class="empty">Loading accounts…</td></tr>';
    try{
      const data=await api('/api/v1/admin/users');
      const stationSelect=$('#new-reviewer-station');
      stationSelect.innerHTML='<option value="">Choose a station</option>'+(data.stations||[]).map(x=>'<option value="'+esc(x)+'">'+esc(x)+'</option>').join('');
      const users=data.users||[];
      body.innerHTML=users.length?users.map(user=>'<tr data-reviewer="'+esc(user.username)+'"><td><strong>'+esc(user.username)+'</strong><small class="account-source">'+esc(user.source==='environment'?'Configured account':'Dashboard account')+'</small></td><td><select class="reviewer-station" aria-label="Station assigned to '+esc(user.username)+'" data-username="'+esc(user.username)+'"><option value="">Unassigned</option>'+(data.stations||[]).map(station=>'<option value="'+esc(station)+'" '+(user.station===station?'selected':'')+'>'+esc(station)+'</option>').join('')+'</select></td><td><span class="account-status '+(user.active?'is-active':'is-disabled')+'">'+(user.active?'Active':'Disabled')+'</span></td><td>'+(user.source==='dashboard'?'<div class="account-actions"><button class="account-disable" type="button" data-status="'+esc(user.username)+'" data-active="'+(!user.active)+'">'+(user.active?'Disable':'Enable')+'</button><button class="account-reset" type="button" data-reset-password="'+esc(user.username)+'">Reset password</button></div>':'—')+'</td></tr>').join(''):'<tr><td colspan="4" class="empty">No reviewer accounts found.</td></tr>';
    }catch(error){body.innerHTML='<tr><td colspan="4" class="empty">'+esc(error.message)+'</td></tr>';}
  }
  $('#reviewer-create-form').addEventListener('submit',async event=>{
    event.preventDefault();const form=event.currentTarget,message=$('#admin-form-message'),button=form.querySelector('button[type="submit"]');
    message.textContent='';button.disabled=true;
    try{
      await api('/api/v1/admin/users',{method:'POST',body:JSON.stringify({username:$('#new-reviewer-username').value.trim(),password:$('#new-reviewer-password').value,station:$('#new-reviewer-station').value})});
      form.reset();message.textContent='Reviewer account created and assigned.';await loadAdminUsers();
    }catch(error){message.textContent=error.message;}
    finally{button.disabled=false;}
  });
  $('#reviewer-table-body').addEventListener('change',async event=>{
    const select=event.target.closest('.reviewer-station');if(!select)return;
    try{await api('/api/v1/admin/users/'+encodeURIComponent(select.dataset.username)+'/station',{method:'PUT',body:JSON.stringify({station:select.value})});toast('Station assignment saved.');}
    catch(error){toast(error.message);await loadAdminUsers();}
  });
  $('#reviewer-table-body').addEventListener('click',async event=>{
    const statusButton=event.target.closest('[data-status]');
    if(statusButton){
      const username=statusButton.dataset.status,active=statusButton.dataset.active==='true';
      if(!window.confirm((active?'Enable':'Disable')+' reviewer account '+username+'?'))return;
      try{await api('/api/v1/admin/users/'+encodeURIComponent(username)+'/status',{method:'PUT',body:JSON.stringify({active})});toast(active?'Reviewer account enabled.':'Reviewer account disabled.');await loadAdminUsers();}
      catch(error){toast(error.message);}return;
    }
    const resetButton=event.target.closest('[data-reset-password]');if(!resetButton)return;
    const password=window.prompt('Enter a new password of at least 4 characters for '+resetButton.dataset.resetPassword+'.');
    if(password===null)return;
    try{await api('/api/v1/admin/users/'+encodeURIComponent(resetButton.dataset.resetPassword)+'/password',{method:'PUT',body:JSON.stringify({password})});toast('Reviewer password updated.');}
    catch(error){toast(error.message);}
  });
  $('#refresh-reviewers').addEventListener('click',loadAdminUsers);
  applyPreferences();
  $('.sidebar nav').addEventListener('click',event=>{
    const link=event.target.closest('[data-view]');if(!link)return;
    event.preventDefault();setDashboardView(link.dataset.view,{push:true,scroll:true});
  });
  window.addEventListener('popstate',()=>setDashboardView(location.hash.slice(1)||'overview',{push:false,scroll:true}));
  $('#status-filter').addEventListener('change',()=>{renderCases();syncChartSelection();});
  $('#channel-filter').addEventListener('change',()=>{renderCases();syncChartSelection();});
  $('#case-search').addEventListener('input',renderCases);
  $('#case-search').addEventListener('paste',event=>{
    const text=event.clipboardData?.getData('text/plain');
    if(text==null)return;
    event.preventDefault();
    const input=event.currentTarget,start=input.selectionStart??input.value.length,end=input.selectionEnd??input.value.length;
    input.value=input.value.slice(0,start)+text+input.value.slice(end);
    const cursor=start+text.length;input.setSelectionRange(cursor,cursor);input.dispatchEvent(new Event('input',{bubbles:true}));
  });
  $('#paste-search').addEventListener('click',async()=>{
    const input=$('#case-search');input.focus();
    let text;
    try{
      if(!navigator.clipboard?.readText)throw new Error('Clipboard access is unavailable');
      text=await navigator.clipboard.readText();
    }catch{text=window.prompt('Clipboard access was blocked. Paste text here to search cases:');if(text===null)return;}
    if(!text){toast('The clipboard has no text to paste.');return;}
    input.value=text;input.dispatchEvent(new Event('input',{bubbles:true}));
  });
  $('#clear-chart-filters').addEventListener('click',clearChartFilters);
  ['#status-chart','#channel-chart'].forEach(selector=>{
    const box=$(selector);
    box.addEventListener('click',event=>{const target=event.target.closest('[data-chart-filter]');if(target)applyChartFilter(target.dataset.filterKind,target.dataset.chartFilter);});
    box.addEventListener('keydown',event=>{const target=event.target.closest('[data-chart-filter]');if(target&&['Enter',' '].includes(event.key)){event.preventDefault();applyChartFilter(target.dataset.filterKind,target.dataset.chartFilter);}});
  });
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
    if(results[0].status==='fulfilled'){
      state.cases=results[0].value.cases||[];renderCases();renderMetrics();renderAnalytics();
      const nextSeen=new Set(state.cases.map(item=>item.case_id));
      if(state.hasLoadedCases){
        const added=state.cases.find(item=>!state.caseSeen.has(item.case_id));
        if(added){const summary=added.summary||{};toast('New simulated case for '+(summary.jurisdiction||state.user.station||'review')+' · '+channel(summary.channel)+'.');}
      }
      state.caseSeen=nextSeen;state.hasLoadedCases=true;
    }
    else{failed=true;$('#case-table-body').innerHTML='<tr><td colspan="5" class="empty">Case data unavailable.</td></tr>';}
    if(results[1].status==='fulfilled')renderGraph(results[1].value);else{failed=true;$('#graph-container').innerHTML='<p class="empty">Graph data unavailable.</p>';}
    if(results[2].status==='fulfilled'){state.dispatches=results[2].value.alerts||[];renderActivity();}
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
  function renderAnalytics(){
    const cases=state.cases;
    const statusData=[['Pending',cases.filter(x=>x.status==='pending_review').length,'#8d7cff'],['Further review',cases.filter(x=>x.status==='further_review').length,'#4aa6ff'],['Accepted',cases.filter(x=>x.status==='accepted').length,'#45d4ad'],['Dismissed',cases.filter(x=>x.status==='dismissed').length,'#b078df']];
    const channelData=['instagram','telegram','whatsapp'].map(key=>[channel(key),cases.filter(x=>(x.summary||{}).channel===key).length,key]);
    const knownChannels=['instagram','telegram','whatsapp'];
    const unknown=cases.filter(x=>!knownChannels.includes((x.summary||{}).channel)).length;if(unknown)channelData.push(['Other',unknown,'other']);
    const statusBox=$('#status-chart'),channelBox=$('#channel-chart');
    if(!cases.length){statusBox.innerHTML='<p class="empty">No case records are available for this chart.</p>';channelBox.innerHTML='<p class="empty">No case records are available for this chart.</p>';return;}
    const width=520,height=350,base=276,top=30,max=Math.max(1,...statusData.map(x=>x[1]));
    const grid=[0,1,2,3].map(i=>{const y=top+(base-top)*i/3;return'<line class="chart-grid" x1="42" y1="'+y+'" x2="505" y2="'+y+'"/><text class="chart-tick" x="32" y="'+(y+3)+'" text-anchor="end">'+Math.round(max*(1-i/3))+'</text>';}).join('');
    const barWidth=52,gap=58,bars=statusData.map((d,i)=>{const filterValue=['pending_review','further_review','accepted','dismissed'][i],h=Math.max(d[1]?5:0,(base-top)*d[1]/max),x=69+i*(barWidth+gap),y=base-h;return'<g class="chart-target" data-chart-filter="'+filterValue+'" data-filter-kind="status" tabindex="0" role="button" aria-pressed="false" aria-label="Filter case queue by '+esc(d[0])+', '+d[1]+' cases"><title>'+esc(d[0])+': '+d[1]+' cases. Select to filter the case queue.</title><rect class="chart-bar" x="'+x+'" y="'+y+'" width="'+barWidth+'" height="'+h+'" rx="8" fill="'+d[2]+'"/><text class="chart-value" x="'+(x+barWidth/2)+'" y="'+(y-8)+'" text-anchor="middle">'+d[1]+'</text><text class="chart-label" x="'+(x+barWidth/2)+'" y="320" text-anchor="middle">'+esc(d[0])+'</text></g>';}).join('');
    statusBox.innerHTML='<svg class="analytics-svg" role="group" aria-label="Case counts by review status" viewBox="0 0 '+width+' '+height+'" preserveAspectRatio="none">'+grid+bars+'</svg>';
    const cmax=Math.max(1,...channelData.map(x=>x[1])),plotLeft=42,plotRight=505,plotTop=30,plotBottom=276,step=channelData.length>1?(plotRight-plotLeft)/(channelData.length-1):0;
    const points=channelData.map((d,i)=>({x:plotLeft+i*step,y:plotBottom-(plotBottom-plotTop)*d[1]/cmax,label:d[0],value:d[1]}));
    const line=points.map((p,i)=>(i?'L':'M')+' '+p.x+' '+p.y).join(' '),area=line+' L '+points[points.length-1].x+' '+plotBottom+' L '+points[0].x+' '+plotBottom+' Z';
    const channelGrid=[0,1,2,3].map(i=>{const y=plotTop+(plotBottom-plotTop)*i/3;return'<line class="chart-grid" x1="42" y1="'+y+'" x2="505" y2="'+y+'"/><text class="chart-tick" x="32" y="'+(y+3)+'" text-anchor="end">'+Math.round(cmax*(1-i/3))+'</text>';}).join('');
    const labels=points.map((p,i)=>'<g class="chart-target" data-chart-filter="'+channelData[i][2]+'" data-filter-kind="channel" tabindex="0" role="button" aria-pressed="false" aria-label="Filter case queue by '+esc(p.label)+', '+p.value+' cases"><title>'+esc(p.label)+': '+p.value+' cases. Select to filter the case queue.</title><circle class="chart-point" cx="'+p.x+'" cy="'+p.y+'" r="4"/><text class="chart-label" x="'+p.x+'" y="320" text-anchor="middle">'+esc(p.label)+'</text></g>').join('');
    channelBox.innerHTML='<svg class="analytics-svg" role="group" aria-label="Case counts by simulation channel" viewBox="0 0 '+width+' '+height+'" preserveAspectRatio="none"><defs><linearGradient id="channelFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#27c6e6" stop-opacity=".46"/><stop offset="1" stop-color="#27c6e6" stop-opacity=".02"/></linearGradient></defs>'+channelGrid+'<path class="chart-area" d="'+area+'"/><path class="chart-line" d="'+line+'"/>'+labels+'</svg>';
    syncChartSelection();
  }
  function applyChartFilter(kind,value){
    const control=kind==='status'?$('#status-filter'):$('#channel-filter');
    control.value=control.value===value?'':value;
    renderCases();syncChartSelection();setDashboardView('case-queue',{push:true,scroll:true});
  }
  function setDashboardView(target,{push=false,scroll=false}={}){
    const valid=['overview','case-queue','scenario-activity','admin-users'];
    if(!valid.includes(target))target='overview';
    if(target==='admin-users'&&!state.user?.roles.includes('admin'))target='overview';
    const casePage=target==='case-queue',scenarioPage=target==='scenario-activity',adminPage=target==='admin-users',separatePage=casePage||scenarioPage||adminPage,main=$('#app-view main');state.view=target;
    main.classList.toggle('case-page',casePage);main.classList.toggle('scenario-page',scenarioPage);
    main.classList.toggle('admin-page',adminPage);
    $('#overview').classList.toggle('hidden',separatePage);
    $('#network-analysis').classList.toggle('hidden',separatePage);
    $('#case-analytics').classList.toggle('hidden',separatePage);
    $('#scenario-activity').classList.toggle('hidden',!scenarioPage);
    $('#case-queue').classList.toggle('hidden',!casePage);
    $('#admin-users').classList.toggle('hidden',!adminPage);
    $('#topbar-page-title').textContent=casePage?'Case queue':scenarioPage?'Scenario activity':adminPage?'User management':'Evidence review';
    document.querySelectorAll('.sidebar nav [data-view]').forEach(link=>{
      const active=link.dataset.view===target;link.classList.toggle('active',active);
      if(active)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');
    });
    if(push&&location.hash!=='#'+target)history.pushState({dashboardView:target},'','#'+target);
    if(adminPage)loadAdminUsers();
    if(scroll){
      window.scrollTo({top:0,behavior:'auto'});
    }
  }
  function clearChartFilters(){
    $('#status-filter').value='';$('#channel-filter').value='';
    renderCases();syncChartSelection();
  }
  function syncChartSelection(){
    const status=$('#status-filter').value,channelValue=$('#channel-filter').value;
    document.querySelectorAll('[data-chart-filter]').forEach(target=>{
      const selected=target.dataset.filterKind==='status'?status===target.dataset.chartFilter:channelValue===target.dataset.chartFilter;
      target.classList.toggle('is-selected',selected);target.setAttribute('aria-pressed',String(selected));
    });
    $('#clear-chart-filters').hidden=!(status||channelValue);
  }
  function renderCases(){
    const filter=$('#status-filter').value,channelFilter=$('#channel-filter').value,q=$('#case-search').value.trim().toLowerCase();
    const knownChannels=['instagram','telegram','whatsapp'];
    const items=state.cases.filter(x=>{const s=x.summary||{};const all=[x.case_id,x.status,s.channel,s.sender_display_name,s.recipient_display_name,s.message_text,s.simulated_locality,s.jurisdiction].join(' ').toLowerCase();const channelMatches=!channelFilter||(channelFilter==='other'?!knownChannels.includes(s.channel):s.channel===channelFilter);return(!filter||x.status===filter)&&channelMatches&&(!q||all.includes(q));});
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
    '<div class="detail-block"><h4>Conversation context</h4><div class="facts"><div class="fact"><span>Sender</span><strong>'+esc(s.sender_display_name||s.sender_id||'—')+'</strong></div><div class="fact"><span>Recipient</span><strong>'+esc(s.recipient_display_name||s.recipient_id||'—')+'</strong></div><div class="fact"><span>Conversation</span><strong>'+esc(s.conversation_id||'—')+'</strong></div><div class="fact"><span>Message time</span><strong>'+esc(when(s.timestamp))+'</strong></div><div class="fact"><span>Simulated locality</span><strong>'+esc(s.simulated_locality||'Not provided')+'</strong></div><div class="fact"><span>Assigned jurisdiction</span><strong>'+esc(s.jurisdiction||'Unassigned')+'</strong></div></div><div class="detail-copy">'+esc(s.message_text||'(No text content)')+'</div></div>'+
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
    const box=$('#graph-container');
    const signature=JSON.stringify([nodes,edges]);
    if(box._graphSignature===signature&&box.querySelector('canvas'))return;
    if(box._graphCleanup){box._graphCleanup();state.setGraphMotion=null;}
    box._graphSignature=signature;
    if(!nodes.length){box.classList.remove('is-3d');box.innerHTML='<p class="empty">No entity relationships available.</p>';return;}
    box.classList.add('is-3d');
    box.innerHTML='<canvas class="network-canvas" role="img" aria-label="Interactive 3D evidence relationship graph. Drag to rotate, scroll to zoom, and focus then use arrow keys to explore." tabindex="0"></canvas><div class="network-tooltip" aria-live="polite"></div><div class="graph-hint">Auto-rotating · drag to orbit · scroll to zoom · hover for labels · arrow keys to explore</div>';
    const canvas=box.querySelector('canvas'),ctx=canvas.getContext('2d'),tooltip=box.querySelector('.network-tooltip');
    if(!ctx){box.innerHTML='<p class="empty">Interactive graph rendering is unavailable in this browser.</p>';return;}
    const nodeIndex=new Map(nodes.map((node,index)=>[node.id,index]));
    const links=edges.map(edge=>({source:nodeIndex.get(edge.source),target:nodeIndex.get(edge.target),type:edge.type})).filter(edge=>Number.isInteger(edge.source)&&Number.isInteger(edge.target)&&edge.source!==edge.target);
    const degree=nodes.map(()=>0);links.forEach(edge=>{degree[edge.source]++;degree[edge.target]++;});
    const goldenAngle=Math.PI*(3-Math.sqrt(5));
    const points=nodes.map((node,index)=>{const y=1-2*(index+.5)/nodes.length,r=Math.sqrt(Math.max(0,1-y*y)),angle=index*goldenAngle;return{x:r*Math.cos(angle),y,z:r*Math.sin(angle)};});
    const colors={fictional_participant:'#58d6ff',message:'#9a89ff',attachment:'#f2b866',candidate_vpa:'#ff79bc'};
    let width=0,height=0,dpr=1,rotation=0,tilt=-.12,zoom=1,frame=0,hover=-1,dragging=false,lastPointer=null,projected=[];
    const reduceMotion=window.matchMedia('(prefers-reduced-motion: reduce)');
    function resize(){const rect=box.getBoundingClientRect();width=Math.max(1,rect.width);height=Math.max(1,rect.height);dpr=Math.min(window.devicePixelRatio||1,2);canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);canvas.style.width=width+'px';canvas.style.height=height+'px';}
    function project(){
      projected=points.map(projectPoint);
    }
    function projectPoint(point){
      const cy=Math.cos(rotation),sy=Math.sin(rotation),cx=Math.cos(tilt),sx=Math.sin(tilt),scale=Math.min(width*.41,height*.4)*zoom,camera=4.2;
      const x=point.x*cy-point.z*sy,z0=point.x*sy+point.z*cy,y=point.y*cx-z0*sx,z=z0*cx+point.y*sx,perspective=camera/(camera-z);
      return{x:width/2+x*scale*perspective,y:height/2+y*scale*perspective,z,perspective};
    }
    function drawWire(samples,closed=true){ctx.beginPath();samples.forEach((point,index)=>{const p=projectPoint(point);if(index===0)ctx.moveTo(p.x,p.y);else ctx.lineTo(p.x,p.y);});if(closed)ctx.closePath();ctx.stroke();}
    function draw(){
      if(!width||!height)return;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);project();
      const cx=width/2,cy=height/2,r=Math.min(width*.41,height*.4)*zoom;
      const halo=ctx.createRadialGradient(cx,cy,0,cx,cy,r*1.45);halo.addColorStop(0,'rgba(18,91,206,.22)');halo.addColorStop(.78,'rgba(9,38,110,.09)');halo.addColorStop(1,'rgba(9,20,58,0)');ctx.fillStyle=halo;ctx.fillRect(0,0,width,height);
      for(let latitude=-1.12;latitude<=1.13;latitude+=.56){const ring=[];for(let i=0;i<72;i++){const angle=i*Math.PI*2/72,latRadius=Math.cos(latitude);ring.push({x:latRadius*Math.cos(angle),y:Math.sin(latitude),z:latRadius*Math.sin(angle)});}ctx.strokeStyle=latitude===0?'rgba(43,151,255,.31)':'rgba(43,151,255,.19)';ctx.lineWidth=.8;drawWire(ring);}
      for(let longitude=0;longitude<Math.PI;longitude+=Math.PI/8){const arc=[];for(let i=0;i<=64;i++){const angle=i*Math.PI*2/64,ring=Math.sin(angle);arc.push({x:ring*Math.cos(longitude),y:Math.cos(angle),z:ring*Math.sin(longitude)});}ctx.strokeStyle='rgba(43,151,255,.22)';ctx.lineWidth=.8;drawWire(arc);}
      ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.strokeStyle='rgba(42,145,255,.68)';ctx.lineWidth=1.2;ctx.shadowColor='rgba(35,135,255,.7)';ctx.shadowBlur=8;ctx.stroke();ctx.shadowBlur=0;
      const hoveredNeighbors=new Set();if(hover>=0)links.forEach(edge=>{if(edge.source===hover)hoveredNeighbors.add(edge.target);if(edge.target===hover)hoveredNeighbors.add(edge.source);});
      const alwaysLabelled=new Set(projected.map((point,index)=>({point,index})).filter(x=>x.point.z>.12&&nodes[x.index].type!=='message').sort((a,b)=>b.point.z-a.point.z).slice(0,10).map(x=>x.index));
      links.forEach(edge=>{
        const a=projected[edge.source],b=projected[edge.target],focused=hover===edge.source||hover===edge.target,opacity=focused ? .92 : .12+Math.max(0,(a.z+b.z)/2)*.25;
        ctx.beginPath();ctx.setLineDash(focused?[]:[3,4]);ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.strokeStyle=focused?'rgba(79,218,255,.98)':'rgba(53,168,225,'+opacity+')';ctx.lineWidth=focused?1.7:.9;ctx.stroke();ctx.setLineDash([]);
      });
      projected.map((point,index)=>({point,index})).sort((a,b)=>a.point.z-b.point.z).forEach(({point,index})=>{
        const node=nodes[index],isFocused=hover===index||hoveredNeighbors.has(index),radius=(2.6+Math.max(0,point.z)*1.8+(degree[index]>3?1:0))*Math.min(1.25,point.perspective);
        ctx.beginPath();ctx.arc(point.x,point.y,radius+(hover===index?2:0),0,Math.PI*2);ctx.fillStyle=colors[node.type]||'#6ebcff';ctx.globalAlpha=hover>=0&&!isFocused ? .26 : .38+Math.max(0,point.z)*.62;ctx.shadowColor=colors[node.type]||'#6ebcff';ctx.shadowBlur=isFocused?16:7;ctx.fill();ctx.shadowBlur=0;ctx.globalAlpha=1;
        const showLabel=hover===index||alwaysLabelled.has(index);
        if(showLabel){ctx.font=(hover===index?'600 11px':'9px')+' Inter, Segoe UI, sans-serif';ctx.textAlign='center';ctx.fillStyle='#dceeff';ctx.shadowColor='#07152d';ctx.shadowBlur=4;ctx.fillText(String(node.label||node.name||node.id),point.x,point.y-radius-8);ctx.shadowBlur=0;}
      });
      if(hover>=0){const node=nodes[hover];tooltip.textContent=(node.label||node.name||node.id)+' · '+String(node.type||'evidence entity').replace(/_/g,' ');tooltip.classList.add('visible');}
      else tooltip.classList.remove('visible');
    }
    function shouldAnimate(){return state.prefs.animateGraph&&!reduceMotion.matches;}
    function animate(){if(document.hidden){frame=0;return;}if(!dragging&&shouldAnimate())rotation+=.0018;draw();frame=shouldAnimate()?requestAnimationFrame(animate):0;}
    function pointFromEvent(event){const rect=canvas.getBoundingClientRect();return{x:event.clientX-rect.left,y:event.clientY-rect.top};}
    function onPointerDown(event){dragging=true;lastPointer=pointFromEvent(event);canvas.setPointerCapture?.(event.pointerId);canvas.classList.add('dragging');}
    function onPointerMove(event){const p=pointFromEvent(event);if(dragging&&lastPointer){rotation+=(p.x-lastPointer.x)*.008;tilt=Math.max(-1.1,Math.min(1.1,tilt+(p.y-lastPointer.y)*.006));lastPointer=p;return;}project();let nearest=-1,best=15;projected.forEach((q,i)=>{const distance=Math.hypot(q.x-p.x,q.y-p.y);if(distance<best){best=distance;nearest=i;}});hover=nearest;canvas.style.cursor=nearest>=0?'pointer':'grab';}
    function onPointerUp(){dragging=false;lastPointer=null;canvas.classList.remove('dragging');}
    function onWheel(event){event.preventDefault();zoom=Math.max(.65,Math.min(1.65,zoom*(event.deltaY<0?1.08:.92)));}
    function onKeyDown(event){const step=.14;if(event.key==='ArrowLeft')rotation-=step;else if(event.key==='ArrowRight')rotation+=step;else if(event.key==='ArrowUp')tilt=Math.max(-1.1,tilt-step);else if(event.key==='ArrowDown')tilt=Math.min(1.1,tilt+step);else if(event.key==='+'||event.key==='=')zoom=Math.min(1.65,zoom*1.1);else if(event.key==='-')zoom=Math.max(.65,zoom/1.1);else return;event.preventDefault();draw();}
    canvas.addEventListener('pointerdown',onPointerDown);canvas.addEventListener('pointermove',onPointerMove);canvas.addEventListener('pointerup',onPointerUp);canvas.addEventListener('pointercancel',onPointerUp);canvas.addEventListener('pointerleave',()=>{if(!dragging){hover=-1;tooltip.classList.remove('visible');}});canvas.addEventListener('wheel',onWheel,{passive:false});canvas.addEventListener('keydown',onKeyDown);
    const observer=new ResizeObserver(resize);observer.observe(box);const onVisibility=()=>{if(!document.hidden&&!frame)animate();};document.addEventListener('visibilitychange',onVisibility);
    state.setGraphMotion=enabled=>{if(enabled&&shouldAnimate()){if(!frame)animate();}else{cancelAnimationFrame(frame);frame=0;draw();}};
    resize();if(shouldAnimate())animate();else draw();
    box._graphCleanup=()=>{cancelAnimationFrame(frame);observer.disconnect();document.removeEventListener('visibilitychange',onVisibility);};
  }
  function renderActivity(){
    $('#dispatch-list').innerHTML=state.dispatches.length?state.dispatches.map(x=>{const d=x.details||{},node=d.assigned_precinct||{};return '<article class="activity-item"><strong><span>Scenario '+esc(x.tracking_token||d.tracking_token||x.id||'event')+'</span><time>'+esc(when(x.created_at||d.timestamp))+'</time></strong><p>Nearest simulation node: '+esc(x.precinct_name||node.name||'Not assigned')+' · route '+esc(x.distance_km??node.distance_km??'—')+' km / '+esc(x.eta_minutes??node.estimated_eta_minutes??'—')+' min. Synthetic scenario only.</p></article>';}).join(''):'<p class="empty">No scenario routing events.</p>';
    $('#hit-list').innerHTML=state.hits.length?state.hits.map(x=>'<article class="activity-item"><strong><span>Scenario '+esc(x.tracking_token||x.id||'event')+'</span><time>'+esc(when(x.created_at))+'</time></strong><p>Fictional scenario location: '+esc([x.city,x.region].filter(Boolean).join(', ')||'not specified')+'. No visitor IP, device fingerprint, or GPS data is collected.</p></article>').join(''):'<p class="empty">No scenario access events.</p>';
  }
  initLoginCursorGlow();
  setDashboardView(location.hash.slice(1)||'overview',{push:false,scroll:false});
  async function session(){try{await enter(await api('/api/v1/auth/me'));}catch{}}
  session();
})();
