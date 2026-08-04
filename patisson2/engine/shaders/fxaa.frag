#version 430

// FXAA 3.11-style edge blend on the tonemapped image.

#include "lib/common.glsl"

in vec2 vUv;

uniform sampler2D u_source;
uniform vec2 u_texel;

out vec4 fragColor;

const float EDGE_MIN = 0.0312;
const float EDGE_MUL = 0.125;
const float SPAN_MAX = 8.0;

void main() {
    vec3 rgbM = texture(u_source, vUv).rgb;
    float lumM = luminance(rgbM);
    float lumNW = luminance(texture(u_source, vUv + vec2(-1.0, -1.0) * u_texel).rgb);
    float lumNE = luminance(texture(u_source, vUv + vec2(1.0, -1.0) * u_texel).rgb);
    float lumSW = luminance(texture(u_source, vUv + vec2(-1.0, 1.0) * u_texel).rgb);
    float lumSE = luminance(texture(u_source, vUv + vec2(1.0, 1.0) * u_texel).rgb);

    float lumMin = min(lumM, min(min(lumNW, lumNE), min(lumSW, lumSE)));
    float lumMax = max(lumM, max(max(lumNW, lumNE), max(lumSW, lumSE)));
    float range = lumMax - lumMin;

    if (range < max(EDGE_MIN, lumMax * EDGE_MUL)) {
        fragColor = vec4(rgbM, 1.0);
        return;
    }

    vec2 dir = vec2(-((lumNW + lumNE) - (lumSW + lumSE)),
                    ((lumNW + lumSW) - (lumNE + lumSE)));
    float dirReduce = max((lumNW + lumNE + lumSW + lumSE) * 0.25 * EDGE_MUL, 1.0 / 128.0);
    float rcpDirMin = 1.0 / (min(abs(dir.x), abs(dir.y)) + dirReduce);
    dir = clamp(dir * rcpDirMin, vec2(-SPAN_MAX), vec2(SPAN_MAX)) * u_texel;

    vec3 rgbA = 0.5 * (texture(u_source, vUv + dir * (1.0 / 3.0 - 0.5)).rgb +
                       texture(u_source, vUv + dir * (2.0 / 3.0 - 0.5)).rgb);
    vec3 rgbB = rgbA * 0.5 + 0.25 * (texture(u_source, vUv - dir * 0.5).rgb +
                                     texture(u_source, vUv + dir * 0.5).rgb);

    float lumB = luminance(rgbB);
    fragColor = vec4((lumB < lumMin || lumB > lumMax) ? rgbA : rgbB, 1.0);
}
