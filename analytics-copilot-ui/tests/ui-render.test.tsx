import { render, screen } from "@testing-library/react";
import ChatWindow from "@/components/chat/ChatWindow";

test("renders chat window empty state and starter prompts", () => {
  render(<ChatWindow />);

  expect(screen.getByText("What would you like to analyze?")).toBeInTheDocument();
  expect(screen.getByText("Analyze India's GDP")).toBeInTheDocument();
});
