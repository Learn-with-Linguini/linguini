const tl=gsap.timeline({paused:true});
const enter=(selector,time,from={y:55,opacity:0},duration=.42)=>tl.fromTo(selector,from,{y:0,x:0,opacity:1,scale:1,rotation:0,duration,ease:'power3.out'},time);
tl.fromTo('#hero-photo',{scale:1.08},{scale:1.17,duration:2,ease:'none'},0);
enter('#hook-a',0,{x:-60,opacity:0},.28);enter('#hook-b',.55,{y:45,opacity:0},.28);
tl.fromTo('#car-ring',{scale:1.5,opacity:0},{scale:1,opacity:1,duration:.4,ease:'back.out(1.4)'},.12);
enter('#language-photo',2,{x:-70,opacity:0},.35);enter('#spanish',2.08,{y:65,opacity:0},.35);
tl.to('#spanish',{rotationX:80,opacity:0,duration:.22,ease:'power2.in'},3.45);
tl.fromTo('#french',{rotationX:-80,opacity:0},{rotationX:0,opacity:1,duration:.32,ease:'power3.out'},3.62);
enter('#map-photo',5,{scale:.91,opacity:0},.4);['.m1','.m2','.m3','.m4','.m5'].forEach((s,i)=>enter(s,5+i*.5,{scale:.7,y:35,opacity:0},.3));enter('#words-count',5.9,{scale:.6,y:40,opacity:0},.45);
enter('#review-shot',8,{x:120,opacity:0},.4);tl.fromTo('#review-focus',{scale:1.13,opacity:0},{scale:1,opacity:1,duration:.25},8.65);tl.to('#review-focus',{scale:1.06,yoyo:true,repeat:3,duration:.22},8.9);
tl.to('#review-shot',{x:-150,opacity:0,duration:.28,ease:'power3.in'},9.85);enter('#audio-card',10,{x:150,scale:.93,opacity:0},.4);tl.fromTo('#speaker',{scale:.8},{scale:1.1,yoyo:true,repeat:3,duration:.22,ease:'sine.inOut'},10.35);
for(let i=0;i<12;i++)tl.fromTo('#w'+i,{scaleY:.35},{scaleY:1.6,duration:.15+(i%3)*.04,yoyo:true,repeat:6,ease:'sine.inOut'},10.45+(i%4)*.03);
enter('#ispy-photo',12,{x:-80,opacity:0},.35);enter('#clue-card',12.15,{x:100,opacity:0},.35);tl.fromTo('#ispy-ring',{scale:1.5,opacity:0},{scale:1,opacity:1,duration:.4},14.3);
tl.fromTo('#pointer',{x:1700,y:800,opacity:0},{x:1495,y:690,opacity:1,duration:.65,ease:'power3.out'},14);tl.to('#pointer',{scale:.85,yoyo:true,repeat:1,duration:.12},14.75);tl.fromTo('#click-halo',{scale:.3,opacity:1},{scale:1.7,opacity:0,duration:.5},14.78);
tl.to('#answer',{backgroundColor:'#d9eedf',borderColor:'#168583',color:'#168583',duration:.2},14.85);enter('#correct-label',15.02,{y:12,opacity:0},.25);
enter('#gap-card',16,{x:90,opacity:0},.35);enter('#flower-token',16.3,{y:80,opacity:0},.3);tl.to('#flower-token',{x:-205,y:-362,scale:1.07,duration:.5,ease:'power3.inOut'},17.25);tl.to('#flower-token',{opacity:0,duration:.12},17.75);tl.to('#gap-blank',{opacity:0,duration:.1},17.75);tl.fromTo('#gap-answer',{opacity:0,scale:1.18},{opacity:1,scale:1,duration:.22},17.75);
for(let i=0;i<7;i++)tl.fromTo('#token-'+i,{y:180+(i%2)*60,rotation:(i%2?8:-8),opacity:0},{y:0,rotation:0,opacity:1,duration:.33,ease:'back.out(1.1)'},19.2+i*.3);
tl.fromTo('#sentence-underline',{scaleX:0},{scaleX:1,duration:.48,ease:'power2.inOut'},21.35);enter('#sentence-check',21.7,{scale:.4,opacity:0},.35);enter('#sentence-done',21.85,{y:15,opacity:0},.3);
tl.fromTo('#journal',{rotationY:-35,x:170,scale:.93,opacity:0},{rotationY:0,x:0,scale:1,opacity:1,duration:.65,ease:'power3.out'},23);['.j1','.j2','.j3'].forEach((s,i)=>enter(s,23.8+i*.5,{y:18,opacity:0},.3));enter('#journal-saved',25.7,{y:20,scale:.95,opacity:0},.3);
enter('#end-main',27,{scale:.93,y:45,opacity:0},.45);tl.fromTo('#end-wordmark',{rotation:-4},{rotation:0,duration:.5,ease:'back.out(1.5)'},27.1);tl.fromTo('#end-cta',{scale:.93},{scale:1,duration:.4,ease:'back.out(1.7)'},27.8);
tl.fromTo('#progress',{scaleX:0},{scaleX:1,duration:30,ease:'none'},0);
tl.fromTo('#host-svg',{y:10,rotation:-3},{y:-6,rotation:3,duration:.5,yoyo:true,repeat:59,ease:'sine.inOut'},0);
for(const t of [.95,4.65,8.5,12.2,16.8,20.6,25,28.6]){tl.to('#eye-l,#eye-r',{scaleY:.12,transformOrigin:'center',duration:.07,yoyo:true,repeat:1},t);}
let env=window.VOICE_ENVELOPE;let samples=Array.isArray(env)?env:(env.samples||env.values||[]);let fps=env.fps||env.sample_rate_hz||30;
if(samples.length){samples.forEach((v,i)=>{const t=typeof v==='object'?(v.time??v.t??i/fps):i/fps;const a=typeof v==='object'?(v.value??v.amplitude??v.rms??0):v;tl.to('#mouth',{scaleY:.15+Math.min(1,a)*.85,duration:1/fps,ease:'none'},t);});}else{tl.fromTo('#mouth',{scaleY:.2},{scaleY:1,duration:.13,yoyo:true,repeat:225,ease:'sine.inOut'},0);}
window.__timelines=window.__timelines||{};window.__timelines.linguini=tl;
