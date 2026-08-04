// Shared helpers: hashing, noise, colour space, packing.

const float PI = 3.14159265358979323846;
const float TAU = 6.28318530717958647692;

float saturate(float x) { return clamp(x, 0.0, 1.0); }
vec3 saturate3(vec3 x) { return clamp(x, vec3(0.0), vec3(1.0)); }

float hash11(float p) {
    p = fract(p * 0.1031);
    p *= p + 33.33;
    p *= p + p;
    return fract(p);
}

float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

vec2 hash22(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.xx + p3.yz) * p3.zy);
}

vec3 hash33(vec3 p3) {
    p3 = fract(p3 * vec3(0.1031, 0.1030, 0.0973));
    p3 += dot(p3, p3.yxz + 33.33);
    return fract((p3.xxy + p3.yxx) * p3.zyx);
}

// Value noise, 2D.
float noise2(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    float a = hash12(i);
    float b = hash12(i + vec2(1.0, 0.0));
    float c = hash12(i + vec2(0.0, 1.0));
    float d = hash12(i + vec2(1.0, 1.0));
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

float fbm2(vec2 p, int octaves) {
    float v = 0.0;
    float a = 0.5;
    mat2 rot = mat2(0.80, 0.60, -0.60, 0.80);
    for (int i = 0; i < octaves; ++i) {
        v += a * noise2(p);
        p = rot * p * 2.02;
        a *= 0.5;
    }
    return v;
}

// Value noise, 3D — used for clouds and wind.
float noise3(vec3 p) {
    vec3 i = floor(p);
    vec3 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float n000 = hash33(i + vec3(0, 0, 0)).x;
    float n100 = hash33(i + vec3(1, 0, 0)).x;
    float n010 = hash33(i + vec3(0, 1, 0)).x;
    float n110 = hash33(i + vec3(1, 1, 0)).x;
    float n001 = hash33(i + vec3(0, 0, 1)).x;
    float n101 = hash33(i + vec3(1, 0, 1)).x;
    float n011 = hash33(i + vec3(0, 1, 1)).x;
    float n111 = hash33(i + vec3(1, 1, 1)).x;
    return mix(mix(mix(n000, n100, f.x), mix(n010, n110, f.x), f.y),
               mix(mix(n001, n101, f.x), mix(n011, n111, f.x), f.y), f.z);
}

float fbm3(vec3 p, int octaves) {
    float v = 0.0;
    float a = 0.5;
    for (int i = 0; i < octaves; ++i) {
        v += a * noise3(p);
        p *= 2.03;
        a *= 0.5;
    }
    return v;
}

vec3 srgbToLinear(vec3 c) {
    return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}

vec3 linearToSrgb(vec3 c) {
    return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
}

float luminance(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }

// Panda3D worlds are Z-up; the atmosphere model below is written Y-up.
vec3 zupToYup(vec3 v) { return vec3(v.x, v.z, v.y); }

// Direction <-> equirectangular UV, for the small sky lookup table.
vec2 dirToEquirect(vec3 d) {
    d = normalize(d);
    return vec2(atan(d.z, d.x) / TAU + 0.5, acos(clamp(d.y, -1.0, 1.0)) / PI);
}

vec3 equirectToDir(vec2 uv) {
    float phi = (uv.x - 0.5) * TAU;
    float theta = uv.y * PI;
    float st = sin(theta);
    return vec3(st * cos(phi), cos(theta), st * sin(phi));
}

// Reconstruct view-space position from a hardware depth sample.
vec3 viewPosFromDepth(float depth, vec2 uv, mat4 invProj) {
    vec4 clip = vec4(uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
    vec4 view = invProj * clip;
    return view.xyz / view.w;
}
