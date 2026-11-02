#version 300 es
precision highp float;
in vec2 uv;
uniform vec2 resolution;
uniform vec4 atmosphere;
uniform vec3 accent;
out vec4 pixel;
float hash(vec2 p){uvec2 q=uvec2(p);uint h=q.x*374761393u+q.y*668265263u;h=(h^(h>>13u))*1274126177u;return float(h^(h>>16u))/4294967295.0;}
void main(){
 vec2 p=(uv-.5)*vec2(resolution.x/resolution.y,1.0);
 float glow=exp(-length(p-vec2(.45,.1))*2.4);
 vec3 dark=vec3(.012,.017,.026)+accent*glow*.045;
 vec3 paper=vec3(.88,.865,.81)-length(p)*.025;
 vec3 c=mix(dark,paper,atmosphere.x);
 float grid=(1.0-smoothstep(.0,.035,abs(sin(p.x*110.0))))*(1.0-smoothstep(.0,.035,abs(sin(p.y*110.0))));
 c+=mix(vec3(.045),vec3(-.12),atmosphere.x)*grid*atmosphere.y;
 float grain=hash(floor(gl_FragCoord.xy))-.5;
 c+=grain*.003;
 pixel=vec4(c,1.0);
}
