/**
 * Reference implementation of the final x-client-transaction-id composition stage.
 *
 * Canonical crawler implementation: src/client/x_transaction.py
 * This JS file exists for parity checks during interface research.
 */

import { createHash } from "node:crypto";

const DEFAULT_RANDOM_KEYWORD = "obfiowerehiring";
const DEFAULT_ADDITIONAL_RANDOM_NUMBER = 3;

export function buildClientTransactionId({
  method,
  path,
  unixDeltaSeconds,
  randomByte,
  keyBytes,
  animationKey,
  randomKeyword = DEFAULT_RANDOM_KEYWORD,
  additionalRandomNumber = DEFAULT_ADDITIONAL_RANDOM_NUMBER,
}) {
  const timeBytes = [
    (unixDeltaSeconds >> 0) & 0xff,
    (unixDeltaSeconds >> 8) & 0xff,
    (unixDeltaSeconds >> 16) & 0xff,
    (unixDeltaSeconds >> 24) & 0xff,
  ];

  const digest = createHash("sha256")
    .update(`${method}!${path}!${unixDeltaSeconds}${randomKeyword}${animationKey}`)
    .digest();

  const payload = Buffer.from([
    ...keyBytes,
    ...timeBytes,
    ...Array.from(digest.subarray(0, 16)),
    additionalRandomNumber,
  ]);

  const obfuscated = Buffer.alloc(payload.length + 1);
  obfuscated[0] = randomByte & 0xff;
  for (let i = 0; i < payload.length; i += 1) {
    obfuscated[i + 1] = payload[i] ^ obfuscated[0];
  }
  return obfuscated.toString("base64").replace(/=+$/g, "");
}

export function getUnixDeltaSeconds(nowMs = Date.now()) {
  const baseSeconds = 1682924400;
  return Math.floor((nowMs - baseSeconds * 1000) / 1000);
}
