const researchLinks = [
  {
    title: "ABIDES: Towards High-Fidelity Market Simulation for AI Research",
    source: "arXiv:1904.12066",
    url: "https://arxiv.org/abs/1904.12066"
  },
  {
    title: "Spoofing the Limit Order Book: An Agent-Based Model",
    source: "AAMAS 2017 / IFAAMAS",
    url: "https://www.ifaamas.org/Proceedings/aamas2017/pdfs/p651.pdf"
  },
  {
    title: "Get Real: Realism Metrics for Robust Limit Order Book Market Simulations",
    source: "arXiv:1912.04941",
    url: "https://arxiv.org/abs/1912.04941"
  },
  {
    title: "Learning to simulate realistic limit order book markets from data as a World Agent",
    source: "arXiv:2210.09897",
    url: "https://arxiv.org/abs/2210.09897"
  },
  {
    title: "TRADES: Generating Realistic Market Simulations with Diffusion Models",
    source: "arXiv:2502.07071",
    url: "https://arxiv.org/abs/2502.07071"
  },
  {
    title: "Simulating Financial Market via Large Language Model based Agents",
    source: "arXiv:2406.19966",
    url: "https://arxiv.org/abs/2406.19966"
  }
];

export function AboutPage() {
  return (
    <section className="about-page">
      <div className="panel about-hero-panel">
        <h2>Governed Historical + Synthetic Order-Book Validation for Market Surveillance</h2>
        <p>
          A research and validation platform that replays licensed historical order-book data, injects
          controlled synthetic attacks, and benchmarks surveillance detectors against reproducible ground
          truth.
        </p>
      </div>

      <div className="about-grid">
        <section className="panel about-card">
          <span className="about-section-label">Training Narrative</span>
          <h3>Educational Story: Why These Attacks Matter</h3>
          <p>
            The demo can be read as a training story for market participants, engineers, and reviewers. It shows
            what abuse-like pressure looks like in a limit order book, how detectors collect evidence, and why even
            short synthetic incidents can damage confidence in a market.
          </p>
          <ul>
            <li><strong>Spoofing-like pressure:</strong> fake visible liquidity can make other participants believe supply or demand is stronger than it is.</li>
            <li><strong>Layering-like pressure:</strong> repeated stacked orders can distort the apparent shape of the book across several price levels.</li>
            <li><strong>Quote Stuffing Burst:</strong> rapid message flow can make the market harder to read and increase surveillance and infrastructure load.</li>
          </ul>
          <p>
            In the educational narrative, an attacker may seek illegal profit by inducing a price move, trading on the
            distorted price, and cancelling misleading orders before execution. The wider harm is larger than one
            trade: the exchange can look unreliable, liquidity providers may retreat, spreads can widen, and trust in
            the affected stock or crypto instrument can deteriorate.
          </p>
          <p>
            The purpose here is defensive literacy: recognize the pattern, preserve replay evidence, explain the
            detector decision, and compare surveillance quality under repeatable synthetic scenarios.
          </p>
        </section>

        <section className="panel about-card">
          <span className="about-section-label">Product Scope</span>
          <h3>What We Solve</h3>
          <p>
            The project makes order-book surveillance validation understandable across synthetic and locally
            licensed historical data. It lets a reviewer see the market move, launch synthetic patterns, inspect
            detector evidence, and compare detector quality through repeatable synthetic and hybrid batch runs.
          </p>
          <ul>
            <li>Live visual order book and market microstructure cockpit.</li>
            <li>Synthetic spoofing-like, layering-like, quote-stuffing, and liquidity-shock scenarios.</li>
            <li>Deterministic detector scores and evidence extraction.</li>
            <li>AI Investigator explanations grounded in compact replay evidence.</li>
            <li>Experiment benchmark and dataset jobs for serious evaluation artifacts.</li>
          </ul>
        </section>

        <section className="panel about-card">
          <span className="about-section-label">ML Framing</span>
          <h3>ML-Friendly Mental Model</h3>
          <ul>
            <li><strong>Market state:</strong> the order book is the feature stream, similar to a time-series sensor feed.</li>
            <li><strong>Red-team scenario:</strong> a controlled synthetic perturbation with known labels and expected signals.</li>
            <li><strong>Detection logic:</strong> a scoring function over recent book windows, event rates, imbalance, cancels, and price impact.</li>
            <li><strong>Incident evidence:</strong> the replay window, detector scores, labels, and agent events used to justify an alert.</li>
            <li><strong>AI Investigator:</strong> narrative summarization of evidence; the deterministic detector remains the source of the decision.</li>
            <li><strong>Batch benchmark:</strong> repeated scenario runs used to compare precision, recall, F1, latency, and artifact quality.</li>
          </ul>
        </section>

        <section className="panel about-card">
          <span className="about-section-label">Cloud Runtime</span>
          <h3>How Nebius Is Used</h3>
          <p>
            Nebius is split into Nebius AI inference and offline jobs. The browser never receives Nebius secrets; it
            calls the FastAPI backend, and the backend calls Nebius.
          </p>
          <ul>
            <li><strong>Nebius AI Serverless Endpoint:</strong> scores order-book windows and powers interactive AI calls.</li>
            <li><strong>Nebius AI Investigation Team:</strong> generates reports through the backend report adapter.</li>
            <li><strong>Nebius AI Scenario Generator:</strong> drafts bounded red-team scenarios through the backend adapter.</li>
            <li><strong>Nebius Serverless Jobs:</strong> run detector tournaments and generate labeled benchmark artifacts.</li>
          </ul>
        </section>

        <section className="panel about-card">
          <span className="about-section-label">Safety</span>
          <h3>Project Guardrails</h3>
          <ul>
            <li>Show the market first; explanations should be grounded in visible state.</li>
            <li>Keep red-team scenarios synthetic, bounded, and explicitly labeled.</li>
            <li>Separate live demo latency from batch benchmark workloads.</li>
            <li>Use deterministic detectors for evidence and AI Investigator only for explanation and narration.</li>
            <li>Preserve the disclaimer: no real manipulation detection, no trading signals, no compliance use.</li>
          </ul>
        </section>

        <section className="panel about-card">
          <span className="about-section-label">Operator Path</span>
          <h3>How To Run</h3>
          <ol>
            <li>Build and run the full local stack: <code>docker compose up --build</code>.</li>
            <li>Open the UI at <code>http://localhost:5173/arena</code>.</li>
            <li>Click <code>Start</code>, then launch a red-team scenario.</li>
            <li>When an incident appears, open Incident Details and run Nebius AI Investigation Team.</li>
            <li>Use Nebius AI Scenario Generator for concrete red-team plans that can be injected, expanded into grids, or submitted to Nebius batches.</li>
            <li>Use Detection for detector scores, suspicious agents, evidence, reports, replay windows, and Nebius AI Investigation Team review.</li>
            <li>Use Nebius AI for the full cloud workflow: scenario creation, Nebius Serverless Jobs, detector scoring, explanations, and artifact storage.</li>
          </ol>
          <p>
            In mock endpoint mode, Docker Compose runs the local serverless endpoint and the backend calls
            <code> http://endpoint:9000</code> inside the Docker network.
          </p>
        </section>
      </div>

      <section className="panel about-card architecture-card">
        <div className="section-heading-row">
          <h3>Architecture Diagram</h3>
        </div>
        <ArchitectureDiagram />
      </section>

      <div className="about-grid">
        <section className="panel about-card">
          <span className="about-section-label">Execution Flow</span>
          <h3>Pipeline</h3>
          <ol>
            <li>Generate or select a bounded synthetic attack scenario.</li>
            <li>Run the market simulation and emit order-book events, trades, snapshots, labels, and detector outputs.</li>
            <li>Score alerts with deterministic detectors over recent book windows.</li>
            <li>Persist replay evidence and compact alert context.</li>
            <li>Use Nebius AI for AI Investigator reports and Nebius jobs for batch experiments.</li>
            <li>Aggregate precision, recall, F1, latency, artifacts, and benchmark report output.</li>
          </ol>
        </section>

        <section className="panel about-card benchmark-summary-card">
          <span className="about-section-label">Evaluation</span>
          <h3>Benchmark Summary</h3>
          <p>Benchmarks compare detector performance across labeled synthetic scenarios and repeatable replay windows.</p>
          <div className="benchmark-summary-grid">
            <article>
              <span>Detection quality</span>
              <strong>Precision, recall, F1</strong>
              <p>How reliably the detector separates suspicious market behavior from normal liquidity.</p>
            </article>
            <article>
              <span>Error profile</span>
              <strong>False positives / negatives</strong>
              <p>Where the detector over-alerts or misses labeled manipulation windows.</p>
            </article>
            <article>
              <span>Operational cost</span>
              <strong>Latency, artifacts, reports</strong>
              <p>How quickly a run produces evidence, replay data, and report-ready outputs.</p>
            </article>
          </div>
        </section>

        <section className="panel about-card research-panel wide">
          <span className="about-section-label">Reading List</span>
          <h3>Research Papers</h3>
          <ul className="research-link-list">
          {researchLinks.map((item) => (
            <li key={item.title}>
              <a href={item.url} rel="noreferrer" target="_blank">
                <strong>{item.title}</strong>
                <span>{item.source}</span>
              </a>
            </li>
          ))}
          </ul>
        </section>
      </div>
    </section>
  );
}

function ArchitectureDiagram() {
  return (
    <svg
      aria-label="Architecture diagram showing browser, backend, identity, simulation runners, Nebius cloud, and evidence artifacts with directional arrows"
      className="architecture-flow-diagram"
      role="img"
      viewBox="0 0 1120 560"
    >
      <defs>
        <marker id="architecture-arrow" markerHeight="10" markerWidth="10" orient="auto" refX="9" refY="5">
          <path d="M0,0 L10,5 L0,10 Z" />
        </marker>
      </defs>

      <text className="architecture-lane-title" x="120" y="38">User Surface</text>
      <text className="architecture-lane-title" x="420" y="38">Backend Control Plane</text>
      <text className="architecture-lane-title" x="735" y="38">Compute</text>
      <text className="architecture-lane-title" x="980" y="38">Evidence</text>

      <g className="architecture-node">
        <rect height="128" width="230" x="36" y="72" />
        <text x="151" y="108">
          <tspan x="151">React / Vite UI</tspan>
          <tspan x="151" dy="24">Arena, Detection,</tspan>
          <tspan x="151" dy="24">Nebius AI, About</tspan>
          <tspan x="151" dy="24">Dashboard views</tspan>
        </text>
      </g>

      <g className="architecture-node">
        <rect height="132" width="252" x="360" y="70" />
        <text x="486" y="105">
          <tspan x="486">FastAPI Backend</tspan>
          <tspan x="486" dy="24">REST, WebSocket,</tspan>
          <tspan x="486" dy="24">runtime config, jobs,</tspan>
          <tspan x="486" dy="24">artifact collection</tspan>
        </text>
      </g>

      <g className="architecture-node architecture-secondary">
        <rect height="104" width="238" x="366" y="252" />
        <text x="485" y="286">
          <tspan x="485">Platform Identity</tspan>
          <tspan x="485" dy="24">workspace, roles,</tspan>
          <tspan x="485" dy="24">cases, audit trail</tspan>
        </text>
      </g>

      <g className="architecture-node">
        <rect height="120" width="242" x="690" y="72" />
        <text x="811" y="106">
          <tspan x="811">Local Simulation</tspan>
          <tspan x="811" dy="24">agent runners, order book,</tspan>
          <tspan x="811" dy="24">detectors, replay windows</tspan>
        </text>
      </g>

      <g className="architecture-node architecture-cloud">
        <rect height="132" width="254" x="686" y="250" />
        <text x="813" y="284">
          <tspan x="813">Nebius Serverless</tspan>
          <tspan x="813" dy="24">vLLM endpoint, AI reports,</tspan>
          <tspan x="813" dy="24">serverless jobs, object</tspan>
          <tspan x="813" dy="24">storage artifact sync</tspan>
        </text>
      </g>

      <g className="architecture-node architecture-evidence">
        <rect height="138" width="220" x="864" y="402" />
        <text x="974" y="438">
          <tspan x="974">Evidence Store</tspan>
          <tspan x="974" dy="24">events, snapshots,</tspan>
          <tspan x="974" dy="24">alerts, reports, metrics,</tspan>
          <tspan x="974" dy="24">benchmark outputs</tspan>
        </text>
      </g>

      <path className="architecture-edge" d="M266 136 L360 136" />
      <text className="architecture-edge-label" x="313" y="120">REST / WS</text>

      <path className="architecture-edge" d="M612 132 L690 132" />
      <text className="architecture-edge-label" x="651" y="116">run state</text>

      <path className="architecture-edge" d="M612 304 L686 304" />
      <text className="architecture-edge-label" x="649" y="288">jobs + AI calls</text>

      <path className="architecture-edge" d="M812 192 L812 250" />
      <text className="architecture-edge-label" x="812" y="224">detector evidence</text>

      <path className="architecture-edge architecture-edge-curved" d="M940 314 C1015 328 1032 370 1006 402" />
      <text className="architecture-edge-label" x="1010" y="354">cloud outputs</text>

      <path className="architecture-edge architecture-edge-curved" d="M812 382 C812 440 840 468 864 472" />
      <text className="architecture-edge-label" x="806" y="428">reports</text>

      <path className="architecture-edge architecture-edge-curved" d="M932 132 C1012 170 1038 295 1000 402" />
      <text className="architecture-edge-label" x="1014" y="240">local artifacts</text>

      <path className="architecture-edge architecture-edge-back" d="M864 506 C620 560 290 520 184 200" />
      <text className="architecture-edge-label" x="514" y="526">artifact links return to the UI</text>
    </svg>
  );
}
