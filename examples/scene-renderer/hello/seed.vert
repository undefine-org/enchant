#version 300 es
precision highp float;
layout(location=0) in vec2 point;
uniform vec4 linear;
uniform vec4 seed;
uniform vec2 resolution;
uniform vec2 offset;
out vec2 local;
void main(){
 local=point*1.65;
 float c=cos(seed.w),s=sin(seed.w);
 vec2 q=vec2(c*local.x-s*local.y,s*local.x+c*local.y)*seed.z+seed.xy;
 vec2 p=vec2(linear.x*q.x+linear.z*q.y,linear.y*q.x+linear.w*q.y)+offset;
 gl_Position=vec4(p.x/resolution.x*2.0-1.0,1.0-p.y/resolution.y*2.0,0,1);
}
