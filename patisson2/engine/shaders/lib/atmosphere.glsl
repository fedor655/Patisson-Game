// Single-scattering atmosphere (Rayleigh + Mie), evaluated per pixel.
// Also provides the night sky: stars, moon and a procedural cloud deck.
// The same functions feed both the sky dome and the ambient term used when
// shading the world, so lighting and background always agree.

#ifndef ATMOSPHERE_GLSL
#define ATMOSPHERE_GLSL

const float ATM_R_PLANET = 6371000.0;
const float ATM_R_ATMOS = 6471000.0;
const vec3 ATM_BETA_RAYLEIGH = vec3(5.5e-6, 13.0e-6, 22.4e-6);
const float ATM_BETA_MIE = 21e-6;
const float ATM_H_RAYLEIGH = 8000.0;
const float ATM_H_MIE = 1200.0;
const float ATM_G_MIE = 0.758;

// Distance to the far intersection of a ray with a sphere centred at origin.
// Returns -1.0 when the ray misses.
float atmRaySphere(vec3 ro, vec3 rd, float radius) {
    float b = dot(ro, rd);
    float c = dot(ro, ro) - radius * radius;
    float d = b * b - c;
    if (d < 0.0) return -1.0;
    return -b + sqrt(d);
}

float atmPhaseRayleigh(float mu) {
    return 3.0 / (16.0 * PI) * (1.0 + mu * mu);
}

float atmPhaseMie(float mu, float g) {
    float gg = g * g;
    return 3.0 / (8.0 * PI) * ((1.0 - gg) * (1.0 + mu * mu)) /
           ((2.0 + gg) * pow(1.0 + gg - 2.0 * g * mu, 1.5));
}

// Scattered light arriving along rayDir. sunDir points *towards* the sun.
vec3 atmScatter(vec3 rayDir, vec3 sunDir, float sunIntensity, int steps, int lightSteps) {
    vec3 origin = vec3(0.0, ATM_R_PLANET + 200.0, 0.0);
    float tMax = atmRaySphere(origin, rayDir, ATM_R_ATMOS);
    if (tMax < 0.0) return vec3(0.0);

    // Rays pointing into the ground still need a sensible horizon colour, so
    // clamp rather than terminate.
    float ground = atmRaySphere(origin, rayDir, ATM_R_PLANET);
    if (ground > 0.0 && rayDir.y < 0.0) tMax = min(tMax, ground);

    float stepSize = tMax / float(steps);
    float mu = dot(rayDir, sunDir);
    float phaseR = atmPhaseRayleigh(mu);
    float phaseM = atmPhaseMie(mu, ATM_G_MIE);

    vec3 sumR = vec3(0.0);
    vec3 sumM = vec3(0.0);
    float odR = 0.0;
    float odM = 0.0;

    for (int i = 0; i < steps; ++i) {
        vec3 p = origin + rayDir * (float(i) + 0.5) * stepSize;
        float h = length(p) - ATM_R_PLANET;
        float hR = exp(-h / ATM_H_RAYLEIGH) * stepSize;
        float hM = exp(-h / ATM_H_MIE) * stepSize;
        odR += hR;
        odM += hM;

        // Optical depth towards the sun from this sample.
        float lMax = atmRaySphere(p, sunDir, ATM_R_ATMOS);
        float lStep = lMax / float(lightSteps);
        float odLR = 0.0;
        float odLM = 0.0;
        bool blocked = false;
        for (int j = 0; j < lightSteps; ++j) {
            vec3 lp = p + sunDir * (float(j) + 0.5) * lStep;
            float lh = length(lp) - ATM_R_PLANET;
            if (lh < 0.0) { blocked = true; break; }
            odLR += exp(-lh / ATM_H_RAYLEIGH) * lStep;
            odLM += exp(-lh / ATM_H_MIE) * lStep;
        }
        if (blocked) continue;

        vec3 tau = ATM_BETA_RAYLEIGH * (odR + odLR) + ATM_BETA_MIE * 1.1 * (odM + odLM);
        vec3 attn = exp(-tau);
        sumR += attn * hR;
        sumM += attn * hM;
    }

    return sunIntensity * (sumR * ATM_BETA_RAYLEIGH * phaseR + sumM * ATM_BETA_MIE * phaseM);
}

// Cheap, smooth version for ambient lookups (few steps, no sun disk).
vec3 atmAmbient(vec3 rayDir, vec3 sunDir, float sunIntensity) {
    return atmScatter(normalize(rayDir), sunDir, sunIntensity, 6, 3);
}

// --- night -----------------------------------------------------------------

float atmStars(vec3 rd, float time) {
    // Cell-hash star field. Cells are built from the direction projected onto
    // the dominant axis, which spreads them evenly instead of clumping the way
    // a raw 3D cell grid does near the axes.
    vec3 a = abs(rd);
    vec2 uv;
    if (a.y >= a.x && a.y >= a.z)      uv = rd.xz / a.y;
    else if (a.x >= a.z)               uv = rd.yz / a.x;
    else                               uv = rd.xy / a.z;

    vec2 p = uv * 96.0;
    vec2 cell = floor(p);
    vec2 f = fract(p) - 0.5;
    vec3 h = hash33(vec3(cell, 1.7));
    if (h.z > 0.10) return 0.0;
    vec2 offset = (h.xy - 0.5) * 0.7;
    float d = length(f - offset);
    float star = smoothstep(0.22, 0.0, d);
    float twinkle = 0.6 + 0.4 * sin(time * 2.3 + h.x * 43.0);
    float horizon = smoothstep(-0.02, 0.22, rd.y);
    return star * twinkle * horizon * (0.35 + 5.0 * (0.10 - h.z));
}

vec3 atmMoon(vec3 rd, vec3 moonDir) {
    float d = dot(rd, moonDir);
    float disk = smoothstep(0.99955, 0.99985, d);
    // A soft crescent from a second, offset sphere.
    vec3 shadowDir = normalize(moonDir + vec3(0.0045, 0.0018, 0.0));
    float shadow = smoothstep(0.99950, 0.99980, dot(rd, shadowDir));
    float lit = clamp(disk - shadow * 0.82, 0.0, 1.0);
    float glow = pow(saturate(d), 2200.0) * 0.12;
    // Kept modest on purpose: a brighter disk survives the bloom chain as a
    // huge blocky white smear rather than a moon.
    return vec3(1.00, 0.97, 0.90) * (lit * 2.4 + glow);
}

// --- clouds ----------------------------------------------------------------

// Flat cloud deck projected onto the dome. Returns rgb premultiplied and alpha.
vec4 atmClouds(vec3 rd, vec3 sunDir, float time, float coverage, vec3 skyTint) {
    if (rd.y < 0.02) return vec4(0.0);
    // Project onto the cloud plane, then compress distance. Without the
    // compression the UVs explode towards the horizon and the noise aliases
    // into hard horizontal bands.
    vec2 uv = rd.xz / max(rd.y, 0.16);
    uv /= 1.0 + length(uv) * 0.055;
    vec2 p = uv * 0.85 + vec2(time * 0.006, time * 0.0035);

    float n = fbm2(p, 5);
    n += 0.35 * fbm2(p * 3.7 + vec2(2.1, 5.3), 3);
    n /= 1.35;

    float density = smoothstep(1.0 - coverage, 1.0 - coverage + 0.28, n);
    if (density <= 0.001) return vec4(0.0);

    // Fade the deck out towards the horizon so the projection never streaks.
    density *= smoothstep(0.03, 0.30, rd.y);

    // Fake self-shadowing: sample the field a little towards the sun.
    vec2 lightStep = normalize(sunDir.xz + vec2(1e-4)) * 0.10;
    float lit = fbm2(p + lightStep, 4);
    float shade = saturate(0.45 + 0.85 * (n - lit));

    float sunAmount = saturate(dot(rd, sunDir));
    vec3 bright = mix(vec3(1.02, 1.00, 0.97), vec3(1.25, 1.10, 0.92), pow(sunAmount, 6.0));
    vec3 dark = mix(vec3(0.42, 0.46, 0.55), skyTint * 2.0, 0.35);
    vec3 col = mix(dark, bright, shade);

    // Silver lining right around the sun.
    col += vec3(1.0, 0.85, 0.6) * pow(sunAmount, 24.0) * 0.6 * (1.0 - shade);

    float sunUp = saturate(sunDir.y * 4.0 + 0.15);
    col *= mix(0.035, 1.0, sunUp);

    return vec4(col, density * 0.92);
}

// --- full sky --------------------------------------------------------------

// Everything the background needs: scattering, sun, moon, stars, clouds.
vec3 atmSky(vec3 rd, vec3 sunDir, float sunIntensity, float time, float coverage) {
    // Below the horizon the scattering integral collapses to nearly nothing
    // because the ray hits the planet immediately. Anything the world geometry
    // doesn't cover should read as distant haze, so lift those directions back
    // towards the horizon colour instead of leaving a black band.
    vec3 sampleDir = rd;
    if (rd.y < 0.0) {
        sampleDir = normalize(vec3(rd.x, mix(0.0, 0.05, saturate(-rd.y * 6.0)), rd.z));
    }
    vec3 col = atmScatter(sampleDir, sunDir, sunIntensity, 16, 8);
    if (rd.y < 0.0) {
        // Darken gently with depth below the horizon so it reads as ground haze.
        col *= mix(1.0, 0.55, saturate(-rd.y * 4.0));
    }

    // Sun disk, softened as it approaches the horizon.
    float sunCos = dot(rd, sunDir);
    float disk = smoothstep(0.99965, 0.99990, sunCos);
    float haze = pow(saturate(sunCos), 900.0) * 0.5;
    col += vec3(1.0, 0.94, 0.84) * (disk * 32.0 + haze) * saturate(sunDir.y * 6.0 + 0.35);

    // Night side: stars and moon fade in as the sun sets.
    float night = saturate(-sunDir.y * 5.0 + 0.10);
    if (night > 0.001) {
        vec3 moonDir = normalize(vec3(-sunDir.x, -sunDir.y, -sunDir.z) * 0.85 + vec3(0.30, 0.42, 0.18));
        vec3 nightCol = vec3(0.0025, 0.0042, 0.0110);
        nightCol += vec3(0.85, 0.90, 1.0) * atmStars(rd, time) * 0.85;
        nightCol += atmMoon(rd, moonDir);
        // Faint milky band.
        float band = exp(-pow((dot(rd, normalize(vec3(0.55, 0.32, -0.77)))) * 3.0, 2.0));
        nightCol += vec3(0.020, 0.024, 0.038) * band * smoothstep(0.0, 0.3, rd.y);
        col += nightCol * night;
    }

    vec4 clouds = atmClouds(rd, sunDir, time, coverage, col);
    col = mix(col, clouds.rgb, clouds.a);

    return col;
}

#endif
