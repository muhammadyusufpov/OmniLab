import test from 'node:test';
import assert from 'node:assert/strict';
const data = new Map();
const events = [];
globalThis.window = {
 location: { pathname:'/guides/sodium-and-chlorine-reaction/', search:'?utm_source=reddit&utm_medium=forum&utm_campaign=cycle40', origin:'https://omnilab-bk8q.onrender.com'},
 localStorage:{getItem:k=>data.get(k)||null, setItem:(k,v)=>data.set(k,v)},
 posthog:{capture:(...event)=>events.push(event)}
};
globalThis.document = {referrer:'https://reddit.com/r/chemistry/?private=hidden#secret'};
const {capture, capturePageView, normalizedPath} = await import('../static/js/analytics/analytics.js');
const {sanitizePayload, analyticsPersistence} = await import('../static/js/analytics/payload.js');
const payload = (session='session-1') => sanitizePayload({event:'lab_setup_started', properties:{distinct_id:'sdk-browser-1', $session_id:session, $current_url:'https://private/?email=hidden', $referrer:document.referrer, email:'hidden', entry_source:'guide'}});

test('one pageview and normalized paths on existing events',()=>{
 capturePageView(); capturePageView();
 assert.equal(events.filter(e=>e[0]==='$pageview').length,1);
 window.location.pathname='/guides/example/?private=hidden#secret';
 capture('chemistry_guide_entered',{page_path:'bad'});
 assert.equal(events.at(-1)[1].page_path,'/guides/example/');
 assert.equal(normalizedPath('/contact/%40private'),'/unknown/');
});
test('SDK identifiers reused and arrival survives same-session navigation',()=>{
 const first=payload();
 assert.equal(first.properties.visitor_id,'sdk-browser-1');
 assert.equal(first.properties.session_id,'session-1');
 assert.equal(first.properties.referrer_origin,'https://reddit.com');
 assert.equal(first.properties.utm_source,'reddit');
 assert.equal(first.properties.$current_url,undefined);
 assert.equal(first.properties.email,undefined);
 window.location.pathname='/demo/sodium-chlorine/';window.location.search='';document.referrer=window.location.origin+'/guides/';
 const next=payload();
 assert.equal(next.properties.landing_path,first.properties.landing_path);
 assert.equal(next.properties.utm_source,'reddit');
 assert.equal(next.properties.page_path,'/demo/sodium-chlorine/');
});
test('SDK session renewal renews arrival; direct differs from unknown',()=>{
 document.referrer='';
 assert.equal(payload('session-2').properties.arrival_type,'direct');
 document.referrer='not a URL';
 assert.equal(payload('session-3').properties.arrival_type,'unknown');
});
test('blocked storage and sensitive campaign values are safe',()=>{
 window.localStorage={getItem(){throw Error('blocked')},setItem(){throw Error('blocked')}};
 window.location.search='?utm_source=person%40example.com&utm_campaign=https%3A%2F%2Fsecret';
 document.referrer='https://user:password@example.com/private';
 const result=payload('session-4');
 assert.equal(result.properties.utm_source,'');assert.equal(result.properties.utm_campaign,'');
 assert.equal(result.properties.referrer_origin,'');
 assert.equal(result.properties.visitor_id,'sdk-browser-1');
});
test('controlled runs drop capture and SDK transport',()=>{
 window.location.search='?verification=controlled'; const count=events.length;
 capture('lab_viewed'); assert.equal(events.length,count); assert.equal(payload(),null);
});

test('blocked durable storage chooses memory without cookie fallback',()=>{
 assert.equal(analyticsPersistence(),'memory');
});
