#version 430

// Water: Fresnel-weighted sky reflection, Beer-Lambert absorption against the
// real lake bed (read from the terrain height field), sun glint and shore foam.

#include "lib/common.glsl"
#include "lib/pbr.glsl"
#include "lib/lighting.glsl"

in vec3 vViewPos;
in vec3 vWorldPos;
in vec4 vClipPos;
in vec3 vWaveNormal;
in float vWaveHeight;

uniform mat3 p3d_NormalMatrix;
uniform mat4 p3d_ViewMatrix;

uniform sampler2D u_heightMap;
uniform vec4 u_terrainBounds;   // xy: min corner, zw: 1/size
uniform float u_waterLevel;
uniform float u_time;
uniform vec3 u_shallowColor;
uniform vec3 u_deepColor;
uniform float u_foamWidth;
uniform sampler2D u_reflection;
uniform float u_reflectStrength;   // 0 while the reflection pass is idle

out vec4 fragColor;

float bedHeight(vec2 p) {
    vec2 uv = (p - u_terrainBounds.xy) * u_terrainBounds.zw;
    return texture(u_heightMap, uv).r;
}

void main() {
    float bed = bedHeight(vWorldPos.xy);
    float depth = max(u_waterLevel - bed, 0.0);
    if (depth <= 0.004) discard;   // dry land

    // Ripple detail on top of the Gerstner normal.
    vec2 rp = vWorldPos.xy;
    float n1 = fbm2(rp * 1.6 + vec2(u_time * 0.30, u_time * 0.11), 3);
    float n2 = fbm2(rp * 3.7 - vec2(u_time * 0.17, u_time * 0.26), 2);
    float e = 0.06;
    float dx = fbm2((rp + vec2(e, 0.0)) * 1.6 + vec2(u_time * 0.30, u_time * 0.11), 3) - n1;
    float dy = fbm2((rp + vec2(0.0, e)) * 1.6 + vec2(u_time * 0.30, u_time * 0.11), 3) - n1;
    vec3 ripple = normalize(vec3(-dx * 5.5, -dy * 5.5, 1.0));

    // Calm the surface right at the shore.
    float shoreCalm = smoothstep(0.0, 0.6, depth);
    vec3 Nw = normalize(mix(vec3(0.0, 0.0, 1.0),
                            normalize(vWaveNormal + (ripple - vec3(0, 0, 1)) * 0.85),
                            shoreCalm));
    vec3 N = normalize(p3d_NormalMatrix * Nw);

    vec3 toEye = normalize(u_cameraWorld - vWorldPos);
    // Fresnel follows the flat surface far more than the ripples: the macro
    // geometry of a pond is a plane, and letting every wavelet swing the term
    // washes the reflection out to nothing across the whole surface.
    vec3 fresnelN = normalize(mix(vec3(0.0, 0.0, 1.0), Nw, 0.30));
    float NdotV = saturate(dot(fresnelN, toEye));
    float fresnel = 0.02 + 0.98 * pow(1.0 - NdotV, 5.0);

    // Sky reflection is the fallback; the planar pass supplies the world.
    vec3 R = reflect(-toEye, Nw);
    R.z = abs(R.z);
    vec3 reflection = sampleSky(R);

    if (u_reflectStrength > 0.0) {
        // The mirrored camera drew each point at the same screen position this
        // fragment occupies, so its own clip coordinate is the lookup.
        vec2 uv = (vClipPos.xy / max(vClipPos.w, 1e-4)) * 0.5 + 0.5;
        // Ripples distort the lookup; scale it down with distance so far water
        // doesn't smear.
        float distFade = 1.0 / (1.0 + length(u_cameraWorld - vWorldPos) * 0.05);
        uv += (Nw.xy - vec2(0.0, 0.0)) * 0.055 * distFade;
        // Off-screen samples have nothing behind them: fade back to the sky.
        vec2 edge = abs(uv - 0.5) * 2.0;
        float valid = (1.0 - smoothstep(0.86, 1.0, max(edge.x, edge.y)))
                      * step(0.0, uv.x) * step(uv.x, 1.0)
                      * step(0.0, uv.y) * step(uv.y, 1.0);
        vec3 world = texture(u_reflection, clamp(uv, 0.001, 0.999)).rgb;
        reflection = mix(reflection, world, valid * u_reflectStrength);
    }

    // Sun glint.
    vec3 L = normalize(u_sunDirWorld);
    vec3 H = normalize(L + toEye);
    float spec = pow(saturate(dot(Nw, H)), 900.0);
    reflection += p3d_LightSource[0].color.rgb * spec * 1.6;

    // Body colour: light scattered back out of the water column plus whatever
    // reaches the bed and returns. Seen from above, Fresnel is nearly zero, so
    // this term is all there is — it has to carry real brightness.
    float absorb = 1.0 - exp(-depth * 0.75);
    vec3 skyLight = sampleSky(vec3(0.0, 0.0, 1.0)) * u_ambientScale;
    float sunOnWater = saturate(dot(vec3(0.0, 0.0, 1.0), L));
    vec3 incoming = skyLight * 0.62 + p3d_LightSource[0].color.rgb * sunOnWater * 0.09;
    vec3 body = mix(u_shallowColor, u_deepColor, absorb * 0.8) * incoming;
    // Caustic-ish shimmer where the water is shallow enough for light to reach.
    float caust = fbm2(rp * 2.4 + vec2(u_time * 0.22, -u_time * 0.15), 2);
    body += u_shallowColor * incoming * pow(saturate(caust), 4.0)
            * (1.0 - absorb) * sunOnWater * 0.9;

    // Foam: a band at the shoreline plus froth on wave crests.
    float shore = 1.0 - smoothstep(0.0, u_foamWidth, depth);
    float crest = smoothstep(0.55, 0.95, n2 + vWaveHeight * 2.2);
    float foam = saturate(shore * (0.55 + 0.45 * sin(u_time * 1.7 + n1 * 9.0))
                          + crest * 0.35 * shoreCalm);
    vec3 foamCol = sampleSky(vec3(0.0, 0.0, 1.0)) * 0.9
                   + p3d_LightSource[0].color.rgb * 0.05;

    vec3 col = mix(body, reflection, fresnel);
    col = mix(col, foamCol, foam * 0.85);
    col = applyAerial(col, vWorldPos);

    float alpha = mix(0.42, 0.96, absorb);
    alpha = max(alpha, fresnel * 0.9);
    alpha = max(alpha, foam * 0.9);
    fragColor = vec4(col, alpha);
}
