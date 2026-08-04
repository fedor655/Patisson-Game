#version 430

#include "lib/common.glsl"
#include "lib/atmosphere.glsl"

in vec3 vRayWorld;

uniform vec3 u_sunDirWorld;   // Z-up, pointing towards the sun
uniform float u_sunIntensity;
uniform float u_time;
uniform float u_cloudCover;

out vec4 fragColor;

void main() {
    vec3 rd = normalize(zupToYup(vRayWorld));
    vec3 sun = normalize(zupToYup(u_sunDirWorld));
    vec3 col = atmSky(rd, sun, u_sunIntensity, u_time, u_cloudCover);
    fragColor = vec4(col, 1.0);
}
