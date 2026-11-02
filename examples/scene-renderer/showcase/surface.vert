#version 300 es
precision highp float;
layout(location=0) in vec3 param;
uniform mat4 viewProjection;
uniform vec4 shape;
uniform vec4 gesture;
uniform vec4 placement;
out vec3 world;
out vec3 normal;
out vec2 cloth;
const float PI=3.14159265359;
mat3 rx(float a){float c=cos(a),s=sin(a);return mat3(1,0,0,0,c,s,0,-s,c);}
mat3 ry(float a){float c=cos(a),s=sin(a);return mat3(c,0,-s,0,1,0,s,0,c);}
mat3 rz(float a){float c=cos(a),s=sin(a);return mat3(c,s,0,-s,c,0,0,0,1);}
vec3 center(float u){
 float a=u*2.0*PI;
 vec3 loop=vec3((2.15+.30*cos(3.0*a))*cos(a),1.8*sin(a),.65*sin(3.0*a));
 vec3 knot=vec3((1.65+.62*cos(3.0*a))*cos(2.0*a),(1.65+.62*cos(3.0*a))*sin(2.0*a),.9*sin(3.0*a));
 vec3 wave=vec3((u-.5)*9.0,.85*sin(2.0*a+gesture.x),.8*cos(a+gesture.x));
 vec3 helix=vec3(1.65*cos(2.0*a),(u-.5)*6.7,1.65*sin(2.0*a));
 return loop*shape.x+knot*shape.y+wave*shape.z+helix*shape.w;
}
vec3 surface(float u,float v,float band){
 vec3 c=center(u), tangent=normalize(center(u+.0002)-center(u-.0002));
 vec3 n=normalize(cross(tangent,vec3(.13,.22,1.0)));
 vec3 b=cross(tangent,n);
 float twist=gesture.y+u*gesture.z*2.0*PI+.25*sin(u*18.8496+gesture.x);
 vec3 across=n*cos(twist)+b*sin(twist);
 vec3 lift=-n*sin(twist)+b*cos(twist);
 float w=gesture.w*(.82+.18*sin(u*12.5664));
 vec3 p=c+across*(v*w+(band-2.0)*w*2.14)+lift*(.05*sin(u*37.699+band*.7));
 return rz(placement.z)*ry(placement.y)*rx(placement.x)*p+vec3(placement.w,0,0);
}
void main(){
 world=surface(param.x,param.y,param.z);
 vec3 du=surface(param.x+.00015,param.y,param.z)-surface(param.x-.00015,param.y,param.z);
 vec3 dv=surface(param.x,param.y+.001,param.z)-surface(param.x,param.y-.001,param.z);
 normal=normalize(normalize(cross(du,dv))+normalize(dv)*sign(param.y)*pow(abs(param.y),24.0)*.32);cloth=vec2(param.x,param.y*.5+.5);
 gl_Position=viewProjection*vec4(world,1.0);
}
