import { chromium } from 'playwright';
const API=process.env.SMOKE_API??'http://127.0.0.1:8000';
const UI=process.env.SMOKE_UI??'http://127.0.0.1:5173';
const check=(ok,message)=>{if(!ok)throw new Error(message);console.log('PASS:',message)};
async function request(path,body){const response=await fetch(API+path,body?{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)}:{});if(!response.ok)throw new Error(`${path}: ${response.status}`);return response.json()}
const initial=await request('/api/state');
check(initial.jobs.length===0,'Smoke suite requires a fresh isolated backend');
check(initial.grid.forecast.length>=48,'Forecast covers the next day');
const p={name:'smoke-proof',energy_kwh:1,duration_minutes:30,deadline_hours:.6,workload:'hash_grind'};
const preview=await request('/api/preview',p);
check(preview.feasible_windows>0,'Preview has feasible windows');
check((await request('/api/state')).jobs.length===0,'Preview does not mutate queue');
const submitted=await request('/api/jobs',p);
await request('/api/speed',{speed:60});
let finished;
for(let i=0;i<90;i++){const {job}=await request('/api/jobs/'+submitted.job.id);if(['DONE','FAILED','MISSED'].includes(job.status)){finished=job;break}await new Promise(r=>setTimeout(r,500))}
check(finished?.status==='DONE','Real workload completes');
check((await request('/api/jobs/'+finished.id+'/artifact')).independently_verified===true,'Hash proof verifies');
await request('/api/speed',{speed:1});
const browser=await chromium.launch(process.env.PLAYWRIGHT_CHROMIUM?{executablePath:process.env.PLAYWRIGHT_CHROMIUM}:{});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto(UI);
 await page.getByRole('heading',{name:'A cleaner time to compute.'}).waitFor();
 check(await page.locator('svg[aria-label="Carbon intensity forecast with optimal execution window"]').isVisible(),'Forecast renders');
 await page.getByRole('button',{name:'New workload',exact:true}).click();
 await page.getByLabel('Workload name',{exact:true}).fill('smoke-ui-job');
 await page.getByRole('button',{name:'Schedule workload',exact:true}).click();
 await page.getByRole('dialog').waitFor({state:'hidden'});
 // Scope to the queue row itself: the cancel control carries an aria-label of
 // "Cancel <job name>", so a bare name match resolves to two buttons and trips
 // Playwright's strict mode.
 check(await page.locator('button.job-select').filter({hasText:'smoke-ui-job'}).isVisible(),'Browser submission appears in queue');
 await page.getByRole('button',{name:'Impact',exact:true}).click();
 check(await page.getByRole('heading',{name:'Make the shift count.'}).isVisible(),'Impact navigation works');
 await page.setViewportSize({width:390,height:844});
 check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile has no page overflow');
 check(errors.length===0,'No JavaScript runtime errors');
}finally{await browser.close()}
