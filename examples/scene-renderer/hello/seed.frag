#version 300 es
precision highp float;
in vec2 local;
uniform vec3 material;
uniform vec2 detail;
out vec4 pixel;
float hash(vec2 p){uvec2 q=uvec2(max(p,vec2(0)));uint h=q.x*374761393u+q.y*668265263u;h=(h^(h>>13u))*1274126177u;return float(h^(h>>16u))/4294967295.;}
vec3 spectrum(float x){return .42+.36*cos(6.2831853*(x+vec3(0,.33,.67)));}
float segment(vec2 p,vec2 a,vec2 b){vec2 v=b-a;return length(p-a-v*clamp(dot(p-a,v)/dot(v,v),0.,1.));}
void main(){
 vec2 p=local;float radius=length(p);float aa=max(fwidth(radius),.0015);
 float core=1.0-smoothstep(1.0-aa,1.0+aa,radius);
 vec2 rp=mat2(.848,-.53,.53,.848)*p;
 float ring=abs(length(vec2(rp.x/1.35,rp.y/.43))-1.0);
 float ringAlpha=1.0-smoothstep(.015,.015+aa,ring);
 float shadow=exp(-dot((p-vec2(.10,.14))*vec2(.8,1.0),(p-vec2(.10,.14))*vec2(.8,1.0))*3.0)*.19*(1.0-core);
 vec3 n=normalize(vec3(p.x,-p.y,sqrt(max(.0001,1.0-dot(p,p)))));
 vec3 light=normalize(vec3(-.55,.7,1.15));float diffuse=max(0.,dot(n,light));
 float grain=(hash(floor((p+2.)*230.+detail.y))-.5)*.016;
 float weave=sin(p.x*310.)*sin(p.y*310.);float brushing=sin(p.y*1700.+sin(p.x*23.)*2.);
 float weaveAA=1.-smoothstep(.5,2.,fwidth(p.x*310.));
 vec3 paper=vec3(.88,.70,.27)*(.65+.35*diffuse)+grain;
 vec3 woven=vec3(.59,.68,.40)*(.51+.48*diffuse)+weave*.085*weaveAA+grain;
 n=normalize(n+vec3(brushing*.012,brushing*.003,0));
 vec3 refl=reflect(vec3(0,0,-1),n);float strip=pow(max(0.,1.-abs(refl.y-.45)*2.0),12.);
 float highlight=pow(max(0.,dot(n,normalize(vec3(-.5,.7,1.5)))),60.);
 vec3 foil=spectrum(n.z*.45+detail.x*.009+p.y*.10)*(.25+.6*diffuse)+strip*vec3(1.2,1.1,.9)+highlight*.8;
 vec3 c=paper*material.x+woven*material.y+foil*material.z;
 // The small notch and orbital line retain identity through every material.
 vec2 a=vec2(.65,-.76),b=vec2(.44,-.51),cc=vec2(.79,-.50);
 float notch=1.-smoothstep(.012,.012+aa,min(segment(p,a,b),min(segment(p,b,cc),segment(p,cc,a))));
 c=mix(c,vec3(.14,.23,.19),notch*.85);
 float edge=smoothstep(.96,1.,radius);c=mix(c,vec3(.18,.26,.20),edge*.7);
 float ringFront=step(0.,rp.y);
 vec3 rgb=vec3(.1,.16,.12)*shadow;float alpha=shadow;
 float backRing=ringAlpha*(1.-core);rgb=mix(rgb,vec3(.78,.35,.24),backRing);alpha=max(alpha,backRing*.88);
 rgb=mix(rgb,c,core);alpha=max(alpha,core);
 float front=ringAlpha*ringFront*.9;rgb=mix(rgb,vec3(.78,.35,.24),front);alpha=max(alpha,front);
 if(alpha<.005)discard;
 pixel=vec4(rgb*alpha,alpha);
}
