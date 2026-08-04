#version 430

// Renders the sky into a small equirectangular table once per frame. Everything
// that needs ambient light or aerial perspective samples this instead of
// re-integrating the atmosphere per pixel.

#include "lib/common.glsl"
#include "lib/atmosphere.glsl"

in vec2 vUv;

uniform vec3 u_sunDirWorld;
uniform float u_sunIntensity;
uniform float u_time;
uniform float u_cloudCover;

out vec4 fragColor;

void main() {
    vec3 rd = equirectToDir(vUv);
    vec3 sun = normalize(zupToYup(u_sunDirWorld));

    vec3 col = atmScatter(rd, sun, u_sunIntensity, 12, 5);

    // The table drives ambient light, so it carries the moon and a night floor
    // but never the sun disk itself.
    float night = saturate(-sun.y * 5.0 + 0.10);
    col += vec3(0.0030, 0.0048, 0.0125) * night;
    col += vec3(0.055, 0.058, 0.075) * night * smoothstep(-0.2, 0.6, rd.y);

    // Below the horizon the integral degenerates (the ray hits the planet almost
    // immediately), so build the lower hemisphere from horizon light bounced off
    // the ground instead. This is what makes downward-facing surfaces read as
    // earth-lit rather than black.
    if (rd.y < 0.0) {
        vec3 horizon = atmScatter(normalize(vec3(rd.x, 0.06, rd.z)), sun, u_sunIntensity, 10, 4);
        vec3 groundAlbedo = vec3(0.21, 0.26, 0.14);
        float sunUp = saturate(sun.y);
        vec3 bounce = horizon * groundAlbedo * (0.45 + 0.85 * sunUp);
        bounce += vec3(0.9, 0.75, 0.45) * u_sunIntensity * 0.0008 * saturate(sun.y);
        col = mix(horizon, bounce, saturate(-rd.y * 3.0));
    }

    fragColor = vec4(col, 1.0);
}
