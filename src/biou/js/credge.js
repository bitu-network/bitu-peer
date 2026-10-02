// file: src/biou/js/credge.js
// description: the browser side of lib/edges.py. Builds the exact text a
// member signs for a trust statement. It must stay byte-for-byte identical to
// lib/edges.py's trust_message(): the server rejects anything that is not in
// canonical form.

export const TRUST_MAX = 255;

/** "ed25519:<hex>" (lowercase) from a pasted key -- bare 64-hex is taken as
 *  ed25519, like pod/users.py's parse_identity. null if it isn't a key. */
export function normalizeIdentity(text) {
    const t = text.trim();
    const i = t.lastIndexOf(":");
    const scheme = i === -1 ? "ed25519" : t.slice(0, i);
    const key = i === -1 ? t : t.slice(i + 1);
    if (scheme !== "ed25519" || !/^[0-9a-fA-F]{64}$/.test(key)) return null;
    return "ed25519:" + key.toLowerCase();
}

/** The text the issuer signs. `trust` is n (2^n bits) or null to withdraw. */
export function trustMessage(issuer, subject, trust, timestamp) {
    if (trust !== null && !(Number.isInteger(trust) && trust >= 0 && trust <= TRUST_MAX)) {
        throw new Error("trust must be a whole number from 0 to " + TRUST_MAX);
    }
    if (!Number.isSafeInteger(timestamp) || timestamp < 0) {
        throw new Error("invalid timestamp");
    }
    return [
        "bitu-trust",
        "issuer: " + issuer,
        "subject: " + subject,
        "trust: " + (trust === null ? "null" : trust),
        "timestamp: " + timestamp,
    ].join("\n");
}

const UNITS = ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"];

/** A trust value n (2^n bits) as a data size, 1 KB = 1024 bytes: n = 3 is
 *  "1 B", n = 13 is "1 KB", n = 23 is "1 MB", n = 33 is "1 GB". Below a byte
 *  it says bits; beyond YB it falls back to "2^n bits". */
export function sizeText(trust) {
    if (trust === null) return "no trust";
    if (trust < 3) return (1 << trust) + (trust === 0 ? " bit" : " bits");
    const byteExp = trust - 3;                   // 2^n bits = 2^(n-3) bytes
    const unit = Math.floor(byteExp / 10);
    if (unit >= UNITS.length) return "2^" + trust + " bits";
    return (1 << (byteExp % 10)) + " " + UNITS[unit];
}
