#!/usr/bin/env python3
"""Original SVG staging boards, not renderer output or a product UI capture."""
from pathlib import Path
import html,json,math,random
ROOT=Path(__file__).resolve().parent
INK='#172827';CREAM='#f2eddf';YELLOW='#e8c750';CORAL='#df735b';BLUE='#538ab8'
def esc(s):return html.escape(str(s),quote=True)
def text(x,y,value,size=24,fill=INK,family='sans',weight=400,extra=''):
 families={'sans':'DM Sans, sans-serif','serif':'Instrument Serif, Georgia, serif','mono':'monospace'}
 return f'<text x="{x}" y="{y}" fill="{fill}" font-family="{families[family]}" font-size="{size}" font-weight="{weight}" {extra}>{esc(value)}</text>'
def rect(x,y,w,h,fill,stroke='none',r=0,extra=''):return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" {extra}/>'
def path(d,stroke=INK,width=2,fill='none',extra=''):return f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{width}" {extra}/>'
def seed(x,y,r=48,material='gold',selected=False):
 fill={'gold':'url(#gold)','paper':'url(#paper)','weave':'url(#weave)','foil':'url(#foil)'}[material]
 s=f'<g transform="translate({x} {y})">'
 s+=f'<ellipse cx="6" cy="12" rx="{r}" ry="{r*.83}" fill="#172827" opacity=".12"/>'
 s+=f'<circle r="{r}" fill="{fill}" stroke="{INK}" stroke-width="1.7"/>'
 if material in ['gold','weave']:
  for j in range(-6,7):
   yy=j*r/7;xx=math.sqrt(max(0,r*r-yy*yy));s+=path(f'M {-xx} {yy} Q 0 {yy+r*.2} {xx} {yy}',INK,.55,extra='opacity=".25"')
 s+=path(f'M {r*.65} {-r*.76} L {r*.45} {-r*.52} L {r*.8} {-r*.5}',INK,3)
 s+=f'<ellipse rx="{r*1.35}" ry="{r*.42}" transform="rotate(-32)" fill="none" stroke="{CORAL}" stroke-width="2.2"/>'
 if selected:s+=rect(-r-13,-r-13,2*r+26,2*r+26,'none',BLUE,0,extra='stroke-width="2" stroke-dasharray="5 5"')
 return s+'</g>'
def hero(long=False,coral=False,material='gold',finish=False):
 s=rect(0,0,1280,720,CREAM)+rect(0,0,1280,720,'url(#grain)')
 s+=path('M 75 82 H 1205',INK,1)
 s+=rect(95,120,875 if long else 690,470,CORAL if coral else '#e7e1d1',INK,2)
 s+=rect(110,105,875 if long else 690,470,CREAM,INK,1.5)
 s+=text(155,356,'Hello, world.' if long else 'Hello.',132 if long else 174,family='serif')
 x=1040 if long else 890;y=360
 s+=path(f'M {860 if long else 700} 370 C 870 470 940 220 {x} {y}',CORAL,3)
 s+=seed(x,y,78,material)
 for xx,yy,r in [(1118,180,21),(1155,525,26),(925,580,18)]:
  s+=path(f'M {x} {y} Q {xx-55} {yy+25} {xx} {yy}',INK,1.2)+seed(xx,yy,r,material)
 if finish:
  for i in range(8):
   a=i*math.pi/4;xx=x+math.cos(a)*190;yy=y+math.sin(a)*145
   if xx<1240 and yy>100:s+=f'<circle cx="{xx}" cy="{yy}" r="{3+i%3}" fill="{INK}"/>'
 return s

def panel(x,y,w,h,label,value):
 return text(x,y,label,13,'#a1aca9')+rect(x,y+12,w,h,'#252c2d','#52605c',5)+text(x+12,y+44,value,17,'#f1eddf',family='mono')
def code(lines,active=0):
 s=''
 for i,line in enumerate(lines):
  if i==active:s+=rect(25,145+i*29,280,27,'#d7b84c22',r=3)
  s+=text(37,164+i*29,line,22,'#f2eddf',family='mono')
 return s

def timeline(t=8,mark=False):
 s=rect(330,613,900,78,'#1d2526',r=6)
 s+=text(348,638,'▶',17,'#eae6d9')+text(382,638,f'00:{int(t):02}.000',14,'#eae6d9',family='mono')
 s+=path('M 350 668 H 1207','#66716b',2)
 for j in range(15):
  x=350+j*60;s+=path(f'M {x} 663 V 673','#75827a',1)
 x=350+t/15*840;s+=path(f'M {x} 648 V 682',BLUE,3)
 if mark:s+=f'<path d="M {x-7} 645 L {x+7} 645 L {x} 654 Z" fill="{YELLOW}"/>'
 return s

def studio(art,lines=None,selected=False,inspect=False,t=8,export=False):
 s=rect(0,0,1280,720,'#111a1b')+text(27,39,'BEAM LISP',19,'#f1eddf',weight=700)
 s+=text(335,38,'hello-world.bl',15,'#b8c1ba')
 if export:s+=rect(1080,14,150,38,YELLOW,r=5)+text(1095,39,'Export film',16,INK,weight=600)
 else:s+=text(1040,38,'●  hello-world',14,'#c9d0c7')
 s+=rect(15,78,299,613,'#1a2324',r=6)+text(30,112,'SOURCE',12,'#a1aca9',weight=600)
 if lines:s+=code(lines,1 if selected else 0)
 s+=f'<svg x="330" y="79" width="900" height="506.25" viewBox="0 0 1280 720">{art}</svg>'
 if selected:
  s+=rect(427,191,583,198,'none',BLUE,extra='stroke-width="2"')
  for x,y in [(427,191),(1010,191),(427,389),(1010,389)]:s+=rect(x-4,y-4,8,8,CREAM,BLUE)
 s+=timeline(t,inspect)
 if inspect:
  s+=rect(991,102,219,231,'#172525',r=6)+text(1008,132,'world/original',14,'#f0ecde',family='mono')
  s+=text(1008,171,'Font',13,'#b2bcb4')+text(1008,195,'Instrument Serif',16,'#f2eddf')
  s+=text(1008,236,'Anchor',13,'#b2bcb4')+text(1008,260,'baseline / east',16,'#f2eddf')
  s+=path('M 995 285 H 1188',BLUE,1)+text(1008,308,'local setting',13,'#b2bcb4')
 return s

def family(mode='grid',material='gold',coral=True):
 s=rect(0,0,1280,720,CREAM)+rect(0,0,1280,720,'url(#grain)');points=[]
 for i in range(24):
  if mode=='grid':
   k=8 if i==0 else (0 if i==8 else i);x=335+(k%6)*145;y=160+(k//6)*135
  elif mode=='tree':
   depth=int(math.log2(i+1));local=i-(2**depth-1);x=200+(local+.5)/(2**depth)*1000;y=610-depth*112
  else:
   k=11 if i==0 else (0 if i==11 else i);x=640+math.sin((k-11)*.41)*390;y=100+k*22
  points.append((x,y))
 if mode!='grid':
  for i,(x,y) in enumerate(points[1:],1):
   px,py=points[(i-1)//2] if mode=='tree' else points[i-1]
   s+=path(f'M {px} {py} C {px+90} {py-20} {x-90} {y+20} {x} {y}',INK,1.4)
 for i,(x,y) in enumerate(points):
  if i==0:s+=seed(x,y,47,material)
  else:
   s+=f'<g transform="translate({x} {y}) rotate({(i%3-1)*6})">'+rect(-47,-34,94,68,CORAL if coral and i%3==0 else '#e5dfcd',INK,3)
   s+=text(-33,-9,'Hello.',23,family='serif')+path('M -32 8 H 27 M -32 17 H 13',INK,.8)+seed(25,19,11,material)+'</g>'
 return s

def material_world():
 s=rect(0,0,1280,720,'#111b20')
 # One silhouette with material boundaries, not separate before/after panels.
 s+='<defs><clipPath id="macroseed"><circle cx="720" cy="375" r="315"/></clipPath></defs>'
 s+=seed(720,375,315,'foil')
 s+='<g clip-path="url(#macroseed)">'+rect(380,30,210,690,'url(#paper)')+rect(590,30,190,690,'url(#weave)')+'</g>'
 s+=path('M 510 126 Q 600 365 510 625',CORAL,3)+path('M 704 68 Q 800 360 704 680',CORAL,3)
 s+=path('M 140 590 C 420 720 920 660 1150 170',CORAL,4)
 s+=f'<ellipse cx="720" cy="375" rx="420" ry="140" transform="rotate(-25 720 375)" fill="none" stroke="{CORAL}" stroke-width="3"/>'
 return s

def endcard():
 s=rect(0,0,1280,720,'#111b20')+text(85,296,'BEAM LISP',100,'#f1eddf',weight=750)
 s+=text(88,370,'Motion graphics.',40,'#f1eddf')+text(88,420,'Written in Lisp.',40,'#f1eddf')
 s+=text(90,536,'Make your first scene.',36,'#ddd9c7')
 s+=seed(985,355,150,'foil')
 for i in range(9):
  a=i*math.pi*2/9;x=985+math.cos(a)*210;y=355+math.sin(a)*215
  s+=path(f'M 985 355 Q {x-40} {y+40} {x} {y}','#566c69',1)+seed(x,y,17+i%3*3,'foil')
 return s

SHOTS=[
 ('The thing you want to make',0,4,'Desire','The finished picture is the opening promise. Follow its seed through a letter, then pull back until the studio is revealed.','Hello.','The moving image must be the same project we later edit.','Hero composition and seed/letter camera path.'),
 ('Put the creator in control',4,8,'Recognition','Reveal source, picture and time around the same frame. Selecting the title links its string to its visible bounds.','BEAM LISP · Motion graphics. Written in Lisp.','The selected word and the source highlight share an eyeline.','Proposed filming UI; coherent source edit and source/object selection needed.'),
 ('Change your mind; the picture follows',8,14,'Relief','Replace Hello. with Hello, world. The measured frame grows. Attached objects make room and stay connected.','Hello, world.','One visible input; one visible geometric consequence; 1.3-second readable hold.','Hero dependent layout and accepted-layout transition; source refresh if filmed live.'),
 ('One decision has reach',14,19,'Agency','Change one material value. Three matching instances update together; their individual identity and content remain.','No new advertising copy.','One definition visibly controls three surfaces.','Shared authored definition and multi-instance control/selection in this project.'),
 ('Small program, expansive picture',19,24,'Possibility','Pull back from three instances into 24. The original stays findable. A map call stays small while its family expands.','One actual map expression.','One rule beside many related results; original recognizable by shape and scale.','Author family with stable keys and actual map expression.'),
 ('Give the idea a rhythm',24,29,'Momentum','The family uncoils through branches, ribbon and helix. Continuous geometry and attachments carry the camera forward.','None.','Same keyed objects and seed trajectory; no cut to unrelated spectacle.','Compose the shared project with continuous score and explicit correspondence.'),
 ('Time is under your hand',29,34,'Control','Pause. Scrub backward. Jump away and return to the marked pose. The seed and connector crossing match exactly.','Real time display only.','Two readable returns to one marked moment; no replay dependency.','General-project seekable preview and equal-state/frame check.'),
 ('The beauty still has structure',34,39,'Confidence','Select the original. Show a real baseline and anchor. Move the component and let its connector remain attached.','Font · Anchor, if implemented.','The highlighted anchor and actual endpoint coincide.','Compact inspector and picking or an honest selector/numeric transform edit.'),
 ('Keep the idea; change its voice',39,46,'Freedom','Track across one surface as ink, weave and metal pass over it. Pull back to the familiar structure wearing its new finish.','None.','One silhouette, notch, texture space and coral line survive every material.','One supported project/material route; separate GPU and vector routes are not yet unified.'),
 ('This is the world you made',46,51,'Ownership','Reverse the opening move through the title’s o. The final frame contains all the decisions we watched the creator make.','Hello, world.','Longer title, coral stock, family, connections and chosen finish belong to this project.','Art-direct the actual cumulative hero, not unrelated final footage.'),
 ('Take the work with you',51,55,'Completion','Export the accepted frame/revision. Use an honest time cut through the job; the delivered movie matches the preview.','Export film · hello-world.mp4, if implemented.','An actual completed artifact, not a cosmetic progress animation.','General-project accepted-revision export and matching canonical frames.'),
 ('Name the medium; invite the maker',55,60,'Desire to act','Keep the world moving quietly at right. Hold the complete brand/category/invitation lockup from 56.2 seconds to the end.','BEAM LISP · Motion graphics. Written in Lisp. · Make your first scene.','Readable product, category and next action with no narrator.','An actual first-scene destination before release; never invent a URL.')
]

def board(n):
 if n==0:return hero()
 if n==1:return studio(hero(),['(text/block', '  {:id "title"}', '  "Hello.")'],True)+text(33,397,'Motion graphics.',24,'#f2eddf')+text(33,432,'Written in Lisp.',24,'#f2eddf')
 if n==2:
  s=studio(hero(True),['(text/block','  {:id "title"}', '  "Hello, world.")'],True)
  s+='<g class="motion">'+path('M 750 420 H 1020',CORAL,3,extra='marker-end="url(#arrow)"')+'</g>';return s
 if n==3:
  art=rect(0,0,1280,720,CREAM)
  for i in range(3):
   x=125+i*385;art+=rect(x,180,330,330,CORAL,INK,3)+text(x+32,275,'Hello.',62,family='serif')+seed(x+165,397,48)
  return studio(art,['(def stock coral)','', '(mapv world ideas)'])
 if n==4:
  return family('grid')+rect(25,24,275,105,'#172626',r=4)+text(45,58,'(defn world [idea] …)',17,'#f2eddf',family='mono')+text(45,99,'(mapv world ideas)',18,'#e8c750',family='mono')
 if n==5:return family('helix')
 if n==6:
  s=studio(family('helix'),['(clip/sample film 8)'],t=8)
  s+='<g class="motion">'+path('M 870 650 C 790 590 690 590 610 651',BLUE,3,extra='marker-end="url(#arrow)"')+path('M 610 683 C 685 715 790 715 870 684',BLUE,3,extra='marker-end="url(#arrow)"')+'</g>';return s
 if n==7:
  art=hero(True);art+=path('M 155 377 H 1020',BLUE,2)+f'<circle cx="1020" cy="377" r="8" fill="{BLUE}"/>'
  return studio(art,['{:id "world/original"', ' :at [1040 360]}'],True,True)
 if n==8:return material_world()
 if n==9:return hero(True,True,'foil',True)
 if n==10:
  s=studio(hero(True,True,'foil',True),['hello-world.bl'],export=True)
  s+=rect(28,385,270,125,'#24312f','#566c60',5)+text(45,420,'hello-world.mp4',19,'#f2eddf')+text(45,450,'▶  Play film',17,'#e8c750')+text(45,483,'Ready',14,'#bdc8ba');return s
 return endcard()

DEFS='''<defs>
<style>@font-face{font-family:'DM Sans';src:url(fonts/DMSans.ttf)}@font-face{font-family:'Instrument Serif';src:url(fonts/InstrumentSerif-Regular.ttf)}</style>
<linearGradient id="gold" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#fff3b7"/><stop offset=".43" stop-color="#e9cd58"/><stop offset="1" stop-color="#ab772e"/></linearGradient>
<linearGradient id="foil" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#e5feea"/><stop offset=".18" stop-color="#488b9a"/><stop offset=".29" stop-color="#edbca5"/><stop offset=".4" stop-color="#e6d46a"/><stop offset=".52" stop-color="#9cbaad"/><stop offset=".63" stop-color="#5d5298"/><stop offset=".72" stop-color="#f0d7e9"/><stop offset=".86" stop-color="#274748"/><stop offset="1" stop-color="#d8e5c5"/></linearGradient>
<pattern id="paper" width="7" height="7" patternUnits="userSpaceOnUse"><rect width="7" height="7" fill="#e8dfc8"/><circle cx="2" cy="3" r=".6" fill="#968e7b" opacity=".25"/></pattern>
<pattern id="weave" width="10" height="10" patternUnits="userSpaceOnUse"><rect width="10" height="10" fill="#b6c293"/><path d="M 0 1 H 10 M 1 0 V 10 M 0 6 H 10 M 6 0 V 10" stroke="#5b7658" stroke-width="1.2"/><path d="M 0 3 H 10 M 3 0 V 10" stroke="#e1ddaa" stroke-width="1"/></pattern>
<pattern id="grain" width="31" height="29" patternUnits="userSpaceOnUse"><circle cx="2" cy="17" r=".6" fill="#695d44" opacity=".13"/><circle cx="21" cy="4" r=".4" fill="#695d44" opacity=".15"/></pattern>
<marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M 0 0 L 6 3 L 0 6" fill="none" stroke="#df735b" stroke-width="1.2"/></marker>
</defs>'''

def main():
 shots=[]
 for i,(name,start,end,feeling,action,copy,proof,gate) in enumerate(SHOTS):
  body=board(i);svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" role="img" aria-label="{esc(name)}">{DEFS}{body}</svg>'
  (ROOT/f'{i+1:02}.svg').write_text(svg)
  shots.append(dict(id=i+1,title=name,start=start,end=end,feeling=feeling,action=action,copy=copy,proof=proof,gate=gate,image=f'{i+1:02}.svg'))
 assert sum(s['end']-s['start'] for s in shots)==60
 (ROOT/'story.json').write_text(json.dumps({'title':'Hello, world.','duration':60,'status':'Proposed staging boards; not captured UI or final film','shots':shots},indent=2)+'\n')
main()
(ROOT/'storyboard.md').write_text((ROOT.parents[1]/'PRODUCT-STORYBOARD.md').read_text().replace('evidence/storyboard/index.html','index.html'))
