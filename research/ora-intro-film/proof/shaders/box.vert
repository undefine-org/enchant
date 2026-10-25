#version 300 es
precision highp float;
layout(location=0) in vec3 position;
layout(location=1) in vec3 facing;
uniform mat4 viewProjection;
uniform vec3 center;
uniform vec3 size;
out vec3 world;
out vec3 normal;
out vec3 local;
void main(){local=position;normal=facing;world=center+position*size;gl_Position=viewProjection*vec4(world,1.0);}
