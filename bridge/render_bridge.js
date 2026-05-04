import { fetchBeatmapFile } from "../osumania_map_analyser/ManiaMapAnalyser by Leo_Black/js/app/analysis.js";
import { state } from "../osumania_map_analyser/ManiaMapAnalyser by Leo_Black/js/app/appContext.js";
import { startGraphAnimationLoop } from "../osumania_map_analyser/ManiaMapAnalyser by Leo_Black/js/app/graph.js";
import {
    hideOverlay,
    setStatus,
    updateCardPlayVisibility,
    updateModeTagVisibility,
    updatePauseCountVisibility,
} from "../osumania_map_analyser/ManiaMapAnalyser by Leo_Black/js/app/hud.js";
import { setRecomputeHandler } from "../osumania_map_analyser/ManiaMapAnalyser by Leo_Black/js/app/scheduler.js";
import {
    applyAzusaSunnyReferenceHoSetting,
    applyCardBlurSetting,
    applyCardOpacitySetting,
    applyCardRadiusSetting,
    applyCompanellaEtternaVersionSetting,
    applyContentBarSetting,
    applyDebugUseAmountSetting,
    applyDebugUseSvDetectionSetting,
    applyDiffTextSetting,
    applyEnableEtternaRainbowBarsSetting,
    applyEnableNumericDifficultySetting,
    applyEnableStatusMarqueeSetting,
    applyEnableUpdateCheckSetting,
    applyEstimatorAlgorithmSetting,
    applyEtternaVersionSetting,
    applyHideCardDuringPlaySetting,
    applyPauseDetectionSetting,
    applyReverseCardExtendDirectionSetting,
    applyShowModeTagCapsuleSetting,
    applySrTextSetting,
    applyVibroDetectionSetting,
    applyWsEndpointSetting,
} from "../osumania_map_analyser/ManiaMapAnalyser by Leo_Black/js/app/settings.js";

const DEFAULT_SETTINGS = Object.freeze({
    contentBar: "Auto",
    srText: "Auto",
    diffText: "Difficulty",
    estimatorAlgorithm: "Mixed",
    etternaVersion: "0.72.3",
    companellaEtternaVersion: "0.74.0",
    enableNumericDifficulty: true,
    enableEtternaRainbowBars: true,
    enableStatusMarquee: true,
    showModeTagCapsule: true,
    vibroDetection: true,
    debugUseAmount: false,
    debugUseSvDetection: false,
    azusaSunnyReferenceHo: true,
    cardOpacity: "95%",
    cardBlur: "Soft",
    cardRadius: "Medium",
    wsEndpoint: "127.0.0.1:24050",
});

const DEFAULT_RUNTIME = Object.freeze({
    speedRate: 1.0,
    odFlag: null,
    cvtFlag: null,
    modSignature: "1.00000|none|none",
});

function ensurePayload() {
    const payload = window.__MA_RENDER_PAYLOAD;
    if (!payload || typeof payload !== "object") {
        throw new Error("Missing render payload.");
    }

    const osuText = typeof payload.osuText === "string" ? payload.osuText : "";
    if (!osuText.trim()) {
        throw new Error("Payload does not contain beatmap text.");
    }

    return {
        osuText,
        settings: {
            ...DEFAULT_SETTINGS,
            ...(payload.settings && typeof payload.settings === "object" ? payload.settings : {}),
        },
        runtime: {
            ...DEFAULT_RUNTIME,
            ...(payload.runtime && typeof payload.runtime === "object" ? payload.runtime : {}),
        },
        postRenderDelayMs: Number(payload.postRenderDelayMs) || 700,
    };
}

function installBeatmapFetchBridge(osuText) {
    const originalFetch = window.fetch.bind(window);
    window.fetch = async (input, init) => {
        const url = typeof input === "string"
            ? input
            : (input && typeof input.url === "string" ? input.url : String(input));

        if (url.includes("/files/beatmap/file")) {
            return new Response(osuText, {
                status: 200,
                headers: {
                    "Content-Type": "text/plain; charset=utf-8",
                },
            });
        }

        if (url.includes("/releases/latest")) {
            return new Response("{}", {
                status: 200,
                headers: {
                    "Content-Type": "application/json; charset=utf-8",
                },
            });
        }

        return originalFetch(input, init);
    };
}

function applyRenderSettings(settings) {
    applyWsEndpointSetting(settings.wsEndpoint);
    applyContentBarSetting(settings.contentBar);
    applySrTextSetting(settings.srText);
    applyDiffTextSetting(settings.diffText);
    applyEstimatorAlgorithmSetting(settings.estimatorAlgorithm);
    applyEtternaVersionSetting(settings.etternaVersion);
    applyCompanellaEtternaVersionSetting(settings.companellaEtternaVersion);
    applyEnableNumericDifficultySetting(settings.enableNumericDifficulty);
    applyEnableEtternaRainbowBarsSetting(settings.enableEtternaRainbowBars);
    applyEnableStatusMarqueeSetting(settings.enableStatusMarquee);
    applyShowModeTagCapsuleSetting(settings.showModeTagCapsule);
    applyVibroDetectionSetting(settings.vibroDetection);
    applyDebugUseAmountSetting(settings.debugUseAmount);
    applyDebugUseSvDetectionSetting(settings.debugUseSvDetection);
    applyAzusaSunnyReferenceHoSetting(settings.azusaSunnyReferenceHo);
    applyCardOpacitySetting(settings.cardOpacity);
    applyCardBlurSetting(settings.cardBlur);
    applyCardRadiusSetting(settings.cardRadius);
    applyPauseDetectionSetting(false);
    applyHideCardDuringPlaySetting(false);
    applyReverseCardExtendDirectionSetting(false);
    applyEnableUpdateCheckSetting(false);
}

function applyRenderRuntime(runtime) {
    const speedRate = Number(runtime.speedRate);
    state.speedRate = Number.isFinite(speedRate) && speedRate > 0 ? speedRate : 1.0;

    const odFlag = runtime.odFlag;
    state.odFlag = odFlag == null ? null : String(odFlag).trim() || null;

    const cvtFlag = runtime.cvtFlag;
    state.cvtFlag = cvtFlag == null ? null : String(cvtFlag).trim().toUpperCase() || null;

    const signature = typeof runtime.modSignature === "string" ? runtime.modSignature.trim() : "";
    state.modSignature = signature || `${state.speedRate.toFixed(5)}|${state.odFlag || "none"}|${state.cvtFlag || "none"}`;
}

async function waitForRenderSettled(maxWaitMs, settleDelayMs) {
    const startedAt = Date.now();
    while (Date.now() - startedAt < maxWaitMs) {
        if (state.recalcTimerId == null && state.statusKind !== "loading") {
            await new Promise((resolve) => {
                window.setTimeout(resolve, settleDelayMs);
            });
            return;
        }
        await new Promise((resolve) => {
            window.setTimeout(resolve, 50);
        });
    }
}

async function renderFromPayload() {
    const payload = ensurePayload();
    installBeatmapFetchBridge(payload.osuText);
    applyRenderSettings(payload.settings);
    applyRenderRuntime(payload.runtime);
    setRecomputeHandler(fetchBeatmapFile);

    state.clientStateName = "";
    updateModeTagVisibility();
    updatePauseCountVisibility();
    updateCardPlayVisibility();
    hideOverlay();
    startGraphAnimationLoop();

    await fetchBeatmapFile("render bridge");
    await waitForRenderSettled(6000, payload.postRenderDelayMs);

    window.__MA_RENDER_STATUS_TEXT = state.statusText || "";
    window.__MA_RENDER_STATUS_KIND = state.statusKind || "";
    if (state.statusKind === "error") {
        window.__MA_RENDER_ERROR = state.statusText || "Unknown render error";
    } else {
        window.__MA_RENDER_ERROR = "";
    }
    window.__MA_RENDER_DONE = true;
}

window.__MA_RENDER_DONE = false;
window.__MA_RENDER_ERROR = "";
window.__MA_RENDER_STATUS_TEXT = "";
window.__MA_RENDER_STATUS_KIND = "";

renderFromPayload().catch((error) => {
    const message = error instanceof Error ? error.message : String(error);
    setStatus(`Render bridge failed: ${message}`, "error");
    window.__MA_RENDER_ERROR = message;
    window.__MA_RENDER_STATUS_TEXT = state.statusText || message;
    window.__MA_RENDER_STATUS_KIND = "error";
    window.__MA_RENDER_DONE = true;
});
