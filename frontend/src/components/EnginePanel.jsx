import { LayersIcon } from "./Icons";

const PASSES = [
  [
    "Duplicates",
    "Extra copies of a transaction ID are set aside before anything is paired.",
  ],
  [
    "Exact references",
    "Same ID on both sides: the amount is checked first, then the date.",
  ],
  [
    "Optimal pairing",
    "Different references: the cheapest one-to-one matching within ±0.50 and 3 days, solved per cluster with min-cost flow.",
  ],
  [
    "Split settlements",
    "One line that equals the exact sum of 2–4 lines on the other side.",
  ],
  ["Leftovers", "Whatever is still unpaired is missing on one side."],
];

export default function EnginePanel() {
  return (
    <section className="panel engine-panel" aria-labelledby="engine-passes">
      <header className="panel-head">
        <h2 id="engine-passes">
          <LayersIcon size={16} /> How each break was decided
        </h2>
      </header>
      <ol className="pass-list">
        {PASSES.map(([name, detail], index) => (
          <li key={name}>
            <span className="pass-index">{index + 1}</span>
            <div>
              <strong>{name}</strong>
              <p>{detail}</p>
            </div>
          </li>
        ))}
      </ol>
      <p className="panel-foot">
        Deterministic rules decide; people resolve. Every label keeps the
        evidence behind it, and nothing here moves money.
      </p>
    </section>
  );
}
