#version 300 es
precision highp float;
in vec2 uv;
uniform sampler2D image;
uniform vec3 ink;
out vec4 pixel;
void main(){float a=texture(image,vec2(uv.x,1.0-uv.y)).a;if(a<.01)discard;pixel=vec4(ink*a,a);}
