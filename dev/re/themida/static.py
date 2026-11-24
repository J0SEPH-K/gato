import struct, re, sys, hashlib, json
P='/Users/jungjunkim/.hermes/cache/scratch/winagent/downloads/Gersang.exe'
d=open(P,'rb').read()
pe=struct.unpack_from('<I',d,0x3c)[0]
nsec=struct.unpack_from('<H',d,pe+6)[0]; opt=struct.unpack_from('<H',d,pe+20)[0]
ib=struct.unpack_from('<Q',d,pe+24+24)[0]
secs=[]
for i in range(nsec):
    o=pe+24+opt+40*i
    vs,va,rs,rp=struct.unpack_from('<4I',d,o+8)
    secs.append((va,vs,rp,rs))
def r2o(rva):
    for va,vs,rp,rs in secs:
        if va<=rva<va+max(vs,rs): return rp+(rva-va)
    return None
D={}
for i,name in [(0,'export'),(1,'import'),(2,'resource'),(3,'exception'),(4,'cert'),(5,'reloc'),(6,'debug'),(9,'tls'),(10,'loadconfig'),(12,'iat'),(13,'delayimport'),(14,'comdesc')]:
    rva,sz=struct.unpack_from('<II',d,pe+24+112+8*i)
    D[name]=(rva,sz)
    if rva and sz:
        o=r2o(rva)
        if o is not None and o+sz<=len(d):
            open(f'blob_{name}.bin','wb').write(d[o:o+sz])
            print('%-12s rva=%08x size=%d -> saved'%(name,rva,sz))
        else: print('%-12s rva=%08x size=%d -> unmapped'%(name,rva,sz))

# imports
out=[]
o=r2o(D['import'][0])
if o:
    p=o
    while True:
        oft,ts,fc,name,ft=struct.unpack_from('<5I',d,p)
        if not name: break
        no=r2o(name); dll=d[no:d.index(b'\0',no)].decode('latin1')
        fns=[]
        fo=r2o(oft or ft)
        if fo:
            q=fo
            while True:
                v=struct.unpack_from('<Q',d,q)[0]
                if not v: break
                if v & (1<<63): fns.append('#%d'%(v&0xffff))
                else:
                    ro=r2o(v&0x7fffffff)
                    fns.append(d[ro+2:d.index(b'\0',ro+2)].decode('latin1') if ro else '?')
                q+=8
        out.append({'dll':dll,'functions':fns})
        p+=20
json.dump(out,open('imports.json','w'),indent=1)
print('imports:',sum(len(x['functions']) for x in out),'funcs in',len(out),'dlls:',', '.join(x['dll'] for x in out))

# exception table = original function map
exc=open('blob_exception.bin','rb').read()
n=len(exc)//12
ents=struct.unpack_from('<%dI'%(n*3),exc,0)
starts=sorted(set(ents[0::3]))
print('pdata entries:',n,'unique starts:',len(starts),'min rva %08x max %08x'%(starts[0],starts[-1]))
open('func_starts.txt','w').write('\n'.join('%08x'%s for s in starts))

# resources tree names
o=r2o(D['resource'][0])
if o:
    names=set()
    for m in re.finditer(rb'(?:\x00\x00)?[\x20-\x7e]{3,40}\x00',d[o:o+2000]):
        s=m.group().strip(b'\x00')
        if len(s)>3: names.add(s.decode('latin1'))
    print('resource names sample:',sorted(names)[:20])

# signature
print('signed:', D['cert'][1]>0, 'cert bytes', D['cert'][1])
print('sha256', hashlib.sha256(d).hexdigest().upper())
