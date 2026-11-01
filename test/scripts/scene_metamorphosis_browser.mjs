import {writeFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const tabs=await(await fetch('http://127.0.0.1:9226/json')).json();
const socket=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);await new Promise(r=>socket.onopen=r);
let id=0;const pending=new Map();socket.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result)}};
const call=(method,params={})=>new Promise((resolve,reject)=>{pending.set(++id,{resolve,reject});socket.send(JSON.stringify({id,method,params}))});
const evaluate=async expression=>{const v=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(v.exceptionDetails)throw Error(JSON.stringify(v.exceptionDetails));return v.result.value};
async function wait(expression){for(let i=0;i<250;i++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,100))}throw Error('Timed out: '+expression)}
try{
 await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1050,deviceScaleFactor:1,mobile:false});
 await call('Page.navigate',{url:'http://100.124.205.18:4051/'});
 await wait("document.getElementById('film')?.readyState>=2");
 assert.equal(await evaluate('film.duration'),48);assert.equal(await evaluate('film.videoWidth'),1920);
 await evaluate('film.muted=true;film.play()');await new Promise(r=>setTimeout(r,800));assert.ok(await evaluate('film.currentTime>0.3 && !film.paused'));
 await evaluate('film.pause()');
 for(const t of [7,23,38,47,0,15]){await evaluate(`film.currentTime=${t}`);await wait(`!film.seeking && Math.abs(film.currentTime-${t})<0.05`)}
 const shot=await call('Page.captureScreenshot',{format:'png'});writeFileSync('/tmp/bl-metamorphosis-browser.png',Buffer.from(shot.data,'base64'));
 await call('Page.navigate',{url:'about:blank'});
 console.log('Metamorphosis browser: continuous 48s 1080p media, playback, and arbitrary forward/backward seek passed');
}finally{socket.close()}
