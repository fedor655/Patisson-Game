// Cook-Torrance microfacet BRDF + shadow lookup helpers.

#ifndef PBR_GLSL
#define PBR_GLSL

float distributionGGX(float NdotH, float roughness) {
    float a = roughness * roughness;
    float a2 = a * a;
    float d = NdotH * NdotH * (a2 - 1.0) + 1.0;
    return a2 / max(PI * d * d, 1e-7);
}

float geometrySchlickGGX(float NdotV, float roughness) {
    float r = roughness + 1.0;
    float k = (r * r) / 8.0;
    return NdotV / (NdotV * (1.0 - k) + k);
}

float geometrySmith(float NdotV, float NdotL, float roughness) {
    return geometrySchlickGGX(NdotV, roughness) * geometrySchlickGGX(NdotL, roughness);
}

vec3 fresnelSchlick(float cosTheta, vec3 F0) {
    return F0 + (1.0 - F0) * pow(1.0 - cosTheta, 5.0);
}

vec3 fresnelSchlickRoughness(float cosTheta, vec3 F0, float roughness) {
    return F0 + (max(vec3(1.0 - roughness), F0) - F0) * pow(1.0 - cosTheta, 5.0);
}

// Direct lighting contribution of one light.
vec3 pbrDirect(vec3 N, vec3 V, vec3 L, vec3 albedo, float metallic, float roughness,
               vec3 radiance) {
    vec3 H = normalize(V + L);
    float NdotL = max(dot(N, L), 0.0);
    if (NdotL <= 0.0) return vec3(0.0);
    float NdotV = max(dot(N, V), 1e-4);
    float NdotH = max(dot(N, H), 0.0);
    float VdotH = max(dot(V, H), 0.0);

    vec3 F0 = mix(vec3(0.04), albedo, metallic);
    float D = distributionGGX(NdotH, roughness);
    float G = geometrySmith(NdotV, NdotL, roughness);
    vec3 F = fresnelSchlick(VdotH, F0);

    vec3 specular = (D * G * F) / max(4.0 * NdotV * NdotL, 1e-5);
    vec3 kD = (vec3(1.0) - F) * (1.0 - metallic);

    return (kD * albedo / PI + specular) * radiance * NdotL;
}

// Analytic stand-in for the split-sum environment BRDF table. Without this the
// bias term grows with roughness and every matte surface picks up a white
// specular sheen from the sky.
vec2 envBRDFApprox(float NdotV, float roughness) {
    const vec4 c0 = vec4(-1.0, -0.0275, -0.572, 0.022);
    const vec4 c1 = vec4(1.0, 0.0425, 1.04, -0.04);
    vec4 r = roughness * c0 + c1;
    float a004 = min(r.x * r.x, exp2(-9.28 * NdotV)) * r.x + r.y;
    return vec2(-1.04, 1.04) * a004 + r.zw;
}

// Split-sum ambient. skyDiffuse/skySpecular come from the sky LUT.
vec3 pbrAmbient(vec3 N, vec3 V, vec3 albedo, float metallic, float roughness,
                vec3 skyDiffuse, vec3 skySpecular, float occlusion) {
    float NdotV = max(dot(N, V), 1e-4);
    vec3 F0 = mix(vec3(0.04), albedo, metallic);
    vec3 F = fresnelSchlickRoughness(NdotV, F0, roughness);
    vec3 kD = (vec3(1.0) - F) * (1.0 - metallic);
    vec2 ab = envBRDFApprox(NdotV, roughness);
    vec3 spec = skySpecular * (F0 * ab.x + ab.y);
    return (kD * albedo * skyDiffuse + spec) * occlusion;
}

// Percentage-closer filtering over a Panda3D shadow map.
float pcfShadow(sampler2DShadow shadowMap, vec4 coord, float texel, float bias) {
    if (coord.w <= 0.0) return 1.0;
    vec3 p = coord.xyz / coord.w;
    if (p.x < 0.0 || p.x > 1.0 || p.y < 0.0 || p.y > 1.0 || p.z > 1.0) return 1.0;
    p.z -= bias;

    float sum = 0.0;
    // 9-tap rotated grid; wide enough to soften without ghosting.
    const vec2 taps[9] = vec2[9](
        vec2(0.0, 0.0), vec2(1.0, 0.0), vec2(-1.0, 0.0),
        vec2(0.0, 1.0), vec2(0.0, -1.0), vec2(0.87, 0.87),
        vec2(-0.87, 0.87), vec2(0.87, -0.87), vec2(-0.87, -0.87));
    for (int i = 0; i < 9; ++i) {
        sum += texture(shadowMap, vec3(p.xy + taps[i] * texel, p.z));
    }
    return sum / 9.0;
}

#endif
