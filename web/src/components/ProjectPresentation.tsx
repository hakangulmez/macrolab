import content from "../data/maintenance-package.json";
import "./project-presentation.css";
const base = import.meta.env.BASE_URL;
export function DemoPreview() {
  return (
    <section className="card project-demo" aria-labelledby="demo-heading">
      <div>
        <p className="overline">See the workflow</p>
        <h2 id="demo-heading">
          From a template to a response and its uncertainty.
        </h2>
        <p>
          Open the existing ECB-shock template, run it, and read the response
          with its confidence band. A real screen recording, without a new model
          or method.
        </p>
      </div>
      <video
        controls
        playsInline
        preload="none"
        poster={`${base}demo/macrolab-demo-poster.png`}
        aria-label="MacroLab screen recording: template, model run, response and confidence interval"
      >
        <source src={`${base}demo/macrolab-demo.webm`} type="video/webm" />
        <track
          kind="captions"
          src={`${base}demo/captions-en.vtt`}
          srcLang="en"
          label="English captions"
          default
        />
        <a href={`${base}demo/`}>Open the demo and transcript</a>
      </video>
      <div className="row">
        <a href={`${base}demo/`}>Watch the demo &amp; read the transcript ↗</a>
        <a href={`${base}case-study/`}>Read the one-page case study ↗</a>
      </div>
    </section>
  );
}
export function ExperimentalReportsNotice({
  compact = false,
}: {
  compact?: boolean;
}) {
  return (
    <aside
      className="card project-experimental"
      aria-label="Experimental report-search limitations"
      data-testid="experimental-notice"
    >
      <p className="overline">Deneysel / Experimental</p>
      <p className="project-beta-warning" lang="tr">
        <strong>{content.warning}</strong>
      </p>
      <p>{content.warningEnglish}</p>
      {compact ? (
        <p>
          Search original report passages as research leads. Check their date,
          instrument and claim against the official source.
        </p>
      ) : (
        <>
          <ul>
            {content.limitations.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <p className="small">{content.evaluationScope}</p>
        </>
      )}
      <div className="row">
        {compact && <a href="#reports">Open experimental report search ↗</a>}
        <a href={`${base}publication/`}>
          Published evaluation record &amp; limits ↗
        </a>
      </div>
    </aside>
  );
}
