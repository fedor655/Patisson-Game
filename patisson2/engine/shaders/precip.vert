#version 430

// GPU-instanced precipitation. One quad, tens of thousands of instances, each
// placed from its instance id inside a box that follows the camera. The box
// wraps on a world-anchored grid, so particles never pop as the player walks.

#include "lib/common.glsl"

in vec4 p3d_Vertex;      // unit quad: x across, z along the fall direction

uniform mat4 p3d_ViewMatrix;
uniform mat4 p3d_ProjectionMatrix;

uniform vec3 u_camera;         // world position the volume centres on
uniform vec3 u_box;            // volume extents (metres)
uniform vec2 u_size;           // particle width, length
uniform float u_time;
uniform float u_fallSpeed;
uniform vec3 u_wind;           // horizontal drift (m/s), z unused
uniform float u_intensity;     // 0..1, also thins the count
uniform float u_sway;          // lateral wobble amplitude (snow)
uniform float u_groundFade;    // metres above terrain to start fading out
uniform sampler2D u_heightMap;
uniform vec4 u_terrainBounds;

out float vFade;
out vec2 vQuad;
out vec3 vViewDir;

float terrainHeight(vec2 p) {
    return texture(u_heightMap, (p - u_terrainBounds.xy) * u_terrainBounds.zw).r;
}

void main() {
    float id = float(gl_InstanceID);
    vec3 h = hash33(vec3(id * 0.0017, id * 0.0009 + 4.3, id * 0.0023 + 9.1));

    // Thinning by intensity keeps light rain cheap instead of just transparent.
    if (h.x > u_intensity) {
        gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
        vFade = 0.0;
        vQuad = vec2(0.0);
        vViewDir = vec3(0.0, 0.0, 1.0);
        return;
    }

    // Base position inside the volume, falling and drifting with the wind.
    float t = u_time;
    vec3 base;
    base.xy = h.yz * u_box.xy;
    base.xy += u_wind.xy * t;
    float phase = h.y * 977.0 + h.z * 331.0;
    base.z = u_box.z - mod(t * u_fallSpeed + phase, u_box.z);

    // Anchor to a world grid and shift whole boxes so the volume tracks the
    // camera without the particles themselves moving.
    vec2 cell = floor((u_camera.xy - base.xy) / u_box.xy + 0.5);
    vec3 pos;
    pos.xy = base.xy + cell * u_box.xy;
    pos.z = u_camera.z + base.z - u_box.z * 0.55;

    if (u_sway > 0.0) {
        float s = t * (0.7 + h.x * 1.3) + phase;
        pos.x += sin(s) * u_sway;
        pos.y += cos(s * 0.83) * u_sway;
    }

    // Fade out as a particle reaches the ground, and cull it below.
    float ground = terrainHeight(pos.xy);
    float above = pos.z - ground;
    if (above < 0.0) {
        gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
        vFade = 0.0;
        vQuad = vec2(0.0);
        vViewDir = vec3(0.0, 0.0, 1.0);
        return;
    }
    vFade = smoothstep(0.0, u_groundFade, above);
    // Also fade at the top of the volume so nothing appears out of thin air.
    vFade *= 1.0 - smoothstep(u_box.z * 0.75, u_box.z * 0.98, base.z);

    // Build the quad facing the camera, stretched along the fall direction.
    vec3 fall = normalize(vec3(u_wind.xy * 0.25, -u_fallSpeed));
    vec3 toCam = u_camera - pos;
    float dist = length(toCam);
    toCam = dist > 1e-4 ? toCam / dist : vec3(0.0, 0.0, 1.0);
    vec3 right = cross(fall, toCam);
    float rl = length(right);
    right = rl > 1e-4 ? right / rl : vec3(1.0, 0.0, 0.0);

    vQuad = p3d_Vertex.xz;
    vec3 world = pos
               + right * (p3d_Vertex.x * u_size.x)
               - fall * (p3d_Vertex.z * u_size.y);

    // Distant particles read as haze rather than streaks, so drop them.
    vFade *= 1.0 - smoothstep(u_box.x * 0.40, u_box.x * 0.52, dist);

    vViewDir = normalize(world - u_camera);

    vec4 viewPos = p3d_ViewMatrix * vec4(world, 1.0);
    gl_Position = p3d_ProjectionMatrix * viewPos;
}
