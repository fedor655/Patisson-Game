#version 430

// Fullscreen sky quad. Vertices arrive as a unit card in the XZ plane; we write
// clip space directly and recover the world-space view ray per corner.

in vec4 p3d_Vertex;

uniform mat4 p3d_ProjectionMatrixInverse;
uniform mat4 p3d_ViewMatrixInverse;

out vec3 vRayWorld;

void main() {
    vec4 clip = vec4(p3d_Vertex.xz, 1.0, 1.0);
    gl_Position = clip;
    vec4 viewH = p3d_ProjectionMatrixInverse * clip;
    vec3 viewDir = viewH.xyz / viewH.w;
    vRayWorld = mat3(p3d_ViewMatrixInverse) * viewDir;
}
