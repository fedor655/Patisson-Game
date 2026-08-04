#version 430

// Water surface. The plane is flat geometry; Gerstner waves displace it and the
// normal is taken from the analytic derivative rather than from the mesh.

#include "lib/common.glsl"

in vec4 p3d_Vertex;

uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;
uniform mat4 p3d_ModelMatrix;
uniform mat3 p3d_NormalMatrix;

uniform float u_time;
uniform float u_waveAmp;
uniform vec3 u_cameraWorld;

out vec3 vViewPos;
out vec3 vWorldPos;
out vec4 vClipPos;
out vec3 vWaveNormal;
out float vWaveHeight;

// One Gerstner component; accumulates position offset and normal partials.
void gerstner(vec2 p, vec2 dir, float wavelength, float steepness, float t,
              inout vec3 offset, inout vec3 tangent, inout vec3 binormal) {
    float k = TAU / wavelength;
    float c = sqrt(9.81 / k);
    vec2 d = normalize(dir);
    float f = k * (dot(d, p) - c * t);
    float a = steepness / k;

    offset.x += d.x * (a * cos(f));
    offset.y += d.y * (a * cos(f));
    offset.z += a * sin(f);

    tangent += vec3(-d.x * d.x * (steepness * sin(f)),
                    -d.x * d.y * (steepness * sin(f)),
                    d.x * (steepness * cos(f)));
    binormal += vec3(-d.x * d.y * (steepness * sin(f)),
                     -d.y * d.y * (steepness * sin(f)),
                     d.y * (steepness * cos(f)));
}

void main() {
    vec4 world = p3d_ModelMatrix * p3d_Vertex;
    vec2 p = world.xy;

    vec3 offset = vec3(0.0);
    vec3 tangent = vec3(1.0, 0.0, 0.0);
    vec3 binormal = vec3(0.0, 1.0, 0.0);

    float amp = u_waveAmp;
    gerstner(p, vec2(1.0, 0.35), 9.0, 0.09 * amp, u_time, offset, tangent, binormal);
    gerstner(p, vec2(-0.6, 1.0), 5.5, 0.07 * amp, u_time, offset, tangent, binormal);
    gerstner(p, vec2(0.3, -1.0), 3.1, 0.05 * amp, u_time, offset, tangent, binormal);
    gerstner(p, vec2(-1.0, -0.4), 1.9, 0.035 * amp, u_time, offset, tangent, binormal);

    world.xyz += offset;
    vWaveHeight = offset.z;
    vWaveNormal = normalize(cross(tangent, binormal));

    vWorldPos = world.xyz;
    vec4 viewPos = p3d_ModelViewMatrix * (p3d_Vertex + vec4(offset, 0.0));
    vViewPos = viewPos.xyz;
    gl_Position = p3d_ModelViewProjectionMatrix * (p3d_Vertex + vec4(offset, 0.0));
    vClipPos = gl_Position;
}
