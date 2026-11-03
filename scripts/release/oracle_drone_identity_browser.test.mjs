import assert from 'node:assert/strict';
import test from 'node:test';
import {validateIdentity,validateAuthorization,validateCallback,totp,freshCode,scopeIdentityRequests} from './oracle_drone_identity_browser.mjs';

function identity(){
 const account={subject:'11111111-1111-4111-8111-111111111111',tenant_id:'22222222-2222-4222-8222-222222222222',email:'fixture@example.test',password:'synthetic-password-only',totp_secret:'JBSWY3DPEHPK3PXP',role:'admin'};
 return {profile:'shared-identity-v1',environment:'staging',origin:'https://drone-staging.onesa.eu',issuer:'https://onesa-company-portal-fixture.vercel.app/api/v1/identity',client_id:'onesa-drone-staging',accounts:{operator:account,foreign:{...account},viewer:{...account,role:'viewer'}},expires_at:new Date(Date.now()+300000).toISOString(),portal_bypass:null};
}
function authorization(value){
 const url=new URL(value.issuer+'/auth');
 for(const [key,item] of Object.entries({client_id:value.client_id,redirect_uri:value.origin+'/api/v1/auth/identity/callback',response_type:'code',scope:'openid email profile onesa',state:'s'.repeat(43),nonce:'n'.repeat(43),code_challenge:'c'.repeat(43),code_challenge_method:'S256'}))url.searchParams.set(key,item);
 return url;
}

test('explicit Drone slot and subject/workspace/role bindings are required',()=>{
 const value=identity();
 for(const actor of ['operator','foreign','viewer'])assert.equal(validateIdentity(value,actor).drone,value.origin);
 for(const change of [v=>v.origin='https://drone-api-staging.onesa.eu',v=>v.environment='production',v=>v.issuer='https://foreign.example.test/api/v1/identity',v=>v.accounts.viewer.role='admin',v=>v.accounts.operator.tenant_id='unbound',v=>v.expires_at=new Date(Date.now()-1000).toISOString()]){
  const changed=structuredClone(value);change(changed);assert.throws(()=>validateIdentity(changed,changed.accounts.viewer.role==='admin'?'viewer':'operator'));
 }
});

test('actual S256 authorization rejects foreign origin, callback, duplicated state and weaker challenge',()=>{
 const value=identity(),url=authorization(value);assert.equal(validateAuthorization(url.href,value).href,url.href);
 for(const [key,item] of [['client_id','unbound-client'],['redirect_uri','https://foreign.example.test/callback'],['code_challenge_method','plain'],['response_type','token'],['scope','openid']]){
  const changed=new URL(url);changed.searchParams.set(key,item);assert.throws(()=>validateAuthorization(changed.href,value));
 }
 const duplicate=new URL(url);duplicate.searchParams.append('state','s'.repeat(43));assert.throws(()=>validateAuthorization(duplicate.href,value));
 assert.throws(()=>validateAuthorization(url.href.replace('onesa-company-portal-fixture.vercel.app','foreign.example.test'),value));
});

test('callback is bound to the observed transaction and exact issuer',()=>{
 const value=identity(),auth=authorization(value),callback=new URL(value.origin+'/api/v1/auth/identity/callback');
 callback.searchParams.set('code','synthetic-code');callback.searchParams.set('state',auth.searchParams.get('state'));callback.searchParams.set('iss',value.issuer);
 assert.equal(validateCallback(callback.href,value,auth),true);
 for(const [key,item] of [['state','foreign-state'],['iss','https://foreign.example.test/api/v1/identity'],['error','access_denied']]){
  const changed=new URL(callback);changed.searchParams.set(key,item);assert.throws(()=>validateCallback(changed.href,value,auth));
 }
});

test('authenticator uses the next real counter once without factor retries',async()=>{
 assert.equal(totp('GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ',1),'287082');
 let current=29500,waits=[];
 const code=await freshCode('GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ',{now:()=>current,wait:async milliseconds=>{waits.push(milliseconds);current+=milliseconds;}});
 assert.equal(code,'287082');assert.deepEqual(waits,[1500]);
});

test('bypass credentials stay in isolated no-redirect handshakes and host-only cookies',async()=>{
 const value=identity();value.portal_bypass='synthetic-portal-bypass';
 const requests=[],added=[];let route;
 const context={setExtraHTTPHeaders:async headers=>assert.deepEqual(headers,{}),addCookies:async cookies=>added.push(...cookies),route:async(_pattern,callback)=>{route=callback;},browser:()=>({newContext:async()=>{
  let destination;
  return {request:{get:async(origin,options)=>{destination=origin;requests.push([origin,options]);return {status:()=>307,headers:()=>({location:'/same-origin'})};}},cookies:async()=>[{name:'_vercel_jwt',value:'synthetic-cookie',secure:true,domain:new URL(destination).hostname}],close:async()=>{}};
 }})};
 await scopeIdentityRequests(context,value,'synthetic-drone-bypass');
 assert.equal(requests.length,2);assert.ok(requests.every(([,options])=>options.maxRedirects===0));
 assert.deepEqual(added.map(cookie=>cookie.url),[value.origin,new URL(value.issuer).origin]);
 assert.ok(added.every(cookie=>!Object.hasOwn(cookie,'domain')&&cookie.httpOnly&&cookie.secure));
 let continued=false,aborted=false;
 await route({request:()=>({url:()=>value.origin+'/api/v1/operations',headers:()=>({}),method:()=> 'GET',isNavigationRequest:()=>false}),continue:async options=>{assert.equal(options,undefined);continued=true;},abort:async()=>{aborted=true;}});
 assert.equal(continued,true);assert.equal(aborted,false);
 await route({request:()=>({url:()=> 'https://foreign.example.test/',headers:()=>({}),method:()=> 'GET',isNavigationRequest:()=>true}),continue:async()=>assert.fail(),abort:async()=>{aborted=true;}});
 assert.equal(aborted,true);
});

test('a cross-origin bypass redirect is refused before any credential reaches it',async()=>{
 const value=identity();let added=false,closed=false;
 const context={setExtraHTTPHeaders:async()=>{},addCookies:async()=>{added=true;},route:async()=>assert.fail(),browser:()=>({newContext:async()=>({request:{get:async(_origin,options)=>{assert.equal(options.maxRedirects,0);return {status:()=>307,headers:()=>({location:'https://foreign.example.test/'})};}},close:async()=>{closed=true;}})})};
 await assert.rejects(scopeIdentityRequests(context,value,'synthetic-bypass'));assert.equal(added,false);assert.equal(closed,true);
});
