#!/usr/bin/env python3
"""Staging boards for the two alternative ORA directions: Zellige and Crease.
Composition proposals only; nothing here is renderer output.
"""
from pathlib import Path
import html,json,math
ROOT=Path(__file__).resolve().parent
NAVY='#1B2D4F';NIGHT='#121C30';CREAM='#FBEACE';CORAL='#D9533F';CORAL2='#F07A66';PAPER='#FAFAF7';INK='#151A24'
CLAY='#B8643F';CLAYD='#7A3B22';GLAZE_B='#27477A';GLAZE_G='#3E7A6A';GLAZE_Y='#D9A441';PLASTER='#EFE6D6'
def esc(s):return html.escape(str(s),quote=True)
def poly(pts,fill,stroke='none',w=1,extra=''):return f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x,y in pts)}" fill="{fill}" stroke="{stroke}" stroke-width="{w}" {extra}/>'
def path(d,stroke,w=2,fill='none',extra=''):return f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{w}" {extra}/>'
def rect(x,y,w,h,fill,stroke='none',r=0,extra=''):return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" fill="{fill}" stroke="{stroke}" {extra}/>'
def circle(x,y,r,fill,extra=''):return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{fill}" {extra}/>'
def text(x,y,v,size,fill,weight=400,extra=''):return f'<text x="{x}" y="{y}" fill="{fill}" font-family="DM Sans, sans-serif" font-size="{size}" font-weight="{weight}" {extra}>{esc(v)}</text>'

# ---------- Zellige ----------
def star(cx,cy,r,rot=0):
 pts=[]
 for k in range(16):
  a=rot+k*math.pi/8;rr=r if k%2==0 else r*.62;pts.append((cx+rr*math.cos(a),cy+rr*math.sin(a)))
 return pts
def tile(cx,cy,r,fill,rot=0,jitter=0,chip=False):
 pts=[(x+jitter*math.sin(i*2.3),y+jitter*math.cos(i*1.7)) for i,(x,y) in enumerate(star(cx,cy,r,rot))]
 s=poly(pts,fill,'#00000055',1.2)+poly(star(cx-r*.12,cy-r*.12,r*.35,rot),'#ffffff22')
 if chip:s+=poly([pts[2],pts[3],((pts[2][0]+pts[3][0])/2+6,(pts[2][1]+pts[3][1])/2+8)],CLAY)
 return s
def tessellation(x0,y0,cols,rows,step,r,fills,missing=()):
 s=''
 for j in range(rows):
  for i in range(cols):
   if (i,j) in missing:continue
   s+=tile(x0+i*step,y0+j*step,r,fills[(i+j*2)%len(fills)])
   s+=poly([(x0+i*step+step/2,y0+j*step-r*.42),(x0+i*step+step/2+r*.42,y0+j*step),(x0+i*step+step/2,y0+j*step+r*.42),(x0+i*step+step/2-r*.42,y0+j*step)],CREAM,'#00000033')
 return s
def construction(cx,cy,r,color=CORAL2,progress=1):
 s=circle(cx,cy,r,'none',f'stroke="{color}" stroke-width="2"')+circle(cx,cy,r*.62,'none',f'stroke="{color}" stroke-width="1.2" stroke-dasharray="4 4"')
 n=int(8*progress)
 for k in range(n):
  a=k*math.pi/4;s+=path(f'M {cx+r*math.cos(a):.1f} {cy+r*math.sin(a):.1f} L {cx+r*math.cos(a+math.pi*3/4):.1f} {cy+r*math.sin(a+math.pi*3/4):.1f}',color,1.6)
 return s+circle(cx,cy,4,color)
def zellige(n):
 bg=rect(0,0,1280,720,'#1a1410')
 if n==0:return bg+rect(0,0,1280,720,'url(#zglaze)')+path('M 0 380 C 300 330 700 430 1280 360',CREAM,3,extra='opacity=".35"')+circle(820,250,90,'#ffffff18')
 if n==1:
  s=bg+rect(0,420,1280,300,'#2b211a')
  fills=[CORAL,GLAZE_B,GLAZE_G,GLAZE_Y,CREAM,'#8a4f8a']
  for i in range(14):s+=tile(110+i*82+(i%3)*14,470+(i%4)*48,34,fills[i%6],i*.37,4,chip=i%5==2)
  s+=circle(640,260,160,'#ffffff08')
  return s
 if n==2:
  s=bg+tile(520,330,60,CORAL,.2,6)+tile(640,330,60,GLAZE_B,.9,8)+path('M 580 300 L 580 360',CREAM,2)
  s+=tile(760,420,60,GLAZE_G,.5,6,True)+path('M 760 400 L 772 432 L 752 452','#000',2.5)
  for i,(x,y) in enumerate([(300,560),(980,600),(1120,640)]):s+=tile(x,y,30,[GLAZE_Y,CORAL,CREAM][i],i,5)+path(f'M {x} {y} L {x+30} {y+90}',CREAM,1,extra='stroke-dasharray="3 6" opacity=".5"')
  return s
 if n==3:return rect(0,0,1280,720,NIGHT)+construction(640,360,220,CORAL2,1)+path('M 640 360 L 860 360',CREAM,1.5)+circle(860,360,5,CREAM)
 if n==4:
  s=rect(0,0,1280,720,PLASTER)+tessellation(220,130,9,5,110,46,[GLAZE_B,CORAL,GLAZE_G,CREAM],missing=((7,1),(8,3),(0,4),(1,4)))
  for (i,j) in [(7,1),(8,3)]:s+=tile(220+i*110+18,130+j*110-30,46,CORAL,.3,7)
  s+=construction(220+4*110,130+2*110,250,CORAL2,1).replace('stroke-width="2"','stroke-width="2" opacity=".6"')
  return s
 if n==5:
  s=rect(0,0,1280,720,PLASTER)+tessellation(220,130,9,5,110,46,[GLAZE_B,CORAL,GLAZE_G,CREAM])
  s+=circle(1100,350,70,'none',f'stroke="{CORAL2}" stroke-width="3"')
  for (i,j) in [(1,1),(3,3),(5,0),(7,2),(2,4)]:s+=circle(220+i*110,130+j*110,52,'none',f'stroke="{CORAL2}" stroke-width="2" stroke-dasharray="3 4"')
  return s
 if n==6:
  s=rect(0,0,1280,720,NIGHT)
  layers=[('#5c3a28',90),(CLAY,60),(PLASTER,30),(GLAZE_B,40),(CORAL2,14)]
  y=600
  for c,h in layers:y-=h;s+=rect(240,y,800,h,c,'#00000044')
  s+=path(f'M 640 {y} V 620',CORAL2,3,extra='filter="url(#zglow)"')
  return s
 if n==7:
  s=rect(0,0,1280,720,'#2b211a')
  for k,(x,w) in enumerate([(60,360),(460,360),(860,360)]):
   s+=rect(x,120,w,480,PLASTER,'#00000044')+f'<g opacity=".95">'+tessellation(x+50,180,4,5,86,36,[[GLAZE_B,CREAM],[GLAZE_G,CREAM],[CORAL,CREAM]][k])+'</g>'
   s+=tile(x+w/2,360,40,CORAL2)
  return s
 s=rect(0,0,1280,720,NIGHT)+rect(0,0,1280,720,'url(#zgrid)')+circle(470,360,96,'none',f'stroke="{CORAL}" stroke-width="34"')
 s+=poly(star(470,360,60,.2),'none',CREAM,1.2)+text(600,404,'RA',150,CREAM,700,'letter-spacing="14"')+text(842,404,'Ventures',72,CREAM)
 return s

# ---------- Crease ----------
def sheet(x,y,w,h,rot=0,fill=PAPER,shadow=True):
 cx,cy=x+w/2,y+h/2
 s=f'<g transform="rotate({rot} {cx} {cy})">'
 if shadow:s+=rect(x+8,y+10,w,h,'#00000018')
 s+=rect(x,y,w,h,fill,'#d8d3c6')
 for k in range(5):s+=rect(x+w*.12,y+h*(.18+k*.12),w*(.6-k*.05),3,'#9aa0aa')
 return s+'</g>'
def crumpled(x,y,r):
 pts=[(x+r*(0.8+0.25*math.sin(k*2.7))*math.cos(k*math.pi/6),y+r*(0.8+0.25*math.cos(k*1.9))*math.sin(k*math.pi/6)) for k in range(12)]
 return poly([(a+8,b+10) for a,b in pts],'#00000018')+poly(pts,PAPER,'#cfc9ba')+path(f'M {x-r*.5} {y-r*.2} L {x} {y+r*.1} L {x+r*.4} {y-r*.3} M {x-r*.2} {y+r*.4} L {x+r*.2} {y}','#cfc9ba',1.2)
def plane(x,y,s=1,rot=0):
 return f'<g transform="translate({x} {y}) rotate({rot}) scale({s})">'+poly([(0,0),(120,30),(0,60),(30,30)],PAPER,'#cfc9ba')+poly([(0,0),(120,30),(30,30)],'#ebe6da','#cfc9ba')+'</g>'
def creases(x,y,w,h,color=CORAL,width=2):
 s=''
 for k in range(1,4):s+=path(f'M {x+w*k/4} {y} V {y+h}',color,width,extra='stroke-dasharray="8 5"')
 for k in range(1,3):s+=path(f'M {x} {y+h*k/3} H {x+w}',color,width)
 s+=path(f'M {x} {y} L {x+w/4} {y+h/3} M {x+w} {y} L {x+w*3/4} {y+h/3} M {x} {y+h} L {x+w/4} {y+h*2/3} M {x+w} {y+h} L {x+w*3/4} {y+h*2/3}',color,width)
 return s
def tiered(x,y,s=1,color=CORAL):
 g=f'<g transform="translate({x} {y}) scale({s})">'
 for k in range(5):
  w=200-k*30;h=26;yy=-k*30
  g+=poly([(-w/2,yy),(w/2,yy),(w/2+22,yy-14),(-w/2+22,yy-14)],'#ece7db','#cfc9ba')+rect(-w/2,yy,w,h,PAPER,'#cfc9ba')
  g+=path(f'M {-w/2} {yy} H {w/2}',color if k==2 else '#cfc9ba',2)
 return g+'</g>'
def crease(n):
 desk=rect(0,0,1280,720,'#e9e4d8')+rect(0,0,1280,720,'url(#cgrain)')
 if n==0:
  s=desk
  for i in range(5):s+=sheet(120+i*200,140+(i%2)*120,140,190,(i*13)%21-10)
  s+=crumpled(1100,520,60)+plane(900,560,1,-20)+plane(180,520,.8,15)+crumpled(600,560,50)
  return s
 if n==1:
  s=desk+plane(380,300,1.2,-35)+plane(470,270,1.2,140)+path('M 470 300 l 20 -30 l 10 40 l 20 -25','#9aa0aa',2)
  s+=crumpled(900,300,70)+sheet(1150,500,140,190,30)+path('M 1180 520 L 1260 600',INK,1,extra='stroke-dasharray="4 6"')
  return s
 if n==2:return desk+sheet(440,110,400,520,0,shadow=True)+creases(440,110,400,520)
 if n==3:
  s=desk
  for i in range(6):s+=tiered(180+i*185,520+(i%2)*40,.7)
  return s
 if n==4:
  s=desk
  for i in range(6):s+=tiered(180+i*185,520+(i%2)*40,.7,CORAL2 if i else CORAL)
  s+=circle(180,430,70,'none',f'stroke="{CORAL}" stroke-width="2" stroke-dasharray="4 5"')+path('M 260 420 C 500 300 800 300 1100 420',CORAL,2,extra='marker-end="url(#carrow)"')
  return s
 if n==5:
  s=desk+rect(0,640,1280,80,'#d6cfbf')+path('M 0 640 H 1280','#bdb5a3',4)+tiered(640,520,1.4)
  s+=sheet(980,170,180,240,6)+path('M 760 400 C 860 360 920 300 990 280',CORAL,1.6)
  s+=path('M 560 330 C 580 300 610 290 640 300','#c9b8a4',16,extra='stroke-linecap="round"')
  return s
 if n==6:
  s=desk
  for k in range(6):s+=rect(110+k*6,520-k*40,250-k*12,34,PAPER,'#cfc9ba')
  s+=rect(500,380,300,170,PAPER,'#cfc9ba')+''.join(poly([(500+i*60,380),(530+i*60,340),(560+i*60,380)],'#ece7db','#cfc9ba') for i in range(5))
  s+=rect(900,300,240,250,PAPER,'#cfc9ba')+''.join(rect(920+c*55,320+r*45,36,24,'#ece7db','#cfc9ba') for r in range(5) for c in range(4))
  return s+path('M 0 600 H 1280',CORAL,3)
 s=rect(0,0,1280,720,PAPER)+rect(0,0,1280,720,'url(#cgridl)')+circle(470,360,96,'none',f'stroke="{CORAL}" stroke-width="34"')
 s+=text(600,404,'RA',150,NAVY,700,'letter-spacing="14"')+text(842,404,'Ventures',72,NAVY)
 return s

DEFS=f'''<defs><style>@font-face{{font-family:'DM Sans';src:url(../storyboard/fonts/DMSans.ttf)}}</style>
<radialGradient id="zglaze" cx=".55" cy=".4" r=".8"><stop stop-color="{CORAL2}"/><stop offset=".45" stop-color="{CORAL}"/><stop offset="1" stop-color="{CLAYD}"/></radialGradient>
<pattern id="zgrid" width="48" height="48" patternUnits="userSpaceOnUse"><path d="M 48 0 H 0 V 48" fill="none" stroke="#263044"/></pattern>
<pattern id="cgridl" width="48" height="48" patternUnits="userSpaceOnUse"><path d="M 48 0 H 0 V 48" fill="none" stroke="#DEDBD2"/></pattern>
<pattern id="cgrain" width="23" height="19" patternUnits="userSpaceOnUse"><circle cx="3" cy="7" r=".7" fill="#8a826f" opacity=".2"/></pattern>
<filter id="zglow" filterUnits="userSpaceOnUse" x="0" y="0" width="1280" height="720"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<marker id="carrow" markerWidth="9" markerHeight="9" refX="6" refY="3" orient="auto"><path d="M 0 0 L 6 3 L 0 6" fill="none" stroke="{CORAL}" stroke-width="1.3"/></marker></defs>'''
TITLES={'zellige':['Macro glaze','Loose tiles','Gaps and cracks','One construction','Tiles snap in','One refinement, everywhere','Five strata','Courtyards','ORA'],
        'crease':['Many folds','Collisions','One crease pattern','Unison refold','One refinement, everywhere','Sources and hands','Paper architectures','ORA']}
TIMES={'zellige':[(0,3),(3,6),(6,13),(13,20),(20,27),(27,31),(31,37),(37,42),(42,45)],'crease':[(0,6),(6,12),(12,19),(19,25),(25,30),(30,36),(36,41),(41,45)]}
def main():
 out={}
 for name,fn,count in [('zellige',zellige,9),('crease',crease,8)]:
  (ROOT/name).mkdir(exist_ok=True);boards=[]
  for i in range(count):
   (ROOT/name/f'{i+1:02}.svg').write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">{DEFS}{fn(i)}</svg>')
   boards.append({'image':f'{name}/{i+1:02}.svg','title':TITLES[name][i],'start':TIMES[name][i][0],'end':TIMES[name][i][1]})
  out[name]=boards
 (ROOT/'boards.json').write_text(json.dumps(out,indent=1)+'\n')
main()
