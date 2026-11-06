"""Headless Chrome smoke test. Decisions are tested on temporary SYNTHETIC fixtures only."""
import base64
import json
import subprocess
import tempfile
import time
from pathlib import Path
import requests
import websocket
from PIL import Image,ImageDraw
import finalize_model_a as f


def main():
    with tempfile.TemporaryDirectory(prefix="fiscycle-review-test-") as directory:
        temp=Path(directory)
        process=subprocess.Popen(["C:/Program Files/Google/Chrome/Application/chrome.exe","--headless=new","--disable-gpu",
            "--no-first-run","--no-default-browser-check","--disable-background-networking","--disable-sync","--disable-component-update","--remote-debugging-port=0","--remote-allow-origins=http://localhost",
            "--user-data-dir="+str(temp/"profile"),"about:blank"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW)
        ws=None
        try:
            portfile=temp/"profile/DevToolsActivePort"
            for _ in range(100):
                if portfile.exists(): break
                time.sleep(.1)
            port=portfile.read_text().splitlines()[0]
            pages=requests.get(f"http://127.0.0.1:{port}/json",timeout=10).json()
            page=next(p for p in pages if p.get("type")=="page" and p.get("url")=="about:blank")
            ws=websocket.create_connection(page["webSocketDebuggerUrl"],origin="http://localhost",timeout=10)
            sequence=0
            def call(method,params=None):
                nonlocal sequence
                sequence+=1;ws.send(json.dumps({"id":sequence,"method":method,"params":params or {}}))
                while True:
                    response=json.loads(ws.recv())
                    if response.get("id")==sequence:
                        if "error" in response: raise RuntimeError(response)
                        return response.get("result",{})
            def js(expression):
                result=call("Runtime.evaluate",{"expression":expression,"returnByValue":True})
                if "exceptionDetails" in result: raise AssertionError(result)
                return result["result"].get("value")
            def wait(expression):
                for _ in range(100):
                    try:
                        if js(expression): return
                    except AssertionError: pass
                    time.sleep(.1)
                raise AssertionError("Timed out: "+expression+" | "+str(js("({url:location.href,body:document.body.innerText.slice(-1500),scripts:[...document.scripts].map(s=>s.src)})")))
            call("Page.enable");call("Runtime.enable")
            call("Emulation.setDeviceMetricsOverride",{"width":1440,"height":1000,"deviceScaleFactor":1,"mobile":False})
            call("Page.navigate",{"url":(f.OUT/"review.html").as_uri()})
            wait("typeof entry!=='undefined' && image!==null")
            assert js("data.items.length")==1435
            assert js("entry.track")=="A1"
            assert js("Object.keys(decisions).length")==0
            shot=call("Page.captureScreenshot",{"format":"png"})
            (temp/"actual_review.png").write_bytes(base64.b64decode(shot["data"]))
            js("$('track').value='A2';filter();")
            wait("entry.track==='A2' && image!==null && crop!==null")
            assert js("entry.split==='train'||entry.split==='validation'")
            js("$('search').value='1460';filter();")
            wait("entry.image_id==='1460' && image!==null")
            assert js("$('approve').disabled && entry.hard_hold")
            js("$('search').value='NO_SUCH_IMAGE';filter();")
            assert js("items.length")==0
            # Separate dummy image/package/profile namespace: never simulate approval of real data.
            img=Image.new("RGB",(640,640),"white");ImageDraw.Draw(img).rectangle((64,64,256,256),fill="brown");img.save(temp/"fixture.png")
            poly={"source_line":1,"source_class":1,"target_class":0,"points":[[.1,.1],[.4,.1],[.4,.4],[.1,.4]]}
            e={"id":"SYNTHETIC_ONLY","track":"A1","image_id":"SYNTHETIC_ONLY","split":"train","hard_hold":False,
               "source_polygons":[poly],"proposed_polygons":[poly],"image_url":"fixture.png","issues":"TEST ONLY",
               "checks_required":f.CHECKS["A1"],"proposal_hash":"synthetic","policy_hash":"synthetic","source_sha256":"synthetic"}
            (temp/"fixture.html").write_text((f.ROOT/"model_a_review.html").read_text(encoding="utf-8"),encoding="utf-8")
            (temp/"review.js").write_text((f.ROOT/"model_a_review.js").read_text(encoding="utf-8"),encoding="utf-8")
            (temp/"review_data.js").write_text("window.REVIEW_DATA="+json.dumps({"package_hash":"SYNTHETIC_BROWSER_TEST_ONLY","items":[e]}),encoding="utf-8")
            call("Page.navigate",{"url":(temp/"fixture.html").as_uri()})
            wait("typeof entry!=='undefined' && entry.id==='SYNTHETIC_ONLY' && image!==null")
            js("$('approve').click()")
            assert js("Object.keys(decisions).length")==0
            js("$('reviewer').value='SYNTHETIC FIXTURE ONLY';$('approve').click()")
            assert js("Object.keys(decisions).length")==0
            js("$('checks').querySelectorAll('input').forEach(c=>c.checked=true);$('approve').click()")
            assert js("decisions.SYNTHETIC_ONLY.decision")=="approve"
            js("$('add').click();pending=[[.5,.5],[.7,.5],[.6,.7]];$('finish').click()")
            assert js("polygons.length")==2
            assert js("Object.keys(decisions).length")==0
            js("$('undo').click()")
            assert js("polygons.length")==1
            js("$('revision').click()")
            assert js("decisions.SYNTHETIC_ONLY.decision")=="needs_revision"
            result={"status":"PASS","actual_package_items":1435,"actual_data_decisions_written":0,
                    "checks":["local file rendering A1/A2","hard hold disabled","empty filter","missing reviewer blocked",
                              "incomplete checklist blocked","synthetic approval only","polygon addition invalidates decision","undo","needs_revision"],
                    "browser":call("Browser.getVersion")["product"]}
            print(json.dumps(result,indent=2))
        finally:
            if ws:
                try: call("Browser.close")
                except Exception: pass
                ws.close()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.terminate();process.wait(timeout=10)


if __name__=="__main__": main()
