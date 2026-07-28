import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import {
  generateNebiusAttackScenario,
  injectNebiusAttackScenario
} from "@/api/client";
import { TeamMark } from "@/components/TeamMark";
import { controlCenterIncidentPath, storeControlCenterIncident } from "@/controlCenterIncident";
import type {
  AttackScenario,
  AttackScenarioInput
} from "@/features/nebius/types";
import type { Incident } from "@/types/arena";
import { arenaScenarioLabels, arenaScenarioTypes } from "@/scenarios";

const initialAttackInput: AttackScenarioInput = {
  attackDuration: "Medium",
  attackType: arenaScenarioLabels.spoofing_like_wall,
  detectorDifficulty: "Medium",
  marketCondition: "Thin liquidity",
  objective: "Buy cheaper",
  redTeamAgentCount: 1,
  stealthLevel: "Medium"
};

const attackTypes: AttackScenarioInput["attackType"][] = arenaScenarioTypes.map((type) => arenaScenarioLabels[type]);
const durations: AttackScenarioInput["attackDuration"][] = ["Short", "Medium", "Long"];

type ReusableScenarioTemplate = {
  attackInput: Partial<AttackScenarioInput>;
  duration: string;
  key: string;
  title: string;
};

const reusableScenarioTemplates: ReusableScenarioTemplate[] = [
  {
    attackInput: { attackType: arenaScenarioLabels.spoofing_like_wall, detectorDifficulty: "Medium", marketCondition: "Thin liquidity", stealthLevel: "Medium" },
    duration: "Medium",
    key: "spoofing_like_wall",
    title: arenaScenarioLabels.spoofing_like_wall
  },
  {
    attackInput: { attackType: arenaScenarioLabels.layering_like, detectorDifficulty: "Hard", marketCondition: "High volatility", stealthLevel: "Subtle" },
    duration: "Long",
    key: "layering_like",
    title: arenaScenarioLabels.layering_like
  },
  {
    attackInput: { attackType: arenaScenarioLabels.liquidity_evaporation, detectorDifficulty: "Hard", marketCondition: "Normal liquidity", objective: "Test detector weakness" },
    duration: "Medium",
    key: "liquidity_evaporation",
    title: arenaScenarioLabels.liquidity_evaporation
  },
  {
    attackInput: { attackType: arenaScenarioLabels.quote_stuffing, detectorDifficulty: "Medium", marketCondition: "Low activity period", stealthLevel: "Obvious" },
    duration: "Short",
    key: "quote_stuffing",
    title: arenaScenarioLabels.quote_stuffing
  }
];

export function AttackScenarioGeneratorPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const appliedDemoScenarioRef = useRef<string | null>(null);
  const [attackInput, setAttackInput] = useState<AttackScenarioInput>(initialAttackInput);
  const [attackScenario, setAttackScenario] = useState<AttackScenario | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const demoScenario = searchParams.get("demoScenario");
    const attackKey = searchParams.get("attack");
    if (!demoScenario || appliedDemoScenarioRef.current === demoScenario) return;
    const template = reusableScenarioTemplates.find((item) => item.key === attackKey) ?? reusableScenarioTemplates[0];
    appliedDemoScenarioRef.current = demoScenario;
    applyScenarioTemplate(template);
    setMessage(`${template.title} demo scenario loaded. Start here, then continue to Arena and Nebius AI.`);
  }, [searchParams]);

  function applyScenarioTemplate(template: ReusableScenarioTemplate) {
    setAttackInput((current) => ({
      ...current,
      ...template.attackInput,
      attackDuration: template.duration as AttackScenarioInput["attackDuration"]
    }));
    setMessage(`${template.title} template loaded. Generate the scenario, then run it in Arena.`);
  }


  async function runAction(action: () => Promise<void>) {
    setBusy(true);
    try {
      await action();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Attack scenario action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function generateAttack() {
    const scenario = await generateNebiusAttackScenario(attackInput);
    setAttackScenario(scenario);
    setMessage(`${scenario.id} persisted and ready for live injection.`);
  }

  async function injectScenario() {
    if (!attackScenario) return;
    await injectNebiusAttackScenario(attackScenario.id);
    navigate(`/arena?replayScenario=${encodeURIComponent(attackScenario.id)}`);
  }

  function sendToInvestigation() {
    if (!attackScenario) return;
    const confidence = attackScenario.expectedDetectorDifficulty === "hard" ? 0.9 : attackScenario.expectedDetectorDifficulty === "medium" ? 0.78 : 0.62;
    const incident: Incident = {
      agent: attackScenario.redTeamAgents.join(", ") || "Scenario Generator",
      confidence,
      evidence: [
        { key: "market_regime", label: "Market regime", value: attackScenario.marketRegime },
        { key: "target_side", label: "Target side", value: attackScenario.targetSide },
        { key: "duration_ticks", label: "Duration", value: attackScenario.durationTicks, unit: "ticks" },
        { key: "expected_signals", label: "Expected signals", value: attackScenario.expectedSignals.join(", ") }
      ],
      explanation: `Generated ${attackScenario.attackType} scenario prepared for bounded Nebius investigation.`,
      id: `SCENARIO-${attackScenario.id}-${Date.now()}`,
      scenario_id: attackScenario.id,
      severity: confidence >= 0.85 ? "Critical" : confidence >= 0.7 ? "High" : "Medium",
      tick: attackScenario.startTick,
      title: attackScenario.name,
      type: attackScenario.attackType
    };
    storeControlCenterIncident(incident);
    navigate(controlCenterIncidentPath(incident));
  }

  return (
    <section className="attack-scenario-page">
      <div className="panel lab-hero-panel team-hero red">
        <TeamMark team="red" />
        <div>
          <h2>Nebius AI Scenario Generator</h2>
        </div>
      </div>

      {message ? <div className="empty-state">{message}</div> : null}

      <div className="scenario-wizard panel">
        <div className="scenario-wizard-header">
          <div>
            <h2>Scenario Setup</h2>
          </div>
        </div>

        <section className="scenario-wizard-step">
          <div className="scenario-step-heading">
            <span>1</span>
            <div>
              <h3>Demo scenario</h3>
            </div>
          </div>
          <div className="scenario-control-grid">
            <Select label="Manipulation type" value={attackInput.attackType} options={attackTypes} onChange={(attackType) => setAttackInput({ ...attackInput, attackType: attackType as AttackScenarioInput["attackType"] })} />
            <Select label="Difficulty" value={attackInput.detectorDifficulty} options={["Easy", "Medium", "Hard"]} onChange={(detectorDifficulty) => setAttackInput({ ...attackInput, detectorDifficulty: detectorDifficulty as AttackScenarioInput["detectorDifficulty"] })} />
            <Select label="Duration" value={attackInput.attackDuration} options={durations} onChange={(attackDuration) => setAttackInput({ ...attackInput, attackDuration: attackDuration as AttackScenarioInput["attackDuration"] })} />
          </div>
        </section>

        <section className="scenario-wizard-step">
          <div className="scenario-step-heading">
            <span>2</span>
            <div>
              <h3>Attack</h3>
            </div>
          </div>
          <div className="nebius-button-row">
            {!attackScenario ? (
              <button className="scenario-primary-action" onClick={() => void runAction(generateAttack)} type="button">Generate</button>
            ) : (
              <button className="scenario-primary-action" disabled={busy} onClick={() => void runAction(injectScenario)} type="button">Run in Arena</button>
            )}
            {attackScenario ? <button onClick={() => void runAction(generateAttack)} type="button">Generate New</button> : null}
            {attackScenario ? (
              <button className="primary-link-button" onClick={sendToInvestigation} type="button">
                Send to Nebius investigation
              </button>
            ) : (
              <button disabled type="button">Send to Nebius investigation</button>
            )}
          </div>
        </section>
      </div>
    </section>
  );
}


function Select({ label, onChange, options, value }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <label className="form-row">
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => <option key={option}>{option}</option>)}
      </select>
    </label>
  );
}
