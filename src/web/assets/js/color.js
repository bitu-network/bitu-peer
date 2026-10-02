// file: src/web/assets/js/color.js
export const COLORS = [
    // "#8F00FF",
    // "#4B0082",
    "#0000FF",
    "#00ffff",
    "#00FF00",
    "#FFFF00",
    // "#FF7F00",
    "#FF0000",
    "#000000",
];

export function hexToRgb(hex) {
    const bigint = parseInt(hex.slice(1), 16);
    return [(bigint >> 16) & 255, (bigint >> 8) & 255, bigint & 255];
}

export function getColorAtRatio(ratio) {
    return getColorAtRatioFromSet(ratio);
}

export function getColorAtRatioFromSet(ratio, colors = COLORS) {
    if (colors.length === 1) return colors[0];
    const numSegments = colors.length - 1;
    let segment = Math.floor(ratio * numSegments);
    if (segment >= numSegments) segment = numSegments - 1;
    if (segment < 0) segment = 0;
    const segmentRatio = (ratio * numSegments) - segment;

    const c1 = hexToRgb(colors[segment]);
    const c2 = hexToRgb(colors[segment + 1]);

    const r = Math.round(c1[0] + (c2[0] - c1[0]) * segmentRatio);
    const g = Math.round(c1[1] + (c2[1] - c1[1]) * segmentRatio);
    const b = Math.round(c1[2] + (c2[2] - c1[2]) * segmentRatio);
    return `rgb(${r},${g},${b})`;
}

export function getColorAtStep(i, blockCount, fn, colors) {
    const ratio = blockCount <= 1 ? 1 : 1 - (i / (blockCount - 1));
    return colors ? getColorAtRatioFromSet(ratio, colors) : fn(ratio);
}

function computeScientific(ratio, factor) {
    const wl = 380 + (270 * ratio);
    let r = 0, g = 0, b = 0;

    if (wl < 440) { r = -(wl - 440) / 60; b = 1.0; }
    else if (wl < 490) { g = (wl - 440) / 50; b = 1.0; }
    else if (wl < 510) { g = 1.0; b = -(wl - 510) / 20; }
    else if (wl < 580) { r = (wl - 510) / 70; g = 1.0; }
    else if (wl < 645) { r = 1.0; g = -(wl - 645) / 65; }
    else if (wl <= 650) { r = 1.0; }

    return `rgb(${Math.round(Math.max(0, Math.min(1, r * factor)) * 255)},${Math.round(Math.max(0, Math.min(1, g * factor)) * 255)},${Math.round(Math.max(0, Math.min(1, b * factor)) * 255)})`;
}

export function getColorAtRatioScientific(ratio) {
    const wl = 380 + (270 * ratio);
    let factor = 1.0;
    if (wl < 420) factor = 0.3 + 0.7 * (wl - 380) / 40;
    else if (wl > 630) factor = 0.3 + 0.7 * (650 - wl) / 20;
    return computeScientific(ratio, factor);
}

export function getColorAtRatioScientificTrimmed(ratio) {
    return computeScientific(ratio, 1.0);
}