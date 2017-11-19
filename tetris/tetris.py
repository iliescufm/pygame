import random as n
import pygame
from pygame import *
def k(w,h):return m(lambda x:[0]*h,' '*w)
def cg(g):return m(lambda x:x[:],g)
def ro(o,c,r):return o if r<1 else ro(m(lambda x:m(lambda y:o[y][3-x-1+c],b(4)),b(4)),c,r-1)
def mo(o):
 p=n.choice(m(lambda x:[x%3+1,x in(0,3),m(lambda y:ord(y)-97,'bfjn cgkj bfjk fgjk cgfj bfgk befg'.split()[x])],b(7)))
 for t in p[2]:o[t%4][t/4]=p[0]
 return o,p[1]
m,b,v,z,L=map,range,filter,255,len
def q(a,o,x,y,n=1):
 g=cg(a)
 for c in b(16):
  tx,ty,p=c%4+x,c/4+y,o[c%4][c/4]
  if p:
   if tx<0 or tx>9 or ty>19 or (a[tx][ty] and n):return 3
   g[tx][ty]=p
 return g
def cl(r,l,t=lambda g:m(lambda x:m(lambda y:g[y][x],b(L(g))),b(L(g[0])))):
 r=v(lambda x:0 in x,t(r))
 return t([[0]*10]*(20-L(r))+r),l+20-L(r)
def dm(o,a,ox,oy,dx,dy):
 ox=ox if q(a,o,ox+dx,oy)==3 else ox+dx
 return(a,o,ox,oy+dy)if(dy==0 or q(a,o,ox,oy+dy)!=3)else(q(a,o,ox,oy),3,ox,0)
def mn(e,s,a,o,ox,oy,fc,ck,cn,l,dr,j,t,f):
 while not('12-Quit'in e or"y': 27,"in e):
  fc,d,y,e=fc+1+5*key.get_pressed()[274]+l/15,((l/10)%7),'0201120 0020110 2001022 0222101 1120011 0000202'.split(),str(v(lambda x:x.type!=3,event.get()))
  c=[[0]*3,[z]*3]+[m(lambda x:127*int(y[:3][x][d]),b(3)),m(lambda x:127*int(y[3:][x][d]),b(3))]
  dx=-1 if("y': 276"in e)else 1 if("y': 275"in e)else 0
  ox,oy=(3,0)if o==3 else (ox,oy)
  o,cn = (o,cn) if o!=3 else mo(k(4,4))
  r=3 if("y': 32,"in e)else 1 if("y': 273"in e)else 0
  o=ro(o,cn,r)
  o=o if q(a,o,ox,oy)!=3 else ro(o,cn,4-r)
  a,o,ox,oy=dm(o,a,ox,oy,dx,(fc>30)+0)
  fc=fc*(fc<31)
  ra=a if o==3 else q(a,o,ox,oy,0)
  if ra==3:return
  a,l=(a,l)if o!=3 else cl(a,l)
  s.fill(c[0])
  for y in b(200):dr(s,c[ra[y%10][y/10]],Rect((y%10)*15+j,t+(y/10)*15,15,15))
  dr(s,c[1],Rect(j,t,151,301),1),s.blit(f.render("Lines: "+str(l),0,c[1]),(j,t/2)),display.flip(),ck.tick(60)
mn(init(),display.set_mode((640,480)),k(10,20),3,0,0,0,time.Clock(),1,0,draw.rect,245,85,font.Font(None,24))
