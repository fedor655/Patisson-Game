#version 430

// Soft-knee highlight extraction with a Karis average to keep fireflies out.

#include "lib/common.glsl"

in vec2 vUv;

uniform sampler2D u_source;
uniform vec2 u_texel;
uniform float u_threshold;
uniform float u_knee;

out vec4 fragColor;

vec3 tap(vec2 uv) {
    vec3 c = texture(u_source, uv).rgb;
    return c / (1.0 + luminance(c));   // Karis weighting
}

void main() {
    vec3 c = tap(vUv) * 4.0;
    c += tap(vUv + vec2(u_texel.x, 0.0));
    c += tap(vUv - vec2(u_texel.x, 0.0));
    c += tap(vUv + vec2(0.0, u_texel.y));
    c += tap(vUv - vec2(0.0, u_texel.y));
    c /= 8.0;
    c = c / max(1.0 - luminance(c), 1e-4);   // undo the weighting

    float lum = luminance(c);
    float soft = clamp(lum - u_threshold + u_knee, 0.0, 2.0 * u_knee);
    soft = soft * soft / (4.0 * u_knee + 1e-5);
    float contribution = max(soft, lum - u_threshold) / max(lum, 1e-5);

    fragColor = vec4(c * contribution, 1.0);
}
