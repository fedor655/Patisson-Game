#version 430

// Props, buildings, plants, animals — anything with an actual mesh.

#include "lib/common.glsl"
#include "lib/pbr.glsl"
#include "lib/lighting.glsl"

in vec3 vViewPos;
in vec3 vViewNormal;
in vec3 vWorldPos;
in vec3 vWorldNormal;
in vec2 vUv;
in vec4 vColor;

uniform struct p3d_MaterialParameters {
    vec4 baseColor;
    vec4 emission;
    float roughness;
    float metallic;
} p3d_Material;

uniform sampler2D p3d_Texture0;
// Panda won't apply this for us once we supply our own shader.
uniform vec4 p3d_ColorScale;
uniform float u_alphaCutoff;
uniform float u_hasAlbedoMap;
uniform float u_microDetail;

out vec4 fragColor;

void main() {
    vec4 albedo4 = p3d_Material.baseColor * vColor * p3d_ColorScale;
    if (u_hasAlbedoMap > 0.5) {
        vec4 tex = texture(p3d_Texture0, vUv);
        albedo4 *= vec4(srgbToLinear(tex.rgb), tex.a);
    }
    if (u_alphaCutoff > 0.0 && albedo4.a < u_alphaCutoff) discard;

    Surface s;
    s.albedo = albedo4.rgb;
    s.metallic = p3d_Material.metallic;
    s.roughness = p3d_Material.roughness;
    // Two-sided shading for thin geometry (leaves, cloth, awnings).
    s.N = normalize(gl_FrontFacing ? vViewNormal : -vViewNormal);
    s.Nw = normalize(gl_FrontFacing ? vWorldNormal : -vWorldNormal);
    s.viewPos = vViewPos;
    s.worldPos = vWorldPos;
    s.occlusion = 1.0;
    s.emission = p3d_Material.emission.rgb;

    if (u_microDetail > 0.0) {
        float n = fbm3(vWorldPos * 3.7, 2) - 0.5;
        s.roughness = clamp(s.roughness + n * u_microDetail, 0.05, 1.0);
    }

    vec3 lit = applyAerial(shadeSurface(s), vWorldPos);
    fragColor = vec4(lit, albedo4.a);
}
