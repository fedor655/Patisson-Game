#version 430

#include "lib/common.glsl"
#include "lib/pbr.glsl"
#include "lib/lighting.glsl"

in vec3 vViewPos;
in vec3 vWorldPos;
in vec3 vViewNormal;
in vec3 vWorldNormal;
in vec3 vColor;
in float vAlong;

out vec4 fragColor;

void main() {
    Surface s;
    // Darker towards the root, where light doesn't reach into the sward.
    s.albedo = vColor * (0.66 + 0.34 * vAlong);
    s.metallic = 0.0;
    s.roughness = 0.78;
    s.N = normalize(gl_FrontFacing ? vViewNormal : -vViewNormal);
    s.Nw = normalize(gl_FrontFacing ? vWorldNormal : -vWorldNormal);
    s.viewPos = vViewPos;
    s.worldPos = vWorldPos;
    // Fake self-occlusion in the sward instead of paying for real AO.
    s.occlusion = 0.58 + 0.42 * vAlong;
    s.emission = vec3(0.0);

    vec3 lit = shadeSurface(s);

    // Cheap translucency: blades glow when backlit by the sun.
    vec3 L = normalize(p3d_LightSource[0].position.xyz);
    vec3 V = normalize(-vViewPos);
    float back = pow(saturate(dot(-V, L) * 0.5 + 0.5), 3.0);
    lit += vColor * p3d_LightSource[0].color.rgb * back * 0.055 * vAlong;

    fragColor = vec4(applyAerial(lit, vWorldPos), 1.0);
}
