from langchain_experimental.agents import create_pandas_dataframe_agent
from langchain_openai import ChatOpenAI


def qa_agent(state):
    df = state["data"]
    question = state["question"]

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    agent = create_pandas_dataframe_agent(
        llm,
        df,
        verbose=True,
        allow_dangerous_code=True
    )

    response = agent.invoke(question)

    state["answer"] = response["output"]

    return state