/**
 * Chrome MCP analysis helper for x-client-transaction-id dependencies.
 * This file is for interface research and repeatable diagnostics.
 */

const ONDEMAND_REGEX = /["']ondemand\.s["']\s*:\s*["']([\w]+)["']/m;
const LOADING_ANIM_ID_REGEX = /id=["']loading-x-anim[^"']*["']/g;
const TX_INDEX_REGEX = /(\(\w\[(\d{1,2})\],\s*16\))+/g;

export function analyzeTransactionInputs(homeHtml, ondemandScript) {
  const ondemandMatch = ONDEMAND_REGEX.exec(homeHtml ?? "");
  const loadingAnimMatches = (homeHtml ?? "").match(LOADING_ANIM_ID_REGEX) ?? [];

  const indexCandidates = [];
  for (const match of (ondemandScript ?? "").matchAll(TX_INDEX_REGEX)) {
    indexCandidates.push(Number(match[2]));
  }

  const siteVerificationMatch = /meta[^>]+name=["']twitter-site-verification["'][^>]+content=["']([^"']+)["']/i.exec(
    homeHtml ?? "",
  );

  return {
    hasSiteVerification: Boolean(siteVerificationMatch?.[1]),
    siteVerificationLength: siteVerificationMatch?.[1]?.length ?? 0,
    ondemandHash: ondemandMatch?.[1] ?? "",
    loadingAnimFrameCount: loadingAnimMatches.length,
    txIndexCandidateCount: indexCandidates.length,
    txIndexCandidates: indexCandidates,
  };
}
