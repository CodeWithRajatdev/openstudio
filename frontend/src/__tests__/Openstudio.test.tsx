import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import App from "../App";

describe("Openstudio unified shell", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/projects")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (url.endsWith("/api/collections")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (url.endsWith("/api/export/fonts")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      })
    );
  });

  it("renders Openstudio Step 1 with both Word Search and Crossword options and switches cleanly", async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(screen.getByText("Openstudio")).toBeInTheDocument();
    expect(screen.getByTestId("studio-card-wordsearch")).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(screen.getByTestId("studio-card-crossword")).toHaveAttribute(
      "aria-pressed",
      "false"
    );

    await user.click(screen.getByTestId("studio-card-crossword"));
    expect(screen.getByTestId("studio-card-crossword")).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(screen.getByRole("heading", { name: /Project Library/i })).toBeInTheDocument();
  });
});
