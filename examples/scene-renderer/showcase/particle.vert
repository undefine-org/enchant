#version 300 es
precision highp float;
layout(location=0) in float index;
uniform mat4 viewProjection;
uniform vec4 gesture;
uniform vec4 placement;
out float energy;
void main(){
 float a=index*2.399963+gesture.x*.13;
 float ring=3.5+fract(index*.618)*1.4;
 vec3 p=vec3(cos(a)*ring,sin(a)*ring*.66,sin(index*1.7+gesture.x*.1)*2.2);
 p.x+=placement.w;
 gl_Position=viewProjection*vec4(p,1.0);
 gl_PointSize=clamp(20.0/gl_Position.w,1.1,4.0);
 energy=.15+.35*pow(.5+.5*sin(index+gesture.x*.5),4.0);
}
