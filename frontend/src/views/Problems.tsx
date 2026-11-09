import { useMemo } from "react";
import { useApp } from "../App";
import { href } from "../data";

const MAX = 200;
const ORDER = { error: 0, warning: 1, info: 2 } as const;

/** Errors and warnings under the canvas (the issues view has filters and every finding); a click selects the object. */
export function Problems() {
  const { ix, select } = useApp();
  const list = useMemo(() => ix.issues.filter((i) => i.severity !== "info").sort((a, b) => ORDER[a.severity] - ORDER[b.severity]), [ix]);
  const n = (s: string) => ix.issues.filter((i) => i.severity === s).length;
  return (
    <section className="problems" aria-label="Problems">
      <h2 className="panel-title">Problems <small>{n("error")} errors · {n("warning")} warnings · {n("info")} info · <a href="#/issues">all findings</a></small></h2>
      <ul>
        {list.slice(0, MAX).map((i) => {
          const o = i.objects[0] || "";
          const [type, ...id] = o.split(":");
          return (
            <li key={i.k}>
              <span className={`badge ${i.severity}`}>{i.severity}</span> <span className="muted">{i.rule}</span>{" "}
              {o ? <a href={href(type, id.join(":"))} onClick={() => select({ type, id: id.join(":") })}>{i.message}</a> : i.message}
            </li>);
        })}
        {!list.length ? <li className="muted">No errors or warnings.</li> : null}
        {list.length > MAX ? <li className="muted">{list.length - MAX} more in <a href="#/issues">Issues</a></li> : null}
      </ul>
    </section>
  );
}
