#version 430

// Shared vertex stage for every fullscreen pass.

in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;

uniform mat4 p3d_ModelViewProjectionMatrix;

out vec2 vUv;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    vUv = p3d_MultiTexCoord0;
}
