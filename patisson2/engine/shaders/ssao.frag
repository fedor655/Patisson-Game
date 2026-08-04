#version 430

// Ambient occlusion from depth alone — normals are reconstructed with a
// best-of-four-taps scheme so edges stay sharp without an aux buffer.
//
// NOTE ON SPACE: u_proj/u_invProj come from the Panda3D lens, so the positions
// reconstructed here live in Panda's view space — +Y is forward, +Z is up.
// Depth comparisons therefore run along Y, not Z.

#include "lib/common.glsl"

in vec2 vUv;

uniform sampler2D u_depth;
uniform mat4 u_invProj;
uniform mat4 u_proj;
uniform vec2 u_texel;
uniform float u_radius;
uniform float u_intensity;
uniform float u_bias;
uniform float u_time;

out vec4 fragColor;

vec3 viewPosAt(vec2 uv) {
    return viewPosFromDepth(texture(u_depth, uv).r, uv, u_invProj);
}

void main() {
    float depth = texture(u_depth, vUv).r;
    if (depth >= 0.99999) {  // sky
        fragColor = vec4(1.0);
        return;
    }

    vec3 P = viewPosFromDepth(depth, vUv, u_invProj);

    // Reconstruct the normal from the closest neighbour on each axis so that
    // silhouettes don't smear across depth discontinuities.
    vec3 pRight = viewPosAt(vUv + vec2(u_texel.x, 0.0));
    vec3 pLeft = viewPosAt(vUv - vec2(u_texel.x, 0.0));
    vec3 pUp = viewPosAt(vUv + vec2(0.0, u_texel.y));
    vec3 pDown = viewPosAt(vUv - vec2(0.0, u_texel.y));
    vec3 dx = abs(pRight.y - P.y) < abs(P.y - pLeft.y) ? (pRight - P) : (P - pLeft);
    vec3 dy = abs(pUp.y - P.y) < abs(P.y - pDown.y) ? (pUp - P) : (P - pDown);
    vec3 N = cross(dx, dy);
    if (dot(N, N) < 1e-12) { fragColor = vec4(1.0); return; }
    N = normalize(N);
    if (dot(N, -normalize(P)) < 0.0) N = -N;   // face the camera

    // Fade the effect out with distance; far geometry has too little depth
    // precision for the comparison to mean anything.
    float fade = 1.0 - smoothstep(35.0, 70.0, P.y);
    if (fade <= 0.0) { fragColor = vec4(1.0); return; }

    vec3 up = abs(N.z) < 0.9 ? vec3(0.0, 0.0, 1.0) : vec3(1.0, 0.0, 0.0);
    vec3 T = normalize(cross(up, N));
    vec3 B = cross(N, T);

    float noise = hash12(gl_FragCoord.xy + fract(u_time) * 71.0);
    float occlusion = 0.0;
    const int SAMPLES = 16;

    for (int i = 0; i < SAMPLES; ++i) {
        float fi = (float(i) + 0.5) / float(SAMPLES);
        float angle = fi * 6.0 * TAU + noise * TAU;
        float r = sqrt(fi);
        vec3 dir = vec3(cos(angle) * r, sin(angle) * r, sqrt(max(1.0 - r * r, 0.0)));
        vec3 offset = (T * dir.x + B * dir.y + N * dir.z) * u_radius * (0.30 + 0.70 * fi);
        vec3 samplePos = P + offset;

        vec4 clip = u_proj * vec4(samplePos, 1.0);
        if (clip.w <= 0.0) continue;
        vec2 sUv = (clip.xy / clip.w) * 0.5 + 0.5;
        if (sUv.x < 0.0 || sUv.x > 1.0 || sUv.y < 0.0 || sUv.y > 1.0) continue;

        float sDepth = texture(u_depth, sUv).r;
        if (sDepth >= 0.99999) continue;
        vec3 sceneP = viewPosFromDepth(sDepth, sUv, u_invProj);

        // Occluded when real geometry sits nearer to the eye than the sample.
        float diff = samplePos.y - sceneP.y;
        if (diff > u_bias) {
            float rangeCheck = smoothstep(0.0, 1.0, u_radius / max(abs(P.y - sceneP.y), 1e-4));
            occlusion += rangeCheck;
        }
    }

    float ao = 1.0 - (occlusion / float(SAMPLES)) * u_intensity * fade;
    fragColor = vec4(clamp(ao, 0.0, 1.0));
}
