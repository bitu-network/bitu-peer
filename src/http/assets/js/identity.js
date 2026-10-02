// file: src/http/assets/js/identity.js
// description: the member's identity in this browser: the Ed25519 keypair that
// login.html stores in IndexedDB (database "bitu", store "keys", key
// "identity"). Read-only here -- this module never creates a key, because a
// new key would not be the one the session was opened with.

const toHex = buf => [...new Uint8Array(buf)]
    .map(b => b.toString(16).padStart(2, "0")).join("");

function openDb() {
    return new Promise((resolve, reject) => {
        const req = indexedDB.open("bitu", 1);
        req.onupgradeneeded = () => req.result.createObjectStore("keys");
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
}

function getStored(db, key) {
    return new Promise((resolve, reject) => {
        const req = db.transaction("keys", "readonly").objectStore("keys").get(key);
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
}

/** { pair, identity } for this browser's key, or null if it has none. */
export async function loadIdentity() {
    const db = await openDb();
    try {
        const pair = await getStored(db, "identity");
        if (!pair) return null;
        const publicKey = toHex(await crypto.subtle.exportKey("raw", pair.publicKey));
        return { pair, identity: "ed25519:" + publicKey };
    } finally {
        db.close();
    }
}

/** Ed25519 signature (hex) of `text` as UTF-8 -- what the server verifies. */
export async function sign(pair, text) {
    return toHex(await crypto.subtle.sign(
        "Ed25519", pair.privateKey, new TextEncoder().encode(text)));
}
