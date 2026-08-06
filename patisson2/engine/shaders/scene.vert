#version 430

// Main opaque/foliage vertex stage. Handles wind sway for anything flagged as
// vegetation and hands the fragment stage both view- and world-space data.

#include "lib/common.glsl"

in vec4 p3d_Vertex;
in vec3 p3d_Normal;
in vec2 p3d_MultiTexCoord0;
in vec4 p3d_Color;

uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;
uniform mat4 p3d_ModelMatrix;
uniform mat4 p3d_ViewMatrix;
uniform mat3 p3d_NormalMatrix;

uniform float u_time;
// xyz: wind direction (world, Z-up). w: strength. 0 disables the whole path.
uniform vec4 u_wind;
// Vertices above this model-space height sway; below it they are pinned.
uniform float u_windPivot;

out vec3 vViewPos;
out vec3 vViewNormal;
out vec3 vWorldPos;
out vec3 vWorldNormal;
out vec2 vUv;
out vec4 vColor;

void main() {
    vec4 modelPos = p3d_Vertex;

    if (u_wind.w > 0.0) {
        // Phase from the vertex's own world position, not the node origin.
        // Static dressing is flattened into 40 m tiles for batching, so a
        // whole tile shared one model matrix and every tree in it swayed to
        // the same metronome — "все деревья качаются одинаково". The low
        // spatial frequency keeps a single canopy moving as one (a 4 m crown
        // spans well under a radian) while trees a few metres apart fall
        // audibly out of step.
        vec3 worldV = (p3d_ModelMatrix * vec4(modelPos.xyz, 1.0)).xyz;
        float height = max(modelPos.z - u_windPivot, 0.0);
        float phase = dot(worldV.xy, u_wind.xy) * 0.13
                    + dot(worldV.xy, vec2(-u_wind.y, u_wind.x)) * 0.09
                    + u_time * 1.9;
        // Two frequencies so the motion never looks like a single sine.
        float sway = sin(phase) * 0.7 + sin(phase * 2.37 + 1.7) * 0.3;
        float gust = 0.65 + 0.35 * fbm2(worldV.xy * 0.06 + u_time * 0.08, 2);
        modelPos.xy += u_wind.xy * sway * gust * u_wind.w * height * height * 0.09;
    }

    vec4 viewPos = p3d_ModelViewMatrix * modelPos;
    vViewPos = viewPos.xyz;
    vViewNormal = normalize(p3d_NormalMatrix * p3d_Normal);
    vec4 worldPos = p3d_ModelMatrix * modelPos;
    vWorldPos = worldPos.xyz;
    vWorldNormal = normalize(mat3(p3d_ModelMatrix) * p3d_Normal);
    vUv = p3d_MultiTexCoord0;
    vColor = p3d_Color;

    gl_Position = p3d_ModelViewProjectionMatrix * modelPos;
}
