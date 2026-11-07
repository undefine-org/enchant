#version 300 es
precision highp float;
layout(location=0) in float index;
uniform mat4 viewProjection;
uniform vec4 motes; // order, time
out float energy;
out float warm;
float h(float x){return fract(sin(x*91.345+7.1)*47453.5453);}
void main(){
 float i=index,t=motes.y;
 // Before the common block: every mote on its own clock and its own path.
 vec3 home=vec3(h(i)*18.-9.,.3+h(i+1.)*6.,h(i+2.)*14.-7.);
 vec3 chaos=home+vec3(sin(t*(.4+h(i+3.)*1.8)+h(i+4.)*6.),sin(t*(.3+h(i+5.)*1.4)),cos(t*(.5+h(i+6.)*1.6)))*(.4+h(i+7.)*.8);
 // After: three rings around the stack, one shared tempo.
 float k=mod(i,3.);float a=i*2.399963+t*.42;
 vec3 ring=vec3(cos(a)*(4.4+k*.9),1.1+k*.85+.08*sin(a*3.),sin(a)*(3.2+k*.7));
 float o=smoothstep(h(i+8.)*.5,h(i+8.)*.5+.5,motes.x);
 vec3 p=mix(chaos,ring,o);
 gl_Position=viewProjection*vec4(p,1.0);
 gl_PointSize=clamp(58.0/gl_Position.w,1.5,7.0);
 energy=mix(.45+.3*sin(t*3.+i),.95,o);
 warm=o*step(.82,h(i+9.));
}
