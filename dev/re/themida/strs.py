import re,sys,collections
d=open(sys.argv[1],'rb').read()
s=set()
for m in re.finditer(rb'[\x20-\x7e]{5,80}',d):
    t=m.group()
    if sum(chr(c).isalpha() for c in t)<len(t)*0.6: continue
    s.add(t.decode('latin1'))
u=set()
for m in re.finditer(rb'(?:[\x20-\x7e]\x00){5,80}',d):
    u.add(m.group().decode('utf-16-le'))
print('ascii',len(s),'utf16',len(u))
kw=['xign','x3','corona','mag','nina','scan','detect','debug','thread','window','class','module','driver','hash','cheat','macro','input','key','mouse','hook','inject','vm','time','snap','capture','bitblt','protect','gersang','akinter','wellbia','heartbeat','report','ban']
for k in kw:
    hits=sorted(x for x in s|u if k in x.lower())[:14]
    if hits: print('\n##',k); [print('  ',h) for h in hits]
