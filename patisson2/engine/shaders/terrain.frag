#version 430

// Procedural ground: grass / soil / rock / sand blended by slope, height and
// noise, with a tilled-field mask painted in from the game side.

#include "lib/common.glsl"
#include "lib/pbr.glsl"
#include "lib/lighting.glsl"

in vec3 vViewPos;
in vec3 vViewNormal;
in vec3 vWorldPos;
in vec3 vWorldNormal;
in vec2 vUv;

uniform vec3 u_grassColor;
uniform vec3 u_grassColorDry;
uniform vec3 u_soilColor;
uniform vec3 u_rockColor;
uniform vec3 u_sandColor;
uniform vec3 u_snowColor;
uniform float u_snowAmount;
uniform float u_waterLevel;
uniform sampler2D u_fieldMask;    // r: tilled soil, g: trampled path
uniform vec4 u_worldBounds;       // xy: min corner, zw: 1/size

out vec4 fragColor;

void main() {
    vec3 Nw = normalize(vWorldNormal);
    float slope = 1.0 - saturate(Nw.z);
    vec2 p = vWorldPos.xy;

    // Macro variation so the ground never reads as one flat colour.
    float macro = fbm2(p * 0.021, 4);
    float meso = fbm2(p * 0.13, 3);
    float micro = noise2(p * 1.7);

    vec3 grass = mix(u_grassColor, u_grassColorDry, saturate(macro * 1.5 - 0.25));
    grass *= 0.82 + 0.36 * meso;
    grass *= 0.90 + 0.20 * micro;

    vec3 albedo = grass;
    float roughness = 0.94;

    // Bare soil shows through where the grass thins out.
    float bare = smoothstep(0.55, 0.78, macro * 0.6 + meso * 0.5);
    albedo = mix(albedo, u_soilColor * (0.85 + 0.3 * micro), bare * 0.55);

    // Rock on steep faces.
    float rock = smoothstep(0.30, 0.58, slope + (meso - 0.5) * 0.16);
    albedo = mix(albedo, u_rockColor * (0.75 + 0.5 * micro), rock);
    roughness = mix(roughness, 0.72, rock);

    // Sand around the waterline.
    float toWater = vWorldPos.z - u_waterLevel;
    float sand = 1.0 - smoothstep(0.05, 0.80, toWater);
    sand *= smoothstep(-1.6, -0.20, toWater);
    albedo = mix(albedo, u_sandColor * (0.88 + 0.24 * micro), sand * 0.92);
    roughness = mix(roughness, 0.86, sand);

    // Lake bed below the water.
    float bed = 1.0 - smoothstep(-0.35, 0.02, toWater);
    albedo = mix(albedo, u_soilColor * 0.68, bed * 0.85);

    // Tilled plots and worn paths, painted by the game.
    vec2 maskUv = (p - u_worldBounds.xy) * u_worldBounds.zw;
    vec2 mask = texture(u_fieldMask, maskUv).rg;
    vec3 tilled = u_soilColor * (0.62 + 0.5 * noise2(p * 6.0));
    // Furrows.
    float furrow = 0.72 + 0.28 * sin(p.x * 7.2 + noise2(p * 3.0) * 1.4);
    albedo = mix(albedo, tilled * furrow, mask.r);
    roughness = mix(roughness, 0.98, mask.r);
    albedo = mix(albedo, mix(u_soilColor, grass, 0.35) * 0.92, mask.g * 0.8);

    // Snow settles on flat ground in winter.
    if (u_snowAmount > 0.001) {
        float snow = u_snowAmount * smoothstep(0.42, 0.05, slope);
        snow *= smoothstep(0.0, 0.35, toWater);
        snow *= 0.75 + 0.25 * meso;
        albedo = mix(albedo, u_snowColor, saturate(snow));
        roughness = mix(roughness, 0.60, saturate(snow));
    }

    Surface s;
    s.albedo = albedo;
    s.metallic = 0.0;
    s.roughness = roughness;
    s.N = normalize(vViewNormal);
    s.Nw = Nw;
    s.viewPos = vViewPos;
    s.worldPos = vWorldPos;
    s.occlusion = 1.0;
    s.emission = vec3(0.0);

    fragColor = vec4(applyAerial(shadeSurface(s), vWorldPos), 1.0);
}
