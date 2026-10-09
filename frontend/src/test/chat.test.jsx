import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { STUDENT, mock, mockDashboard, mockMe, renderApp, storeSession } from "./helpers";

function open() {
  storeSession(STUDENT);
  mockMe(STUDENT);
  mockDashboard("student");
  renderApp("/");
}
const reply = (text, id = "conv-1", tool_calls = []) => [200, { reply: text, conversation_id: id, tool_calls }];
const body = (i = 0) => JSON.parse(mock.history.post.filter((r) => r.url === "/assistant/chat")[i].data);

describe("AI assistant chat window", () => {
  it("shows suggestions first, and a suggestion sends that question", async () => {
    const user = userEvent.setup();
    open();
    mock.onPost("/assistant/chat").reply(...reply("Here are some internships."));
    await user.click(await screen.findByRole("button", { name: "Find internships in my preferred cities" }));
    expect(await screen.findByText("Here are some internships.")).toBeInTheDocument();
    expect(screen.getByTestId("chat-user")).toHaveTextContent("Find internships in my preferred cities");
    expect(body()).toEqual({ message: "Find internships in my preferred cities", conversation_id: null });
  });

  it("sends with the Send button and with Enter, but not Shift+Enter", async () => {
    const user = userEvent.setup();
    open();
    mock.onPost("/assistant/chat").reply(...reply("ok"));
    const box = await screen.findByLabelText("Message to the assistant");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();            // nothing typed yet

    await user.type(box, "hello{Shift>}{Enter}{/Shift}there");
    expect(mock.history.post).toHaveLength(0);                                       // Shift+Enter = new line
    await user.type(box, "{Enter}");
    expect(await screen.findByTestId("chat-assistant")).toBeInTheDocument();
    expect(body().message).toBe("hello\nthere");
    expect(box).toHaveValue("");

    await user.type(box, "second");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findAllByTestId("chat-assistant");
    expect(mock.history.post).toHaveLength(2);
  });

  it("keeps the same conversation id for the next message and starts fresh on 'New conversation'", async () => {
    const user = userEvent.setup();
    open();
    mock.onPost("/assistant/chat").reply(...reply("answer", "conv-42"));
    const box = await screen.findByLabelText("Message to the assistant");
    await user.type(box, "one{Enter}");
    await screen.findByTestId("chat-assistant");
    await user.type(box, "two{Enter}");
    await screen.findAllByTestId("chat-assistant").then((a) => expect(a).toHaveLength(2));
    expect(body(0).conversation_id).toBeNull();
    expect(body(1).conversation_id).toBe("conv-42");

    await user.click(screen.getByRole("button", { name: "New conversation" }));
    expect(screen.queryByTestId("chat-user")).not.toBeInTheDocument();
    await user.type(box, "three{Enter}");
    await screen.findByTestId("chat-assistant");
    expect(body(2).conversation_id).toBeNull();
  });

  it("shows the tools the assistant used", async () => {
    const user = userEvent.setup();
    open();
    mock.onPost("/assistant/chat").reply(...reply("Found 3 jobs.", "c", [
      { name: "search_jobs", arguments: { city: "San Jose", category: "internship" }, result: "3 jobs" }]));
    await user.type(await screen.findByLabelText("Message to the assistant"), "jobs{Enter}");
    const bubble = await screen.findByTestId("chat-assistant");
    expect(within(bubble).getByText("Tools used (1)")).toBeInTheDocument();
    expect(within(bubble).getByText("search_jobs")).toBeInTheDocument();
    expect(within(bubble).getByText(/San Jose/)).toBeInTheDocument();
  });

  it("shows the assistant's words as plain text, never as HTML", async () => {
    const user = userEvent.setup();
    open();
    mock.onPost("/assistant/chat").reply(...reply('<img src=x onerror="alert(1)"><b>bold</b>'));
    await user.type(await screen.findByLabelText("Message to the assistant"), "hi{Enter}");
    const bubble = await screen.findByTestId("chat-assistant");
    expect(bubble).toHaveTextContent('<img src=x onerror="alert(1)"><b>bold</b>');
    expect(bubble.querySelector("img, b")).toBeNull();
  });

  it("shows a thinking message while waiting and blocks double sends", async () => {
    const user = userEvent.setup();
    open();
    let release;
    mock.onPost("/assistant/chat").reply(() => new Promise((res) => { release = () => res(reply("done")); }));
    const box = await screen.findByLabelText("Message to the assistant");
    await user.type(box, "slow{Enter}");
    expect(await screen.findByText("Assistant is thinking…")).toBeInTheDocument();
    expect(box).toBeDisabled();
    expect(mock.history.post).toHaveLength(1);
    release();
    expect(await screen.findByText("done")).toBeInTheDocument();
    expect(screen.queryByText("Assistant is thinking…")).not.toBeInTheDocument();
  });

  it("explains a failure and 'Try again' re-sends without repeating the user's message", async () => {
    const user = userEvent.setup();
    open();
    mock.onPost("/assistant/chat").replyOnce(500, {}).onPost("/assistant/chat").reply(...reply("second time works"));
    await user.type(await screen.findByLabelText("Message to the assistant"), "hello{Enter}");
    expect(await screen.findByText(/server had a problem/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("second time works")).toBeInTheDocument();
    expect(screen.getAllByTestId("chat-user")).toHaveLength(1);
    expect(body(1).message).toBe("hello");
    expect(screen.queryByText(/server had a problem/i)).not.toBeInTheDocument();
  });

  it("shows the server's message, e.g. when the assistant is off", async () => {
    const user = userEvent.setup();
    open();
    mock.onPost("/assistant/chat").reply(503, { detail: "The assistant is not running" });
    await user.type(await screen.findByLabelText("Message to the assistant"), "hello{Enter}");
    expect(await screen.findByText("The assistant is not running")).toBeInTheDocument();
  });

  it("waits up to two minutes for the model", async () => {
    const user = userEvent.setup();
    open();
    mock.onPost("/assistant/chat").reply(...reply("ok"));
    await user.type(await screen.findByLabelText("Message to the assistant"), "hello{Enter}");
    await screen.findByTestId("chat-assistant");
    expect(mock.history.post[0].timeout).toBe(120000);
  });
});
