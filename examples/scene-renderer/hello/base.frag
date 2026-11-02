#version 300 es
precision highp float;
in vec2 uv;
uniform sampler2D image;
out vec4 pixel;
void main(){pixel=texture(image,vec2(uv.x,1.0-uv.y)).bgra;}
