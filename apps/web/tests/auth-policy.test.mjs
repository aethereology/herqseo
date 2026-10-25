import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
import ts from 'typescript';
function load(relative, imports={}) {
  const source=fs.readFileSync(path.join(__dirname,'..',relative),'utf8');
  const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const mod={exports:{}};
  new Function('module','exports','require',compiled)(mod,mod.exports,name=>{if(name in imports)return imports[name];throw Error(name)});
  return mod.exports;
}
const {developmentAuthEnabled}=load('src/lib/auth-policy.ts');
test('development identities are refused in production and every hosted Vercel environment',()=>{
  for(const env of [{NODE_ENV:'production'},{NODE_ENV:'development',VERCEL:'1'},{NODE_ENV:'test',VERCEL_ENV:'preview'},{VERCEL_ENV:'development'}])assert.equal(developmentAuthEnabled(env),false);
  assert.equal(developmentAuthEnabled({NODE_ENV:'development'}),true);
});
test('production has no credentials provider and strips existing demo identity from JWT and session',()=>{
  const config=load('auth.ts',{'next-auth':{default:()=>({})},'next-auth/providers/credentials':{default:x=>x},'./src/lib/auth-policy':{developmentAuthEnabled:()=>false},'@queryclear/shared':{AUTONOMY_MODE_KEYS:['review'],PLAN_LIMITS:{},isPlanTier:()=>false}}).authConfig;
  assert.equal(config.providers.length,0);
  assert.equal(config.callbacks.jwt({token:{tenant:{user:{role:'owner'}}},user:null}).tenant,undefined);
  assert.equal(config.callbacks.session({session:{},token:{tenant:{user:{role:'owner'}}}}).tenant,undefined);
});
