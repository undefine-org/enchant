#version 300 es
precision highp float;
in vec3 world;
uniform vec3 eye;
uniform vec4 floorState; // shock radius, shock strength, footprint, time
out vec4 pixel;
const vec3 NAVY=vec3(.0063,.0116,.0296);
const vec3 CORAL=vec3(.871,.195,.133);
// The ORA site grid, laid flat: 0.5-unit cells, a brighter line every four.
float gridLine(vec2 p,float cell,float width){
 vec2 q=abs(fract(p/cell-.5)-.5)*cell;vec2 w=fwidth(p)*width;
 vec2 l=1.0-smoothstep(vec2(0),w,q);return max(l.x,l.y);
}
float box(vec2 p,vec2 b,float r){vec2 d=abs(p)-b+r;return length(max(d,0.))+min(max(d.x,d.y),0.)-r;}
void main(){
 vec2 p=world.xz;float dist=length(p);
 float fine=gridLine(p,.5,1.0),major=gridLine(p,2.0,1.4);
 vec3 c=NAVY*1.25+vec3(.010,.016,.034)*fine+vec3(.022,.032,.062)*major;
 // Soft contact shadow under the stack footprint.
 float shadow=1.0-smoothstep(-.3,1.6,box(p,vec2(3.1,1.9),.4));
 c*=1.0-.75*shadow*floorState.z;
 // Landing shock ring: lights the grid lines it passes through.
 float ring=exp(-pow((dist-floorState.x)/.32,2.0))*floorState.y;
 c+=CORAL*ring*(.25+2.2*max(fine,major));
 // Atmospheric fade to the page's navy.
 float fog=1.0-exp(-pow(length(world-eye)/38.0,2.0));
 c=mix(c,NAVY,fog);
 pixel=vec4(c,1.0);
}
