"""Compare functions of an original .pyc against a decompiled .py, instruction by instruction (run with Python 3.11).
   python dev/tools/bytecode_compare.py original.pyc decompiled.py [name-prefix ...]
Decompiled sources here have known mistakes; this finds them (one was in jochul.periodic_decode)."""
import sys, dis, marshal, types
def load_pyc(p):
    with open(p,'rb') as f: f.read(16); return marshal.load(f)
def norm(code):
    ins=list(dis.get_instructions(code)); skip=('CACHE','RESUME','NOP','EXTENDED_ARG')
    kept=[i for i in ins if i.opname not in skip]; kidx={i.offset:n for n,i in enumerate(kept)}
    idx={}
    nxt=len(kept)
    for i in reversed(ins):
        if i.offset in kidx: nxt=kidx[i.offset]
        idx[i.offset]=nxt
    out=[]
    for i in ins:
        if i.opname in ('CACHE','RESUME','NOP','EXTENDED_ARG'): continue
        if i.opcode in dis.hasjrel or i.opcode in dis.hasjabs:
            out.append((i.opname,'->',idx.get(i.argval)))
        elif isinstance(i.argval, types.CodeType): out.append((i.opname,'<code %s>'%i.argval.co_name))
        else: out.append((i.opname, repr(i.argval)))
    return out
def walk(code, prefix=''):
    d={prefix+code.co_name: code}
    cnt={}
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            cnt[c.co_name]=cnt.get(c.co_name,0)+1
            sub=walk(c, prefix+code.co_name+'.')
            # unique key: name + ordinal among siblings
            for k,v in sub.items():
                d[k.replace(prefix+code.co_name+'.'+c.co_name, prefix+code.co_name+'.'+c.co_name+'#%d'%cnt[c.co_name],1)]=v
    return d
def compare(orig_pyc, src, only=None):
    o=walk(load_pyc(orig_pyc)); n=walk(compile(open(src,encoding='utf-8').read(), src, 'exec'))
    res=[]
    for k in sorted(set(o)|set(n)):
        if only and not any(k.startswith(x) or ('.'+x) in k for x in only): continue
        if k not in o: res.append((k,'ONLY IN REPO')); continue
        if k not in n: res.append((k,'ONLY IN ORIGINAL')); continue
        a,b=norm(o[k]),norm(n[k])
        res.append((k,'same' if a==b else 'DIFFERENT (%d vs %d ops)'%(len(a),len(b))))
    return res
if __name__=='__main__':
    for r in compare(sys.argv[1], sys.argv[2], sys.argv[3:] or None): print('%-45s %s'%r)

def firstdiff(orig_pyc, src, names):
    o=walk(load_pyc(orig_pyc)); n=walk(compile(open(src,encoding='utf-8').read(), src, 'exec'))
    for k in names:
        a,b=norm(o[k]),norm(n[k]); d=[(i,x,y) for i,(x,y) in enumerate(zip(a,b)) if x!=y]
        print('==',k,'diff ops:',len(d))
        for i,x,y in d[:6]: print('   #%d orig %s | repo %s'%(i,x,y))
