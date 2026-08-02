import os
import ast
import re

REPO_ROOT = r"C:\Users\abhis\projects\AI-Analyst-Agent"
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
TESTS_DIR = os.path.join(REPO_ROOT, "tests")

STATE_FIELDS = [
    "data", "cleaned", "insights", "question", "answer", "chart", "plan",
    "file_path", "dataset_url", "dataset_profile", "dataset_explanation",
    "recommended_next_steps", "detected_patterns", "dataset_topic",
    "last_column_used", "last_columns_used", "last_chart_type", "last_intent",
    "last_operation", "last_forecast_target", "chart_columns_used", "charts",
    "chart_explanation", "hypotheses", "related_datasets", "rows", "columns",
    "error", "stop", "needs_user_data", "data_acquisition_options",
    "dataset_discovery", "search_queries", "source", "local_path", "dataset_id",
    "dataset_metadata", "retrieval_result", "acquisition_result",
    "dataset_intelligence", "learning_result", "session_dataset_topic",
    "session_id", "user_id", "dataset_fingerprint", "memory",
    "conversation_memory", "dataset_memory", "knowledge_memory",
    "memory_hierarchy_loaded", "recent_messages", "conversation_summary",
    "preferred_columns", "preferred_chart_types"
]

def analyze_fields():
    read_counts = {f: 0 for f in STATE_FIELDS}
    write_counts = {f: 0 for f in STATE_FIELDS}
    file_references = {f: set() for f in STATE_FIELDS}

    all_files = []
    for d in [BACKEND_DIR, TESTS_DIR]:
        for root, dirs, files in os.walk(d):
            for file in files:
                if file.endswith('.py'):
                    all_files.append(os.path.join(root, file))

    for filepath in all_files:
        rel = os.path.relpath(filepath, REPO_ROOT)
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as fp:
            content = fp.read()

        for field in STATE_FIELDS:
            # check string patterns like state.get("field") or state["field"] or "field": ...
            p_read = r'state\.(get\([\'"]' + re.escape(field) + r'[\'"]|\[[\'"]' + re.escape(field) + r'[\'"]\])'
            p_write = r'state\[[\'"]' + re.escape(field) + r'[\'"]\]\s*='
            p_dict_key = r'[\'"]' + re.escape(field) + r'[\'"]\s*:'

            matches_read = len(re.findall(p_read, content))
            matches_write = len(re.findall(p_write, content))
            matches_key = len(re.findall(p_dict_key, content))

            if matches_read or matches_write or matches_key:
                file_references[field].add(rel)
                read_counts[field] += matches_read + matches_key
                write_counts[field] += matches_write

    print("=== ANALYST STATE FIELD USAGE ===")
    print(f"{'Field Name':30s} | {'Total Refs':10s} | {'Write Refs':10s} | {'Files Count':12s} | Status")
    print("-" * 75)
    
    unused_fields = []
    low_usage_fields = []
    
    for f in STATE_FIELDS:
        tot = read_counts[f] + write_counts[f]
        n_files = len(file_references[f])
        if tot == 0:
            status = "UNUSED"
            unused_fields.append(f)
        elif tot <= 2:
            status = "LOW USAGE"
            low_usage_fields.append(f)
        else:
            status = "ACTIVE"
        print(f"{f:30s} | {tot:10d} | {write_counts[f]:10d} | {n_files:12d} | {status}")

    print(f"\nUnused Fields ({len(unused_fields)}): {unused_fields}")
    print(f"Low Usage / Duplicate Fields ({len(low_usage_fields)}): {low_usage_fields}")

if __name__ == '__main__':
    analyze_fields()
