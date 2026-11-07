#version 300 es
precision highp float;
layout(location=0) in vec2 point;
uniform mat4 viewProjection;
out vec3 world;
void main(){world=vec3(point.x*60.0,0.0,point.y*60.0);gl_Position=viewProjection*vec4(world,1.0);}
