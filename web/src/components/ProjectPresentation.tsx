import content from "../data/maintenance-package.json";
import "./project-presentation.css";
const base = import.meta.env.BASE_URL;
export function DemoPreview() {
  return (
    <section className="card project-demo" aria-labelledby="demo-heading">
      <div>
        <p className="overline">See the workflow</p>
        <h2 id="demo-heading">
          Start with a template. Or build your own analysis.
        </h2>
        <p>Two real screen recordings, with English narration and captions.</p>
      </div>
      <div className="project-demo-grid">
        <article aria-labelledby="ecb-demo-heading">
          <h3 id="ecb-demo-heading">One ECB shock. Four country responses.</h3>
          <p>
            82 seconds · Run a template, compare responses and inspect
            uncertainty.
          </p>
          <video
            controls
            playsInline
            preload="none"
            poster={`${base}demo/macrolab-demo-poster.png?v=60063fb11ff1`}
            aria-label="MacroLab ECB template screen recording"
          >
            <source
              src={`${base}demo/macrolab-demo.mp4?v=60063fb11ff1`}
              type="video/mp4"
            />
            <track
              kind="captions"
              src={`${base}demo/captions-en.vtt`}
              srcLang="en"
              label="English captions"
            />
            <a href={`${base}demo/#ecb`}>Open the ECB demo and transcript</a>
          </video>
          <a href={`${base}demo/#ecb`}>
            Watch the ECB demo &amp; read the transcript ↗
          </a>
        </article>
        <article aria-labelledby="build-demo-heading">
          <h3 id="build-demo-heading">Build your own analysis.</h3>
          <p>
            67 seconds · Choose variables, a model and a country. Run and
            export.
          </p>
          <video
            controls
            playsInline
            preload="none"
            poster={`${base}demo/macrolab-build-poster.png?v=f559ad342e9b`}
            aria-label="MacroLab Build screen recording: custom linear and rolling regressions"
          >
            <source
              src={`${base}demo/macrolab-build-demo.mp4?v=f559ad342e9b`}
              type="video/mp4"
            />
            <track
              kind="captions"
              src={`${base}demo/build-captions-en.vtt`}
              srcLang="en"
              label="English captions"
            />
            <a href={`${base}demo/#build`}>
              Open the Build demo and transcript
            </a>
          </video>
          <a href={`${base}demo/#build`}>
            Watch the Build demo &amp; read the transcript ↗
          </a>
        </article>
      </div>
      <div className="row">
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
      <p className="overline">Experimental</p>
      <p className="project-beta-warning">
        <strong>{content.warningEnglish}</strong>
      </p>
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
