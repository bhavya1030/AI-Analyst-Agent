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
        "climate": "https://raw.githubusercontent.com/datasets/global-temp/master/data/annual.csv",
        "inflation india": "https://raw.githubusercontent.com/datasets/inflation/master/data/inflation.csv",
        "co2 emissions": "https://raw.githubusercontent.com/datasets/co2-fossil-by-nation/master/global.csv",
        "world bank gdp": "https://raw.githubusercontent.com/datasets/gdp/master/data/gdp.csv",
        "world bank population": "https://raw.githubusercontent.com/datasets/population/master/data/population.csv",
        "data.gov employment": "https://raw.githubusercontent.com/datasets/unemployment/master/data/unemployment.csv",
        "github dataset": "https://raw.githubusercontent.com/datasets/gdp/master/data/gdp.csv",
    }

    selected_url = None
    selected_topic = None
    for keyword, url in dataset_map.items():
        if keyword in question:
            selected_url = url
            selected_topic = keyword
            break

    if selected_url is None:
        for keyword, url in dataset_map.items():
            if keyword.split()[0] in question:
                selected_url = url
                selected_topic = keyword
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
        state["dataset_topic"] = selected_topic or "dataset discovery"
        state["source"] = "dataset_discovery"
        state.pop("error", None)
        print("DATASET LOADED SUCCESSFULLY")
    except Exception as e:
        state["error"] = f"Dataset loading failed: {str(e)}"
        state["data"] = None
        print("DATASET FAILED:", str(e))

    return state
