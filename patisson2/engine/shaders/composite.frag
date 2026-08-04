#version 430

// Final HDR resolve: AO, bloom, exposure, ACES tonemap, grade, vignette, grain.

#include "lib/common.glsl"

in vec2 vUv;

uniform sampler2D u_color;
uniform sampler2D u_bloom0;
uniform sampler2D u_bloom1;
uniform sampler2D u_bloom2;
uniform sampler2D u_ao;
uniform sampler2D u_depth;

uniform float u_exposure;
uniform float u_bloomStrength;
uniform float u_aoStrength;
uniform float u_vignette;
uniform float u_grain;
uniform float u_saturation;
uniform float u_time;
uniform vec3 u_lift;
uniform vec3 u_gain;
uniform float u_sunVisibility;
uniform vec2 u_sunScreenPos;
uniform float u_godrayStrength;

out vec4 fragColor;

// Narkowicz's ACES filmic curve.
vec3 acesFilm(vec3 x) {
    const float a = 2.51, b = 0.03, c = 2.43, d = 0.59, e = 0.14;
    return saturate3((x * (a * x + b)) / (x * (c * x + d) + e));
}

void main() {
    vec3 color = texture(u_color, vUv).rgb;

    float ao = texture(u_ao, vUv).r;
    ao = mix(1.0, ao, u_aoStrength);
    color *= ao;

    vec3 bloom = texture(u_bloom0, vUv).rgb * 0.5
               + texture(u_bloom1, vUv).rgb * 0.32
               + texture(u_bloom2, vUv).rgb * 0.18;
    color += bloom * u_bloomStrength;

    // Screen-space god rays: march towards the sun accumulating bright pixels.
    if (u_godrayStrength > 0.0 && u_sunVisibility > 0.0) {
        vec2 delta = (u_sunScreenPos - vUv) / 24.0;
        vec2 uv = vUv;
        float decay = 1.0;
        vec3 rays = vec3(0.0);
        float jitter = hash12(gl_FragCoord.xy + u_time);
        uv += delta * jitter;
        for (int i = 0; i < 24; ++i) {
            uv += delta;
            float d = texture(u_depth, uv).r;
            vec3 s = texture(u_bloom0, uv).rgb * step(0.9999, d);
            rays += s * decay;
            decay *= 0.94;
        }
        color += rays / 24.0 * u_godrayStrength * u_sunVisibility;
    }

    color *= u_exposure;
    color = acesFilm(color);

    // Lift/gain grade, then saturation.
    color = saturate3(color * u_gain + u_lift);
    float lum = luminance(color);
    color = mix(vec3(lum), color, u_saturation);

    // Vignette.
    vec2 d = (vUv - 0.5) * vec2(1.0, 0.85);
    float vig = 1.0 - dot(d, d) * u_vignette;
    color *= clamp(vig, 0.0, 1.0);

    // Fine grain keeps gradients from banding on 8-bit output.
    float grain = (hash12(gl_FragCoord.xy + fract(u_time) * 137.0) - 0.5);
    color += grain * u_grain;

    fragColor = vec4(linearToSrgb(saturate3(color)), 1.0);
}
