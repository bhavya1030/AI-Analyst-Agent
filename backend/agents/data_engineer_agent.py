from backend.core.logger import get_logger
from backend.errors.error_types import DATASET_NOT_FOUND, DATASET_LOAD_FAILED
from backend.utils.dataset_loader import load_dataset

logger = get_logger(__name__)


def data_engineer_agent(state):
    logger.info(
        "Data engineer agent executing",
        extra={"action": "fetch_data", "question": state.get("question")},
    )

    question = (state.get("question") or "").lower()
    dataset_map = {
        "student": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/exercise.csv",
        "students": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/exercise.csv",
        "unemployment": "https://raw.githubusercontent.com/datasets/unemployment/master/data/unemployment.csv",
        "gdp": "https://raw.githubusercontent.com/datasets/gdp/master/data/gdp.csv",
        "population": "https://raw.githubusercontent.com/datasets/population/master/data/population.csv",
        "climate": "https://raw.githubusercontent.com/datasets/global-temp/master/data/annual.csv",
        "inflation": "https://raw.githubusercontent.com/datasets/inflation/master/data/inflation.csv",
        "temperature": "https://raw.githubusercontent.com/datasets/global-temp/master/data/annual.csv",
        "sales": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/tips.csv",  # placeholder
        "revenue": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/tips.csv",  # placeholder
        "stock": "https://raw.githubusercontent.com/datasets/stock-prices/master/data/stock-prices.csv",  # placeholder
        "energy": "https://raw.githubusercontent.com/datasets/co2-fossil-by-nation/master/global.csv",
        "covid": "https://raw.githubusercontent.com/datasets/covid-19/master/data/countries-aggregated.csv",  # placeholder
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
        state["error_type"] = DATASET_NOT_FOUND
        return state

    logger.info(
        "Loading dataset",
        extra={"action": "fetch_data", "dataset": selected_url},
    )

    try:
        df = load_dataset(selected_url)
        state["data"] = df
        state["dataset_url"] = selected_url
        state["rows"] = int(df.shape[0])
        state["columns"] = df.columns.tolist()
        state["dataset_topic"] = selected_topic or "dataset discovery"
        state["source"] = "dataset_discovery"
        state.pop("error", None)
        state["error_type"] = None
        logger.info(
            "Dataset loaded successfully",
            extra={"action": "fetch_data", "dataset": selected_url, "rows": int(df.shape[0])},
        )
    except Exception as e:
        state["error"] = f"Dataset loading failed: {str(e)}"
        state["error_type"] = DATASET_LOAD_FAILED
        state["data"] = None
        logger.error(
            "Dataset loading failed",
            extra={"action": "fetch_data", "dataset": selected_url, "error": str(e)},
        )

    return state
