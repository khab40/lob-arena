import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { launchAttackExperiment, type AttackExperimentRequest } from "@/api/client";
import { controlCenterIncidentPath, storeControlCenterIncident } from "@/controlCenterIncident";
import type { ArenaScenarioType } from "@/hooks/useArenaSource";
import { arenaScenarioLabels, arenaScenarioTypes } from "@/scenarios";
import type { Incident } from "@/types/arena";

type CancelStyle = "instant" | "gradual" | "partial";
type Difficulty = "Easy" | "Medium" | "Hard";
type NoiseCover = "none" | "low" | "high";

export function AttackBuilder({ onLaunchScenario }: { onLaunchScenario?: (type: ArenaScenarioType) => void }) {
  const navigate = useNavigate();
  const cancelStyle: CancelStyle = "instant";
  const [difficulty, setDifficulty] = useState<Difficulty>("Medium");
  const [distanceFromMidBps, setDistanceFromMidBps] = useState(12);
  const [lifetimeSeconds, setLifetimeSeconds] = useState(5);
  const [noiseCover, setNoiseCover] = useState<NoiseCover>("low");
  const [scenarioType, setScenarioType] = useState<ArenaScenarioType>("spoofing_like_wall");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [wallSizeMultiplier, setWallSizeMultiplier] = useState(8);

  const risk = useMemo(() => calculateRisk({
    cancelStyle,
    distanceFromMidBps,
    lifetimeSeconds,
    noiseCover,
    scenarioType,
    wallSizeMultiplier
  }), [cancelStyle, distanceFromMidBps, lifetimeSeconds, noiseCover, scenarioType, wallSizeMultiplier]);

  const request = useMemo<AttackExperimentRequest>(() => ({
    cancel_style: cancelStyle,
    distance_from_mid_bps: distanceFromMidBps,
    lifetime_seconds: lifetimeSeconds,
    noise_cover: noiseCover,
    predicted_detection_risk: risk.score,
    scenario_type: scenarioType,
    wall_size_multiplier: wallSizeMultiplier
  }), [cancelStyle, distanceFromMidBps, lifetimeSeconds, noiseCover, risk.score, scenarioType, wallSizeMultiplier]);

  async function handleLaunch() {
    if (onLaunchScenario) {
      onLaunchScenario(scenarioType);
      setStatusMessage(`Launched ${arenaScenarioLabels[scenarioType]} in Arena.`);
      return;
    }

    setIsSubmitting(true);
    setStatusMessage("Launching scenario in Arena...");
    try {
      const result = await launchAttackExperiment(request);
      setStatusMessage(`Launched ${scenarioType}. Experiment ${result.experiment_id} persisted.`);
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Launch failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleDifficultyChange(nextDifficulty: Difficulty) {
    setDifficulty(nextDifficulty);
    if (nextDifficulty === "Easy") {
      setWallSizeMultiplier(5);
      setDistanceFromMidBps(24);
      setNoiseCover("high");
      return;
    }
    if (nextDifficulty === "Hard") {
      setWallSizeMultiplier(12);
      setDistanceFromMidBps(8);
      setNoiseCover("none");
      return;
    }
    setWallSizeMultiplier(8);
    setDistanceFromMidBps(12);
    setNoiseCover("low");
  }

  function handleInvestigation() {
    const incident: Incident = {
      agent: "Arena Scenario Builder",
      confidence: risk.score,
      evidence: [
        { key: "wall_size_multiplier", label: "Wall size multiplier", value: wallSizeMultiplier, unit: "x" },
        { key: "distance_from_mid_bps", label: "Distance from mid", value: distanceFromMidBps, unit: "bps" },
        { key: "lifetime_seconds", label: "Order lifetime", value: lifetimeSeconds, unit: "seconds" },
        { key: "cancel_style", label: "Cancel style", value: cancelStyle },
        { key: "noise_cover", label: "Noise cover", value: noiseCover }
      ],
      explanation: risk.explanation,
      id: `ARENA-BUILDER-${Date.now()}`,
      severity: risk.score >= 0.85 ? "Critical" : risk.score >= 0.7 ? "High" : risk.score >= 0.5 ? "Medium" : "Low",
      title: `${arenaScenarioLabels[scenarioType]} investigation`,
      type: scenarioType
    };
    storeControlCenterIncident(incident);
    navigate(controlCenterIncidentPath(incident));
  }

  return (
    <section className="attack-builder">
      <div className="section-heading-row">
        <div>
          <h2>Scenario Setup</h2>
        </div>
        <span className={`risk-chip ${risk.label.toLowerCase()}`}>{risk.label} risk</span>
      </div>

      <div className="attack-builder-grid">
        <label className="form-row">
          Manipulation type
          <select value={scenarioType} onChange={(event) => setScenarioType(event.target.value as ArenaScenarioType)}>
            {arenaScenarioTypes.map((scenario) => <option key={scenario} value={scenario}>{arenaScenarioLabels[scenario]}</option>)}
          </select>
        </label>

        <label className="form-row">
          Difficulty
          <select value={difficulty} onChange={(event) => handleDifficultyChange(event.target.value as Difficulty)}>
            {["Easy", "Medium", "Hard"].map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>

        <label className="form-row">
          Duration
          <input
            max={15}
            min={1}
            onChange={(event) => setLifetimeSeconds(Number(event.target.value))}
            type="range"
            value={lifetimeSeconds}
          />
          <strong>{lifetimeSeconds}s</strong>
        </label>
      </div>

      <div className="attack-risk-panel">
        <div className="risk-meter-track">
          <div style={{ width: `${risk.score * 100}%` }} />
        </div>
        <p>{risk.explanation}</p>
      </div>

      <div className="attack-builder-actions">
        <button disabled={isSubmitting} type="button" onClick={() => void handleLaunch()}>
          Run scenario
        </button>
        <button className="primary-link-button" onClick={handleInvestigation} type="button">
          Send to Nebius investigation
        </button>
        {statusMessage ? <span>{statusMessage}</span> : null}
      </div>
    </section>
  );
}

function calculateRisk(config: {
  cancelStyle: CancelStyle;
  distanceFromMidBps: number;
  lifetimeSeconds: number;
  noiseCover: NoiseCover;
  scenarioType: ArenaScenarioType;
  wallSizeMultiplier: number;
}) {
  let score = 0.2;
  score += Math.min(config.wallSizeMultiplier / 20, 0.35);
  score += config.lifetimeSeconds <= 5 ? 0.18 : 0.08;
  score += config.distanceFromMidBps <= 15 ? 0.16 : config.distanceFromMidBps <= 30 ? 0.08 : 0.02;
  score += config.cancelStyle === "instant" ? 0.14 : config.cancelStyle === "partial" ? 0.08 : 0.04;
  score += config.noiseCover === "none" ? 0.1 : config.noiseCover === "low" ? 0.04 : -0.04;
  score += config.scenarioType === "quote_stuffing" ? 0.12 : 0;

  const boundedScore = Math.max(0.05, Math.min(0.99, score));
  const label = boundedScore >= 0.78 ? "High" : boundedScore >= 0.52 ? "Medium" : "Low";

  return {
    explanation: `${label} predicted detection risk (${boundedScore.toFixed(2)}). Larger walls, shorter lifetimes, closer placement, and instant cancellation increase detector confidence.`,
    label,
    score: boundedScore
  };
}
