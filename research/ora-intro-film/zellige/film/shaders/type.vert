#version 300 es
precision highp float;
layout(location=0) in vec2 point;
uniform vec4 rect; // pixels, top-left origin
uniform vec2 resolution;
out vec2 uv;
void main(){
 uv=point*.5+.5;
 vec2 px=rect.xy+vec2(uv.x,1.0-uv.y)*rect.zw;
 gl_Position=vec4(px.x/resolution.x*2.0-1.0,1.0-px.y/resolution.y*2.0,0,1);
}
