// Owned camera-atlas review server at 4050 and Chromium CDP at 9225.
import {writeFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const tabs=await(await fetch('http://127.0.0.1:9225/json')).json();
const socket=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
await new Promise(r=>socket.onopen=r);
let id=0;const pending=new Map();
socket.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result)}};
const call=(method,params={})=>new Promise((resolve,reject)=>{pending.set(++id,{resolve,reject});socket.send(JSON.stringify({id,method,params}))});
const evaluate=async expression=>{const response=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(response.exceptionDetails)throw Error(JSON.stringify(response.exceptionDetails));return response.result.value};
async function wait(expression){for(let k=0;k<300;k++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,100))}throw Error('Timed out: '+expression)}
try{
 await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1080,deviceScaleFactor:1,mobile:false});
 await call('Page.navigate',{url:'http://100.124.205.18:4050/'});
 await wait("document.getElementById('film')?.readyState>=2");
 assert.equal(await evaluate('film.duration'),56);
 assert.equal(await evaluate('film.videoWidth'),1920);
 assert.equal(await evaluate('film.videoHeight'),1080);
 await evaluate('film.muted=true;film.play()');
 await new Promise(r=>setTimeout(r,900));
 assert.ok(await evaluate('film.currentTime>0.3 && !film.paused'));
 await evaluate('film.pause()');
 await evaluate("document.querySelector('[data-time=\"28.4\"]').click()");
 await wait('!film.seeking && film.currentTime>=28.4 && film.currentTime<32');
 await evaluate('film.pause();film.currentTime=41.2');
 await wait('!film.seeking && Math.abs(film.currentTime-41.2)<0.05');
 const shot=await call('Page.captureScreenshot',{format:'png'});
 writeFileSync('/tmp/bl-atlas-browser.png',Buffer.from(shot.data,'base64'));
 await evaluate('film.currentTime=3');
 await wait('!film.seeking && Math.abs(film.currentTime-3)<0.05');
 await call('Page.navigate',{url:'about:blank'});
 console.log('Atlas browser: 56-second 1080p media, playback, chapter navigation, arbitrary forward/backward seek passed');
}finally{socket.close()}
