import subprocess,struct,json,os,select,time
from pathlib import Path
deadline=time.monotonic()+12
p=subprocess.Popen(['/usr/local/bin/docker','exec','-i','wheel-gateway-dual','socat','STDIO','UNIX-CONNECT:/tmp/.X11-unix/X1'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
def read(n):
 b=b''
 while len(b)<n:
  if not select.select([p.stdout],[],[],max(0,deadline-time.monotonic()))[0]: raise TimeoutError('X11 layout timeout')
  d=os.read(p.stdout.fileno(),n-len(b))
  if not d: raise RuntimeError('X11 connection closed')
  b+=d
 return b
p.stdin.write(struct.pack('<BBHHHHH',108,0,11,0,0,0,0));p.stdin.flush()
h=read(8);body=read(struct.unpack_from('<H',h,6)[0]*4)
if h[0]!=1: raise RuntimeError(repr(body))
vlen=struct.unpack_from('<H',body,16)[0]; nformats=body[21]; offset=32+((vlen+3)//4)*4+nformats*8
root=struct.unpack_from('<I',body,offset)[0]; width,height=struct.unpack_from('<HH',body,offset+20)

def req(op,data=b'',arg=0,reply=False):
 p.stdin.write(struct.pack('<BBH',op,arg,1+len(data)//4)+data);p.stdin.flush()
 if not reply:return
 while True:
  r=read(32)
  if r[0]==0: raise RuntimeError('X11 error '+repr(r))
  if r[0]==1:return r+read(struct.unpack_from('<I',r,4)[0]*4)
def tree(w):
 r=req(15,struct.pack('<I',w),reply=True); n=struct.unpack_from('<H',r,16)[0];return list(struct.unpack_from('<'+'I'*n,r,32))
def prop(w,atom):
 r=req(20,struct.pack('<IIIII',w,atom,0,0,1024),reply=True);return r[32:].rstrip(b'\0').decode(errors='replace')
def geo(w):
 r=req(14,struct.pack('<I',w),reply=True);return struct.unpack_from('<hhHH',r,12)
try:
 windows=[]
 for w in tree(root):
  if prop(w,39)!='IBKR Gateway': continue
  attrs=req(3,struct.pack('<I',w),reply=True)
  if attrs[26]==2: windows.append(w)
 if len(windows)==2:
  windows.sort()
  container=subprocess.check_output(['/usr/local/bin/docker','inspect','--format','{{.Id}} {{.State.StartedAt}}','wheel-gateway-dual'],text=True,timeout=3).strip()
  identity=[container,windows,width,height]
  state=Path.home()/'Library/Application Support/Wheel/gateway/layout-state.json'
  previous=json.loads(state.read_text()) if state.exists() else None
  if previous!=identity:
   gap=14; pane=(width-gap)//2; h=height-6
   for i,w in enumerate(windows):
    # Configure x/y/width/height only. Never close, activate, or send keys.
    req(12,struct.pack('<IHHIIII',w,15,0,i*(pane+gap),2,pane,h))
   req(43,reply=True) # round-trip flush before recording success
   assert all(geo(w)==(i*(pane+gap),2,pane,h) for i,w in enumerate(windows))
   state.parent.mkdir(parents=True,exist_ok=True)
   state.write_text(json.dumps(identity)); state.chmod(0o600)
finally:
 p.terminate()
 try:p.wait(timeout=2)
 except subprocess.TimeoutExpired:p.kill()
