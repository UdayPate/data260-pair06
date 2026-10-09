import { useState } from "react";
import Card from "react-bootstrap/Card";
import ErrorAlert from "./ErrorAlert";
import Loading from "./Loading";
import { useAsync } from "../hooks/useAsync";
import { getActivity } from "../services/activityService";

// A GitHub-style calendar of the student's applications: 53 weeks (columns) by 7 days (rows,
// Sunday to Saturday), drawn with a plain CSS grid. The last column is the current week.
// The colour is only a hint: every square also carries its count as text (hover tooltip,
// screen-reader label, and the line under the grid when a square is tapped).

const WEEKS = 53;
const MS_PER_DAY = 24 * 60 * 60 * 1000;

const addDays = (date, n) => new Date(date.getFullYear(), date.getMonth(), date.getDate() + n);
const pad = (n) => String(n).padStart(2, "0");
// "2026-09-14" in the browser's own time zone (toISOString would shift the day for some users)
const toKey = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const formatDay = (d) => d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

// How dark a square is: 0, 1, 2 or 3 (3 means three or more applications)
const levelFor = (count) => Math.min(count, 3);

export function describeDay(count, date) {
  if (count === 0) return `No applications on ${formatDay(date)}`;
  return `${count} application${count === 1 ? "" : "s"} on ${formatDay(date)}`;
}

export default function ActivityHeatmap({ today = new Date() }) {
  // The calendar starts on the Sunday 52 weeks before this week's Sunday.
  const todayMidnight = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const start = addDays(todayMidnight, -todayMidnight.getDay() - (WEEKS - 1) * 7);
  const daysToLoad = Math.round((todayMidnight - start) / MS_PER_DAY) + 1; // start .. today, at most 371

  const { data, loading, error, reload } = useAsync(() => getActivity(daysToLoad), [daysToLoad]);
  const [selected, setSelected] = useState("");

  const counts = {};
  (data || []).forEach((item) => {
    counts[item.date] = item.count;
  });
  const total = Object.values(counts).reduce((sum, n) => sum + n, 0);

  // One entry per square, filled column by column (week 1: Sun..Sat, week 2: Sun..Sat, ...)
  const squares = Array.from({ length: WEEKS * 7 }, (_, i) => {
    const date = addDays(start, i);
    return { date, key: toKey(date), future: date > todayMidnight };
  });

  // A month name above the first week that belongs to a new month
  const months = Array.from({ length: WEEKS }, (_, week) => {
    const sunday = squares[week * 7].date;
    if (week === 0) return sunday.toLocaleDateString("en-US", { month: "short" });
    const previous = squares[(week - 1) * 7].date;
    return sunday.getMonth() !== previous.getMonth()
      ? sunday.toLocaleDateString("en-US", { month: "short" })
      : "";
  });
  if (months[0] && months[1]) months[0] = ""; // first month is too short to fit its name

  return (
    <Card className="mb-4" data-testid="activity-heatmap">
      <Card.Body>
        <div className="d-flex justify-content-between align-items-baseline flex-wrap mb-2">
          <h2 className="h6 mb-0">Application activity</h2>
          {data && (
            <span className="text-muted small" data-testid="heatmap-total">
              {total} application{total === 1 ? "" : "s"} since {formatDay(start)}
            </span>
          )}
        </div>

        {loading && <Loading label="Loading your activity…" />}
        <ErrorAlert message={error} onRetry={reload} />

        {data && (
          <>
            <div className="heatmap-scroll">
              <div className="heatmap">
                <div className="heatmap-weekdays" aria-hidden="true">
                  <span style={{ gridRow: 2 }}>Mon</span>
                  <span style={{ gridRow: 4 }}>Wed</span>
                  <span style={{ gridRow: 6 }}>Fri</span>
                </div>
                <div>
                  <div className="heatmap-months" aria-hidden="true">
                    {months.map((name, week) => (
                      <span key={week} style={{ gridColumn: week + 1 }}>
                        {name}
                      </span>
                    ))}
                  </div>
                  <div className="heatmap-grid">
                    {squares.map(({ date, key, future }) => {
                      if (future) return <div key={key} className="heat-cell heat-future" aria-hidden="true" />;
                      const count = counts[key] || 0;
                      const text = describeDay(count, date);
                      return (
                        <div
                          key={key}
                          role="img"
                          aria-label={text}
                          title={text}
                          data-testid="heat-cell"
                          data-date={key}
                          className={`heat-cell heat-${levelFor(count)}`}
                          onClick={() => setSelected(text)}
                        />
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>

            <div className="d-flex justify-content-between align-items-center flex-wrap mt-2 small text-muted">
              <span aria-live="polite" data-testid="heatmap-selected">
                {selected || "Tap or hover a square to see the day"}
              </span>
              <span className="heatmap-legend d-inline-flex align-items-center" aria-hidden="true">
                Less
                {[0, 1, 2, 3].map((level) => (
                  <span key={level} className={`heat-cell heat-${level}`} />
                ))}
                More
              </span>
            </div>
          </>
        )}
      </Card.Body>
    </Card>
  );
}
