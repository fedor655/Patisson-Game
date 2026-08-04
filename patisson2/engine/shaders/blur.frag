#version 430

// Separable 9-tap gaussian, reused for bloom levels and AO cleanup.

in vec2 vUv;

uniform sampler2D u_source;
uniform vec2 u_direction;   // texel-sized step along one axis

out vec4 fragColor;

void main() {
    const float w[5] = float[5](0.227027, 0.194595, 0.121622, 0.054054, 0.016216);
    vec4 sum = texture(u_source, vUv) * w[0];
    for (int i = 1; i < 5; ++i) {
        sum += texture(u_source, vUv + u_direction * float(i)) * w[i];
        sum += texture(u_source, vUv - u_direction * float(i)) * w[i];
    }
    fragColor = sum;
}
