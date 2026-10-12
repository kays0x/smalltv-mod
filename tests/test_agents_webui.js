// Exercise the real Agents settings and controls without a device or browser.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const html=fs.readFileSync('src/webui.html','utf8');
const script=html.slice(html.indexOf('<script>')+8,html.indexOf('</script>'));
new vm.Script(script);
const nodes={};
for(const id of ['agents','agentsUrl','agentsRefreshSec','agentsPageSec','agentsAutoRotate',
 'agentsClockThemeId','agentsTouchEnabled','agentsTouchSensitivity','agentsStatus','agentsRotationBtn',
 'agentsTouchStatus','agentsCalibrateBtn','mode','carouselAgents']){
 nodes[id]={value:'',checked:false,disabled:false,innerHTML:'',children:[],
  appendChild(child){this.children.push(child)},
  get textContent(){return this.text||''},
  set textContent(value){this.text=value;this.children=[]}};
}
let requests=[],response={},lastToast='';
const context={C:{agents:{}},Promise,JSON,Math,parseInt,
 $:id=>nodes[id],
 sv:(id,value)=>{if(nodes[id])nodes[id].value=value},
 sc:(id,value)=>{if(nodes[id])nodes[id].checked=!!value},
 gv:id=>nodes[id]?nodes[id].value:'',gc:id=>!!(nodes[id]&&nodes[id].checked),
 document:{createElement:()=>({}),querySelectorAll:()=>[]},
 toast:message=>{lastToast=message},collectWifi:()=>[],TZMAP:{},
 j:async(path,options)=>{requests.push([path,options]);return response[path]||{}},
 themeEntries:[],
};
vm.createContext(context);
vm.runInContext(html.slice(html.indexOf('// Agents settings'),html.indexOf('// OTA\nfunction themeRequest')),context);
vm.runInContext(html.slice(html.indexOf('function agentsClockChoices'),html.indexOf('function loadThemes')),context);
vm.runInContext(html.slice(html.indexOf('function esc('),html.indexOf('function symHintFor')),context);
vm.runInContext(html.slice(html.indexOf('function kv('),html.indexOf('// WireGuard: one line')),context);
vm.runInContext(html.slice(html.indexOf('function collect(){'),html.indexOf('function saveAll')),context);

(async()=>{
 context.loadAgentsConfig({});
 assert.equal(nodes.agentsTouchEnabled.checked,false,'touch stays opt-in');
 assert.equal(nodes.agentsAutoRotate.checked,true);
 assert.equal(nodes.agentsRefreshSec.value,5);
 assert.equal(nodes.agentsPageSec.value,20);
 assert.equal(nodes.agentsTouchSensitivity.value,88,'legacy settings receive the default threshold');
 nodes.agentsTouchSensitivity.value='99';assert.equal(context.collectAgentsConfig().touchSensitivity,95);
 nodes.agentsTouchSensitivity.value='60';assert.equal(context.collectAgentsConfig().touchSensitivity,75);
 const settings={url:'http://bridge.local:9879/agents.json',refreshSec:7,pageSec:45,
  autoRotate:false,clockThemeId:'pixel-room',touchEnabled:true,touchSensitivity:90};
 context.loadAgentsConfig(settings);
 context.themeEntries=[{id:'pixel-room',name:'Pixel room',valid:true},
  {id:'invalid',name:'Broken clock',valid:false}];
 context.agentsClockChoices();
 assert.equal(nodes.agentsClockThemeId.value,'pixel-room');
 assert.equal(nodes.agentsClockThemeId.children.length,2,'invalid themes excluded');
 assert.deepEqual(JSON.parse(JSON.stringify(context.collectAgentsConfig())),settings);
 nodes.mode.value='agents';nodes.carouselAgents.checked=true;
 const collected=JSON.parse(JSON.stringify(context.collect()));
 assert.equal(collected.mode,'agents');assert.equal(collected.carouselAgents,true);
 assert.deepEqual(collected.agents,settings,'normal Save settings includes complete Agents slice');
 nodes.agentsClockThemeId.value='';context.agentsClockChoices();
 assert.equal(nodes.agentsClockThemeId.value,'','reload must not undo explicit no-clock choice');
 context.loadAgentsConfig({...settings,clockThemeId:'missing-clock'});context.agentsClockChoices();
 assert.equal(nodes.agentsClockThemeId.value,'missing-clock','unavailable saved theme remains visible');
 assert.match(nodes.agentsClockThemeId.children.at(-1).textContent,/unavailable/);
 const status={valid:true,fresh:true,ageSec:3,page:2,pages:4,title:'<script>private</script>',
  autoRotate:false,clockActive:false,error:'<img src=x onerror=x>',fetching:false};
 context.renderAgentsStatus(status);
 assert.match(nodes.agentsStatus.innerHTML,/3 \/ 4/);
 assert.match(nodes.agentsStatus.innerHTML,/>View<.*>Agents</);
 context.renderAgentsStatus({...status,clockActive:true});
 assert.match(nodes.agentsStatus.innerHTML,/>View<.*>Clock</);
 assert.equal(nodes.mode.value,'agents','runtime clock switching must preserve selected mode');
 assert.doesNotMatch(nodes.agentsStatus.innerHTML,/<script>|<img/,'feed text must be escaped');
 assert.match(nodes.agentsStatus.innerHTML,/&lt;script&gt;/);
 assert.equal(nodes.agentsRotationBtn.textContent,'Resume rotation');
 context.renderTouchStatus({supported:false});
 assert.equal(nodes.agentsTouchEnabled.disabled,true);
 assert.equal(nodes.agentsCalibrateBtn.disabled,true);
 assert.equal(nodes.agentsTouchSensitivity.disabled,true);
 const touch={supported:true,enabled:false,raw:100,baseline:105,pressed:false,
  calibrated:true,min:80,max:110,pressThreshold:92,releaseThreshold:98,
  thresholdPercent:88,releasePercent:94,single:2,double:1,hold:0,lastGesture:'single'};
 context.renderTouchStatus(touch);
 assert.equal(nodes.agentsTouchEnabled.disabled,false);
 assert.equal(nodes.agentsTouchSensitivity.disabled,false);
 assert.equal(nodes.agentsCalibrateBtn.disabled,false,'diagnostics and calibration work with gestures disabled');
 assert.match(nodes.agentsTouchStatus.innerHTML,/100 \/ 105/);
 assert.match(nodes.agentsTouchStatus.innerHTML,/80 \/ 110/);
 assert.match(nodes.agentsTouchStatus.innerHTML,/92 \(88%\)/);
 assert.match(nodes.agentsTouchStatus.innerHTML,/98 \(94%\)/);
 assert.equal(nodes.agentsTouchSensitivity.value,90,'diagnostics preserve an unsaved sensitivity choice');
 response={'/api/agents/status':status,'/api/touch':touch,
  '/api/agents/control':{...status,autoRotate:true},'/api/touch/calibrate':touch};
 requests=[];await context.agentsControl('toggleRotation');
 assert.equal(requests[0][0],'/api/agents/control');
 assert.deepEqual(JSON.parse(requests[0][1].body),{action:'toggleRotation'});
 assert.equal(nodes.agentsAutoRotate.checked,true,'control result must not be undone by later Save settings');
 assert.equal(context.C.agents.autoRotate,true);
 response['/api/touch/calibrate']={...touch,calibrated:false};
 response['/api/touch']={...touch,calibrated:false};
 requests=[];await context.calibrateTouch();
 assert.equal(requests[0][0],'/api/touch/calibrate');
 assert.equal(requests[0][1].body,'{}');assert.equal(lastToast,'Calibration started; keep your hand off the top');
 assert.match(nodes.agentsTouchStatus.innerHTML,/Not calibrated/,'asynchronous calibration must not claim completion');
 context.j=async()=>{throw new Error('Device unavailable')};
 await context.loadAgentsStatus();
 assert.equal(nodes.agentsStatus.textContent,'Device unavailable');
 assert.equal(nodes.agentsTouchStatus.textContent,'Device unavailable');
 assert.equal(context.agentsStatusBusy,false,'failure releases polling lock');
 delete nodes.agents;
 assert.equal('agents' in context.collect(),false,'missing feature tab cannot erase stored settings');
 console.log('Agents web UI tests passed');
})().catch(error=>{console.error(error);process.exitCode=1});
