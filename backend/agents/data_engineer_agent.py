from backend.utils.dataset_loader import load_dataset


def data_engineer_agent(state):

    print("DATA ENGINEER AGENT EXECUTING")

    question = (state.get("question") or "").lower()

    dataset_map = {

        "student": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/exercise.csv",
        "students": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/exercise.csv",

        "unemployment": "https://raw.githubusercontent.com/datasets/unemployment/master/data/unemployment.csv",

        "gdp": "https://raw.githubusercontent.com/datasets/gdp/master/data/gdp.csv",

        "population": "https://raw.githubusercontent.com/datasets/population/master/data/population.csv",

        "climate": "https://raw.githubusercontent.com/datasets/global-temp/master/data/annual.csv"
    }

    selected_url = None

    for keyword, url in dataset_map.items():

        if keyword in question:
            selected_url = url
            break

    if selected_url is None:

        state["error"] = "No matching dataset found."
        return state

    print("LOADING DATASET:", selected_url)

    try:

        df = load_dataset(selected_url)

        state["data"] = df
        state["dataset_url"] = selected_url
        state["rows"] = int(df.shape[0])
        state["columns"] = df.columns.tolist()
        state["dataset_topic"] = next(
            keyword for keyword, url in dataset_map.items()
            if url == selected_url
        )
        state["source"] = "fallback_dataset_loader"
        state.pop("error", None)

        print("DATASET LOADED SUCCESSFULLY")

    except Exception as e:

        state["error"] = f"Dataset loading failed: {str(e)}"
        state["data"] = None
        print("DATASET FAILED:", str(e))

    return state
