#version 300 es
precision highp float;
layout(location=0) in vec2 point;
out vec2 uv;
void main(){uv=point*.5+.5;gl_Position=vec4(point,0,1);}
