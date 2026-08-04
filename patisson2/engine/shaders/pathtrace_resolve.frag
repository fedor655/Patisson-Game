#version 430

// Resolves the path tracer's accumulation buffer: divide by the sample count,
// tonemap with the same curve the raster path uses so the two match.

#include "lib/common.glsl"

in vec2 vUv;

uniform sampler2D u_accum;
uniform float u_exposure;
uniform float u_samples;

out vec4 fragColor;

vec3 acesFilm(vec3 x) {
    const float a = 2.51, b = 0.03, c = 2.43, d = 0.59, e = 0.14;
    return saturate3((x * (a * x + b)) / (x * (c * x + d) + e));
}

void main() {
    vec4 acc = texture(u_accum, vUv);
    float n = max(acc.a, 1.0);
    vec3 col = acc.rgb / n;
    col = clamp(col, vec3(0.0), vec3(65000.0));
    col = acesFilm(col * u_exposure);
    fragColor = vec4(linearToSrgb(col), 1.0);
}
