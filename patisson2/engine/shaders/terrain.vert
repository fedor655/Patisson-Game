#version 430

in vec4 p3d_Vertex;
in vec3 p3d_Normal;
in vec2 p3d_MultiTexCoord0;

uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;
uniform mat4 p3d_ModelMatrix;
uniform mat3 p3d_NormalMatrix;

out vec3 vViewPos;
out vec3 vViewNormal;
out vec3 vWorldPos;
out vec3 vWorldNormal;
out vec2 vUv;

void main() {
    vec4 viewPos = p3d_ModelViewMatrix * p3d_Vertex;
    vViewPos = viewPos.xyz;
    vViewNormal = normalize(p3d_NormalMatrix * p3d_Normal);
    vWorldPos = (p3d_ModelMatrix * p3d_Vertex).xyz;
    vWorldNormal = normalize(mat3(p3d_ModelMatrix) * p3d_Normal);
    vUv = p3d_MultiTexCoord0;
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
}
