#version 430

in vec2 vUv;
uniform sampler2D u_source;
out vec4 fragColor;

void main() {
    fragColor = texture(u_source, vUv);
}
