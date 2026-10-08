import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import EmptyState from "../components/EmptyState";
import PageHeader from "../components/PageHeader";
import StatCard from "../components/StatCard";
import StatusBadge from "../components/StatusBadge";

describe("shared components", () => {
  it.each(["Pending", "Reviewed", "Declined"])("StatusBadge shows %s", (status) => {
    render(<StatusBadge status={status} />);
    expect(screen.getByText(status)).toBeInTheDocument();
  });

  it("StatusBadge gives each status its own colour", () => {
    const { rerender } = render(<StatusBadge status="Pending" />);
    const pending = screen.getByText("Pending").className;
    rerender(<StatusBadge status="Declined" />);
    expect(screen.getByText("Declined").className).not.toBe(pending);
    rerender(<StatusBadge status="Something else" />);        // an unknown value must not crash
    expect(screen.getByText("Something else")).toBeInTheDocument();
  });

  it("PageHeader shows title, subtitle and actions", () => {
    render(<PageHeader title="My jobs" subtitle="Three postings" actions={<button>Post a job</button>} />);
    expect(screen.getByRole("heading", { name: "My jobs" })).toBeInTheDocument();
    expect(screen.getByText("Three postings")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Post a job" })).toBeInTheDocument();
  });

  it("PageHeader works with just a title", () => {
    render(<PageHeader title="Only a title" />);
    expect(screen.getByRole("heading", { name: "Only a title" })).toBeInTheDocument();
  });

  it("EmptyState explains and offers an action", () => {
    render(<EmptyState title="No jobs found" action={<button>Clear filters</button>}>Try a different search.</EmptyState>);
    expect(screen.getByRole("heading", { name: "No jobs found" })).toBeInTheDocument();
    expect(screen.getByText("Try a different search.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear filters" })).toBeInTheDocument();
  });

  it("StatCard shows zero as a number", () => {
    render(<StatCard id="zero" value={0} label="Nothing yet" />);
    expect(screen.getByTestId("stat-zero")).toHaveTextContent("0");
    expect(screen.getByTestId("stat-zero")).toHaveTextContent("Nothing yet");
  });
});
