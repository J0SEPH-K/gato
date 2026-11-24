import struct, sys

def secs_of(d):
    pe=struct.unpack_from('<I',d,0x3c)[0]
    nsec=struct.unpack_from('<H',d,pe+6)[0]; opt=struct.unpack_from('<H',d,pe+20)[0]
    out=[]
    for i in range(nsec):
        o=pe+24+opt+40*i; nm=d[o:o+8].rstrip(b'\0'); vs,va,rs,rp=struct.unpack_from('<4I',d,o+8); out.append((nm,va,rs,rp))
    return pe,opt,out

def r2o(secs,rva):
    for nm,va,rs,rp in secs:
        if rp and va<=rva<va+rs: return rp+(rva-va)
    return None

p=sys.argv[1]; d=open(p,'rb').read()
pe,opt,secs=secs_of(d)
magic=struct.unpack_from('<H',d,pe+24)[0]
diroff = pe+24+(96 if magic==0x10b else 112)
print('magic',hex(magic))
for idx,nm in [(0,'export'),(1,'import'),(2,'resource'),(3,'exception')]:
    rva,sz=struct.unpack_from('<II',d,diroff+8*idx)
    print(' dir %-9s %08x %d'%(nm,rva,sz))
    if nm=='export' and rva:
        o=r2o(secs,rva)
        ch,ts,maj,mi,dn,base,nf,nn,af,an,ao=struct.unpack_from('<IIHHIIIIIII',d,o)
        print('  dllname',d[r2o(secs,dn):d.index(b'\0',r2o(secs,dn))].decode('latin1'),'nf',nf,'nn',nn)
        for i in range(min(nn,30)):
            nr=struct.unpack_from('<I',d,r2o(secs,an)+4*i)[0]
            print('   name',d[r2o(secs,nr):d.index(b'\0',r2o(secs,nr))].decode('latin1'))
        for i in range(min(nf,30)):
            print('   ord%d rva %08x'%(base+i,struct.unpack_from('<I',d,r2o(secs,af)+4*i)[0]))
    if nm=='import' and rva:
        q=r2o(secs,rva)
        while True:
            oft,ts,fc,nmr,ft=struct.unpack_from('<5I',d,q)
            if not nmr: break
            no=r2o(secs,nmr); print('  ',d[no:d.index(b'\0',no)].decode('latin1')); q+=20
