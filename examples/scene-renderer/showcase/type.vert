#version 300 es
precision highp float;
layout(location=0) in vec2 point;
uniform vec4 rect;
uniform vec4 typeGesture;
out vec2 uv;
void main(){
 uv=point*.5+.5;
 vec3 p=vec3(point*rect.zw*.5+rect.xy,typeGesture.x);
 p.y+=typeGesture.y*sin(p.x*1.25+typeGesture.z);
 p.x+=point.y*typeGesture.w;
 gl_Position=vec4(p.x/10.0,p.y/5.625,0,1);
}
