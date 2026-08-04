#version 430

#include "lib/common.glsl"

in float vFade;
in vec2 vQuad;
in vec3 vViewDir;

uniform sampler2D u_skyLut;
uniform vec3 u_tint;
uniform float u_opacity;
uniform float u_round;      // 0 = streak, 1 = soft round flake
uniform float u_boost;      // snow is far more reflective than a raindrop

out vec4 fragColor;

void main() {
    if (vFade <= 0.001) discard;

    float mask = 1.0;
    if (u_round > 0.5) {
        // Soft disc for snow.
        float r = length(vQuad) * 2.0;
        mask = 1.0 - smoothstep(0.45, 1.0, r);
    } else {
        // Streak: taper the ends and soften across the width.
        mask = (1.0 - smoothstep(0.15, 0.5, abs(vQuad.x)))
             * (1.0 - smoothstep(0.30, 0.5, abs(vQuad.y)));
    }
    if (mask <= 0.002) discard;

    // Sample the sky along the particle's own view ray rather than at the
    // zenith: looking towards the horizon the backdrop is several times
    // brighter, and a zenith-lit flake reads as a dark speck against it.
    vec3 dir = normalize(vViewDir);
    dir.z = max(dir.z, 0.02);
    vec3 sky = texture(u_skyLut, dirToEquirect(zupToYup(dir))).rgb;
    // Pull towards neutral so snow doesn't come out cornflower blue.
    vec3 col = mix(sky, vec3(luminance(sky)), 0.7) * u_tint * u_boost;

    fragColor = vec4(col, mask * vFade * u_opacity);
}
