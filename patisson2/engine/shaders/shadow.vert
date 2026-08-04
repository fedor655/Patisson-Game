#version 430

// Depth-only pass for the sun's shadow map.
//
// Panda renders a node into a shadow buffer with whatever shader is bound to
// it. Without this override the whole 2048x2048 map was filled by the full PBR
// fragment stage — sky-table lookups, PCF, aerial perspective — for an image
// where only depth is ever read back.
//
// This deliberately declares no uniforms of its own beyond the built-in
// matrix: overriding a ShaderAttrib replaces it wholesale, inputs included, so
// anything custom here would be missing its value and fail to bind. That costs
// us wind sway in shadows, which is not visible at plant scale.

in vec4 p3d_Vertex;
uniform mat4 p3d_ModelViewProjectionMatrix;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
}
