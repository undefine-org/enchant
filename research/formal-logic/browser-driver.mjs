// Owned packet-4 JSON browser helper for the ordinary BL Scenario Runner.
// No HTTP listener and no npm dependencies. EOF always disposes the browser.
import {spawn} from 'node:child_process';
import {mkdtemp,readFile,writeFile,mkdir,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve,sep} from 'node:path';
let browser, profile, ws, session, next=0, closing, buffer=Buffer.alloc(0), chain=Promise.resolve();
const pending=new Map(); const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function rpc(method,params={}) {
 const id=++next;
 return new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout: '+method));},15000);
  pending.set(id,{resolve,reject,timer});
  ws.send(JSON.stringify({id,method,params,...(session?{sessionId:session}:{})}));
 });
}
async function evaluate(expression) {
 const result=await rpc('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
 if(result.exceptionDetails)throw Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);
 return result.result.value??null;
}
async function cleanup() {
 if(closing)return closing;
 return closing=(async()=>{
  if(ws?.readyState===WebSocket.OPEN){await rpc('Browser.close').catch(()=>{});ws.close();}
  if(browser?.exitCode===null){try{process.kill(-browser.pid,'SIGTERM');}catch{}
   for(let i=0;i<20&&browser.exitCode===null;i++)await sleep(50);
   if(browser.exitCode===null)try{process.kill(-browser.pid,'SIGKILL');}catch{}
  }
  if(profile)await rm(profile,{recursive:true,force:true});
 })();
}
async function dispatch(message) {
 switch(message.op){
 case 'open':{
  profile=await mkdtemp(join(tmpdir(),'formal-story-browser-'));
  const flags=['--headless=new','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0',
    '--user-data-dir='+profile,'--disable-background-networking','--disable-extensions','--disable-sync',
    '--disable-dev-shm-usage','--no-first-run','--no-default-browser-check','--hide-scrollbars','about:blank'];
  if(process.getuid?.()===0)flags.unshift('--no-sandbox');
  browser=spawn('/home/othman/.nix-profile/bin/chromium',flags,{detached:true,stdio:['ignore','ignore','ignore']});
  let active;
  for(let i=0;i<150;i++){try{active=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).trim().split('\n');break;}catch{await sleep(100);}}
  if(!active)throw Error('Chromium did not become ready');
  ws=new WebSocket('ws://127.0.0.1:'+active[0]+active[1]);
  await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
  ws.addEventListener('message',event=>{const message=JSON.parse(String(event.data));if(!message.id)return;const p=pending.get(message.id);if(!p)return;
   pending.delete(message.id);clearTimeout(p.timer);message.error?p.reject(Error(JSON.stringify(message.error))):p.resolve(message.result);});
  const target=await rpc('Target.createTarget',{url:'about:blank'});
  session=(await rpc('Target.attachToTarget',{targetId:target.targetId,flatten:true})).sessionId;
  await rpc('Page.enable');await rpc('Runtime.enable');await rpc('Network.enable');
  await rpc('Network.setBlockedURLs',{urls:['https://fonts.googleapis.com/*','https://fonts.gstatic.com/*']});
  await rpc('Emulation.setDeviceMetricsOverride',{width:message.width||390,height:message.height||844,deviceScaleFactor:1,mobile:true});
  await rpc('Emulation.setEmulatedMedia',{features:[{name:'prefers-color-scheme',value:'light'},{name:'prefers-reduced-motion',value:'reduce'}]});
  return {pid:browser.pid,width:message.width||390,height:message.height||844};
 }
 case 'navigate':
  await rpc('Page.navigate',{url:message.url});
  for(let i=0;i<150;i++){if(await evaluate("document.readyState==='complete'").catch(()=>false))break;await sleep(50);}
  await sleep(150);return true;
 case 'eval':return evaluate(message.expression);
 case 'wait':
  for(let i=0;i<120;i++){if(await evaluate(message.expression).catch(()=>false))return true;await sleep(50);}
  throw Error('Timed out waiting for '+message.expression);
 case 'click':{
  const point=await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(message.selector)});if(!e)throw Error('Missing control');e.scrollIntoView({block:'center',inline:'nearest'});const r=e.getBoundingClientRect();const x=Math.max(1,Math.min(innerWidth-2,r.x+r.width/2)),y=Math.max(1,Math.min(innerHeight-2,r.y+r.height/2));const h=document.elementFromPoint(x,y);if(!h||!(e===h||e.contains(h)))throw Error('Obscured control');return{x,y}})()`);
  await rpc('Input.dispatchMouseEvent',{type:'mousePressed',...point,button:'left',clickCount:1});
  await rpc('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'left',clickCount:1});await sleep(100);return true;
 }
 case 'screenshot':{
  const file=resolve(message.path);const root=resolve(process.argv[2]);
  if(!file.startsWith(root+sep))throw Error('Frame path outside owned output');
  await mkdir(root,{recursive:true});const shot=await rpc('Page.captureScreenshot',{format:'png',captureBeyondViewport:false,fromSurface:true});
  await writeFile(file,Buffer.from(shot.data,'base64'));return {path:file,recordedAt:Date.now()};
 }
 case 'stop':await cleanup();return {closed:true};
 default:throw Error('Unknown browser operation');
 }
}
function send(value){const body=Buffer.from(JSON.stringify(value));const size=Buffer.alloc(4);size.writeUInt32BE(body.length);process.stdout.write(Buffer.concat([size,body]));}
process.stdin.on('data',data=>{
 buffer=Buffer.concat([buffer,data]);
 while(buffer.length>=4){const size=buffer.readUInt32BE(0);if(size>1048576){cleanup().finally(()=>process.exit(1));return;}if(buffer.length<4+size)break;
  const packet=buffer.subarray(4,4+size);buffer=buffer.subarray(4+size);
  chain=chain.then(async()=>{try{const request=JSON.parse(packet.toString());send({ok:true,result:await dispatch(request)});}catch(error){send({ok:false,error:error.message});}});
 }
});
process.stdin.on('end',()=>cleanup().finally(()=>process.exit(0)));
for(const sig of ['SIGTERM','SIGINT'])process.on(sig,()=>cleanup().finally(()=>process.exit(0)));
