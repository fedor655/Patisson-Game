// Shared surface shading: the sun with PCF shadows, point lights, sky-LUT
// ambient and aerial perspective. Every world shader (props, terrain, grass,
// water) goes through here so they can never drift out of agreement.
//
// Requires NUM_LIGHTS to be defined and lib/common.glsl + lib/pbr.glsl included.

#ifndef LIGHTING_GLSL
#define LIGHTING_GLSL

uniform struct p3d_LightSourceParameters {
    vec4 color;
    vec4 position;
    vec3 attenuation;
    mat4 shadowViewMatrix;
    sampler2DShadow shadowMap;
} p3d_LightSource[NUM_LIGHTS];

uniform sampler2D u_skyLut;
uniform vec3 u_sunDirWorld;
uniform vec3 u_cameraWorld;
uniform float u_shadowTexel;
uniform float u_shadowBias;
uniform float u_ambientScale;
uniform float u_fogDensity;
uniform vec3 u_fogTint;

struct Surface {
    vec3 albedo;
    float metallic;
    float roughness;
    vec3 N;        // view-space normal, already flipped for back faces
    vec3 Nw;       // world-space normal
    vec3 viewPos;
    vec3 worldPos;
    float occlusion;
    vec3 emission;
};

vec3 sampleSky(vec3 worldDir) {
    return texture(u_skyLut, dirToEquirect(zupToYup(normalize(worldDir)))).rgb;
}

uniform float u_shadowWorldTexel;   // metres covered by one shadow-map texel

// Normal-offset shadows: push the lookup off the surface along its normal
// before projecting. This is what keeps large, gently curved geometry (the
// terrain especially) from shadowing itself under a grazing sun, where a depth
// bias alone would have to be so large it detaches contact shadows.
float sunShadow(vec3 viewPos, vec3 N, float NdotL) {
    float slope = clamp(1.0 - NdotL, 0.0, 1.0);
    vec3 offset = N * u_shadowWorldTexel * (1.6 + 5.0 * slope);
    vec4 coord = p3d_LightSource[0].shadowViewMatrix * vec4(viewPos + offset, 1.0);
    float bias = u_shadowBias * (1.0 + 2.0 * slope);
    return pcfShadow(p3d_LightSource[0].shadowMap, coord, u_shadowTexel, bias);
}

vec3 shadeSurface(Surface s) {
    vec3 V = normalize(-s.viewPos);
    float roughness = clamp(s.roughness, 0.035, 1.0);
    float metallic = clamp(s.metallic, 0.0, 1.0);
    vec3 lit = vec3(0.0);

    // --- sun ---
    vec3 L = normalize(p3d_LightSource[0].position.xyz);
    float NdotL = max(dot(s.N, L), 0.0);
    float shadow = sunShadow(s.viewPos, s.N, NdotL);
    lit += pbrDirect(s.N, V, L, s.albedo, metallic, roughness,
                     p3d_LightSource[0].color.rgb) * shadow;

    // --- point lights ---
    for (int i = 1; i < NUM_LIGHTS; ++i) {
        vec3 toLight = p3d_LightSource[i].position.xyz - s.viewPos * p3d_LightSource[i].position.w;
        float dist = length(toLight);
        if (dist < 1e-4) continue;
        vec3 att3 = p3d_LightSource[i].attenuation;
        float att = 1.0 / max(att3.x + att3.y * dist + att3.z * dist * dist, 1e-4);
        vec3 radiance = p3d_LightSource[i].color.rgb * att;
        if (luminance(radiance) < 2e-4) continue;
        lit += pbrDirect(s.N, V, toLight / dist, s.albedo, metallic, roughness, radiance);
    }

    // --- ambient from the sky table ---
    vec3 toEye = normalize(u_cameraWorld - s.worldPos);
    vec3 Rw = reflect(-toEye, s.Nw);
    vec3 skyDiffuse = mix(sampleSky(s.Nw), sampleSky(vec3(0.0, 0.0, 1.0)), 0.35);
    vec3 skySpecular = mix(sampleSky(Rw), skyDiffuse, roughness * roughness);
    float horizon = saturate(s.Nw.z * 0.5 + 0.62);
    lit += pbrAmbient(s.N, V, s.albedo, metallic, roughness,
                      skyDiffuse * u_ambientScale * horizon,
                      skySpecular * u_ambientScale, s.occlusion);

    return lit + s.emission;
}

// Blend towards the sky along the view ray. The direction is clamped to the
// horizon: the table's lower hemisphere models looking down at a planet from
// altitude and is far too dark to fog distant ground with.
vec3 applyAerial(vec3 lit, vec3 worldPos) {
    vec3 toCam = worldPos - u_cameraWorld;
    float dist = length(toCam);
    vec3 dir = normalize(toCam);
    dir.z = max(dir.z, 0.0);
    float fog = 1.0 - exp(-dist * u_fogDensity);
    return mix(lit, sampleSky(dir) * u_fogTint, fog);
}

#endif
