#version 430

// GPU-instanced grass. The mesh is a single 7-vertex blade; every instance
// derives its own position, size, tilt and colour from gl_InstanceID, samples
// the terrain height field for its base, and bends in the wind. Blades that
// land on steep ground, in water or on a tilled plot collapse to nothing.

#include "lib/common.glsl"

in vec4 p3d_Vertex;      // x: across the blade (-1..1), z: along it (0..1)

uniform mat4 p3d_ViewMatrix;
uniform mat4 p3d_ProjectionMatrix;

uniform sampler2D u_heightMap;
uniform sampler2D u_fieldMask;
uniform vec4 u_terrainBounds;   // xy: min corner, zw: 1/size
uniform vec2 u_center;          // patch follows the player
uniform float u_radius;
uniform float u_time;
uniform vec4 u_wind;            // xyz dir, w strength
uniform float u_waterLevel;
uniform vec3 u_colorA;
uniform vec3 u_colorB;
uniform float u_heightScale;

out vec3 vViewPos;
out vec3 vWorldPos;
out vec3 vViewNormal;
out vec3 vWorldNormal;
out vec3 vColor;
out float vAlong;

float terrainHeight(vec2 p) {
    return texture(u_heightMap, (p - u_terrainBounds.xy) * u_terrainBounds.zw).r;
}

void main() {
    float id = float(gl_InstanceID);
    vec3 r = hash33(vec3(id * 0.0013, id * 0.0007 + 3.1, id * 0.0021 + 7.7));
    vec3 r2 = hash33(vec3(id * 0.0029 + 11.0, id * 0.0017 + 5.0, id * 0.0011 + 2.0));

    // Every instance owns one fixed spot in a world-space tile of side
    // 2*radius, repeated across the map; we draw the repetition nearest the
    // player. The base used to be u_center plus a per-instance offset -- the
    // whole field was welded to the camera and every blade slid across the
    // ground with each step, which was the first thing the player noticed.
    vec2 offset = (r.xy * 2.0 - 1.0) * u_radius;
    float tile = 2.0 * u_radius;
    vec2 base = offset + tile * floor((u_center - offset) / tile + 0.5);
    float rad = distance(base, u_center);

    float h = terrainHeight(base);

    // Slope from finite differences on the height field.
    float e = 0.9;
    float hx = terrainHeight(base + vec2(e, 0.0)) - terrainHeight(base - vec2(e, 0.0));
    float hy = terrainHeight(base + vec2(0.0, e)) - terrainHeight(base - vec2(0.0, e));
    vec3 groundN = normalize(vec3(-hx, -hy, 2.0 * e));

    vec2 maskUv = (base - u_terrainBounds.xy) * u_terrainBounds.zw;
    vec3 mask = texture(u_fieldMask, maskUv).rgb;

    // Patchiness so the lawn isn't uniform.
    float density = fbm2(base * 0.09, 3);

    bool cull = rad > u_radius
             || h < u_waterLevel + 0.12
             || groundN.z < 0.74
             || mask.r > 0.25
             || mask.g > 0.55
             || mask.b > 0.35
             || density < 0.19;

    if (cull) {
        gl_Position = vec4(2.0, 2.0, 2.0, 1.0);   // outside clip space
        vViewPos = vec3(0.0);
        vWorldPos = vec3(0.0);
        vViewNormal = vec3(0.0, 0.0, 1.0);
        vWorldNormal = vec3(0.0, 0.0, 1.0);
        vColor = vec3(0.0);
        vAlong = 0.0;
        return;
    }

    float across = p3d_Vertex.x;
    float along = p3d_Vertex.z;
    vAlong = along;

    float yaw = r.z * TAU;
    vec2 dir = vec2(cos(yaw), sin(yaw));
    vec2 side = vec2(-dir.y, dir.x);

    float height = u_heightScale * (0.55 + 0.85 * r2.x) * smoothstep(0.17, 0.45, density);
    // Shrink towards the edge of the patch so the disc has no visible rim.
    height *= 1.0 - smoothstep(0.72, 1.0, rad / u_radius);
    float width = 0.017 * (0.7 + 0.6 * r2.y);

    // Natural droop plus wind. Both scale with the square of the height so the
    // base stays planted.
    float gust = 0.55 + 0.45 * fbm2(base * 0.05 + u_time * 0.12, 2);
    float phase = dot(base, u_wind.xy) * 0.5 + u_time * 2.1 + r.x * 6.0;
    float sway = (sin(phase) * 0.7 + sin(phase * 2.3 + 1.1) * 0.3);
    vec2 bendDir = normalize(u_wind.xy + dir * 0.35 + vec2(1e-4));
    float bend = (0.16 + u_wind.w * gust * 0.55 * (0.6 + 0.4 * sway)) * height;

    vec3 pos;
    pos.xy = base + side * across * width * (1.0 - along * 0.85) + bendDir * bend * along * along;
    pos.z = h + along * height * (1.0 - 0.22 * along * along);

    // A blade's true surface normal is horizontal, which makes a whole field
    // read as black under a high sun. Round it across the width for shape, then
    // pull it most of the way back towards the ground normal so the sward
    // lights like the surface it is.
    vec3 faceN = normalize(vec3(dir, 0.0));
    faceN = normalize(mix(faceN, vec3(side, 0.0), across * 0.55));
    faceN = normalize(faceN + vec3(0.0, 0.0, 0.85));
    vec3 bladeN = normalize(mix(groundN, faceN, 0.34));

    vColor = mix(u_colorA, u_colorB, r2.y) * (0.72 + 0.55 * r.y);

    vWorldPos = pos;
    vWorldNormal = bladeN;
    vec4 viewPos = p3d_ViewMatrix * vec4(pos, 1.0);
    vViewPos = viewPos.xyz;
    vViewNormal = normalize(mat3(p3d_ViewMatrix) * bladeN);
    gl_Position = p3d_ProjectionMatrix * viewPos;
}
