#version 300 es
precision highp float;
in float energy;
in float warm;
uniform vec4 motes;
out vec4 pixel;
void main(){
 float r=length(gl_PointCoord-.5);if(r>.5)discard;
 vec3 cool=vec3(.32,.38,.52),cream=vec3(.965,.823,.617),coral=vec3(.871,.195,.133);
 vec3 c=mix(mix(cool,cream,motes.x),coral*1.6,warm);
 pixel=vec4(c*energy*(1.-smoothstep(.2,.5,r)),1.);
}
