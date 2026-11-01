// Reuse a completed API acceptance export; prove the real button finds that
// exact revision and exposes a downloadable film without another physical export.
import {readFileSync,writeFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const report=JSON.parse(readFileSync('/tmp/bl-studio-export-checks.json','utf8'));
const config=await(await fetch('http://127.0.0.1:4048/api/config')).json();
config.title='A world worth making.';
config.cards[0].body='This exact sentence belongs to the captured film.';
config.cue=0.4;
const tabs=await(await fetch('http://127.0.0.1:9224/json')).json();
const socket=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
await new Promise(r=>socket.onopen=r);
let id=0;const pending=new Map();
socket.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result)}};
const call=(method,params={})=>new Promise((resolve,reject)=>{pending.set(++id,{resolve,reject});socket.send(JSON.stringify({id,method,params}))});
const evaluate=async expression=>(await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true})).result.value;
async function wait(expression){for(let k=0;k<200;k++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,100))}throw Error('Timed out: '+expression)}
try{
 await call('Emulation.setDeviceMetricsOverride',{width:1380,height:1200,deviceScaleFactor:1,mobile:false});
 await call('Page.navigate',{url:'http://127.0.0.1:4048/'});
 await wait("typeof accepted!=='undefined' && !!accepted");
 await evaluate(`config=${JSON.stringify(config)};populate();seek(60)`);
 await wait(`accepted.revision===${JSON.stringify(report.revision)} && !busy`);
 await evaluate("document.getElementById('export').click()");
 await wait("!document.getElementById('download').hidden");
 assert.equal(await evaluate("new URL(document.getElementById('download').href).searchParams.get('revision')"),report.revision);
 assert.ok(await evaluate("fetch(document.getElementById('download').href).then(r=>r.arrayBuffer()).then(b=>b.byteLength>10000)"));
 const shot=await call('Page.captureScreenshot',{format:'png'});writeFileSync('/tmp/bl-studio-export-ready.png',Buffer.from(shot.data,'base64'));
 await call('Page.navigate',{url:'about:blank'});
 console.log('Studio export: real button resolves exact accepted revision and downloadable cached MP4');
}finally{socket.close()}
