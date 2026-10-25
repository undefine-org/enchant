#version 300 es
precision highp float;
// One ray per pixel onto the floor plane y=0. Star-and-cross zellige on a unit lattice:
// 8-point stars at integer points, crosses at cell centres. Each tile has its own clock
// until the fit wave reaches it. All story values arrive as uniforms from the BL plan.
uniform vec2 resolution;
uniform vec3 eye;uniform vec3 right;uniform vec3 up;uniform vec3 forward;uniform float tanHalf;
uniform vec4 clock;  // t, beats
uniform vec4 build;  // circle, star outline, grid radius, line glow
uniform vec4 fit;    // wave radius, wave width, dim, joint glow
uniform vec4 refine; // origin x, origin z, radius, on
uniform vec4 light;  // azimuth, elevation, glint, exposure
uniform vec4 finale; // ring morph, field fade, ring radius, ring glow
uniform vec4 grade;  // scrim
out vec4 pixel;
const float PI=3.14159265;
const float A=.35355339;
const float GAP=.016;
const vec3 NIGHT=vec3(.0063,.0116,.0296);
const vec3 CREAM=vec3(.92,.79,.60);
const vec3 CORAL=vec3(.693,.087,.050);
const vec3 CORAL2=vec3(.871,.195,.133);
const vec3 NAVYG=vec3(.018,.045,.16);
const vec3 CLAY=vec3(.50,.22,.11);
const vec3 GLAZES[6]=vec3[6](vec3(.02,.17,.19),vec3(.38,.24,.04),vec3(.12,.045,.18),vec3(.035,.17,.065),vec3(.40,.13,.17),vec3(.11,.13,.16));
const vec3 SAND=vec3(.80,.60,.37);

vec4 hash4(vec2 h){
 uvec2 q=uvec2(ivec2(floor(h*2.+4096.5)));uint n=q.x*1597334677u^q.y*3812015801u;n^=n>>15;n*=2246822519u;n^=n>>13;
 uint a=n*0x27d4eb2du;a^=a>>15;uint b=a*0x165667b1u;b^=b>>13;uint c=b*0x9e3779b1u;c^=c>>16;uint d=c*0x85ebca77u;d^=d>>13;
 return vec4(a,b,c,d)/4294967295.;
}
float box(vec2 q,float a){vec2 d=abs(q)-a;return length(max(d,0.))+min(max(d.x,d.y),0.);}
float starD(vec2 q){vec2 r=vec2(q.x-q.y,q.x+q.y)*.70710678;return min(box(q,A),box(r,A));}
float crossD(vec2 q){
 float s=min(min(starD(q-vec2(.5,.5)),starD(q-vec2(-.5,.5))),min(starD(q-vec2(.5,-.5)),starD(q-vec2(-.5,-.5))));
 return max(box(q,.5),-s);
}
float easeSnap(float x){return x>=1.?1.:1.-pow(1.-x,3.)+.22*sin(x*PI)*(1.-x);}
float fitOf(vec2 home){return clamp((fit.x-length(home))/fit.y,0.,1.);}

struct Tile{vec2 home;float kind;float s;float th;vec2 d;float x;vec4 h;bool centre;};
Tile tileAt(vec2 home,float kind){
 Tile T;T.home=home;T.kind=kind;T.h=hash4(home+kind*.25);T.centre=kind<.5&&dot(home,home)<.01;
 float x=fitOf(home);float e=easeSnap(x);T.x=x;float t=clock.x;vec4 h=T.h;
 vec2 d0=(h.xy-.5)*.42+.07*vec2(sin(t*(.6+h.z*1.7)+h.w*6.),cos(t*(.5+h.w*1.5)+h.z*6.));
 float th0=(h.z-.5)*1.5+.2*sin(t*(.4+h.y*1.2)+h.x*6.);
 float s0=.74+.22*h.w;
 if(T.centre){d0*=.12;th0*=.15;s0=1.;}
 bool missing=!T.centre&&h.y>.86;
 T.d=d0*(1.-e);T.th=th0*(1.-e);T.s=missing?max(e,0.):mix(s0,1.,e);
 return T;
}
float crack(vec2 p){ // craquelure: distance to cell borders of a jittered grid
 vec2 i=floor(p),f=fract(p);float d1=8.,d2=8.;
 for(int y=-1;y<=1;y++)for(int x=-1;x<=1;x++){vec2 g=vec2(x,y);vec2 o=hash4(i+g).xy;float d=length(g+o-f);if(d<d1){d2=d1;d1=d;}else if(d<d2)d2=d;}
 return d2-d1;
}
vec3 patternColour(Tile T){
 if(T.centre)return CORAL2;
 if(T.kind>.5)return NAVYG;
 return ((int(mod(T.home.x+T.home.y,2.))==0)?CREAM:SAND)*(.94+.12*T.h.w);
}
void main(){
 vec2 ndc=gl_FragCoord.xy/resolution*2.-1.;float aspect=resolution.x/resolution.y;
 vec3 dir=normalize(forward+ndc.x*aspect*tanHalf*right+ndc.y*tanHalf*up);
 vec3 horizon=NIGHT*2.2+vec3(.010,.012,.022);
 vec3 col;
 if(dir.y>-1e-4){col=NIGHT*1.2+vec3(.012,.014,.03)*pow(1.-clamp(dir.y,0.,1.),10.);}
 else{
  float dist=-eye.y/dir.y;vec3 P=eye+dist*dir;vec2 p=P.xz;
  vec2 fwv=fwidth(p);float fw=max(length(fwv),1e-5);
  // ---- find the topmost tile covering p ----
  vec2 base=floor(p+.5),cbase=floor(p)+.5;
  bool found=false;float hitLayer=-1.,hitD=1.,minD=1e3;Tile hit;vec2 hitQ;
  for(int k=0;k<2;k++)for(int j=-1;j<=1;j++)for(int i=-1;i<=1;i++){
   vec2 home=(k==0?base:cbase)+vec2(i,j);
   Tile T=tileAt(home,float(k));
   if(T.s<.003)continue;
   if(T.centre&&finale.x>0.)continue;
   vec2 rel=p-home-T.d;float bound=(k==0?.52:.72)*T.s+.02;
   if(dot(rel,rel)>bound*bound)continue;
   float c=cos(T.th),s=sin(T.th);vec2 q=mat2(c,-s,s,c)*rel/T.s;
   float dd=(k==0?starD(q):crossD(q))*T.s+GAP;
   minD=min(minD,dd);
   if(dd<fw){float layer=T.h.x+(T.centre?2.:0.)+T.x;if(layer>hitLayer){hitLayer=layer;hit=T;hitQ=q;hitD=dd;found=true;}}
  }
  // ---- ground and joints ----
  float r=length(p),fl=clamp((fit.x-r)/fit.y,0.,1.);
  vec3 ground=NIGHT*1.5*(.5+.5*smoothstep(0.,.14,minD));
  float front=exp(-pow((r-fit.x)/1.6,2.));
  float joint=1.-smoothstep(0.,.05,minD);
  ground+=CORAL2*fit.w*joint*fl*(.28+2.6*front);
  col=ground;
  vec3 V=-dir,L=normalize(vec3(cos(light.x)*cos(light.y),sin(light.y),sin(light.x)*cos(light.y)));
  float lod=smoothstep(.05,.22,fw);
  if(found){
   Tile T=hit;vec2 q=hitQ;vec4 h=T.h;float t=clock.x;
   float colourFit=smoothstep(0.,.7,T.x);
   vec3 c=mix(GLAZES[int(h.y*5.999)],patternColour(T),colourFit);
   if(T.centre)c=CORAL2;
   // the shared refinement: a finer inner star inside every star
   if(T.kind<.5&&!T.centre){
    float ref=clamp((refine.z-length(T.home-refine.xy))/1.2,0.,1.)*refine.w*colourFit;
    float inner=1.-smoothstep(-.006,.006,starD(q*2.7)/2.7+.0);
    float ring=1.-smoothstep(.006,.016,abs(starD(q*1.55)/1.55));
    vec3 inlay=CORAL2;
    c=mix(c,inlay,ref*max(inner,ring*.9));
   }
   // fragmented chips expose terracotta
   float chip=(1.-step(.35,T.x))*step(.8,h.w)*(1.-smoothstep(.09,.11,length(q-vec2(.47,0.))));
   float edge=smoothstep(0.,.05,-(hitD-GAP)/T.s);
   c=mix(CLAY*.75,c,.35+.65*edge);
   c=mix(c,CLAY*.55,chip);
   float cr=crack(q*26.+h.zw*31.);c*=1.-.07*(1.-smoothstep(.0,.04,cr))*(1.-lod);
   // glaze: domed, tilted by hand; glints on its own clock until it fits, then with everyone
   vec2 tilt=(h.zw-.5)*.30;
   tilt+=(1.-T.x)*.14*vec2(sin(t*(1.1+h.x*2.3)+h.y*9.),cos(t*(.9+h.z*2.1)+h.w*9.));
   tilt+=T.x*.11*vec2(sin(clock.y*PI*.5-length(T.home)*.55),cos(clock.y*PI*.5-length(T.home)*.55));
   vec3 n=normalize(vec3(-q.x*.42+tilt.x,1.,-q.y*.42+tilt.y));
   float diffuse=max(dot(n,L),0.);
   vec3 R=reflect(-V,n);float rl=max(dot(R,L),0.);
   float glint=pow(rl,140.)*light.z*(1.-lod)*1.2*(1.-finale.y);float sheen=pow(rl,9.)*.18;
   float fres=pow(1.-max(dot(n,V),0.),5.);
   vec3 sky=mix(NIGHT*2.,vec3(.20,.22,.30),smoothstep(-.1,.7,R.y));
   // a broad studio softbox: each hand-set tile catches it at its own angle
   vec2 la=normalize(L.xz);float face=dot(normalize(R.xz+1e-4),la);
   float strip=pow(max(0.,1.-abs(R.y-.5)*2.6),18.)*smoothstep(.2,.9,face)*(1.-lod*.7)*(1.-finale.y);
   float glaze=(1.-chip)*(1.-lod*.5);
   vec3 tc=c*.62*(.18+.82*diffuse)+vec3(1.,.95,.86)*(glint+sheen*.35+strip*.42)*glaze+sky*(.04+.32*fres)*glaze;
   tc*=1.-fit.z*.78;
   tc=mix(tc,mix(c*.55,ground,.2),lod*.6);
   if(!T.centre)tc=mix(tc,NIGHT*1.25+tc*.035,finale.y);
   float cov=clamp(.5-hitD/fw,0.,1.);
   col=mix(ground,tc,cov);
  }else if(finale.y>0.)col=mix(col,NIGHT*1.3,finale.y);
  // ---- the closing ring: the centre star becomes the O ----
  if(finale.x>0.){
   float rd=abs(length(p)-finale.z)-finale.z*.19;
   float sd=mix(starD(p)+GAP,rd,finale.x);
   float cov=clamp(.5-sd/fw,0.,1.);
   vec3 n=normalize(vec3(-p.x*.25,1.,-p.y*.25));vec3 R=reflect(-V,n);float rl=max(dot(R,L),0.);
   vec3 rc=CORAL2*(.3+.7*max(dot(n,L),0.))+vec3(1.,.9,.8)*(pow(rl,60.)*1.5+pow(rl,8.)*.15);
   col=mix(col,rc,cov);
   col+=CORAL2*finale.w*.35*exp(-max(rd,0.)/.09)*(1.-cov);
  }
  // ---- the construction: circle, star, then the lines that generate the lattice ----
  if(build.w>0.){
   float lw=max(.007,fw*1.2);
   float ang=fract(atan(p.y,p.x)/(2.*PI)+.25);
   float circ=abs(length(p)-.5);
   float star=abs(starD(p));
   float dx=min(abs(fract(p.x-A+.5)-.5),abs(fract(p.x+A+.5)-.5));
   float dz=min(abs(fract(p.y-A+.5)-.5),abs(fract(p.y+A+.5)-.5));
   float du=abs(fract(p.x-p.y)-.5)*.70710678,dv=abs(fract(p.x+p.y)-.5)*.70710678;
   float grid=min(min(dx,dz),min(du,dv));
   float gm=1.-smoothstep(build.z-2.,build.z,r);
   float g=exp(-pow(circ/lw,2.))*step(ang,build.x)+exp(-pow(star/lw,2.))*step(ang,build.y)+.75*exp(-pow(grid/lw,2.))*gm;
   g+=.18*(exp(-circ/(lw*7.))*step(ang,build.x)+exp(-star/(lw*7.))*step(ang,build.y));
   col+=CORAL2*build.w*g*2.2;
  }
  col=mix(col,horizon,1.-exp(-dist*.02));
 }
 vec2 uv=gl_FragCoord.xy/resolution;
 col*=1.-grade.x*.62*smoothstep(.5,.0,uv.y)*smoothstep(1.05,.15,uv.x);
 pixel=vec4(col*light.w,1.);
}
