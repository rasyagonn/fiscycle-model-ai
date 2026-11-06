"""Add a one-click review UI; keep the original review package and data unchanged."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"hasil/model_a_finalization_v1"

ADDON=r'''
<style>
#checks{columns:1}#checks label{margin:3px;font-size:13px}#checks input{display:none}
#quickActions{position:sticky;bottom:0;background:#fff;border:2px solid #167354;padding:12px;z-index:10;border-radius:10px;box-shadow:0 -4px 20px #0002}
#quickActions button{font-size:17px;padding:12px 18px}#approve{background:#167354;color:white;border:0;border-radius:7px}
#approve:disabled{background:#888}#message{margin:8px 0;font-weight:600;color:#173530}#decision{display:block;margin:6px 0}
#confirmation{margin:8px 0;font-size:14px}#checks{display:none}#quickActions details{margin:5px 0}
</style>
<script>
// Single explicit per-image confirmation replaces separate checkbox clicks.
// No decisions are created on load or for any unseen image.
const quickActions=$('approve').parentElement;
quickActions.id='quickActions';
quickActions.querySelector('h2').textContent='Periksa gambar, lalu pilih keputusan';
const detail=document.createElement('details');
const summary=document.createElement('summary');summary.textContent='Lihat kriteria lengkap';
detail.append(summary);const criteria=document.createElement('div');detail.append(criteria);
quickActions.insertBefore(detail,$('checks'));
const confirmation=document.createElement('p');confirmation.id='confirmation';
quickActions.insertBefore(confirmation,$('approve'));
quickActions.append($('message'));
$('approve').textContent='Approve & lanjut →';
$('revision').textContent='Perlu perbaikan & lanjut';
$('reject').textContent='Reject & lanjut';
const oldUpdateCounts=updateCounts;
updateCounts=function(){
 oldUpdateCounts();
 if(!entry){$('approve').disabled=true;$('revision').disabled=true;$('reject').disabled=true;return;}
 $('revision').disabled=false;$('reject').disabled=false;
 const status=decisions[entry.id]?.decision|| (entry.hard_hold?'HOLD TETAP':'Belum diputuskan');
 $('identity').textContent=`${entry.track} • ${entry.image_id} • split: ${entry.split} • ${status}`;
 $('approve').disabled=entry.hard_hold;
 confirmation.textContent=entry.hard_hold?'Gambar ini ditahan: pilih Perlu perbaikan atau Reject.':
  entry.track==='A1'?'Dengan klik Approve, saya menyatakan semua larva sudah diberi mask yang benar, instance terpisah, hanya bagian terlihat, tanpa duplikat, serta memenuhi aturan visibility dan truncation.':
  'Dengan klik Approve, saya menyatakan objek adalah larva utuh, kedua ujung masuk crop, morfologi terjaga, tanpa ID/sex/penggaris, dan background layak.';
 criteria.replaceChildren();
 entry.checks_required.forEach(key=>{const p=document.createElement('div');p.textContent='• '+labels[key];criteria.append(p);});
};
const reviewerStorage=storage+'-reviewer';
try{$('reviewer').value=localStorage.getItem(reviewerStorage)||'';}catch{}
$('reviewer').oninput=()=>{try{localStorage.setItem(reviewerStorage,$('reviewer').value);}catch{}};
let savingQuickDecision=false;
function quickDecide(value){
 if(!entry||savingQuickDecision)return;
 const reviewer=$('reviewer').value.trim();
 if(!reviewer){message('Isi nama reviewer sekali di bagian atas.');$('reviewer').focus();return;}
 if(value==='approve'&&(entry.hard_hold||!image||(entry.track==='A2'&&!crop)||adding||
    (entry.track==='A1'&&!polygons.length))){message('Belum bisa approve: gambar harus termuat, polygon selesai, dan tidak dalam HOLD.');return;}
 savingQuickDecision=true;
 const reviewed=entry;
 const d={id:reviewed.id,proposal_hash:reviewed.proposal_hash,policy_hash:reviewed.policy_hash,
  source_sha256:reviewed.source_sha256,split:reviewed.split,reviewer_kind:'human',reviewer,
  reviewed_at:new Date().toISOString(),decision:value,
  checks:Object.fromEntries(reviewed.checks_required.map(k=>[k,value==='approve'])),
  notes:$('notes').value,approval_method:'explicit_single_click_v1',
  confirmation_text:value==='approve'?confirmation.textContent:''};
 if(reviewed.track==='A1')d.polygons=clone(polygons);else{d.crop_sha256=reviewed.crop_sha256;d.crop_bbox=reviewed.crop_bbox;}
 decisions[reviewed.id]=d;
 let saved=false;
 try{localStorage.setItem(storage,JSON.stringify(decisions));localStorage.setItem(reviewerStorage,reviewer);saved=true;}
 catch{message('Browser gagal menyimpan. Keputusan ada di memori: klik Unduh keputusan JSON sebelum menutup halaman.');}
 updateCounts();
 if(saved){
  if(index+1<items.length){index++;load();message(`${reviewed.image_id}: ${value} tersimpan. Sekarang gambar berikutnya.`);}
  else message(`${reviewed.image_id}: ${value} tersimpan. Ini gambar terakhir pada filter ini. Unduh keputusan JSON.`);
 }
 // Prevent a double-click from approving a second image as it loads.
 setTimeout(()=>{savingQuickDecision=false;},700);
}
$('approve').onclick=()=>quickDecide('approve');
$('revision').onclick=()=>quickDecide('needs_revision');
$('reject').onclick=()=>quickDecide('reject');
updateCounts();
</script>
'''


def main():
    original=(OUT/"review.html").read_text(encoding="utf-8")
    page=original.replace("</html>",ADDON+"</html>")
    page=page.replace("Model A — Human review","Model A — Review cepat")
    page=page.replace("Simpan keputusan sebelum menutup browser.","Approve langsung menyimpan dan membuka gambar berikutnya. Unduh JSON sebelum menutup browser.")
    (OUT/"review_cepat.html").write_text(page,encoding="utf-8")
    receipt={"ui_version":"explicit_single_click_v1","source_review_html_sha256":hashlib.sha256((OUT/"review.html").read_bytes()).hexdigest(),
             "review_data_sha256":hashlib.sha256((OUT/"review_data.js").read_bytes()).hexdigest(),
             "review_cepat_html_sha256":hashlib.sha256((OUT/"review_cepat.html").read_bytes()).hexdigest(),
             "authorization":"User requests one click approve then next; click explicitly confirms displayed image criteria",
             "original_package_modified":False,"automatic_or_bulk_approval":False}
    (OUT/"REVIEW_CEPAT_RECEIPT.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    print(OUT/"review_cepat.html")


if __name__=="__main__": main()
