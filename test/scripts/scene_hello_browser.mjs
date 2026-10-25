import {writeFileSync} from 'node:fs';import assert from 'node:assert/strict';
const tabs=await(await fetch('http://127.0.0.1:9229/json')).json();
const socket=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);await new Promise(r=>socket.onopen=r);
let id=0;const pending=new Map();socket.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result)}};
const call=(method,params={})=>new Promise((resolve,reject)=>{pending.set(++id,{resolve,reject});socket.send(JSON.stringify({id,method,params}))});
const evaluate=async expression=>{const v=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(v.exceptionDetails)throw Error(JSON.stringify(v.exceptionDetails));return v.result.value};
async function wait(expression){for(let i=0;i<950;i++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,100))}throw Error('Timed out: '+expression)}
try{
 await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
 await call('Page.navigate',{url:process.env.HELLO_URL||'http://100.124.205.18:4054/'});
 await wait("document.getElementById('film')?.readyState>=2");await evaluate('document.fonts.ready');assert.equal(await evaluate('document.fonts.check("16px Nunito")'),true);
 assert.equal(await evaluate('film.duration'),60);assert.equal(await evaluate('film.videoWidth'),1920);assert.equal(await evaluate('film.videoHeight'),1080);
 await evaluate("document.getElementById('play').click()");await wait('!film.paused && film.currentTime>.5');assert.equal(await evaluate('film.muted'),false);
 await wait('film.ended');assert.equal(await evaluate("document.getElementById('play').hidden"),false);
 const playback=await evaluate('({time:film.currentTime,total:film.getVideoPlaybackQuality().totalVideoFrames,dropped:film.getVideoPlaybackQuality().droppedVideoFrames})');
 for(const t of [11,16.5,21,27,30,42.5,57,0,33]){await evaluate(`film.currentTime=${t}`);await wait(`!film.seeking && Math.abs(film.currentTime-${t})<.05`)}
 const shot=await call('Page.captureScreenshot',{format:'png'});writeFileSync('/tmp/bl-hello-browser.png',Buffer.from(shot.data,'base64'));
 await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});assert.ok(await evaluate('document.documentElement.scrollWidth<=390'));
 const mobile=await call('Page.captureScreenshot',{format:'png'});writeFileSync('/tmp/bl-hello-mobile.png',Buffer.from(mobile.data,'base64'));
 await call('Page.navigate',{url:'about:blank'});
 const result={duration:60,width:1920,height:1080,unmuted_full_playback:true,nunito_loaded:true,seeks:[11,16.5,21,27,30,42.5,57,0,33],mobile_width:390,replay_button:true,playback};writeFileSync('/tmp/bl-hello-browser-check.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result,null,2));
}finally{socket.close()}
