#!/usr/bin/env python3
"""Original SVG staging boards for the ORA Ventures intro film "The Common Block".
These are composition proposals, not renderer output. Board 03 links the rendered proof.
"""
from pathlib import Path
import html,json,math
ROOT=Path(__file__).resolve().parent
# Palette taken from the ORA Ventures website mockup (v2, October 2026).
NAVY='#1B2D4F';NIGHT='#121C30';DEEP='#0C1322';CREAM='#FBEACE';CORAL='#D9533F';CORAL2='#F07A66'
GOOD='#2E8B57';WARN='#C4862A';BAD='#EE6A5E';LINE='#263044';MUTED='#9FAAC0'
def esc(s):return html.escape(str(s),quote=True)
def text(x,y,v,size=24,fill=CREAM,weight=400,extra=''):return f'<text x="{x}" y="{y}" fill="{fill}" font-family="DM Sans, sans-serif" font-size="{size}" font-weight="{weight}" {extra}>{esc(v)}</text>'
def rect(x,y,w,h,fill,stroke='none',r=0,extra=''):return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" fill="{fill}" stroke="{stroke}" {extra}/>'
def path(d,stroke=CREAM,width=2,fill='none',extra=''):return f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{width}" {extra}/>'
def circle(x,y,r,fill,extra=''):return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{fill}" {extra}/>'
def poly(points,fill,stroke='none',extra=''):return f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x,y in points)}" fill="{fill}" stroke="{stroke}" {extra}/>'

def night():return rect(0,0,1280,720,NIGHT)+rect(0,0,1280,720,'url(#sitegrid)')
def floor(horizon=360,color=LINE):
 s=rect(0,horizon,1280,720-horizon,DEEP)
 for i in range(-16,17):s+=path(f'M {640+i*30} {horizon} L {640+i*170} 720',color,1)
 y=horizon
 for k in range(1,12):y=horizon+(720-horizon)*(k/11)**1.8;s+=path(f'M 0 {y:.1f} H 1280',color,1)
 return s
def orb(x,y,r,color,glow=True):
 s=circle(x,y,r*2.6,color,'opacity=".18"') if glow else ''
 return s+circle(x,y,r,color)+circle(x-r*.3,y-r*.3,r*.35,'#ffffff','opacity=".5"')
def figure(x,y,scale=1,color='#33415f'):
 return circle(x,y-38*scale,9*scale,color)+rect(x-11*scale,y-27*scale,22*scale,27*scale,color,r=8*scale)
def crystal(x,y,kind,color=CREAM,cracked=False):
 shapes={0:[(0,-22),(14,-4),(6,18),(-8,16),(-14,-6)],1:[(0,-18),(18,0),(0,18),(-18,0)],2:[(-4,-24),(12,-10),(16,14),(-12,18),(-16,-2)],3:[(0,-20),(16,-10),(16,10),(0,20),(-16,10),(-16,-10)]}
 s=poly([(x+a,y+b) for a,b in shapes[kind]],color,DEEP,'stroke-width="1.5"')
 if cracked:s+=path(f'M {x-3} {y-18} L {x+4} {y-4} L {x-4} {y+4} L {x+3} {y+16}',BAD,2.5)
 return s
def gauge(x,y,level,h=90):
 color=BAD if level<0 else WARN if level<.5 else MUTED if level<1 else GOOD
 s=rect(x,y-h,10,h,'#ffffff08')+path(f'M {x-4} {y-h/1.3:.1f} H {x+14}',MUTED,1,extra='stroke-dasharray="2 2"')
 hh=abs(level)*h/1.3
 return s+(rect(x,y,10,min(hh,25),color) if level<0 else rect(x,y-hh,10,hh,color))
def room(x,y,w,h,orb_color,kind,level,cracked=False,figure_color='#33415f',lit='#1f2c47'):
 s=rect(x,y,w,h,lit,LINE,2)+figure(x+w*.3,y+h-10,1,figure_color)+orb(x+w*.62,y+h*.42,9,orb_color)
 s+=crystal(x+w*.62,y+h*.78,kind,CREAM if not cracked else '#e4c9b5',cracked)+gauge(x+w-22,y+h-8,level)
 return s
def tower(x,y,cols,rows,cell_w,cell_h,orbs,unified=False):
 s=rect(x-12,y-12,cols*cell_w+24,rows*cell_h+24,'#16223b',LINE,2)
 palette=[CORAL2,'#7FB3D5','#C9A0DC',WARN,'#8ED1B2','#E9E07A']
 for r in range(rows):
  for c in range(cols):
   i=r*cols+c;cx=x+c*cell_w;cy=y+r*cell_h
   s+=rect(cx+3,cy+3,cell_w-6,cell_h-6,'#24365a' if unified else '#1c2a45',LINE,1)
   s+=orb(cx+cell_w*.5,cy+cell_h*.45,4,CREAM if unified else palette[(i*7)%6],unified)
 return s
def slab(x,y,w,h,depth,top,side,front,stroke='#00000033'):
 return (poly([(x,y),(x+w,y),(x+w+depth,y-depth*.55),(x+depth,y-depth*.55)],top,stroke)
  +rect(x,y,w,h,front,stroke)+poly([(x+w,y),(x+w+depth,y-depth*.55),(x+w+depth,y+h-depth*.55),(x+w,y+h)],side,stroke))
def stack(x,y,scale=1,lines=False,lit=0):
 s=''
 s+=slab(x,y,520*scale,46*scale,110*scale,'#24375e','#14213a','#1b2b4b')
 s+=slab(x+28*scale,y-58*scale,464*scale,30*scale,96*scale,'#2e323b','#1a1d24','#23262e')
 s+=slab(x+56*scale,y-130*scale,408*scale,60*scale,84*scale,CORAL2,'#9c3a2c',CORAL)
 for row in range(4):
  for k in range(6):s+=rect(x+(80+k*62)*scale,y-(118-row*13)*scale,(40-row*3)*scale,3*scale,'#fbeace66')
 for i in range(5):
  cx=x+(80+i*76)*scale
  s+=slab(cx,y-196*scale,64*scale,58*scale,70*scale,'#22324f','#0f1729','#18233a')
  s+=slab(cx+6*scale,y-214*scale,52*scale,12*scale,60*scale,CREAM if lit else '#c9bda8','#a59a86','#e2d4ba')
  if lines:s+=path(f'M {cx+12*scale} {y-70*scale} V {y-198*scale}',CORAL2,4*scale,extra='filter="url(#glow)"')
 if lines:s+=path(f'M {x+92*scale} {y-70*scale} H {x+396*scale}',CORAL2,4*scale,extra='filter="url(#glow)"')
 return s

def board(n):
 if n==0: # Grid becomes façade
  s=night()+rect(0,0,1280,720,'url(#vignette)')
  s+=tower(330,90,9,6,68,84,False)
  s+='<g class="motion">'+path('M 160 640 C 160 420 230 250 300 170',CORAL2,2.5,extra='marker-end="url(#arrow)"')+text(60,676,'camera tilts: page grid → tower façade',16,MUTED)+'</g>'
  return s
 if n==1: # Fragmentation inside the rooms
  s=rect(0,0,1280,720,'#141f36')
  levels=[.13,.08,-.12,.16,.08];colors=[CORAL2,'#7FB3D5','#C9A0DC',WARN,'#8ED1B2']
  for i in range(5):
   x=40+i*244;s+=room(x,170,226,330,colors[i],i%4,levels[i],cracked=(i==2))
   s+=path(f'M {x+140} 170 C {x+150} 110 {x+120} 70 {x+170} 20',CORAL,1.6,extra='stroke-dasharray="4 6" opacity=".7"')
  for i in range(5):s+=rect(70+i*244,530,70,48,'#e9dcc4','#7b7466',r=3)+path(f'M {80+i*244} {546} h {40+i*3} M {80+i*244} {558} h {30-i*2}','#7b7466',1.5)
  s+=text(40,628,'same document, five slightly different copies',16,MUTED)+text(40,654,'threads of data drift out of the windows and fade',16,MUTED)
  return s
 if n==2: # Underground — linked to the actual proof render
  s=rect(0,0,1280,720,NIGHT)
  s+='<image href="proof-hero.png" x="0" y="0" width="1280" height="720" preserveAspectRatio="xMidYMid slice"/>'
  s+=rect(28,30,328,34,'#0C1322cc',r=4)+text(42,53,'RENDERED PROOF FRAME · not a sketch',14,CREAM,600)
  return s
 if n==3: # Connection — lines rise through the tower
  s=night()+floor(560)
  s+=stack(380,700,.55,True,1)
  s+=tower(380,40,9,5,64,84,True)
  for c in range(9):s+=path(f'M {412+c*64} 580 V 70',CORAL2,2.2,extra='filter="url(#glow)" opacity=".9"')
  for c in range(9):s+=gauge(992+ (c%3)*28,170+(c//3)*120,1.1+0.1*(c%3),80)
  s+=text(960,560,'every gauge column rises past 100 % together',15,MUTED)
  return s
 if n==4: # The improvement loop
  s=night()+floor(580)+stack(380,705,.55,True,1)+tower(380,40,9,5,64,84,True)
  s+=crystal(668,300,3,CORAL2)+circle(668,300,46,'none','stroke="#F07A66" stroke-width="2" stroke-dasharray="3 5"')
  s+='<g class="motion">'+path('M 668 350 C 668 470 640 540 640 600',CORAL2,3,extra='marker-end="url(#arrow)"')
  for c in [0,2,4,6,8]:s+=path(f'M 640 610 C {420+c*64} 560 {412+c*64} 420 {412+c*64} 150',CREAM,1.6,extra='marker-end="url(#arrowcream)" opacity=".75"')
  s+='</g>'+text(830,300,'one room finds a better cut',16,MUTED)+text(830,326,'↓ into the common block, ↑ to every room',16,MUTED)
  return s
 if n==5: # Trust as physics
  s=rect(0,0,1280,720,'#141f36')
  for i in range(3):
   x=90+i*390;s+=rect(x,120,330,330,'#1f2c47',LINE,2)+figure(x+90,440,1.3,'#3b4b6c')+orb(x+210,210,11,CREAM)
   s+=crystal(x+210,330,3,CREAM)+path(f'M {x+210} 350 C {x+250} 420 {x+120} 540 {x+70} 620',CORAL2,2,extra='opacity=".85"')
   s+=rect(x+40,600,70,46,'#e9dcc4','#7b7466',r=3)
  s+=path('M 132 410 C 150 380 190 360 228 350','#3b4b6c',10,extra='stroke-linecap="round"')
  s+=rect(0,660,1280,60,'#1B2D4F')+path('M 0 660 H 1280',CORAL,2)
  for x in [310,700,1090]:s+=path(f'M {x} 120 C {x+40} 40 {x+120} 40 {x+140} 120 S {x+120} 640 {x+60} 660',CORAL,1.6,extra='stroke-dasharray="5 5"')
  s+=text(40,60,'data loops back into the foundation · every output trails a thread to its source · a hand settles before it leaves',15,MUTED)
  return s
 if n==6: # The city
  s=rect(0,0,1280,720,'url(#dusk)')
  s+=rect(0,470,1280,250,'#0f1a2e')+path('M 0 470 H 1280',CORAL,3,extra='filter="url(#glow)"')
  s+=path('M 0 455 Q 200 440 360 452 T 760 448 T 1280 452 V 470 H 0 Z',NAVY,0,'#1B2D4F')
  s+=rect(1105,250,16,205,'#2a3a5c')+poly([(1100,252),(1113,226),(1126,252)],'#2a3a5c')+rect(1101,300,24,10,'#2a3a5c')
  # Knowledger: library of stacked folios
  for k in range(6):s+=rect(110+k*8,410-k*34,250-k*16,30,'#e9dcc4' if k%2 else '#d7c6a6','#7b7466',r=2)
  s+=text(140,500,'KNOWLEDGER · law firms',14,MUTED)
  # Blueprint: factory floor with bays
  s+=rect(470,330,320,140,'#22324f',LINE)+''.join(poly([(470+i*64,330),(502+i*64,300),(534+i*64,330)],'#2a3a5c',LINE) for i in range(5))
  for i in range(5):s+=rect(486+i*62,390,40,60,'#fbeace33',CORAL,r=2)
  s+=text(520,500,'BLUEPRINT · manufacturing',14,MUTED)
  # Backdesk: hotel courtyard with balconies
  s+=rect(880,250,200,220,'#1f2c47',LINE)
  for r in range(5):
   for c in range(4):s+=rect(894+c*48,264+r*40,32,22,CREAM if (r+c)%3 else '#fbeace55',r=2)
  s+=text(890,500,'BACKDESK · hospitality',14,MUTED)
  s+=stack(560,700,.35,True,1)+text(510,640,'the same foundation under every building',15,MUTED)
  return s
 # Aerial lockup
 s=night()+rect(0,0,1280,720,'url(#vignette)')
 s+=circle(470,360,96,'none',f'stroke="{CORAL}" stroke-width="34" filter="url(#glow)"')+circle(470,360,96,'none',f'stroke="{CORAL2}" stroke-width="10"')
 s+=text(600,404,'RA',150,CREAM,700,'letter-spacing="14"')+text(842,404,'Ventures',72,CREAM,400)
 s+=orb(470+96*math.cos(-.6),360+96*math.sin(-.6),10,CREAM)
 s+=path('M 470 360 m -150 0 a 150 150 0 1 0 300 0 a 150 150 0 1 0 -300 0',CREAM,1,extra='stroke-dasharray="2 8" opacity=".5"')
 return s

SHOTS=[
 ('The page becomes a city',0,5,'Recognition','The ORA site grid, face-on. The camera tilts and the grid becomes a dusk tower façade. Every cell is a room; every room has its own orb, its own colour, its own pulse.','None.','Every employee already has AI — each one differently.','Tower façade instancing; per-room orb clocks.'),
 ('Everyone on their own',5,12,'Friction','Inside the rooms: crystals come out in different shapes; one cracks red and is repaired by hand. One document exists in five drifting copies. Coral data threads leave through the windows and fade. Light-level gauges sit low; one dips below the floor.','None.','Scattered knowledge, uneven quality, data leaving unnoticed, efficiency near zero — all visible.','Crystal variants, crack event, thread curves, score-driven gauge columns.'),
 ('The difference is in the foundations',12,19,'Revelation','Below street level, five slabs fall on the beat. The coral common block hovers, hesitates, and lands with a shockwave. Coral lines run from it to every team.','None.','Something shared and structural sits underneath the work.','RENDERED: proof/ layers.mp4 (15 s) is this shot.'),
 ('One layer reaches everyone',19,25,'Relief','Coral lines rise from the common block through every floor. The orbs lock to one pulse and one colour; the crystals come out identical. Every gauge column rises past 100 % and turns green together.','None.','Shared infrastructure → consistent output → efficiency above 100 %.','Vertical tower lines; synchronized orb clock; gauge columns crossing the 100 % mark.'),
 ('One improvement, everywhere',25,30,'Momentum','One room cuts a better crystal. A pulse travels down into the common block, which reshapes, then up to every room at once.','None.','Optimisers: improvement found once is shared across all teams.','Pulse travel along existing lines; block surface update.'),
 ('Built to be trusted',30,36,'Confidence','Data threads now curve back into the foundation. Each crystal trails a thread to its source tile. A hand settles on each crystal before it leaves the room.','None.','Data stays yours · every answer has a source · people keep the decision.','Thread routing back into foundation; source tiles; hand gesture.'),
 ('A city on the same foundation',36,41,'Scale','Hard pullback. A library of folios, a factory floor, a hotel courtyard light up on the same coral foundation line. A Casablanca-like spire against the sea at dusk.','None.','Knowledger · Blueprint · Backdesk — ready for specific sectors.','Three massing models in the same materials; keep them abstract.'),
 ('ORA',41,45,'Ownership','Straight-down aerial. Streets straighten into the site grid. The common block seen from above is a coral ring: the O. “RA Ventures” sets beside it. One orb keeps circling.','ORA Ventures','The company is the foundation underneath everything we just saw.','Wordmark shaping with the site’s display face; top-down camera handoff.'),
]

DEFS=f'''<defs>
<style>@font-face{{font-family:'DM Sans';src:url(fonts/DMSans.ttf)}}</style>
<pattern id="sitegrid" width="48" height="48" patternUnits="userSpaceOnUse"><path d="M 48 0 H 0 V 48" fill="none" stroke="{LINE}" stroke-width="1"/></pattern>
<radialGradient id="vignette" cx=".5" cy=".5" r=".75"><stop offset=".55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".55"/></radialGradient>
<linearGradient id="dusk" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#0C1322"/><stop offset=".55" stop-color="#1B2D4F"/><stop offset=".7" stop-color="#6b3b3a"/><stop offset=".72" stop-color="{CORAL}"/></linearGradient>
<filter id="glow" filterUnits="userSpaceOnUse" x="0" y="0" width="1280" height="720"><feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<marker id="arrow" markerWidth="9" markerHeight="9" refX="6" refY="3" orient="auto"><path d="M 0 0 L 6 3 L 0 6" fill="none" stroke="{CORAL2}" stroke-width="1.3"/></marker>
<marker id="arrowcream" markerWidth="9" markerHeight="9" refX="6" refY="3" orient="auto"><path d="M 0 0 L 6 3 L 0 6" fill="none" stroke="{CREAM}" stroke-width="1.3"/></marker>
</defs>'''

def main():
 shots=[]
 for i,(name,start,end,feeling,action,copy,proof,gate) in enumerate(SHOTS):
  svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" role="img" aria-label="{esc(name)}">{DEFS}{board(i)}</svg>'
  (ROOT/f'{i+1:02}.svg').write_text(svg)
  shots.append(dict(id=i+1,title=name,start=start,end=end,feeling=feeling,action=action,copy=copy,proof=proof,gate=gate,image=f'{i+1:02}.svg'))
 assert sum(s['end']-s['start'] for s in shots)==45
 (ROOT/'story.json').write_text(json.dumps({'title':'The Common Block','duration':45,'status':'Proposed staging boards; board 03 is a rendered proof frame','shots':shots},indent=2)+'\n')
main()
