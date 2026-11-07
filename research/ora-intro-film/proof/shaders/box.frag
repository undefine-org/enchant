#version 300 es
precision highp float;
in vec3 world;
in vec3 normal;
in vec3 local;
uniform vec3 eye;
uniform vec3 size;
uniform vec4 look; // material, glow, time, unused
out vec4 pixel;
const vec3 NAVY=vec3(.0063,.0116,.0296);
const vec3 CORAL=vec3(.871,.195,.133);
const vec3 CREAM=vec3(.965,.823,.617);
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
vec3 env(vec3 r){
 // Analytic studio: one broad softbox strip, a navy sky and a coral rim card.
 float strip=pow(max(0.,1.-abs(r.y-.52)*2.5),10.)*(.25+.75*smoothstep(-.6,.4,r.x));
 float sky=smoothstep(-.3,.9,r.y);
 float rim=pow(max(0.,dot(r,normalize(vec3(.85,.12,-.5)))),14.);
 return NAVY*.6+vec3(.05,.08,.16)*sky+vec3(1.45,1.35,1.2)*strip+CORAL*rim*1.4;
}
void main(){
 vec3 n=normalize(normal);vec3 v=normalize(eye-world);vec3 a=abs(n);
 vec2 face,dims;
 if(a.y>.5){face=local.xz;dims=size.xz;}else if(a.x>.5){face=local.zy;dims=size.zy;}else{face=local.xy;dims=size.xy;}
 vec2 fp=(face+.5)*dims;vec2 ed=(.5-abs(face))*dims;float e=min(ed.x,ed.y);
 float bevel=1.-smoothstep(0.,.022,e);
 int m=int(look.x+.5);float glow=look.y,time=look.z;bool top=n.y>.5;
 vec3 base;float metal=.0,gloss=.0;vec3 emit=vec3(0);
 if(m==0){ // data foundation: polished navy stone engraved with record cells
  base=vec3(.028,.05,.105);gloss=.55;
  vec2 cell=floor(fp/.085);vec2 f=fract(fp/.085);
  float groove=1.-smoothstep(.04,.09,min(min(f.x,1.-f.x),min(f.y,1.-f.y)));
  base*=1.-(top?.45:.25)*groove;
  float rec=step(.9,hash(cell))*(.5+.5*sin(time*1.7+hash(cell+3.)*40.));
  emit+=CREAM*rec*(1.-groove)*(top?.3:.12)*glow;
 }else if(m==1){ // connectors: graphite with channels carrying pulses toward the centre
  base=vec3(.045,.05,.065);gloss=.35;
  float lane=fp.y/.28;float g=1.-smoothstep(.02,.05,abs(fract(lane)-.5)*.28);
  float sx=abs(fp.x-dims.x*.5);
  float pulse=pow(fract(sx*.45+time*.9+hash(vec2(floor(lane),7.))),28.);
  base*=1.-.5*g;
  emit+=mix(vec3(.35,.45,.75),CREAM,.6)*g*(.05+.8*pulse)*glow*(top?1.:.35);
 }else if(m==2){ // the common block: brushed coral metal engraved with playbook lines
  base=CORAL*.62;metal=.88;gloss=.9;
  float brush=sin(fp.y*900.+sin(fp.x*40.)*2.)*.5+.5;base*=.88+.12*brush;
  if(top||a.z>.5){
   float row=fract(fp.y/.11);vec2 word=vec2(floor(fp.x/.23+hash(vec2(floor(fp.y/.11),1.))*3.),floor(fp.y/.11));
   float ink=step(.35,row)*step(row,.6)*step(.25,hash(word))*step(.06,fract(fp.x/.23));
   float margin=step(.14,min(ed.x,ed.y));
   base=mix(base,base*.55,ink*margin);emit+=CREAM*ink*margin*glow*.35;
  }
  emit+=CORAL*glow*(.07+.45*pow(1.-clamp(e/.35,0.,1.),2.));
 }else if(m==3){ // assistants: smoked glass cells lit from below once connected
  base=vec3(.03,.045,.08);gloss=1.;
  float h=local.y+.5;emit+=mix(CORAL,CREAM,h)*glow*pow(1.-h,1.6)*.9*(a.y<.5?1.:.3);
 }else if(m==4){ // teams: warm ceramic tiles
  base=CREAM*.55;gloss=.15;emit+=CREAM*glow*.75;
 }else{ // beam
  base=CORAL;emit+=CORAL*(1.6+1.2*glow)+CREAM*.3*glow;
 }
 vec3 l=normalize(vec3(-.45,.85,.55));float diffuse=max(0.,dot(n,l));
 float fres=pow(1.-max(0.,dot(n,v)),5.);
 vec3 refl=env(reflect(-v,n));
 vec3 spec=refl*mix(mix(.04,.12,gloss),1.,fres)*mix(vec3(1),base*1.6,metal);
 vec3 c=base*(1.-metal*.7)*(.06+.8*diffuse)+spec*gloss+emit;
 c+=bevel*(CREAM*.16*(.3+diffuse)+refl*.2);
 // Grounding: the lower part of each side face receives less light.
 if(a.y<.5)c*=.75+.25*smoothstep(-.5,.3,local.y);
 pixel=vec4(c,1.0);
}
