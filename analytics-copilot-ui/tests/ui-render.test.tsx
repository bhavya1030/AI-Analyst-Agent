import { render, screen } from "@testing-library/react";
import ChatWindow from "@/components/chat/ChatWindow";

test("renders chat window prompt and upload panel", () => {
  render(<ChatWindow />);

  expect(screen.getByText("Upload a dataset or ask a question to begin analysis.")).toBeInTheDocument();
  expect(screen.getByText("Upload a dataset")).toBeInTheDocument();
});
