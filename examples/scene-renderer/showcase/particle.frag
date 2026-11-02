#version 300 es
precision highp float;
in float energy;
uniform vec3 accent;
uniform vec4 atmosphere;
out vec4 pixel;
void main(){
 float r=length(gl_PointCoord-.5);
 if(r>.5)discard;
 vec3 c=mix(vec3(.45)+accent*.4,vec3(.12,.22,.16),atmosphere.x);
 pixel=vec4(c*energy*(1.0-smoothstep(.3,.5,r)),1.0);
}
