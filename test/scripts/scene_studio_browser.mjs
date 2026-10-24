// Owned studio at 4048, Chromium CDP at 9224. Uses Node's built-in WebSocket.
import {writeFileSync} from 'node:fs';
const tabs=await(await fetch('http://127.0.0.1:9224/json')).json();
const page=tabs.find(tab=>tab.type==='page');
if(!page)throw Error('No browser page target');
const socket=new WebSocket(page.webSocketDebuggerUrl);await new Promise(r=>socket.onopen=r);
let id=0;const pending=new Map();socket.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result)}};
const call=(method,params={})=>new Promise((resolve,reject)=>{pending.set(++id,{resolve,reject});socket.send(JSON.stringify({id,method,params}))});
const evaluate=async expression=>(await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true})).result.value;
async function wait(expr){for(let i=0;i<160;i++){if(await evaluate(expr))return;await new Promise(r=>setTimeout(r,100))}throw Error('Timed out: '+expr)}
await call('Emulation.setDeviceMetricsOverride',{width:1380,height:1200,deviceScaleFactor:1,mobile:false});
await call('Page.navigate',{url:'http://127.0.0.1:4048/'});
await wait("document.getElementById('revision')?.textContent.length>50");
await evaluate("document.getElementById('object').value='postcard/cards/compose/title';document.getElementById('showBounds').click()");
await wait("document.getElementById('overlay').children.length>3");
const shot=await call('Page.captureScreenshot',{format:'png'});writeFileSync('/tmp/bl-postcard-studio.png',Buffer.from(shot.data,'base64'));
await evaluate("seek(30)");await wait("document.getElementById('status').textContent.startsWith('Frame 30 ')");
await evaluate("document.getElementById('next').click()");await wait("document.getElementById('status').textContent.startsWith('Frame 31 ')");
await evaluate("document.getElementById('theme').value='blueprint';document.getElementById('theme').dispatchEvent(new Event('input'))");
await wait("Object.values(objects).some(o=>o.id==='postcard/heading'&&o.properties.color==='#f2efda')");
await evaluate("document.getElementById('play').click()");await new Promise(r=>setTimeout(r,700));
if(!(await evaluate('desired>31')))throw Error('Playback did not advance');
await evaluate("document.getElementById('play').click();for(let i=0;i<80;i++)seek(i)");
await wait("document.getElementById('status').textContent.startsWith('Frame 79 ')");
await call('Page.navigate',{url:'about:blank'});socket.close();console.log('Studio: inspector overlay, seek, step, style edit, playback, rapid scrub and close passed');
