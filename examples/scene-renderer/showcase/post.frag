#version 300 es
precision highp float;
in vec2 uv;
uniform sampler2D image;
uniform vec2 resolution;
uniform vec4 finish;
out vec4 pixel;
vec3 aces(vec3 x){return clamp((x*(2.51*x+.03))/(x*(2.43*x+.59)+.14),0.0,1.0);}
void main(){
 vec2 px=1.0/resolution;vec2 center=uv-.5;
 vec2 fringe=center*finish.y*.001;
 vec3 c=vec3(texture(image,uv+fringe).r,texture(image,uv).g,texture(image,uv-fringe).b);
 vec3 bloom=vec3(0);
 for(int i=0;i<32;i++){
  float a=float(i)*2.399963;vec2 d=vec2(cos(a),sin(a))*sqrt(float(i)+.5)*.62*px;
  bloom+=max(vec3(0),texture(image,uv+d).rgb-.72);
 }
 c+=bloom*(finish.x/32.0);
 c=aces(c*1.18);
 c=pow(c,vec3(1.0/2.2));
 c*=1.0-.14*dot(center,center);
 pixel=vec4(c,1);
}
