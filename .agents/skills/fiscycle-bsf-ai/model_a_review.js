"use strict";
const $=id=>document.getElementById(id), data=window.REVIEW_DATA;
const clone=x=>JSON.parse(JSON.stringify(x));
let items=[], index=0, entry=null, polygons=[], selected=0, adding=false, pending=[], undoStack=[], image=null,crop=null, decisions={};
const storage="fiscycle-review-"+data.package_hash;
const labels={coverage_complete:"Semua larva terlihat telah dianotasi",instances_separate:"Setiap larva tetap instance terpisah",visible_masks_only:"Mask hanya bagian yang terlihat",boundaries_unambiguous:"Identitas dan batas tidak ambigu",duplicates_checked:"Proposal duplikat telah diperiksa",minimum_visibility_policy:"Semua objek memenuhi kebijakan minimum visibility",truncation_policy:"Objek tepi memenuhi kebijakan truncation",correct_larva:"Objek crop benar-benar larva",source_body_complete:"Tubuh lengkap di gambar sumber",both_ends_inside:"Kedua ujung di dalam crop",morphology_preserved:"Morfologi utuh tanpa distorsi",no_id_or_sex:"Tidak ada tulisan ID atau sex",no_ruler:"Tidak ada penggaris/tanda ukur",background_acceptable:"Background tidak memberi shortcut yang jelas"};
try{decisions=JSON.parse(localStorage.getItem(storage)||"{}");}catch{}
function message(t){$("message").textContent=t;}
function persist(){try{localStorage.setItem(storage,JSON.stringify(decisions));}catch{message("Penyimpanan browser gagal. Unduh JSON untuk menyimpan keputusan.");}}
function updateCounts(){const ds=Object.values(decisions);$("counts").textContent=`Tercatat: ${ds.length}; approve: ${ds.filter(d=>d.decision==="approve").length}. Tidak ada training yang dijalankan.`;$("decision").textContent=entry&&decisions[entry.id]?decisions[entry.id].decision:"Belum diputuskan";}
function invalidate(){if(entry&&decisions[entry.id]){delete decisions[entry.id];persist();updateCounts();message("Keputusan dibatalkan karena gambar ini diubah. Periksa dan putuskan lagi.");}}
function beforeEdit(){undoStack.push(clone(polygons));invalidate();}
function drawPolygon(ctx,p,color,vertices=false){ctx.beginPath();p.points.forEach(([x,y],i)=>i?ctx.lineTo(x*640,y*640):ctx.moveTo(x*640,y*640));ctx.closePath();ctx.fillStyle=color+"22";ctx.fill();ctx.strokeStyle=color;ctx.lineWidth=2;ctx.stroke();if(vertices)for(const [x,y]of p.points){ctx.fillStyle="#fff";ctx.fillRect(x*640-3,y*640-3,6,6);}}
function base(id){const c=$(id),ctx=c.getContext("2d");ctx.clearRect(0,0,640,640);if(image){if(entry.track==="A1")ctx.drawImage(image,0,0,640,640);else{const s=Math.min(640/image.width,640/image.height);ctx.drawImage(image,0,0,image.width*s,image.height*s);}}return ctx;}
function render(){if(!entry)return;base("original");const src=base("source"),prop=base("proposal"),change=base("changes");
 if(entry.track==="A1"){
  entry.source_polygons.forEach(p=>drawPolygon(src,p,p.source_class===0?"#00ffff":"#ff9100"));
  polygons.forEach((p,i)=>drawPolygon(prop,p,i===selected?"#ffff00":"#00e5a0",i===selected));
  for(const p of entry.source_polygons){const next=polygons.find(n=>n.source_line===p.source_line);if(!next)drawPolygon(change,p,"#ff3030");else if(JSON.stringify(next.points)!==JSON.stringify(p.points)){drawPolygon(change,p,"#ff3030");drawPolygon(change,next,"#ffff00");}}
  polygons.filter(p=>p.source_line==null).forEach(p=>drawPolygon(change,p,"#00ff70"));
  if(pending.length)drawPolygon(prop,{points:pending},"#ff00ff",true);
 }else{
  if(entry.crop_bbox&&image){const [x,y,x1,y1]=entry.crop_bbox,s=640/entry.width;src.strokeStyle="#00ee88";src.lineWidth=3;src.strokeRect(x*s,y*s,(x1-x)*s,(y1-y)*s);}
  prop.clearRect(0,0,640,640);if(crop)prop.drawImage(crop,0,0,640,640);
 }
}
function polygonSelect(){const sel=$("polygons");sel.replaceChildren();polygons.forEach((p,i)=>{const o=document.createElement("option");o.value=i;o.textContent=`Instance ${i+1} | source line ${p.source_line??"baru"}`;sel.append(o);});sel.value=selected;render();}
function load(){entry=items[index];if(!entry){$("identity").textContent="Tidak ada gambar sesuai filter";return;}adding=false;pending=[];undoStack=[];selected=0;image=null;crop=null;
 const saved=decisions[entry.id];polygons=clone(saved?.polygons||entry.proposed_polygons||[]);
 $("identity").textContent=`${entry.track} • ${entry.image_id} • frozen split: ${entry.split} • ${entry.hard_hold?"HOLD TETAP":"PENDING HUMAN REVIEW"}`;
 $("issues").textContent=entry.issues;$("position").textContent=`${index+1}/${items.length}`;$("notes").value=saved?.notes||"";message("");
 $("editor").hidden=entry.track!=="A1";$("changePanel").hidden=entry.track!=="A1";$("cropHint").hidden=entry.track!=="A2";
 $("sourceTitle").textContent=entry.track==="A1"?"Anotasi sumber: 0 cyan, 1 oranye":"Context dan batas crop";
 $("proposalTitle").textContent=entry.track==="A1"?"Proposal target 0: visible_bsf_larva":"Candidate crop — belum disahkan";
 $("approve").disabled=entry.hard_hold;$("checks").replaceChildren();
 for(const key of entry.checks_required){const label=document.createElement("label"),checkbox=document.createElement("input");checkbox.type="checkbox";checkbox.dataset.key=key;checkbox.checked=saved?.checks?.[key]===true;checkbox.onchange=invalidate;label.append(checkbox,document.createTextNode(labels[key]||key));$("checks").append(label);}
 const id=entry.id,im=new Image();im.onload=()=>{if(entry?.id===id){image=im;render();}};im.onerror=()=>{if(entry?.id===id)message("Gagal membaca gambar sumber. Jangan approve.");};im.src=entry.image_url;
 if(entry.crop_url){const ci=new Image();ci.onload=()=>{if(entry?.id===id){crop=ci;render();}};ci.onerror=()=>{if(entry?.id===id)message("Gagal membaca crop. Jangan approve.");};ci.src=entry.crop_url;}
 polygonSelect();updateCounts();
}
function filter(){items=data.items.filter(e=>e.track===$("track").value&&(!$("split").value||e.split===$("split").value)&&e.image_id.toLowerCase().includes($("search").value.toLowerCase()));index=0;load();}
for(const id of ["track","split","search"])$(id).oninput=filter;
$("previous").onclick=()=>{if(index>0){index--;load();}};$("next").onclick=()=>{if(index+1<items.length){index++;load();}};
$("polygons").onchange=()=>{selected=Number($("polygons").value);render();};
$("add").onclick=()=>{adding=true;pending=[];message("Klik titik-titik batas bagian terlihat, lalu Selesai polygon.");};
$("finish").onclick=()=>{if(!adding||pending.length<3){message("Minimal tiga titik diperlukan.");return;}beforeEdit();polygons.push({source_line:null,source_class:null,target_class:0,points:clone(pending)});selected=polygons.length-1;adding=false;pending=[];polygonSelect();};
$("remove").onclick=()=>{if(polygons[selected]){beforeEdit();polygons.splice(selected,1);selected=Math.max(0,selected-1);polygonSelect();}};
$("undo").onclick=()=>{if(undoStack.length){invalidate();polygons=undoStack.pop();polygonSelect();}};
$("reset").onclick=()=>{beforeEdit();polygons=clone(entry.proposed_polygons);selected=0;polygonSelect();};
let drag=-1;function point(ev){const r=$("proposal").getBoundingClientRect();return [Math.max(0,Math.min(1,(ev.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(ev.clientY-r.top)/r.height))];}
$("proposal").onpointerdown=ev=>{if(!entry||entry.track!=="A1")return;const p=point(ev);if(adding){pending.push(p);render();return;}const poly=polygons[selected];if(!poly)return;drag=poly.points.findIndex(q=>Math.hypot(q[0]-p[0],q[1]-p[1])<.025);if(drag>=0){beforeEdit();$("proposal").setPointerCapture(ev.pointerId);}};
$("proposal").onpointermove=ev=>{if(drag>=0){polygons[selected].points[drag]=point(ev);render();}};$("proposal").onpointerup=()=>{drag=-1;};
$("notes").oninput=invalidate;
function decide(value){if(!entry)return;const reviewer=$("reviewer").value.trim();if(!reviewer){message("Isi nama reviewer manusia.");return;}const checks={};$("checks").querySelectorAll("input").forEach(c=>checks[c.dataset.key]=c.checked);
 if(value==="approve"&&(entry.hard_hold||!image||(entry.track==="A2"&&!crop)||adding||!Object.values(checks).every(Boolean))){message("Approval memerlukan semua pemeriksaan, gambar termuat, dan tanpa hard hold atau polygon belum selesai.");return;}
 const d={id:entry.id,proposal_hash:entry.proposal_hash,policy_hash:entry.policy_hash,source_sha256:entry.source_sha256,split:entry.split,reviewer_kind:"human",reviewer,reviewed_at:new Date().toISOString(),decision:value,checks,notes:$("notes").value};
 if(entry.track==="A1")d.polygons=clone(polygons);else{d.crop_sha256=entry.crop_sha256;d.crop_bbox=entry.crop_bbox;}
 decisions[entry.id]=d;persist();updateCounts();message("Keputusan tersimpan lokal. Unduh JSON, lalu jalankan import-reviews untuk validasi dan freeze subset yang sah.");}
$("approve").onclick=()=>decide("approve");$("revision").onclick=()=>decide("needs_revision");$("reject").onclick=()=>decide("reject");
$("export").onclick=()=>{const blob=new Blob([JSON.stringify({package_hash:data.package_hash,decisions:Object.values(decisions)},null,2)],{type:"application/json"});const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="model_a_human_decisions.json";a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
$("restore").onchange=async ev=>{try{const r=JSON.parse(await ev.target.files[0].text());if(r.package_hash!==data.package_hash||!Array.isArray(r.decisions))throw Error("Versi paket berbeda");const next={...decisions};for(const d of r.decisions){const e=data.items.find(e=>e.id===d.id);if(!e||e.proposal_hash!==d.proposal_hash)throw Error("Proposal tidak cocok");next[d.id]=d;}decisions=next;persist();load();}catch(e){message(e.message);}};
filter();
