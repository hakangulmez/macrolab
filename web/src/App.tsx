import { analysisErrorMessage, errorControl } from "./analysisErrors";
import { buildVersion, snapshotDate } from "./version";
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import type { ValidateFunction } from "ajv/dist/2020.js";
import {
  AnalysisRuntime,
  applicationURL,
  buildBundle,
  getCountry,
  getManifest,
} from "./runtime";
import type {
  AnalysisConfig,
  AnalysisResult,
  Check,
  CountryBundle,
  JsonRecord,
  Manifest,
  Model,
  Screen,
  Template,
} from "./types";
import { download, text } from "./format";
import { routeFromHash, screenHash } from "./navigation";
import {
  readRecentResults,
  rememberResult,
  type RecentResult,
} from "./recentResults";
import { RecentResults } from "./components/RecentResults";
import { Home, Library } from "./components/Explore";
import { PublicationNotice } from "./components/PublicationNotice";
import "./styles.css";
import "./ui-v3.css";
import "./navigation.css";
import { useTheme, setTheme } from "./theme";
import { SeriesSearch } from "./components/SeriesSearch";
const DatasetExplorer = lazy(() => import("./components/DatasetExplorer"));
const Builder = lazy(() =>
  import("./components/Builder").then((module) => ({
    default: module.Builder,
  })),
);
const loadResults = () => import("./components/Results");
const Results = lazy(() =>
  loadResults().then((module) => ({ default: module.Results })),
);
const Catalogue = lazy(() =>
  import("./components/ReferenceScreens").then((module) => ({
    default: module.Catalogue,
  })),
);
const Methods = lazy(() =>
  import("./components/ReferenceScreens").then((module) => ({
    default: module.Methods,
  })),
);
const NAV: [Screen, string][] = [
  ["home", "Explore"],
  ["data", "Data"],
  ["builder", "Build"],
];
export function App() {
  const theme = useTheme();
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [config, setRawConfig] = useState<AnalysisConfig | null>(null);
  const [catalogueSelection, setCatalogueSelection] = useState<{
    country?: string;
    search?: string;
    category?: string;
    region?: string;
  }>({});
  const [route, setRoute] = useState(
    () =>
      (typeof location !== "undefined" && routeFromHash(location.hash)) || {
        screen: "home" as Screen,
        methodsOpen: false,
      },
  );
  const { screen, methodsOpen } = route;
  const [recent, setRecent] = useState<RecentResult[]>([]);
  const [aboutAnchor, setAboutAnchor] = useState(() =>
    typeof location !== "undefined" &&
    routeFromHash(location.hash)?.screen === "methods"
      ? location.hash.slice(1)
      : "",
  );
  useEffect(() => {
    const followLocation = () => {
      const next = routeFromHash(location.hash);
      if (next) {
        setRoute(next);
        if (next.screen === "methods") setAboutAnchor(location.hash.slice(1));
      }
    };
    window.addEventListener("popstate", followLocation);
    window.addEventListener("hashchange", followLocation);
    return () => {
      window.removeEventListener("popstate", followLocation);
      window.removeEventListener("hashchange", followLocation);
    };
  }, []);
  const [bundles, setBundles] = useState<Record<string, CountryBundle>>({});
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [resultKnownChecks, setResultKnownChecks] = useState<Check[]>([]);
  const [compatible, setCompatible] = useState<Model[] | null>(null);
  const [checks, setChecks] = useState<Check[]>([]);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");
  const [runtimeStatus, setRuntimeStatus] = useState("idle");
  const [error, setError] = useState("");
  const [shareUrl, setShareUrl] = useState("");
  const validator = useRef<ValidateFunction<AnalysisConfig> | null>(null);
  const requestId = useRef(0);
  const [runtime] = useState(() => new AnalysisRuntime(setProgress));
  useEffect(() => {
    let active = true;
    void getManifest()
      .then(async (data) => {
        const m = data as unknown as Manifest;
        const schema = await fetch(applicationURL(data.schema_url)).then(
          (r) => {
            if (!r.ok) throw new Error("Configuration schema is unavailable.");
            return r.json();
          },
        );
        const { default: Ajv2020 } = await import("ajv/dist/2020.js");
        validator.current = new Ajv2020({
          strict: false,
        }).compile<AnalysisConfig>(schema);
        if (!active) return;
        setManifest(m);
        setRecent(
          readRecentResults((value) => Boolean(validator.current?.(value))),
        );
        const token = new URL(location.href).searchParams.get("c");
        let initial = m.templates.find(
          (t) => t.id === "monetary_policy",
        )!.config;
        if (token) {
          setBusy(true);
          try {
            initial = await runtime.decode(token);
            if (!validator.current(initial))
              throw new Error(
                "Shared configuration does not match the supported schema.",
              );
            if (active) {
              setRuntimeStatus("ready");
              setRoute({ screen: "builder", methodsOpen: false });
            }
          } finally {
            if (active) {
              setBusy(false);
              setProgress("");
            }
          }
        }
        if (active) setRawConfig(structuredClone(initial));
      })
      .catch((e: unknown) => {
        if (active) setError(analysisErrorMessage(e));
      });
    return () => {
      active = false;
      runtime.dispose();
    };
  }, [runtime]);
  useEffect(() => {
    if (screen !== "builder" || !manifest) return;
    let active = true;
    // The next analysis shares this initialization promise and the same worker.
    void runtime
      .prewarm()
      .then(() => {
        if (active) setRuntimeStatus("ready");
      })
      .catch((e: unknown) => {
        if (active) setRuntimeStatus("idle");
        if (active && String(e) !== "Error: Cancelled") {
          setError(
            `The local analysis engine could not be prepared. Run analysis to retry. ${analysisErrorMessage(e)}`,
          );
        }
      });
    // Fetch the charts while assumptions are being selected, before the result arrives.
    void loadResults().catch(() => undefined);
    return () => {
      active = false;
    };
  }, [screen, manifest, runtime]);
  useEffect(() => {
    if (!config) return;
    let active = true;
    void Promise.all(
      config.countries.map(async (iso) => ({
        iso,
        bundle: await getCountry(iso),
      })),
    )
      .then((values) => {
        if (active)
          setBundles((previous) => ({
            ...previous,
            ...Object.fromEntries(
              values.map((v) => [v.iso, v.bundle as unknown as CountryBundle]),
            ),
          }));
      })
      .catch((e: unknown) => {
        if (active) setError(analysisErrorMessage(e));
      });
    return () => {
      active = false;
    };
  }, [config]);
  function navigate(next: Screen) {
    const target = routeFromHash(screenHash(next))!;
    if (target.screen === "builder" && runtimeStatus !== "ready")
      setRuntimeStatus("preparing");
    setRoute(target);
    const url = new URL(location.href);
    url.hash = screenHash(next);
    if (url.href !== location.href) history.pushState(null, "", url);
    setError("");
    requestAnimationFrame(() =>
      document
        .getElementById(target.methodsOpen ? "browse-methods" : "main-content")
        ?.focus(),
    );
  }
  function openAbout(anchor = "") {
    setAboutAnchor(anchor);
    navigate("methods");
    requestAnimationFrame(() => {
      if (anchor)
        document.getElementById(anchor)?.scrollIntoView({ block: "start" });
    });
  }
  function openSource(country: string, conceptId: string) {
    setCatalogueSelection({ country, search: conceptId });
    navigate("catalogue");
  }
  function setConfig(next: AnalysisConfig) {
    if (busy) {
      requestId.current += 1;
      runtime.cancel();
      setResult(null);
      setRuntimeStatus("idle");
      setBusy(false);
      setProgress("");
    }
    setRawConfig(next);
    setCompatible(null);
    setChecks([]);
    setShareUrl("");
  }
  function validate(next: AnalysisConfig) {
    if (!validator.current?.(next))
      throw new Error(
        `Check the configuration fields: ${validator.current?.errors?.map((e) => `${e.instancePath} ${e.message}`).join("; ") ?? "schema unavailable"}`,
      );
  }
  const builderChecks: Check[] = config
    ? checks.length
      ? checks
      : config.series.flatMap((s) =>
          config.countries.flatMap((iso) => {
            const c = bundles[iso]?.cards.find(
              (i) => i.concept_id === s.concept_id,
            );
            return c && (c.status === "limited" || c.status === "missing")
              ? [
                  {
                    phase: "preflight",
                    level: c.status === "missing" ? "block" : "warn",
                    code:
                      c.status === "missing"
                        ? "missing_coverage"
                        : "limited_coverage",
                    message: `${c.title}: ${c.status === "missing" ? "No data are available for this selection." : "Coverage limitations may affect the usable sample."}`,
                    concept_id: c.concept_id,
                    flags: c.reason_codes,
                    country: iso,
                  },
                ]
              : [];
          }),
        )
    : [];
  async function execute(
    next: AnalysisConfig,
    compatibility = false,
    knownOverride?: Check[],
  ) {
    if (busy) return;
    const id = ++requestId.current;
    // Snapshot the exact pre-run disclosure separately from mutable Builder state.
    const knownChecks = structuredClone(knownOverride ?? builderChecks);
    setBusy(true);
    setError("");
    setProgress("Loading selected snapshot data…");
    try {
      validate(next);
      const bundle = await buildBundle(next);
      if (id !== requestId.current) return;
      setProgress(
        compatibility
          ? "Checking compatibility…"
          : "Estimating the model and sensitivity variants…",
      );
      if (compatibility) {
        const output = await runtime.compatibility(next, bundle);
        if (id !== requestId.current) return;
        const models = output.models as Model[];
        setRuntimeStatus("ready");
        setCompatible(models);
        setChecks(models.find((m) => m.id === next.model.id)?.checks ?? []);
      } else {
        const output = (await runtime.run(next, bundle, (partial) => {
          if (id !== requestId.current) return;
          setResult(partial as unknown as AnalysisResult);
          setResultKnownChecks(knownChecks);
          setShareUrl("");
          navigate("results");
        })) as unknown as AnalysisResult;
        if (id !== requestId.current) return;
        setRuntimeStatus("ready");
        setResult(output);
        setResultKnownChecks(knownChecks);
        setRawConfig(output.config);
        if (output.status !== "blocked" && output.status !== "error")
          setRecent((current) => rememberResult(current, output.config));
        setChecks(output.checks);
        setShareUrl("");
        navigate("results");
      }
    } catch (e: unknown) {
      if (id === requestId.current) {
        setResult((current) => (current?.sensitivity_pending ? null : current));
        setError(analysisErrorMessage(e));
      }
    } finally {
      if (id === requestId.current) {
        setBusy(false);
        setProgress("");
      }
    }
  }
  function reopenRecent(entry: RecentResult) {
    if (busy) return;
    const next = structuredClone(entry.config);
    try {
      validate(next);
      setConfig(next);
      setResult(null);
      navigate("builder");
      void execute(next, false, []);
    } catch (e: unknown) {
      setError(analysisErrorMessage(e));
    }
  }
  function select(t: Template) {
    setConfig(structuredClone(t.config));
    navigate("builder");
  }
  function selectModel(m: Model) {
    if (!config) return;
    const next = structuredClone(config);
    next.model = { id: m.id, params: {} };
    if (!["var.ols", "ident.recursive"].includes(m.id)) {
      next.identification = null;
      delete next.outputs.irf;
    } else if (m.id === "ident.recursive") {
      next.identification = {
        id: "recursive",
        params: {
          order: next.series
            .filter((s) => ["shock", "response", "endogenous"].includes(s.role))
            .map((s) => s.concept_id),
        },
      };
      next.outputs.irf ??= {
        horizon: 12,
        bands: 0.68,
        shock_mode: "one_sd",
        shock_size: 1,
        method: "bootstrap",
        draws: 500,
      };
    }
    setConfig(next);
    navigate("builder");
  }
  function applyFix(fix: JsonRecord) {
    if (!config) return;
    const next = structuredClone(config);
    if (fix.sample) Object.assign(next.sample, fix.sample);
    if (typeof fix.remove_series === "string") {
      next.series = next.series.filter(
        (series) => series.concept_id !== fix.remove_series,
      );
      delete next.aggregation[fix.remove_series];
      if (next.identification)
        next.identification.params.order =
          next.identification.params.order.filter(
            (id) => id !== fix.remove_series,
          );
    }
    if (fix.special_periods)
      Object.assign(next.special_periods, fix.special_periods);
    if (
      typeof fix.concept_id === "string" &&
      typeof fix.transform === "string"
    ) {
      const series = next.series.find((s) => s.concept_id === fix.concept_id);
      if (series) {
        series.transform = fix.transform;
        series.transform_params = {};
      }
    }
    setConfig(next);
  }
  async function share() {
    if (!result) return;
    setBusy(true);
    setError("");
    try {
      const token = await runtime.encode(result.config);
      const url = new URL(location.href);
      url.searchParams.set("c", token);
      url.hash = "builder";
      setShareUrl(url.href);
      try {
        await navigator.clipboard.writeText(url.href);
      } catch {
        /* Visible selectable link remains available. */
      }
    } catch (e: unknown) {
      setError(analysisErrorMessage(e));
    } finally {
      setBusy(false);
      setProgress("");
    }
  }
  async function exportPython() {
    if (!result) return;
    setBusy(true);
    setError("");
    setProgress("Preparing a standalone, local reproduction…");
    try {
      const bundle = await buildBundle(result.config);
      const script = await runtime.exportPython(result.config, bundle);
      download(script, "macrolab_analysis.py", "text/x-python");
    } catch (e: unknown) {
      setError(analysisErrorMessage(e));
    } finally {
      setBusy(false);
      setProgress("");
    }
  }
  function loadCountry(iso: string) {
    void getCountry(iso)
      .then((bundle) =>
        setBundles((previous) => ({
          ...previous,
          [iso]: bundle as unknown as CountryBundle,
        })),
      )
      .catch((e: unknown) => setError(analysisErrorMessage(e)));
  }
  function useSeries(country: string, concept: string) {
    if (!config) return;
    const next = structuredClone(config);
    next.countries = [country];
    next.series = [
      { concept_id: concept, role: "response", transform: "level" },
    ];
    next.aggregation = { [concept]: "mean" };
    next.model = { id: "desc.plot", params: {} };
    next.identification = null;
    next.outputs = {};
    next.comparison = { enabled: false };
    setConfig(next);
    navigate("builder");
  }
  const header = (
    <header className="site-header">
      <div className="header-inner">
        <button
          className="brand"
          onClick={() => navigate("home")}
          aria-label="MacroLab home"
        >
          <span className="brand-mark" aria-hidden="true">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M3 17l6-6 4 4 8-8M15 7h6v6" />
            </svg>
          </span>
          MacroLab
        </button>
        <nav className="site-nav" aria-label="Main navigation">
          {NAV.map(([id, label]) => (
            <button
              key={id}
              data-testid={`nav-${id}`}
              aria-current={screen === id ? "page" : undefined}
              onClick={() => navigate(id)}
            >
              {label}
            </button>
          ))}
        </nav>
        <SeriesSearch
          manifest={manifest}
          select={(cell) => {
            setCatalogueSelection({
              country: cell.country,
              search: cell.concept_id,
            });
            navigate("data");
          }}
        />
        <button
          className="theme-toggle"
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          aria-pressed={theme === "dark"}
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        >
          {theme === "dark" ? "Light" : "Dark"}
        </button>
        <button
          className="link header-about"
          data-testid="nav-methods"
          aria-current={screen === "methods" ? "page" : undefined}
          onClick={() => openAbout()}
        >
          About
        </button>
        <div className="snapshot">
          <span className="badge draft">
            {buildVersion} · Data snapshot {snapshotDate(manifest?.as_of_date)}
          </span>
        </div>
      </div>
    </header>
  );
  return (
    <>
      <a className="skip" href="#main-content">
        Skip to main content
      </a>
      {header}
      <main id="main-content" tabIndex={-1} data-runtime-status={runtimeStatus}>
        {manifest && (
          <PublicationNotice
            manifest={manifest}
            openMethods={() => navigate("methods")}
          />
        )}
        {error && (
          <div role="alert" className="error-box section">
            <strong>We couldn’t complete that action.</strong>
            <p>{error}</p>
            <button
              onClick={() => {
                const target = errorControl(error, config?.model.id);
                navigate("builder");
                requestAnimationFrame(() => {
                  const element = document.getElementById(target.id);
                  element?.scrollIntoView({ block: "center" });
                  (element?.matches("input, select, textarea")
                    ? element
                    : element?.querySelector<HTMLElement>(
                        "input, select, textarea, button",
                      )
                  )?.focus();
                });
              }}
            >
              {errorControl(error, config?.model.id).label}
            </button>
            <button onClick={() => setError("")}>Dismiss message</button>
          </div>
        )}
        <Suspense
          fallback={
            <section className="empty" role="status">
              Loading this screen locally…
            </section>
          }
        >
          {!manifest || !config ? (
            <section className="empty">
              <span className="overline">MacroLab</span>
              <h1>
                {error
                  ? "Local data could not be loaded"
                  : "Preparing your workspace"}
              </h1>
              <p>
                {error
                  ? "The review build requires its local snapshot and runtime assets."
                  : "Reading the accepted snapshot and validated model library."}
              </p>
            </section>
          ) : screen === "home" ? (
            <Home
              manifest={manifest}
              select={select}
              start={() => navigate("builder")}
              about={openAbout}
              recentResults={
                <RecentResults
                  entries={recent}
                  manifest={manifest}
                  busy={busy}
                  reopen={reopenRecent}
                />
              }
              catalogue={(selection = {}) => {
                setCatalogueSelection(selection);
                navigate("data");
              }}
            />
          ) : screen === "builder" ? (
            <Builder
              browseMethods={() => navigate("library")}
              methodsOpen={methodsOpen}
              methodBrowser={
                methodsOpen ? (
                  <section
                    id="browse-methods"
                    className="method-browser card stack"
                    tabIndex={-1}
                    aria-label="Browse methods"
                  >
                    <div className="row between">
                      <h2>Browse methods</h2>
                      <button onClick={() => navigate("builder")}>
                        Close method browser
                      </button>
                    </div>
                    <Library
                      manifest={manifest}
                      compatibility={compatible}
                      check={() => void execute(config, true)}
                      busy={busy}
                      selectModel={selectModel}
                      config={config}
                      embedded
                    />
                  </section>
                ) : null
              }
              recentResults={
                <RecentResults
                  entries={recent}
                  manifest={manifest}
                  busy={busy}
                  reopen={reopenRecent}
                />
              }
              openSource={openSource}
              manifest={manifest}
              config={config}
              setConfig={setConfig}
              bundles={bundles}
              models={compatible}
              checks={builderChecks}
              busy={busy}
              runtimeStatus={runtimeStatus}
              run={() => void execute(config)}
              check={() => void execute(config, true)}
              fix={applyFix}
            />
          ) : screen === "results" ? (
            <>
              <Results
                runtime={runtime}
                previouslyDisplayedChecks={resultKnownChecks}
                onSourceCard={openSource}
                bundles={bundles}
                result={result}
                manifest={manifest}
                busy={busy}
                rerun={(next) => void execute(next)}
                exportPython={() => void exportPython()}
                share={() => void share()}
                shareUrl={shareUrl}
                edit={() => navigate("builder")}
              />
              {!result && (
                <p className="empty-explore-link">
                  <button className="link" onClick={() => navigate("home")}>
                    Explore templates →
                  </button>
                </p>
              )}
            </>
          ) : screen === "data" ? (
            <DatasetExplorer
              key={JSON.stringify(catalogueSelection)}
              manifest={manifest}
              initialSelection={catalogueSelection}
              onUse={useSeries}
            />
          ) : screen === "catalogue" ? (
            <section data-testid="screen-catalogue">
              <Catalogue
                key={JSON.stringify(catalogueSelection)}
                initialSelection={catalogueSelection}
                manifest={manifest}
                countryBundles={bundles}
                loadCountry={loadCountry}
              />
            </section>
          ) : (
            <section data-testid="screen-methods">
              <Methods
                manifest={manifest}
                models={() => navigate("library")}
                anchor={aboutAnchor}
              />
            </section>
          )}
        </Suspense>
      </main>
      {busy && (
        <div className="runtime-banner" role="status">
          <progress aria-label="Analysis progress" />
          <span className="grow">{progress || "Working locally…"}</span>
          <button
            data-testid="cancel-analysis"
            onClick={() => {
              requestId.current++;
              runtime.cancel();
              setResult(null);
              setRuntimeStatus("idle");
              setBusy(false);
              setError(
                "Analysis cancelled. Incomplete sensitivity results were cleared. You can run again.",
              );
            }}
          >
            Cancel
          </button>
        </div>
      )}
      <footer>
        <span>
          MacroLab {buildVersion} · Runs entirely in your browser ·{" "}
          <a
            href="https://hakangulmez.github.io/"
            target="_blank"
            rel="noreferrer"
          >
            Hakan Zeki Gülmez
          </a>
        </span>
        <span>
          Snapshot {text(manifest?.snapshot_id, "loading")} · Country notes are
          not yet published
          <span className="footer-links">
            <button className="link" onClick={() => openAbout()}>
              About
            </button>
            <a
              href="https://github.com/hakangulmez/macrolab/blob/main/LICENSE"
              target="_blank"
              rel="noreferrer"
            >
              MIT code licence
            </a>
            <button className="link" onClick={() => openAbout("source-terms")}>
              Data terms
            </button>
            <a
              href="https://github.com/hakangulmez/macrolab"
              target="_blank"
              rel="noreferrer"
            >
              Source
            </a>
          </span>
        </span>
      </footer>
    </>
  );
}
