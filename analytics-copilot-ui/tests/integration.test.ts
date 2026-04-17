import axios from "axios";

const baseURL = "http://localhost:8000";

jest.setTimeout(30000);

describe("backend integration", () => {
  test("backend responds to ask endpoint", async () => {
    const response = await axios.get(`${baseURL}/v1/ask`, {
      params: {
        question: "find dataset about gdp",
        session_id: "test-session",
      },
    });

    expect(response.status).toBe(200);
    expect(response.data.answer).toBeDefined();
  });

  test("backend returns charts when visualization requested", async () => {
    const response = await axios.get(`${baseURL}/v1/ask`, {
      params: {
        question: "show correlation heatmap",
        session_id: "test-session",
      },
    });

    expect(response.data.charts).toBeDefined();
  });

  test("forecast endpoint returns prediction data", async () => {
    const response = await axios.get(`${baseURL}/v1/ask`, {
      params: {
        question: "predict next 10 years",
        session_id: "test-session",
      },
    });

    expect(response.data.forecast).toBeDefined();
  });

  test("deep analysis returns hypotheses", async () => {
    const response = await axios.get(`${baseURL}/v1/ask`, {
      params: {
        question: "analyze dataset deeply",
        session_id: "test-session",
      },
    });

    expect(response.data.hypotheses).toBeDefined();
  });
});
