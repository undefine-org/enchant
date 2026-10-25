#version 300 es
precision highp float;
in vec3 world;
in vec3 normal;
in vec2 cloth;
uniform vec3 eye;
uniform vec4 material;
uniform vec3 accent;
out vec4 pixel;
const float PI=3.14159265;
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
vec3 spectrum(float x){return .42+.38*cos(6.2831853*(x+vec3(0.0,.33,.67)));}
vec3 env(vec3 r){
 // An original analytic studio environment: broad strip boxes, coloured cards.
 float strip=pow(max(0.0,1.0-abs(r.y-.55)*2.7),12.0)*(.2+.8*smoothstep(-.7,.3,r.x));
 float soft=pow(max(0.0,dot(r,normalize(vec3(-.7,.6,.8)))),18.0);
 float rim=pow(max(0.0,dot(r,normalize(vec3(.8,.2,-.6)))),32.0);
 return vec3(.035,.045,.065)+vec3(1.9,1.8,1.55)*strip+vec3(.5,.75,1.4)*soft+accent*rim*3.0;
}
void main(){
 vec3 n=normalize(normal);if(!gl_FrontFacing)n=-n;
 vec3 v=normalize(eye-world);
 // UV-locked brushing and woven micro-normal remain attached during deformation.
 float brush=sin(cloth.y*1700.0+sin(cloth.x*900.0)*.7);
 float weave=sin(cloth.x*2600.0)*sin(cloth.y*320.0);
 float aa=1.0-smoothstep(.7,2.0,max(fwidth(cloth.x*2600.0),fwidth(cloth.y*320.0)));
 vec3 tangent=normalize(dFdx(world)+vec3(.00001));
 n=normalize(n+tangent*(brush*.008+weave*.045*material.y*aa));
 float nv=max(.001,dot(n,v)),fres=pow(1.0-nv,4.0);
 vec3 l=normalize(vec3(-3.0,5.0,6.0)),h=normalize(l+v);
 float diffuse=max(.0,dot(n,l));
 vec3 foil=mix(vec3(.26,.32,.38),spectrum(nv*.38+material.x+world.y*.025),material.z);
 vec3 dyed=mix(foil,accent,material.y*.85);
 vec3 reflection=env(reflect(-v,n));
 float spec=pow(max(0.0,dot(n,h)),mix(130.0,32.0,material.y));
 vec3 c=dyed*(.035+.48*diffuse)+reflection*mix(.62,.16,material.y)+spec*vec3(1.6)+fres*accent*.24;
 float seam=1.0-smoothstep(.006,.023,min(cloth.y,1.0-cloth.y));
 c+=seam*(vec3(.8,.7,.35)*.45+accent*material.w*2.0);
 c*=.96+.04*brush;
 pixel=vec4(c,1.0);
}
